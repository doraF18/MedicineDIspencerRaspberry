from __future__ import annotations

from time import sleep

import RPi.GPIO as GPIO

from hardware_common import BUZZER_PIN, print_pin_table, wait_for_enter


def test_buzzer() -> None:
    GPIO.setwarnings(False)
    GPIO.setmode(GPIO.BCM)
    GPIO.setup(BUZZER_PIN, GPIO.OUT)

    try:
        print("Testing buzzer...")

        print("Trying active-high pulse mode...")
        for _ in range(3):
            GPIO.output(BUZZER_PIN, GPIO.HIGH)
            sleep(0.5)
            GPIO.output(BUZZER_PIN, GPIO.LOW)
            sleep(0.5)

        print("Trying active-low pulse mode...")
        for _ in range(3):
            GPIO.output(BUZZER_PIN, GPIO.LOW)
            sleep(0.5)
            GPIO.output(BUZZER_PIN, GPIO.HIGH)
            sleep(0.5)

        print("Trying PWM tone mode at 2 kHz...")
        pwm = GPIO.PWM(BUZZER_PIN, 2000)
        pwm.start(50)
        sleep(1)
        pwm.stop()

        print("Buzzer test complete.")
    finally:
        GPIO.output(BUZZER_PIN, GPIO.LOW)
        GPIO.cleanup(BUZZER_PIN)


def main() -> None:
    print_pin_table()
    wait_for_enter("Make sure the buzzer module is wired correctly.")
    test_buzzer()


if __name__ == "__main__":
    main()