from __future__ import annotations

import json
import time
from pathlib import Path

from gpiozero import OutputDevice
from gpiozero.devices import Device

STEPS_PER_REVOLUTION = 4096
DEFAULT_STEPS_PER_DOSE = 295
STEPS_PER_DOSE = DEFAULT_STEPS_PER_DOSE
CONFIG_FILE_PATH = Path(__file__).resolve().parents[1] / "device_config.json"


class StepperMotor(Device):
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

        try:
            self._release_gpio_resources()
            self.pins = [
                OutputDevice(pin1),
                OutputDevice(pin2),
                OutputDevice(pin3),
                OutputDevice(pin4),
            ]
        except Exception as exc:
            self._release_gpio_resources()
            try:
                self.pins = [
                    OutputDevice(pin1),
                    OutputDevice(pin2),
                    OutputDevice(pin3),
                    OutputDevice(pin4),
                ]
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
