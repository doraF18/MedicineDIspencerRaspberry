from flask import Flask, request
import subprocess
import threading
import time

app = Flask(__name__)

HTML = """
<!DOCTYPE html>
<html>
<head>
    <title>Raspberry Pi WiFi Setup</title>
    <style>
        body {
            font-family: Arial;
            max-width: 400px;
            margin: 50px auto;
            padding: 20px;
        }

        h2 {
            text-align: center;
        }

        input, button {
            width: 100%;
            padding: 12px;
            margin-top: 10px;
            box-sizing: border-box;
        }

        button {
            background: black;
            color: white;
            border: none;
            cursor: pointer;
        }
    </style>
</head>
<body>

<h2>Connect Raspberry Pi to WiFi</h2>

<form method="POST">
    <input name="ssid" placeholder="WiFi Name" required>
    <input name="password" placeholder="WiFi Password" type="password" required>
    <button type="submit">Connect</button>
</form>

</body>
</html>
"""

def connect_wifi(ssid, password):
    time.sleep(2)

    subprocess.run([
        "nmcli",
        "dev",
        "wifi",
        "connect",
        ssid,
        "password",
        password,
        "ifname",
        "wlan0"
    ])

    subprocess.run([
        "nmcli",
        "con",
        "down",
        "PiSetupHotspot"
    ])

@app.route("/", methods=["GET", "POST"])
def index():
    if request.method == "POST":
        ssid = request.form["ssid"]
        password = request.form["password"]

        threading.Thread(
            target=connect_wifi,
            args=(ssid, password)
        ).start()

        return """
        <h2>Connecting...</h2>
        <p>The Raspberry Pi is connecting to your WiFi.</p>
        <p>The hotspot should disappear in a few seconds.</p>
        """

    return HTML

app.run(host="0.0.0.0", port=80)
