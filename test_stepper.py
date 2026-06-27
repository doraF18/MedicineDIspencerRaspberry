from __future__ import annotations

from time import sleep

from hardware_common import STEPPER_PINS, print_pin_table, wait_for_enter
from models import StepperMotor


def test_stepper() -> None:
    stepper = StepperMotor(*STEPPER_PINS)

    try:
        print("Testing stepper motor...")
        print("Rotating forward...")
        stepper.half_turn(direction=1)
        sleep(1)
        print("Rotating backward...")
        stepper.half_turn(direction=1)
        print("Stepper motor test complete.")
    finally:
        stepper.close()


def main() -> None:
    print_pin_table()
    wait_for_enter("Make sure the ULN2003 board and motor are wired correctly.")
    test_stepper()


if __name__ == "__main__":
    main()