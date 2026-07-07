from __future__ import annotations

import os
from time import sleep

from gpiozero import Button

from hardware_common import BUTTON_PIN, STEPPER_PINS, print_pin_table, wait_for_enter
from models import StepperMotor


DEFAULT_DELAY_SECONDS = 0.003
WHEEL_MOMENTS = ["MORNING", "NOON", "EVENING"]


def _target_moment_for_test(current_position: str) -> str:
    """Pick target moment for test: env override, else next slot in wheel order."""
    forced_target = os.getenv("STEPPER_TEST_TARGET_MOMENT", "").strip().upper()
    if forced_target in WHEEL_MOMENTS:
        return forced_target

    current_idx = WHEEL_MOMENTS.index(current_position)
    next_idx = (current_idx + 1) % len(WHEEL_MOMENTS)
    return WHEEL_MOMENTS[next_idx]


def test_stepper() -> None:
    # Use a conservative delay for 28BYJ-48 reliability during diagnostics.
    stepper = StepperMotor(*STEPPER_PINS, delay=DEFAULT_DELAY_SECONDS)
    button = Button(BUTTON_PIN, bounce_time=0.15)

    try:
        print("Stepper button test started (main.py behavior emulation).")
        print(f"Current wheel position: {stepper.current_wheel_position}")
        print(f"Configured steps_per_slot from config: {stepper.steps_per_slot}")
        print("Each button press runs main.py alignment logic with direction=clockwise")
        print("steps_to_rotate = slots_to_advance * steps_per_slot")
        print("Optional: STEPPER_TEST_TARGET_MOMENT=MORNING|NOON|EVENING")
        print("Press Ctrl+C to stop the test.")

        while True:
            button.wait_for_press()

            current_position = stepper.current_wheel_position
            target_moment = _target_moment_for_test(current_position)

            slots_to_advance = stepper.calculate_slots_to_advance(current_position, target_moment)
            steps_to_rotate = slots_to_advance * stepper.steps_per_slot

            print(
                "Button pressed -> "
                f"current={current_position}, target={target_moment}, "
                f"slots={slots_to_advance}, steps={steps_to_rotate}, direction=clockwise"
            )

            if steps_to_rotate > 0:
                stepper.step(steps_to_rotate, direction=1)

            stepper.current_wheel_position = target_moment
            stepper._save_current_wheel_position(target_moment)

            sleep(0.2)
    except KeyboardInterrupt:
        print("Stepper test stopped by user.")
    finally:
        button.close()
        stepper.close()


def main() -> None:
    print_pin_table()
    wait_for_enter("Make sure button + ULN2003 board + motor are wired correctly.")
    test_stepper()


if __name__ == "__main__":
    main()