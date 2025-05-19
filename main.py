import requests
import json
from gpiozero import Button

button = Button(17, hold_time=3)

@button.when_held
def on_button_held():
    print("Pairing...")
    init_device()

@button.when_activated
def on_button_activated():
    print("Button activated!")
    add_to_history()

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
        print("Error signing in:", response.json())
        return

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
        print("Error refreshing token:", response.json())
        init_device() 
        return
    else:
        with open("firebase_tokens.json", "w") as f:
            json.dump(response.json(), f, indent=4)
        return response.json()["id_token"]

# TODO: call this when the user presses the button
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

    body = {"entry": ["LCD", "cox", "weed", "meth"]}

    res = requests.put(url, json=body, headers=header)

    if res.status_code != 200:
        print("Error adding to history:", res.json())
    else:
        print("Added to history")
