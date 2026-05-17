import os
import requests
import json
from gpiozero import Button
from signal import pause
from RPLCD.i2c import CharLCD
from time import sleep
from dotenv import load_dotenv
from hardware_common import STEPPER_PINS
from models import StepperMotor
from api import DeviceConfigurator

load_dotenv()

DEVICE_CONFIG_PATH = os.getenv("DEVICE_CONFIG_PATH")
FIREBASE_PATH = os.getenv("FIREBASE_PATH")

motor = StepperMotor(*STEPPER_PINS)
button = Button(26, hold_time=3, bounce_time=0.15)
lcd = CharLCD('PCF8574', address=0x27, port=1, cols=16, rows=2)
# configurator = DeviceConfigurator(config_path=DEVICE_CONFIG_PATH)
long_press = False

def printToLCD(message, timeout = None):
    lcd.clear()
    lcd.write_string(message)

    if timeout:
        sleep(timeout)
        lcd.clear()

# TODO: implement a way to get the credentials from mobile app, not hardcoded
def get_credentials():
    return {
        "email": "test@gmail.com",
        "password": "asdasd"
    }

def init_device():
    url = "https://identitytoolkit.googleapis.com/v1/accounts:signInWithPassword?key=AIzaSyAZdzV7TQMmA4nTFr59HspOIWq9XDeYzk0"

    credentials = get_credentials()
    email = credentials["email"]
    password = credentials["password"]

    body = {
        "email": email,
        "password": password,
        "returnSecureToken": True
    }

    response = requests.post(url, json=body)

    print("Got here")

    if response.status_code != 200:
        print(response.text)
        raise Exception("Error signing in: " + response.text)
    
    print("Got here 2")

    with open(FIREBASE_PATH, "w") as f:
        json.dump(response.json(), f, indent=4)

    print("Got here 3")

def refresh_id_token(refresh_token):

    url = "https://identitytoolkit.googleapis.com/v1/token?key=AIzaSyAZdzV7TQMmA4nTFr59HspOIWq9XDeYzk0"

    body = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }

    response = requests.post(url, json=body)

    if response.status_code != 200:
        print(response.text)
        raise Exception("Error refreshing ID token: " + response.text)
    else:
        return response.json()["id_token"]

def add_to_history():

    with open(FIREBASE_PATH, "r") as f:
        tokens = f.read()
        tokens = json.loads(tokens)
        refresh_token = tokens["refreshToken"]
        id_token = refresh_id_token(refresh_token)
    
    url = "https://iiotca.onrender.com/api/user/history"

    header = {
        "Authorization": "Bearer " + id_token,
    }

    res = requests.put(url, headers=header)

    if res.status_code != 200:
        print(res.text)
        raise Exception("Error adding to history")      
    else:
        print("Added to history")

def on_button_held():
    global long_press
    long_press = True

    printToLCD("Pairing...")

    try:
        init_device()
        printToLCD("Device paired successfully", timeout=5)
    except Exception as e:
        printToLCD("Error occurred!\nTry pairing again", timeout=5)

def on_button_pressed():

    global long_press
    if long_press:
        long_press = False
        return
    
    try:
        print("Button pressed")
        add_to_history()
        print("Added to history")
        # TODO: fix problem with motor not rotating
        motor.half_turn(direction=1)
        print("Motor rotated")

        printToLCD("Pills had been taken", timeout=5)
    except Exception as e:
        print("Error occurred:", e)
        printToLCD("Error occurred!\nTry pairing again", timeout=5)


try:
    button.when_released = on_button_pressed
    button.when_held = on_button_held

    printToLCD("Device is online", timeout=3)

    # motor.test()

    pause()
finally:
    motor.close()
    lcd.clear()
    lcd.close()
    button.close()
