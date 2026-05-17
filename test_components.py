"""Combined hardware test runner for all device components."""

from __future__ import annotations

from hardware_common import print_pin_table, wait_for_enter
from test_button import test_button
from test_buzzer import test_buzzer
from test_lcd import test_lcd
from test_led import test_led
from test_stepper import test_stepper


def main() -> None:
    print_pin_table()
    wait_for_enter("Make sure the hardware is wired and powered.")

    wait_for_enter("Next: LCD")
    test_lcd()

    wait_for_enter("Next: LED")
    test_led()

    wait_for_enter("Next: buzzer")
    test_buzzer()

    wait_for_enter("Next: button")
    test_button()

    wait_for_enter("Next: stepper motor")
    test_stepper()

    print("\nAll component tests finished.")


if __name__ == "__main__":
    main()