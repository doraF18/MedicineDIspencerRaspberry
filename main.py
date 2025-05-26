import requests
import json
from gpiozero import Button
from signal import pause
from RPLCD.i2c import CharLCD
from time import sleep
from models.StepperMotor import StepperMotor

motor = StepperMotor(18, 23, 27, 22)
button = Button(17, hold_time=3, bounce_time=0.15)
lcd = CharLCD('PCF8574', address=0x27, port=1, cols=16, rows=2)
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

    if response.status_code != 200:
        raise Exception("Error signing in: " + response.text)

    with open("firebase_tokens.json", "w") as f:
        json.dump(response.json(), f, indent=4)

def refresh_id_token(refresh_token):

    url = "https://identitytoolkit.googleapis.com/v1/token?key=AIzaSyAZdzV7TQMmA4nTFr59HspOIWq9XDeYzk0"

    body = {
        "grant_type": "refresh_token",
        "refresh_token": refresh_token
    }

    response = requests.post(url, json=body)

    if response.status_code != 200:
        raise Exception("Error refreshing ID token: " + response.text)
    else:
        with open("firebase_tokens.json", "w") as f:
            json.dump(response.json(), f, indent=4)
        return response.json()["id_token"]

def add_to_history():

    with open("firebase_tokens.json", "r") as f:
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
        add_to_history()
        motor.half_turn(direction=1)

        printToLCD("Pills had been taken", timeout=5)
    except Exception as e:
        printToLCD("Error occurred!\nTry pairing again", timeout=5)


try:
    button.when_released = on_button_pressed
    button.when_held = on_button_held

    printToLCD("Device is online", timeout=3)

    pause()
finally:
    motor.close()
    lcd.clear()
    lcd.close()
    button.close()
