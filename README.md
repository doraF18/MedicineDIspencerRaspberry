# Raspberry Pi 5 Hardware Test Suite

This project includes small Python scripts to test each connected component individually and a combined runner that tests everything one by one.

## Recommended GPIO mapping

| Component | Raspberry Pi physical pin | GPIO number |
|---|---:|---:|
| LCD SDA | Pin 3 | GPIO 2 |
| LCD SCL | Pin 5 | GPIO 3 |
| LCD VCC | Pin 2 or 4 | 5V |
| LCD GND | Any GND | GND |
| LED | Pin 29 | GPIO 5 |
| Button | Pin 15 | GPIO 22 |
| Buzzer | Pin 31 | GPIO 6 |
| ULN2003 IN1 | Pin 11 | GPIO 17 |
| ULN2003 IN2 | Pin 12 | GPIO 18 |
| ULN2003 IN3 | Pin 13 | GPIO 27 |
| ULN2003 IN4 | Pin 16 | GPIO 23 |

## Breadboard wiring guide

### LCD 16x2 with I2C backpack

- Connect LCD VCC to 5V.
- Connect LCD GND to GND.
- Connect SDA to GPIO 2, physical pin 3.
- Connect SCL to GPIO 3, physical pin 5.

### LED

- Connect GPIO 5, physical pin 29, to the LED anode through a 220 ohm or 330 ohm resistor.
- Connect the LED cathode to GND.

### Button

- Connect one side of the push button to GPIO 22, physical pin 15.
- Connect the other side to GND.
- The scripts use the internal pull-up, so the button is active-low.

### Buzzer

- Connect signal to GPIO 6, physical pin 31.
- Connect VCC to 5V if your module needs it.
- Connect GND to GND.

### 28BYJ-48 stepper with ULN2003

- Connect IN1 to GPIO 17, physical pin 11.
- Connect IN2 to GPIO 18, physical pin 12.
- Connect IN3 to GPIO 27, physical pin 13.
- Connect IN4 to GPIO 23, physical pin 16.
- Connect ULN2003 VCC to 5V.
- Connect ULN2003 GND to GND.
- Plug the motor cable into the ULN2003 board.

## Python scripts

Run each component test individually:

```bash
python test_lcd.py
python test_led.py
python test_button.py
python test_buzzer.py
python test_stepper.py
```

Run everything in sequence:

```bash
python test_components.py
```

## Enable and verify I2C

Enable I2C:

```bash
sudo raspi-config
```

Then open:

- Interface Options
- I2C
- Enable
- Reboot

Install tools:

```bash
sudo apt update
sudo apt install -y i2c-tools python3-smbus
```

Verify the device node:

```bash
ls -l /dev/i2c-1
```

Scan the bus:

```bash
sudo i2cdetect -y 1
```

## Detect the LCD address

Use:

```bash
sudo i2cdetect -y 1
```

Common I2C LCD backpack addresses are `0x27` and `0x3F`.

If your address differs, update `LCD_I2C_ADDRESS` in `hardware_common.py`.

## Raspberry Pi 5 setup notes

Install the project dependencies with:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

The Pi 5 GPIO backend uses `lgpio`. If it is missing, install the system build tools first:

```bash
sudo apt install -y swig liblgpio-dev
```

## Common wiring mistakes

- Mixing up physical pin numbers and GPIO numbers.
- Wiring SDA and SCL backwards.
- Forgetting to connect grounds together.
- Driving an LED without a resistor.
- Powering the stepper from the Pi GPIO pin instead of the ULN2003 board supply.
- Expecting the LCD to work before I2C is enabled.
- Using the wrong LCD I2C address.

## Safety recommendations

- Power the stepper motor from a stable 5V supply.
- Share ground between the Pi and the motor driver.
- Never connect motor coils directly to GPIO.
- Do not connect 5V to any GPIO pin.
- If the Pi resets when the motor runs, the supply is too weak or noisy.
- Keep the LED current limited with a resistor.
- If the LCD does not show up on I2C scan, fix wiring and I2C enablement before changing code.