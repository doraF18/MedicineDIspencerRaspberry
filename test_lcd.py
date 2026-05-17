from __future__ import annotations

from time import sleep

from hardware_common import create_lcd, close_lcd, print_pin_table, wait_for_enter


def test_lcd() -> None:
    lcd = create_lcd()
    if lcd is None:
        return

    try:
        lcd.clear()
        lcd.write_string("LCD test")
        sleep(5)
        lcd.cursor_pos = (1, 0)
        lcd.write_string("Hello Pi 5")
        sleep(5)
        # print("LCD should now show: 'LCD test' / 'Hello Pi 5'.")
        # input("Look at the display now, then press Enter to finish the LCD test...")
        lcd.clear()
        # lcd.write_string("Backlight on\nDisplay OK?")
        sleep(2)
    finally:
        close_lcd(lcd)


def main() -> None:
    print_pin_table()
    wait_for_enter("Make sure the LCD is wired and powered.")
    test_lcd()


if __name__ == "__main__":
    main()