from __future__ import annotations

from time import sleep

from gpiozero import Button

from hardware_common import BUTTON_PIN, print_pin_table, wait_for_enter


def when_button_pressed() -> None:
    print("Button was pressed!")


def test_button() -> None:
    button = Button(BUTTON_PIN, bounce_time=0.15)

    button.when_pressed = when_button_pressed

    sleep(10)  # Wait for button presses

def main() -> None:
    print_pin_table()
    wait_for_enter("Make sure the button is wired correctly.")
    test_button()


if __name__ == "__main__":
    main()