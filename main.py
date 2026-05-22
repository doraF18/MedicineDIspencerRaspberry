"""
Raspberry Pi Medication Dispenser Application

Manages:
- Device registration and pairing with backend
- Hardware control (LED, buzzer, stepper motor, LCD)
- Medication intake tracking via physical button
- Backend API integration with retry logic
"""

import os
import requests
import json
import logging
import threading
import signal
import sys
import time
from gpiozero import Button
from gpiozero import LED, Buzzer
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
FIREBASE_PATH = os.getenv("FIREBASE_PATH")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8080")

# Hardware initialization
motor = None
button = None
lcd = None
led = None
buzzer = None

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

    # Note: Stepper motor uses GPIO 17, 18, 27, 22 which conflicts with button (22)
    # and LED (17) and buzzer (27). Disabling motor to allow button/LED/buzzer.
    # To use the motor, reassign button/LED/buzzer to different pins or use motor via different pins.
    try:
        # Disabled: motor = StepperMotor(*STEPPER_PINS)
        motor = None
        logger.info("Stepper motor disabled to allow button/LED/buzzer pins")
    except Exception as e:
        motor = None
        logger.error(f"Stepper motor unavailable: {e}")

    try:
        button = Button(BUTTON_PIN, hold_time=3, bounce_time=0.15)
        logger.info(f"✓ Button initialized on GPIO{BUTTON_PIN}")
    except Exception as e:
        button = None
        logger.error(f"Button unavailable: {e}")

    try:
        led = LED(LED_PIN)
        led.off()
        logger.info(f"✓ LED initialized on GPIO{LED_PIN}")
    except Exception as e:
        led = None
        logger.error(f"LED unavailable: {e}")

    try:
        buzzer = Buzzer(BUZZER_PIN)
        buzzer.off()
        logger.info(f"✓ Buzzer initialized on GPIO{BUZZER_PIN}")
    except Exception as e:
        buzzer = None
        logger.error(f"Buzzer unavailable: {e}")

    try:
        lcd = CharLCD('PCF8574', address=0x27, port=1, cols=16, rows=2)
        logger.info("✓ LCD initialized")
    except Exception as e:
        lcd = None
        logger.error(f"LCD unavailable: {e}")


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
        # Post intake event to backend
        if device_manager.post_intake_event(source="BUTTON"):
            logger.info("✓ INTAKE EVENT RECORDED to backend")

            if led is not None:
                led.off()
            if buzzer is not None:
                buzzer.off()

            printToLCD("Dose Taken", timeout=3)

            # Trigger motor rotation (disabled for now due to pin conflict)
            if motor is not None:
                try:
                    motor.half_turn(direction=1)
                    logger.info("✓ Motor rotated")
                except Exception as e:
                    logger.error(f"Error rotating motor: {e}")
            else:
                logger.debug("Motor not available (disabled for button GPIO)")

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
    global device_manager

    while True:
        try:
            time.sleep(300)  # Check every 5 minutes

            if device_manager and device_manager.is_paired:
                logger.debug("Fetching medication schedule...")
                schedule = device_manager.get_schedule()
                if schedule:
                    logger.info(f"Schedule updated: {schedule}")

        except Exception as e:
            logger.error(f"Error fetching schedule: {e}")


def check_and_cleanup_existing_instance():
    """Check for and optionally kill existing main.py instance before GPIO init"""
    pid_file = ".app.pid"
    
    # First, kill any stale Python processes that may be holding /dev/gpiochip0
    # (from previous crashes or unclean exits)
    try:
        import subprocess
        result = subprocess.run(
            "lsof 2>/dev/null | grep gpiochip0 | awk '{print $2}' | sort -u",
            shell=True,
            capture_output=True,
            text=True,
            timeout=2
        )
        stale_pids = result.stdout.strip().split('\n')
        for pid_str in stale_pids:
            if pid_str and pid_str.isdigit():
                pid = int(pid_str)
                # Don't kill ourselves
                if pid != os.getpid():
                    try:
                        os.kill(pid, signal.SIGKILL)
                        logger.info(f"Killed stale gpiochip0 holder PID {pid}")
                        time.sleep(0.5)
                    except ProcessLookupError:
                        pass
                    except Exception:
                        pass
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
    if button is not None:
        button.when_released = on_button_pressed
        button.when_held = on_button_held
    else:
        logger.warning("Button unavailable, input handling disabled")

    # Initialize device on startup
    if not initialize_device():
        logger.warning("Device initialization incomplete, but continuing...")
        printToLCD("Initializing...", timeout=3)

    # Start background monitoring threads
    monitor_thread = threading.Thread(target=monitor_pairing_status, daemon=True)
    schedule_thread = threading.Thread(target=fetch_schedule_periodically, daemon=True)

    monitor_thread.start()
    schedule_thread.start()

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


# Legacy functions for backward compatibility
def get_credentials():
    """Get user credentials (legacy)"""
    return {
        "email": "test@gmail.com",
        "password": "asdasd"
    }


def init_device_legacy():
    """Legacy Firebase authentication (deprecated)"""
    url = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=AIzaSyAZdzV7TQMmA4nTFr59HspOIWq9XDeYzk0"

    credentials = get_credentials()
    email = credentials["email"]
    password = credentials["password"]

    body = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }

    response = requests.post(url, json=body)

    if response.status_code != 200:
        logger.error(f"Error signing in: {response.text}")
        raise Exception("Error signing in: " + response.text)

    if FIREBASE_PATH:
        with open(FIREBASE_PATH, "w") as f:
            json.dump(response.json(), f, indent=4)

    logger.info("Legacy init_device completed")


def refresh_id_token(refresh_token):
    """Refresh Firebase ID token (legacy)"""
    url = "https://identitytoolkit.googleapis.com/v1/token?key=AIzaSyAZdzV7TQMmA4nTFr59HspOIWq9XDeYzk0"

    body = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }

    response = requests.post(url, json=body)

    if response.status_code != 200:
        raise Exception("Error refreshing ID token: " + response.text)
    else:
        return response.json()["id_token"]


def add_to_history():
    """Add to history (legacy Firebase)"""
    try:
        with open(FIREBASE_PATH, "r") as f:
            tokens = json.loads(f.read())
            refresh_token = tokens["refreshToken"]
            id_token = refresh_id_token(refresh_token)

        url = "https://iiotca.onrender.com/api/user/history"

        header = {
            "Authorization": "Bearer " + id_token,
        }

        res = requests.put(url, headers=header)

        if res.status_code != 200:
            raise Exception("Error adding to history")
        else:
            logger.info("Added to history (legacy)")
    except Exception as e:
        logger.error(f"Legacy add_to_history failed: {e}")


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
