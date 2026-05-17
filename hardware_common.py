"""Shared helpers and constants for the hardware test scripts."""

from __future__ import annotations

try:
    from RPLCD.i2c import CharLCD
except ImportError:  # pragma: no cover - optional on non-hardware environments.
    CharLCD = None


LCD_I2C_BUS = 1
LCD_I2C_ADDRESS = 0x27
LED_PIN = 17
BUTTON_PIN = 22
BUZZER_PIN = 27
STEPPER_PINS = (17, 18, 27, 22)

PIN_MAP = {
    "LCD SDA": "GPIO2",
    "LCD SCL": "GPIO3",
    "LED": "GPIO17",
    "Button": "GPIO22",
    "Buzzer": "GPIO27",
    "ULN2003 IN1": "GPIO17",
    "ULN2003 IN2": "GPIO18",
    "ULN2003 IN3": "GPIO27",
    "ULN2003 IN4": "GPIO22",
}


def print_pin_table() -> None:
    print("\nComponent pin map")
    print("| Device      | GPIO   |")
    print("| ----------- | ------ |")
    for device, gpio in PIN_MAP.items():
        print(f"| {device:<11} | {gpio:<6} |")
    print()


def wait_for_enter(message: str) -> None:
    input(f"{message} Press Enter to continue...")


def create_lcd():
    if CharLCD is None:
        print("LCD test skipped: RPLCD is not installed.")
        return None

    try:
        return CharLCD(
            i2c_expander="PCF8574",
            address=LCD_I2C_ADDRESS,
            port=LCD_I2C_BUS,
            cols=16,
            rows=2,
            # charmap="A00",
            # auto_linebreaks=True,
            # backlight_enabled=True,
        )
    except FileNotFoundError:
        print("LCD test skipped: /dev/i2c-1 is not available. Enable I2C on the Pi to test the display.")
    except OSError as error:
        print(f"LCD test skipped: {error}")

    return None


def close_lcd(lcd) -> None:
    if lcd is None:
        return

    try:
        lcd.clear()
    finally:
        lcd.close()