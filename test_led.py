from __future__ import annotations

from time import sleep

from gpiozero import LED

from hardware_common import LED_PIN, print_pin_table, wait_for_enter


def test_led() -> None:
    led = LED(LED_PIN)

    try:
        print("Testing LED...")
        for _ in range(3):
            led.on()
            sleep(2)
            led.off()
            sleep(2)
        print("LED test complete.")
    finally:
        led.off()
        led.close()


def main() -> None:
    print_pin_table()
    wait_for_enter("Make sure the LED is wired correctly.")
    test_led()


if __name__ == "__main__":
    main()