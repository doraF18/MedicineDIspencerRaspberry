"""
Raspberry Pi Medication Dispenser Application

Manages:
- Device registration and pairing with backend
- Hardware control (LED, buzzer, stepper motor, LCD)
- Medication intake tracking via physical button
- Backend API integration with retry logic
"""

import os
import json
import logging
import threading
import signal
import sys
import time
from datetime import datetime
from gpiozero import Button
from gpiozero import LED, PWMOutputDevice, OutputDevice
from signal import pause
from RPLCD.i2c import CharLCD
from time import sleep
from dotenv import load_dotenv
from hardware_common import STEPPER_PINS, LED_PIN, BUTTON_PIN, BUZZER_PIN
from models import StepperMotor
from api import DeviceConfigurator, DeviceManager, PairingManager

# Configure environment
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Constants
DEVICE_CONFIG_PATH = os.getenv("DEVICE_CONFIG_PATH", "device_config.json")
BACKEND_URL = os.getenv("BACKEND_URL", "http://10.195.30.69:8080")

# Hardware initialization
motor = None
button = None
lcd = None
led = None
buzzer = None

# Schedule/reminder state
schedule_lock = threading.Lock()
cached_schedule = None
triggered_reminders = set()

# Active reminder cancellation map: reminder_key -> threading.Event
active_reminders_lock = threading.Lock()
active_reminders = {}

# Global state
long_press = False
last_button_press_time = 0.0
device_manager = None
pairing_manager = None
is_initialized = False


def printToLCD(message, timeout=None):
    """Display message on LCD display (16x2)"""
    try:
        if lcd is None:
            logger.debug(f"LCD unavailable: {message}")
            return

        lcd.clear()
        
        # Split message by newlines
        lines = message.split('\n')
        
        # Pad and write each line
        for row, line_text in enumerate(lines[:2]):  # Max 2 rows
            # Pad to 16 chars, then truncate if longer
            line_text = (line_text + ' ' * 16)[:16]
            lcd.cursor_pos = (row, 0)
            lcd.write_string(line_text)
        
        if timeout:
            sleep(timeout)
            lcd.clear()
    except Exception as e:
        logger.error(f"Error displaying on LCD: {e}")


def _normalize_schedule_entries(schedule_data):
    """Return a flat list of schedule entries from the backend payload."""
    if schedule_data is None:
        return []

    if isinstance(schedule_data, list):
        return schedule_data

    if isinstance(schedule_data, dict):
        for key in ("schedules", "schedule", "data", "items"):
            entries = schedule_data.get(key)
            if isinstance(entries, list):
                return entries

        return [schedule_data]

    return []


