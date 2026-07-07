from __future__ import annotations

import json
import time
from pathlib import Path

from gpiozero import OutputDevice
from gpiozero.devices import Device

STEPS_PER_REVOLUTION = 4096
DEFAULT_STEPS_PER_DOSE = 300
STEPS_PER_DOSE = DEFAULT_STEPS_PER_DOSE
DEFAULT_STEPS_PER_SLOT = DEFAULT_STEPS_PER_DOSE
CONFIG_FILE_PATH = Path(__file__).resolve().parents[1] / "device_config.json"

# Wheel moment positions in rotation order
WHEEL_MOMENTS = ["MORNING", "NOON", "EVENING"]


class StepperMotor(Device):
    def _build_output_pins(self, pin_numbers) -> list:
        created_pins = []
        try:
            for pin_number in pin_numbers:
                created_pins.append(OutputDevice(pin_number))
            return created_pins
        except Exception:
            for pin in created_pins:
                try:
                    pin.close()
                except Exception:
                    pass
            raise

    def _release_gpio_resources(self) -> None:
        try:
            import RPi.GPIO as GPIO  # type: ignore

            GPIO.setwarnings(False)
            GPIO.cleanup()
        except Exception:
            pass

    def __init__(
        self,
        pin1,
        pin2,
        pin3,
        pin4,
        steps_per_rev=STEPS_PER_REVOLUTION,
        delay=0.001,
        steps_per_dose=None,
        config_path=None,
    ):
        super().__init__()
        self.pins = []
        self.steps_per_rev = steps_per_rev
        self.delay = delay
        self.config_path = Path(config_path) if config_path else CONFIG_FILE_PATH
        self.steps_per_dose = steps_per_dose if steps_per_dose is not None else self._load_steps_per_dose()
        self.current_wheel_position = self._load_current_wheel_position()
        self.steps_per_slot = self._load_steps_per_slot()
        pin_numbers = (pin1, pin2, pin3, pin4)

        try:
            self._release_gpio_resources()
            self.pins = self._build_output_pins(pin_numbers)
        except Exception:
            self._release_gpio_resources()
            try:
                self.pins = self._build_output_pins(pin_numbers)
            except Exception as retry_exc:
                self.close()
                raise RuntimeError(
                    f"Unable to initialize stepper GPIO pins: {retry_exc}. "
                    "Make sure no other process is using the ULN2003 motor pins."
                ) from retry_exc

        # Half-step sequence for 28BYJ-48 + ULN2003
        self.sequence = [
            [1, 0, 0, 1],
            [1, 0, 0, 0],
            [1, 1, 0, 0],
            [0, 1, 0, 0],
            [0, 1, 1, 0],
            [0, 0, 1, 0],
            [0, 0, 1, 1],
            [0, 0, 0, 1],
        ]

    def _load_steps_per_dose(self) -> int:
        try:
            if not self.config_path.exists():
                return DEFAULT_STEPS_PER_DOSE

            with self.config_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)

            if isinstance(data, dict):
                stepper_config = data.get("stepper", {})
                if isinstance(stepper_config, dict):
                    value = stepper_config.get("steps_per_dose")
                    if isinstance(value, int) and value > 0:
                        return value
        except (FileNotFoundError, TypeError, ValueError, OSError) as exc:
            print(f"Could not load steps_per_dose from {self.config_path}: {exc}")

        return DEFAULT_STEPS_PER_DOSE

    def _load_current_wheel_position(self) -> str:
        """Load current wheel position from config file. Defaults to MORNING."""
        try:
            if not self.config_path.exists():
                return "MORNING"

            with self.config_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)

            if isinstance(data, dict):
                stepper_config = data.get("stepper", {})
                if isinstance(stepper_config, dict):
                    position = stepper_config.get("current_position")
                    if position in WHEEL_MOMENTS:
                        return position
        except (FileNotFoundError, TypeError, ValueError, OSError) as exc:
            print(f"Could not load current_position from {self.config_path}: {exc}")

        return "MORNING"

    def _load_steps_per_slot(self) -> int:
        """Load STEPS_PER_SLOT from config file. Defaults to steps_per_dose calibration."""
        try:
            if not self.config_path.exists():
                return self.steps_per_dose

            with self.config_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)

            if isinstance(data, dict):
                stepper_config = data.get("stepper", {})
                if isinstance(stepper_config, dict):
                    value = stepper_config.get("steps_per_slot")
                    if isinstance(value, int) and value > 0:
                        return value
        except (FileNotFoundError, TypeError, ValueError, OSError) as exc:
            print(f"Could not load steps_per_slot from {self.config_path}: {exc}")

        return self.steps_per_dose

    def _save_current_wheel_position(self, position: str) -> None:
        """Save current wheel position to config file."""
        if position not in WHEEL_MOMENTS:
            raise ValueError(f"Invalid position: {position}. Must be one of {WHEEL_MOMENTS}")

        try:
            if not self.config_path.exists():
                data = {"stepper": {}}
            else:
                with self.config_path.open("r", encoding="utf-8") as handle:
                    data = json.load(handle)

            if not isinstance(data, dict):
                data = {}

            if "stepper" not in data or not isinstance(data["stepper"], dict):
                data["stepper"] = {}

            data["stepper"]["current_position"] = position

            with self.config_path.open("w", encoding="utf-8") as handle:
                json.dump(data, handle, indent=2)
        except (TypeError, ValueError, OSError) as exc:
            print(f"Could not save current_position to {self.config_path}: {exc}")

    def calculate_slots_to_advance(self, current_position: str, target_moment: str) -> int:
        """
        Calculate the number of slots to advance from current position to target moment.
        
        Args:
            current_position: One of MORNING, NOON, EVENING
            target_moment: One of MORNING, NOON, EVENING
        
        Returns:
            Number of slots to advance (0-2)
        
        Raises:
            ValueError: If positions are invalid
        """
        if current_position not in WHEEL_MOMENTS:
            raise ValueError(f"Invalid current_position: {current_position}")
        if target_moment not in WHEEL_MOMENTS:
            raise ValueError(f"Invalid target_moment: {target_moment}")

        current_idx = WHEEL_MOMENTS.index(current_position)
        target_idx = WHEEL_MOMENTS.index(target_moment)

        slots_to_advance = (target_idx - current_idx) % len(WHEEL_MOMENTS)
        return slots_to_advance

    def get_next_active_moment(
        self, current_position: str, active_moments: list) -> tuple:
        """
        Get the next active medication moment starting from current position.
        
        Args:
            current_position: One of MORNING, NOON, EVENING
            active_moments: List of active moments like ["MORNING", "EVENING"]
        
        Returns:
            (target_moment, slots_to_advance) or (None, 0) if no active moments
        """
        if not active_moments:
            return (None, 0)

        if current_position not in WHEEL_MOMENTS:
            raise ValueError(f"Invalid current_position: {current_position}")

        # Filter active moments to valid ones
        valid_active = [m for m in active_moments if m in WHEEL_MOMENTS]
        if not valid_active:
            return (None, 0)

        # Find the next active moment in wheel rotation order
        current_idx = WHEEL_MOMENTS.index(current_position)

        # Check moments in order: current+1, current+2, etc.
        for i in range(1, len(WHEEL_MOMENTS) + 1):
            idx = (current_idx + i) % len(WHEEL_MOMENTS)
            moment = WHEEL_MOMENTS[idx]
            if moment in valid_active:
                slots_to_advance = i
                return (moment, slots_to_advance)

        # No active moment found (shouldn't happen if active_moments is non-empty)
        return (None, 0)

    def _set_step(self, step):
        for pin, value in zip(self.pins, step):
            pin.value = value

    def step(self, steps, direction=1):
        if steps < 0:
            raise ValueError("steps must be zero or greater")

        sequence = self.sequence if direction > 0 else self.sequence[::-1]
        for _ in range(steps):
            for step in sequence:
                self._set_step(step)
                time.sleep(self.delay)

    def rotate(self, turns=1.0, direction=1):
        steps = int(self.steps_per_rev * turns)
        self.step(steps, direction)

    def half_turn(self, direction=1):
        self.rotate(0.12, direction)

    def dispense_one_dose(self, direction=1):
        if not self.steps_per_dose or self.steps_per_dose <= 0:
            raise ValueError("STEPS_PER_DOSE must be configured before dispensing")

        try:
            self.step(self.steps_per_dose, direction)
        except Exception as exc:
            raise RuntimeError(f"Unable to dispense one dose: {exc}") from exc

        return self.steps_per_dose

    def release(self):
        for pin in getattr(self, "pins", []):
            try:
                pin.off()
            except Exception:
                pass

    def cleanup(self):
        self.release()
        try:
            import RPi.GPIO as GPIO  # type: ignore
        except Exception:
            GPIO = None

        if GPIO is not None:
            try:
                GPIO.cleanup()
            except Exception:
                pass

    def close(self):
        self.release()
        for pin in getattr(self, "pins", []):
            try:
                pin.close()
            except Exception:
                pass
        self.pins = []
        self.cleanup()
        super().close()

    def test(self):
        print("Testing stepper...")
        start_time = time.time()

        while time.time() - start_time < 5:
            for step in self.sequence:
                for p in range(min(4, len(self.pins))):
                    self.pins[p].value = step[p]
                time.sleep(self.delay)

        print("Stepper has been tested...")