def _parse_schedule_time(value):
    if not value:
        return None

    text = str(value).strip()
    for format_string in ("%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(text, format_string).time()
        except ValueError:
            continue

    return None


def _normalize_hhmm(value):
    """Normalize backend time values like HH:MM:SS or HH:MM into HH:MM."""
    if not value:
        return None

    text = str(value).strip()
    parts = text.split(":")
    if len(parts) < 2:
        return None

    hour = parts[0].zfill(2)
    minute = parts[1].zfill(2)
    if not (hour.isdigit() and minute.isdigit()):
        return None

    return f"{hour}:{minute}"


def _extract_dose_times(schedule_snapshot):
    """Extract dose times by moment from multiple backend payload shapes."""
    dose_by_moment = {}

    if not schedule_snapshot:
        return dose_by_moment

    if isinstance(schedule_snapshot, dict):
        dose_times = {}
        if isinstance(schedule_snapshot.get("doseTimes"), dict):
            dose_times = schedule_snapshot.get("doseTimes") or {}
        elif isinstance(schedule_snapshot.get("schedule"), dict) and isinstance(schedule_snapshot.get("schedule", {}).get("doseTimes"), dict):
            dose_times = schedule_snapshot.get("schedule", {}).get("doseTimes") or {}
        elif isinstance(schedule_snapshot.get("data"), dict) and isinstance(schedule_snapshot.get("data", {}).get("doseTimes"), dict):
            dose_times = schedule_snapshot.get("data", {}).get("doseTimes") or {}

        morning = _normalize_hhmm(dose_times.get("morningTime"))
        noon = _normalize_hhmm(dose_times.get("noonTime"))
        evening = _normalize_hhmm(dose_times.get("eveningTime"))

        if morning:
            dose_by_moment["MORNING"] = morning
        if noon:
            dose_by_moment["NOON"] = noon
        if evening:
            dose_by_moment["EVENING"] = evening

    for entry in _normalize_schedule_entries(schedule_snapshot):
        if not isinstance(entry, dict):
            continue

        moment = _infer_moment(entry)
        if not moment:
            continue

        raw_time = entry.get("time") or entry.get("doseTime") or entry.get("scheduledTime")
        normalized = _normalize_hhmm(raw_time)
        if normalized:
            dose_by_moment[moment] = normalized

    return dose_by_moment


def _extract_patient_id_from_payload(payload):
    """Extract patient ID from common payload shapes."""
    if not isinstance(payload, dict):
        return None

    direct = payload.get("patientId") or payload.get("patient_id")
    if direct is not None and str(direct).strip():
        return str(direct).strip()

    patient_obj = payload.get("patient")
    if isinstance(patient_obj, dict):
        nested = patient_obj.get("id") or patient_obj.get("patientId") or patient_obj.get("patient_id")
        if nested is not None and str(nested).strip():
            return str(nested).strip()

    for key in ("data", "schedule"):
        nested_payload = payload.get(key)
        if isinstance(nested_payload, dict):
            nested_patient_id = _extract_patient_id_from_payload(nested_payload)
            if nested_patient_id:
                return nested_patient_id

    return None


def _resolve_patient_id_for_reminders():
    """Resolve patient ID from paired schedule first, then config/env fallback."""
    with schedule_lock:
        schedule_snapshot = cached_schedule

    patient_id = _extract_patient_id_from_payload(schedule_snapshot)
    if patient_id:
        return patient_id

    if device_manager is not None:
        patient_id = _extract_patient_id_from_payload(getattr(device_manager, "schedule", None))
        if patient_id:
            return patient_id

        # Fallback: ask backend pairing-status for the paired patient context.
        try:
            if device_manager.is_paired and device_manager.device_id:
                pairing_status = device_manager._make_request(
                    "GET", f"/api/devices/{device_manager.device_id}/pairing-status"
                )
                patient_id = _extract_patient_id_from_payload(pairing_status)
                if patient_id:
                    # Cache for next startup/use.
                    try:
                        with open(DEVICE_CONFIG_PATH, "r", encoding="utf-8") as handle:
                            cfg = json.load(handle)
                    except Exception:
                        cfg = {}

                    if not isinstance(cfg, dict):
                        cfg = {}
                    cfg["patientId"] = patient_id

                    with open(DEVICE_CONFIG_PATH, "w", encoding="utf-8") as handle:
                        json.dump(cfg, handle, indent=2)

                    return patient_id
        except Exception:
            pass

    try:
        with open(DEVICE_CONFIG_PATH, "r", encoding="utf-8") as handle:
            cfg = json.load(handle)
        patient_id = cfg.get("patientId") or cfg.get("patient_id")
        if patient_id is not None and str(patient_id).strip():
            return str(patient_id).strip()
    except Exception:
        pass

    patient_id = os.getenv("PATIENT_ID")
    if patient_id is not None and str(patient_id).strip():
        return str(patient_id).strip()

    return None


def _infer_moment(entry):
    if not isinstance(entry, dict):
        return None

    for key in ("moment", "doseMoment", "timeSlot", "period"):
        raw_moment = entry.get(key)
        if raw_moment:
            moment = str(raw_moment).strip().upper()
            if moment in {"MORNING", "NOON", "EVENING"}:
                return moment

    schedule_time = _parse_schedule_time(
        entry.get("time")
        or entry.get("doseTime")
        or entry.get("scheduledTime")
    )

    if schedule_time is None:
        return None

    if 5 <= schedule_time.hour < 12:
        return "MORNING"
    if 12 <= schedule_time.hour < 17:
        return "NOON"
    return "EVENING"


def _time_matches_now(now, schedule_time):
    if schedule_time is None:
        return False

    return now.strftime("%H:%M") == schedule_time.strftime("%H:%M")


def _flash_led_for_reminder(duration_seconds=3):
    if led is None:
        logger.debug("LED unavailable for reminder")
        return

    logger.info("LED flashing for 3 seconds")
    end_time = time.monotonic() + duration_seconds

    try:
        while time.monotonic() < end_time:
            led.on()
            sleep(0.3)
            led.off()
            sleep(0.3)
    finally:
        led.off()


def _buzzer_tone_on(frequency_hz=2000, duty_cycle=0.5):
    """Drive buzzer with PWM tone."""
    if buzzer is None:
        return

    try:
        if hasattr(buzzer, "frequency"):
            buzzer.frequency = frequency_hz

        if hasattr(buzzer, "value"):
            buzzer.value = duty_cycle
        else:
            buzzer.on()
    except Exception:
        try:
            buzzer.on()
        except Exception:
            pass


def _beep_buzzer_for_reminder(duration_seconds=1.2):
    if buzzer is None:
        logger.debug("Buzzer unavailable for reminder")
        return

    logger.info("Buzzer beep")
    try:
        for _ in range(2):
            _buzzer_tone_on(2000, 0.5)
            sleep(duration_seconds)
            buzzer.off()
            sleep(0.2)
    finally:
        buzzer.off()


def _led_blink(duration_seconds=3, fast=False):
    if led is None:
        logger.debug("LED unavailable for reminder")
        return

    logger.info(f"LED blinking for {duration_seconds}s{' fast' if fast else ''}")
    end_time = time.monotonic() + duration_seconds
    try:
        while time.monotonic() < end_time:
            led.on()
            sleep(0.15 if fast else 0.3)
            led.off()
            sleep(0.1 if fast else 0.3)
    finally:
        try:
            led.off()
        except Exception:
            pass


def _buzzer_pattern(pattern: str):
    if buzzer is None:
        logger.debug("Buzzer unavailable for reminder")
        return

    pattern = (pattern or "NORMAL").upper()
    try:
        if pattern == "NORMAL":
            _buzzer_tone_on(2000, 0.5); sleep(0.5); buzzer.off()
        elif pattern == "MEDIUM":
            for _ in range(3):
                _buzzer_tone_on(2000, 0.5); sleep(0.4); buzzer.off(); sleep(0.3)
        elif pattern == "AGGRESSIVE":
            for _ in range(5):
                _buzzer_tone_on(2000, 0.5); sleep(0.35); buzzer.off(); sleep(0.2)
        else:
            # Unknown pattern -> single short beep
            _buzzer_tone_on(2000, 0.5); sleep(0.5); buzzer.off()
    except Exception as e:
        logger.debug(f"Buzzer pattern failed: {e}")


def get_current_moment():
    now = datetime.now()
    if 5 <= now.hour < 12:
        return "MORNING"
    if 12 <= now.hour < 17:
        return "NOON"
    return "EVENING"


def stop_reminder_for_key(reminder_key: str):
    with active_reminders_lock:
        ev = active_reminders.get(reminder_key)
        if ev is not None:
            ev.set()
            logger.info("Reminder stopped because dose was taken")
            try:
                del active_reminders[reminder_key]
            except KeyError:
                pass


def start_reminder_sequence(moment: str, reminder_key: str):
    """Fetch strategy and run the reminder sequence with repeats and cancellation."""
    # Default low strategy
    strategy = {"risk": "LOW", "repeatEveryMinutes": 0, "maxRepeats": 0, "buzzerPattern": "NORMAL"}

    # Fetch remote strategy if possible
    try:
        fetched = None
        patient_id = _resolve_patient_id_for_reminders()

        if device_manager is not None and device_manager.is_paired and patient_id:
            fetched = device_manager._make_request("GET", f"/api/patients/{patient_id}/reminder-strategy")
        elif device_manager is not None and device_manager.is_paired:
            logger.warning("Patient ID not found in paired schedule; using default LOW reminder strategy")

        if fetched:
            logger.info("Risk strategy fetched")
            strategies = fetched.get("strategies") or {}
            # Support exact and case-variant keys from backend payload
            s = strategies.get(moment) or strategies.get(str(moment).upper()) or strategies.get(str(moment).lower())
            if isinstance(s, dict):
                strategy.update(s)
            ai_explanation = fetched.get("aiExplanation")
            if ai_explanation:
                logger.info(f"Strategy note: {ai_explanation}")
    except Exception as e:
        logger.debug(f"Failed to fetch reminder strategy: {e}")

    risk = str(strategy.get("risk") or "LOW").upper()
    repeat_minutes = int(strategy.get("repeatEveryMinutes") or 0)
    max_repeats = int(strategy.get("maxRepeats") or 0)
    buzzer_pattern = str(strategy.get("buzzerPattern") or "NORMAL").upper()

    logger.info(f"Using {risk} behavior for {moment}")

    # Register cancellation event
    cancel_event = threading.Event()
    with active_reminders_lock:
        active_reminders[reminder_key] = cancel_event

    # Perform single alert
    printToLCD(f"Time for pills / Risk: {risk}", timeout=3)

    # Start LED and buzzer for initial alert
    if risk == "LOW":
        led_thread = threading.Thread(target=_led_blink, args=(3, False), daemon=True)
        buzzer_thread = threading.Thread(target=_buzzer_pattern, args=(buzzer_pattern,), daemon=True)
        led_thread.start(); buzzer_thread.start()
        # no repeats
    elif risk == "MEDIUM":
        led_thread = threading.Thread(target=_led_blink, args=(5, False), daemon=True)
        buzzer_thread = threading.Thread(target=_buzzer_pattern, args=(buzzer_pattern,), daemon=True)
        led_thread.start(); buzzer_thread.start()
    else:  # HIGH
        led_thread = threading.Thread(target=_led_blink, args=(10, True), daemon=True)
        buzzer_thread = threading.Thread(target=_buzzer_pattern, args=(buzzer_pattern,), daemon=True)
        led_thread.start(); buzzer_thread.start()

    # Handle repeats for MEDIUM/HIGH
    if risk in ("MEDIUM", "HIGH") and repeat_minutes > 0 and max_repeats > 0:
        for i in range(1, max_repeats + 1):
            # Wait for repeat interval or cancellation
            waited = cancel_event.wait(timeout=repeat_minutes * 60)
            if cancel_event.is_set():
                break

            logger.info(f"Repeating reminder {i}/{max_repeats}")
            # Play the alert again
            printToLCD(f"Time for pills / Risk: {risk}", timeout=3)
            try:
                if risk == "MEDIUM":
                    _led_blink(5, False)
                    _buzzer_pattern(buzzer_pattern)
                else:
                    _led_blink(10, True)
                    _buzzer_pattern(buzzer_pattern)
            except Exception:
                pass

    # Clean up after finishing
    with active_reminders_lock:
        if reminder_key in active_reminders:
            try:
                del active_reminders[reminder_key]
            except KeyError:
                pass


def trigger_reminder(moment, reminder_key):
    logger.info(f"Reminder triggered for {moment}")

    # Start a background reminder sequence which handles intensity, repeats and cancellation
    t = threading.Thread(target=start_reminder_sequence, args=(moment, reminder_key), daemon=True)
    t.start()


def trigger_scheduled_alarm(moment):
    logger.info(f"Triggering alarm for {moment}")
    # Run LED and buzzer in parallel threads so all three fire simultaneously
    led_thread = threading.Thread(target=_led_blink, args=(10, False), daemon=True)
    buzzer_thread = threading.Thread(target=_beep_buzzer_for_reminder, args=(3.0,), daemon=True)
    led_thread.start()
    buzzer_thread.start()
    printToLCD(f"Time for pills\n{moment}", timeout=10)
    led_thread.join(timeout=15)
    buzzer_thread.join(timeout=15)
    logger.info(f"Alarm completed for {moment}")


def check_scheduled_reminders():
    global triggered_reminders

    while True:
        try:
            logger.info("Schedule loop running")

            if device_manager is None or not device_manager.is_paired:
                time.sleep(10)
                continue

            now = datetime.now()
            today = now.strftime("%Y-%m-%d")
            logger.info(f"Current time HH:mm = {now.strftime('%H:%M')}")

            with schedule_lock:
                schedule_snapshot = cached_schedule

            if not schedule_snapshot:
                time.sleep(10)
                continue

            dose_by_moment = _extract_dose_times(schedule_snapshot)
            if not dose_by_moment:
                logger.warning("No dose times found in schedule payload")
                time.sleep(10)
                continue

            for moment in ("MORNING", "NOON", "EVENING"):
                scheduled_time = dose_by_moment.get(moment)
                logger.info(f"Checking {moment} {scheduled_time or 'N/A'}")
                if not scheduled_time:
                    continue

                reminder_key = f"{today}_{moment}"
                if reminder_key in triggered_reminders:
                    continue

                schedule_time_obj = _parse_schedule_time(scheduled_time)
                if schedule_time_obj is None:
                    continue

                scheduled_dt = now.replace(
                    hour=schedule_time_obj.hour,
                    minute=schedule_time_obj.minute,
                    second=0,
                    microsecond=0,
                )
                seconds_since_scheduled = (now - scheduled_dt).total_seconds()

                # Trigger once when loop runs during the scheduled minute.
                if 0 <= seconds_since_scheduled < 60:
                    logger.info(f"MATCH FOUND for {moment}")
                    triggered_reminders.add(reminder_key)
                    # Route scheduled reminders through adaptive strategy flow.
                    trigger_reminder(moment, reminder_key)

            time.sleep(10)

        except Exception as e:
            logger.error(f"Error checking scheduled reminders: {e}")
            time.sleep(10)


def initialize_device():
    """
    Initialize device on startup
    - Load or create device ID
    - Register with backend
    - Attempt pairing if not already paired
    """
    global device_manager, pairing_manager, is_initialized

    logger.info("=" * 60)
    logger.info("Starting Medication Dispenser Application")
    logger.info("=" * 60)

    try:
        # Initialize DeviceManager
        device_manager = DeviceManager(
            config_path=DEVICE_CONFIG_PATH,
            backend_url=BACKEND_URL
        )
        logger.info(f"Device ID: {device_manager.device_id}")

        # Initialize PairingManager with LCD callback
        pairing_manager = PairingManager(device_manager, lcd_callback=printToLCD)

        # Display startup message
        printToLCD("Starting up...", timeout=2)

        # Check if device needs pairing
        # Try to load pairing status from config
        try:
            with open(DEVICE_CONFIG_PATH, "r") as f:
                config = json.load(f)
                if config.get("isPaired"):
                    device_manager.is_paired = True
                    logger.info("Device previously paired")
                    printToLCD("Device Ready", timeout=2)
                    is_initialized = True
                    return True
        except:
            pass

        # Device not paired yet
        logger.info("Device not paired. Starting pairing workflow...")
        
        if pairing_manager.start_pairing():
            # Save pairing status
            with open(DEVICE_CONFIG_PATH, "r") as f:
                config = json.load(f)
            config["isPaired"] = True
            with open(DEVICE_CONFIG_PATH, "w") as f:
                json.dump(config, f, indent=4)
            
            logger.info("Device pairing completed")
            is_initialized = True
            return True
        else:
            logger.error("Device pairing failed")
            printToLCD("Pairing Failed\nRetry: Hold button", timeout=5)
            return False

    except Exception as e:
        logger.error(f"Error during device initialization: {e}")
        printToLCD("Init Error\nCheck logs", timeout=5)
        return False


def initialize_hardware():
    """Initialize optional hardware components."""
    global motor, button, lcd, led, buzzer

    try:
        motor = StepperMotor(*STEPPER_PINS)
        logger.info(
            "✓ Stepper motor initialized on GPIO%s, GPIO%s, GPIO%s, GPIO%s",
            *STEPPER_PINS,
        )
    except Exception as e:
        motor = None
        logger.error(f"Stepper motor unavailable: {e}")

    _initialize_button()

    try:
        led = LED(LED_PIN)
        led.off()
        logger.info(f"✓ LED initialized on GPIO{LED_PIN}")
    except Exception as e:
        led = None
        logger.error(f"LED unavailable: {e}")

    try:
        buzzer = PWMOutputDevice(BUZZER_PIN, frequency=2000, initial_value=0)
        buzzer.off()
        logger.info(f"✓ Buzzer initialized on GPIO{BUZZER_PIN} (PWM 2kHz)")
    except Exception as e:
        try:
            buzzer = OutputDevice(BUZZER_PIN, active_high=True, initial_value=False)
            buzzer.off()
            logger.warning(f"Buzzer PWM unavailable ({e}), using digital fallback on GPIO{BUZZER_PIN}")
        except Exception as fallback_error:
            buzzer = None
            logger.error(f"Buzzer unavailable: {fallback_error}")

    try:
        lcd = CharLCD('PCF8574', address=0x27, port=1, cols=16, rows=2)
        logger.info("✓ LCD initialized")
    except Exception as e:
        lcd = None
        logger.error(f"LCD unavailable: {e}")


def _initialize_button():
    """Attempt to initialize the physical button."""
    global button

    try:
        button = Button(BUTTON_PIN, hold_time=3, bounce_time=0.15)
        logger.info(f"✓ Button initialized on GPIO{BUTTON_PIN}")
        setup_button_handlers()
        return True
    except Exception as e:
        button = None
        logger.error(f"Button unavailable: {e}")
        return False


def retry_button_initialization():
    """Keep retrying button setup until the GPIO becomes available."""
    global button

    while button is None:
        time.sleep(10)
        if _initialize_button():
            return


def setup_button_handlers():
    """Attach button callbacks when the button is available."""
    if button is None:
        return

    button.when_released = on_button_pressed
    button.when_held = on_button_held


def get_active_moments_from_schedule():
    """
    Extract active medication moments from the cached schedule.
    
    Returns:
        List of moments: ["MORNING", "NOON", "EVENING"] etc.
    """
    with schedule_lock:
        schedule_snapshot = cached_schedule

    return list(_extract_dose_times(schedule_snapshot).keys())


def align_motor_to_active_moment(target_moment):
    """
    Rotate motor from current position to target active moment, skipping empty slots.
    
    Args:
        target_moment: One of MORNING, NOON, EVENING
    
    Returns:
        List of moments that were skipped (for logging)
    
    Raises:
        RuntimeError: If motor is not available or rotation fails
    """
    if motor is None:
        raise RuntimeError("Motor not available")

    current_position = motor.current_wheel_position
    logger.info(f"Motor align: current_position={current_position}, target_moment={target_moment}")

    if target_moment not in ["MORNING", "NOON", "EVENING"]:
        raise ValueError(f"Invalid target_moment: {target_moment}")

    # Calculate slots to advance
    slots_to_advance = motor.calculate_slots_to_advance(current_position, target_moment)
    logger.info(f"Need to advance {slots_to_advance} slots to reach {target_moment}")

    # Log skipped moments
    skipped_moments = []
    if slots_to_advance > 0:
        current_idx = ["MORNING", "NOON", "EVENING"].index(current_position)
        for i in range(1, slots_to_advance):
            skipped_idx = (current_idx + i) % 3
            skipped_moment = ["MORNING", "NOON", "EVENING"][skipped_idx]
            skipped_moments.append(skipped_moment)
            logger.info(f"Skipping empty slot: {skipped_moment}")

    # Rotate motor only if slots_to_advance > 0
    if slots_to_advance > 0:
        steps_to_rotate = slots_to_advance * motor.steps_per_slot
        logger.info(f"Rotating motor: {slots_to_advance} slots × {motor.steps_per_slot} steps/slot = {steps_to_rotate} total steps")

        try:
            motor.step(steps_to_rotate, direction=1)
            logger.info(f"Motor rotation complete - now at {target_moment}")
        except Exception as exc:
            raise RuntimeError(f"Motor rotation failed: {exc}") from exc

    # Update and persist current position
    motor.current_wheel_position = target_moment
    motor._save_current_wheel_position(target_moment)
    logger.info(f"Dispensing active slot: {target_moment}")

    return skipped_moments


def on_button_held():
    """Handle long button press - trigger pairing/registration"""
    global long_press, device_manager, pairing_manager

    long_press = True
    logger.info("Button held - triggering pairing workflow...")

    try:
        printToLCD("Pairing mode...")

        # Re-initialize managers if needed
        if device_manager is None:
            device_manager = DeviceManager(
                config_path=DEVICE_CONFIG_PATH,
                backend_url=BACKEND_URL
            )
            pairing_manager = PairingManager(device_manager, lcd_callback=printToLCD)

        if pairing_manager.start_pairing():
            # Save pairing status
            with open(DEVICE_CONFIG_PATH, "r") as f:
                config = json.load(f)
            config["isPaired"] = True
            with open(DEVICE_CONFIG_PATH, "w") as f:
                json.dump(config, f, indent=4)
            
            logger.info("Device successfully paired")
        else:
            logger.error("Pairing failed")
            printToLCD("Pairing failed\nTry again", timeout=3)

    except Exception as e:
        logger.error(f"Error during pairing: {e}")
        printToLCD("Error occurred\nCheck logs", timeout=5)


def on_button_pressed():
    """Handle button press - record medication intake"""
    global long_press, last_button_press_time, device_manager, is_initialized, led, buzzer

    logger.info("━━━ BUTTON PRESSED ━━━")

    now = time.monotonic()
    if now - last_button_press_time < 2:
        logger.info(f"Debounce: ignoring press within 2s (last press {now - last_button_press_time:.1f}s ago)")
        return
    last_button_press_time = now

    if long_press:
        logger.info("Long press flag set, resetting")
        long_press = False
        return

    if device_manager is None or not is_initialized:
        logger.warning("Device not initialized")
        printToLCD("Device not ready", timeout=2)
        return

    if not device_manager.is_paired:
        logger.warning("Device not paired")
        printToLCD("Not paired\nHold to pair", timeout=2)
        return

    logger.info("✓ Button press accepted - recording medication intake...")

    try:
        # Get current medication moment
        moment_now = get_current_moment()
        logger.info(f"Current moment: {moment_now}")

        # Get active moments from schedule
        active_moments = get_active_moments_from_schedule()
        logger.info(f"Active moments from schedule: {active_moments}")

        # Check if current moment is active (has medication scheduled)
        is_current_moment_active = moment_now in active_moments

        if not is_current_moment_active and active_moments:
            logger.warning(f"{moment_now} is not in active moments {active_moments}")
            printToLCD(f"No meds at {moment_now}", timeout=2)
            return

        # Align motor to current active moment (skipping any empty slots)
        motor_aligned = False
        if motor is not None and active_moments:
            try:
                skipped = align_motor_to_active_moment(moment_now)
                motor_aligned = True
                if skipped:
                    logger.info(f"Motor skipped empty slots: {skipped}")
            except Exception as e:
                logger.error(f"Motor alignment failed: {e}")
                printToLCD("Motor error", timeout=2)
                return
        elif motor is not None:
            logger.debug("No active moments in schedule - motor not aligned")
        else:
            logger.debug("Motor not available")

        # Post intake event to backend ONLY if current moment is active
        result = device_manager.post_intake_event(source="BUTTON")
        if result.get("success"):
            if result["duplicate"]:
                printToLCD("Pills already \ntaken", timeout=3)
                logger.info("Pills already taken")
                # Stop active reminders for this moment
                today = datetime.now().strftime("%Y-%m-%d")
                stop_reminder_for_key(f"{today}_{moment_now}")
            else:
                # New intake - only triggered for active medication moments
                logger.info("✓ INTAKE EVENT RECORDED to backend")

                # Trigger buzzer and LED feedback ONLY for active moments
                if led is not None:
                    led.off()
                if buzzer is not None:
                    buzzer.off()

                printToLCD("Dose Taken", timeout=3)

                # Stop active reminders for this moment
                today = datetime.now().strftime("%Y-%m-%d")
                stop_reminder_for_key(f"{today}_{moment_now}")

        else:
            logger.error("✗ Failed to record intake event")
            printToLCD("Sync Failed", timeout=3)

    except Exception as e:
        logger.error(f"✗ Error processing button press: {e}")
        printToLCD("Sync Failed", timeout=3)


def monitor_pairing_status():
    """Background thread to monitor and update pairing status"""
    global device_manager

    while True:
        try:
            time.sleep(60)  # Check every 60 seconds

            if device_manager and not device_manager.is_paired:
                logger.debug("Checking pairing status...")
                device_manager.get_pairing_status()

        except Exception as e:
            logger.error(f"Error monitoring pairing status: {e}")


def fetch_schedule_periodically():
    """Background thread to periodically fetch medication schedule"""
    global device_manager, cached_schedule

    while True:
        try:
            if device_manager and device_manager.is_paired:
                logger.debug("Fetching medication schedule...")
                schedule = device_manager.get_schedule()
                if schedule:
                    with schedule_lock:
                        cached_schedule = schedule
                    logger.info("Schedule fetched")
                    logger.info(f"Schedule updated: {schedule}")

            time.sleep(120)  # Check every 2 minutes

        except Exception as e:
            logger.error(f"Error fetching schedule: {e}")


def check_and_cleanup_existing_instance():
    """Check for and optionally kill existing main.py instance before GPIO init"""
    pid_file = ".app.pid"
    
    # First, kill any stale Python processes that may be holding GPIO resources
    # (from previous crashes, stopped test scripts, or unclean exits)
    try:
        import glob

        stale_patterns = (
            "main.py",
            "test_button.py",
            "test_components.py",
            "test_led.py",
            "test_buzzer.py",
            "test_stepper.py",
        )

        for cmdline_path in glob.glob("/proc/[0-9]*/cmdline"):
            try:
                pid = int(cmdline_path.split("/")[2])
                if pid == os.getpid():
                    continue

                with open(cmdline_path, "r") as f:
                    cmdline = f.read().replace("\x00", " ")

                if not any(pattern in cmdline for pattern in stale_patterns):
                    continue

                try:
                    os.kill(pid, signal.SIGTERM)
                    time.sleep(0.5)
                    if os.path.exists(f"/proc/{pid}"):
                        os.kill(pid, signal.SIGKILL)
                    logger.info(f"Killed stale dispenser process PID {pid}")
                except ProcessLookupError:
                    pass
                except Exception:
                    pass
            except Exception:
                continue
    except Exception as e:
        logger.debug(f"Could not scan for stale GPIO processes: {e}")
    
    # Now check PID file for previous instance
    if os.path.exists(pid_file):
        try:
            with open(pid_file, "r") as f:
                existing = f.read().strip()
            if existing:
                try:
                    existing_pid = int(existing)
                    # Check if process exists and appears to be main.py
                    if os.path.exists(f"/proc/{existing_pid}"):
                        try:
                            with open(f"/proc/{existing_pid}/cmdline", "r") as cf:
                                cmd = cf.read()
                            if "main.py" in cmd:
                                logger.error("Another instance found before GPIO init")
                                logger.info(f"Killing old instance PID {existing_pid}")
                                try:
                                    os.kill(existing_pid, signal.SIGTERM)
                                    time.sleep(2)
                                    # If still exists, force kill
                                    if os.path.exists(f"/proc/{existing_pid}"):
                                        os.kill(existing_pid, signal.SIGKILL)
                                        logger.info(f"Force-killed old instance PID {existing_pid}")
                                        time.sleep(2)
                                except ProcessLookupError:
                                    logger.info(f"Old instance (PID {existing_pid}) already terminated")
                                except Exception as e:
                                    logger.warning(f"Error killing old instance: {e}")
                        except Exception:
                            # If we can't read cmdline, assume running and try to kill
                            logger.error("Another instance found before GPIO init")
                            logger.info(f"Killing old instance PID {existing_pid}")
                            try:
                                os.kill(existing_pid, signal.SIGTERM)
                                time.sleep(2)
                                if os.path.exists(f"/proc/{existing_pid}"):
                                    os.kill(existing_pid, signal.SIGKILL)
                                    time.sleep(2)
                            except ProcessLookupError:
                                pass
                            except Exception:
                                pass
                except ValueError:
                    pass
        except Exception:
            pass
    
    # Allow kernel time to fully release /dev/gpiochip0
    time.sleep(2)


def main():
    """Main application entry point"""
    global device_manager, is_initialized, button

    # Check for and clean up existing instances BEFORE hardware init
    check_and_cleanup_existing_instance()

    # Initialize hardware after cleanup
    initialize_hardware()

    # Write our PID file after hardware is initialized
    pid_file = ".app.pid"
    try:
        with open(pid_file, "w") as f:
            f.write(str(os.getpid()))
    except Exception:
        logger.warning("Unable to write PID file")

    # Setup button handlers
    if button is None:
        logger.warning("Button unavailable, input handling disabled")
    else:
        setup_button_handlers()

    # Initialize device on startup
    if not initialize_device():
        logger.warning("Device initialization incomplete, but continuing...")
        printToLCD("Initializing...", timeout=3)

    # Start background monitoring threads
    monitor_thread = threading.Thread(target=monitor_pairing_status, daemon=True)
    schedule_thread = threading.Thread(target=fetch_schedule_periodically, daemon=True)
    reminder_thread = threading.Thread(target=check_scheduled_reminders, daemon=True)
    button_retry_thread = None

    monitor_thread.start()
    schedule_thread.start()
    reminder_thread.start()

    if os.getenv("TEST_ALARM_ON_START", "").lower() == "true":
        logger.info("TEST_ALARM_ON_START enabled - triggering startup alarm")
        trigger_scheduled_alarm("MORNING")

    if button is None:
        button_retry_thread = threading.Thread(target=retry_button_initialization, daemon=True)
        button_retry_thread.start()
        logger.warning("Button unavailable at startup, retrying in background")

    logger.info("Application ready - waiting for button press...")

    try:
        pause()
    except KeyboardInterrupt:
        logger.info("Shutting down...")
    finally:
        cleanup()


def cleanup():
    """Cleanup hardware resources"""
    try:
        if motor is not None:
            motor.close()
        if led is not None:
            led.off()
            led.close()
        if buzzer is not None:
            buzzer.off()
            buzzer.close()
        if lcd is not None:
            lcd.clear()
            lcd.close()
        if button is not None:
            button.close()
        logger.info("Cleanup complete")
    except Exception as e:
        logger.error(f"Error during cleanup: {e}")


def cleanup_and_exit(signum=None, frame=None):
    """Signal-safe cleanup and exit"""
    logger.info("Cleaning GPIO resources...")
    try:
        cleanup()
    except Exception as e:
        logger.error(f"GPIO cleanup error: {e}")

    # Remove PID file if present
    try:
        pid_file = ".app.pid"
        if os.path.exists(pid_file):
            os.remove(pid_file)
    except Exception:
        pass

    logger.info("GPIO cleanup completed")
    # If called from a signal handler, exit
    try:
        sys.exit(0)
    except SystemExit:
        os._exit(0)


if __name__ == "__main__":
    # Register signal handlers for graceful cleanup
    try:
        signal.signal(signal.SIGINT, cleanup_and_exit)
        signal.signal(signal.SIGTERM, cleanup_and_exit)
    except Exception:
        pass

    try:
        main()
    finally:
        cleanup_and_exit()
