# IIoTCA Device App — Complete Project Documentation

This document consolidates the project overview, backend integration details, implementation summary, and deployment information for the Raspberry Pi medication dispenser project in this repository.

The application is not a cloud-hosted web app. It is a device-first system that runs on a Raspberry Pi, controls physical hardware, communicates with a backend API, and exposes local web pages for setup and pairing.

---

## 1. What This Project Is

The IIoTCA Device App is a smart medication dispenser application designed to run on a Raspberry Pi. It combines:

- physical hardware control for a medication dispensing experience
- backend communication for pairing, schedule retrieval, and intake reporting
- local web-based setup portals for Wi-Fi and credentials
- a compact, embedded-style software architecture for Raspberry Pi deployment

In practical terms, the device can:

- generate and store a persistent device identity
- register itself with a backend service
- pair with a user account or patient profile
- display pairing information on an LCD
- monitor medication schedules
- trigger reminders using LED and buzzer
- record intake events when a physical button is pressed
- rotate a stepper motor to simulate or perform dispensing

---

## 2. High-Level Purpose

The project exists to bring the logic of a connected medication dispense device into a small embedded environment. It is meant to be installed on hardware and used in a real-world setting where:

- the device is physically present near the user
- the user needs reminders for doses
- the device needs to report events to a backend system
- the Pi may not have a keyboard or monitor connected at setup time

Because of that, the project includes a hotspot-based setup workflow that allows the user to configure Wi-Fi without needing a separate screen or terminal.

---

## 3. Repository Structure

The repository contains both device-side application code and supporting documentation.

```text
iiotca-device-app/
├── main.py                     # Main application entry point
├── hardware_common.py          # Shared GPIO and LCD constants
├── wifi_portal.py              # Flask hotspot-based Wi-Fi setup portal
├── device_config.json          # Runtime device state (generated at first run)
├── requirements.txt            # Python dependencies
├── api/
│   ├── __init__.py
│   ├── DeviceManager.py        # Backend integration and pairing logic
│   ├── DeviceConfigurator.py   # FastAPI-based local configuration portal
│   └── static/
│       └── index.html          # Simple local credential form
├── models/
│   └── StepperMotor.py         # Stepper motor driver
├── ui/                         # Bundled frontend/static UI assets
├── tests and helpers           # test_* scripts for hardware and integration
└── *.md                        # Documentation files
```

---

## 4. Architecture Overview

The system is structured into three main layers:

1. Device layer
   - Raspberry Pi hardware
   - LCD, button, LED, buzzer, stepper motor
   - GPIO-based control through Python libraries

2. Application layer
   - `main.py` orchestrates the device behavior
   - background threads handle monitoring and scheduling
   - local state is managed in memory and persisted to `device_config.json`

3. Integration layer
   - outbound HTTP requests to a backend API
   - local web pages for setup and pairing
   - local Wi-Fi configuration workflow through a temporary hotspot

### Simplified architecture diagram

```text
User / Patient / Mobile App
          │
          ▼
    Backend API (remote)
          ▲
          │ HTTP / REST
          │
┌─────────┴──────────────────────────────┐
│ Raspberry Pi Device App                │
│ ┌───────────────────────────────────┐  │
│ │ main.py                           │  │
│ │ - startup workflow                │  │
│ │ - reminder scheduler             │  │
│ │ - button handling                │  │
│ │ - hardware orchestration         │  │
│ └──────────────┬────────────────────┘  │
│                │                      │
│ ┌──────────────▼────────────────────┐ │
│ │ Hardware Layer                   │ │
│ │ LED / Buzzer / Button / LCD     │ │
│ │ Stepper Motor                   │ │
│ └─────────────────────────────────┘ │
│                                      │
│ ┌──────────────┬───────────────────┐ │
│ │ wifi_portal.py│ DeviceConfigurator│ │
│ │ hotspot portal│ local config form│ │
│ └──────────────┴───────────────────┘ │
└──────────────────────────────────────┘
```

---

## 5. Hardware Components and Wiring

The project is designed around a Raspberry Pi and several common hardware parts.

### 5.1 Supported Hardware

- Raspberry Pi (target platform)
- 16x2 LCD with I2C backpack
- LED
- physical button
- buzzer
- 28BYJ-48 stepper motor with ULN2003 driver board

### 5.2 GPIO Pin Mapping

| Component | GPIO | Physical Pin |
|---|---:|---:|
| LCD SDA | GPIO 2 | Pin 3 |
| LCD SCL | GPIO 3 | Pin 5 |
| LED | GPIO 5 | Pin 29 |
| Button | GPIO 22 | Pin 15 |
| Buzzer | GPIO 6 | Pin 31 |
| ULN2003 IN1 | GPIO 17 | Pin 11 |
| ULN2003 IN2 | GPIO 18 | Pin 12 |
| ULN2003 IN3 | GPIO 27 | Pin 13 |
| ULN2003 IN4 | GPIO 23 | Pin 16 |

### 5.3 Wiring Notes

- The LCD uses I2C and is expected at address `0x27` by default.
- The button is wired as active-low and uses internal pull-up behavior.
- The stepper motor uses four control pins through the ULN2003 driver board.
- The buzzer is driven with PWM-like output for simple audible alerts.

### 5.4 Enabling I2C

On Raspberry Pi OS, I2C must be enabled before the LCD can work:

```bash
sudo raspi-config
# Interface Options -> I2C -> Enable -> Reboot
sudo apt update && sudo apt install -y i2c-tools python3-smbus
sudo i2cdetect -y 1
```

---

## 6. Core Software Modules

### 6.1 `main.py`

This is the main application controller. It orchestrates all runtime behavior.

Its responsibilities include:

- initializing hardware objects
- reading and writing device configuration
- starting device registration and pairing workflows
- handling short and long button presses
- detecting scheduled reminders
- triggering LED and buzzer patterns
- communicating with the backend through `DeviceManager`
- providing user feedback on the LCD

The file also contains helper functions for:

- schedule normalization
- time parsing
- reminder flashing and beeping
- reminder state management

### 6.2 `api/DeviceManager.py`

This module handles the device’s backend integration.

It provides:

- persistent device identity management via UUID
- device registration against the backend
- pairing status polling
- medication schedule fetching
- intake event reporting
- request retry logic with timeout and backoff behavior

It contains two main classes:

- `DeviceManager`: handles backend API communication and local state
- `PairingManager`: handles the pairing workflow and callback-based LCD updates

### 6.3 `api/DeviceConfigurator.py`

This is a local FastAPI-based web server used to present a simple configuration form.

It serves a local web page from `api/static/index.html` and allows the user to submit credentials. The form submission saves the values locally and stops the server after pairing.

It is intended to run on port `8000` by default.

### 6.4 `wifi_portal.py`

This is the hotspot-based configuration portal.

It uses Flask to host a small HTML page that collects Wi-Fi SSID and password. Once submitted, it calls `nmcli` to connect the Pi to the home network and disconnects the temporary hotspot.

This file is central to the “hotspot mode” feature of the device.

### 6.5 `models/StepperMotor.py`

This file implements the stepper motor driving logic for the 28BYJ-48 motor.

It uses a half-step sequence and exposes methods such as:

- `step()`
- `rotate()`
- `half_turn()`
- `release()`
- `close()`

### 6.6 `hardware_common.py`

This file centralizes shared constants and helper functions for the hardware layer.

It includes:

- pin constants
- LCD I2C address and bus configuration
- a pin map helper
- LCD initialization helpers

### 6.7 `ui/`

The repository contains a built frontend under `ui/`. It appears to be a bundled React-based web UI for Wi-Fi connectivity/setup. It is part of the project’s web-facing experience, although the core runtime logic in this repository is implemented through the Python services above.

---

## 7. Runtime Workflow

### 7.1 First Launch

When the application starts for the first time:

1. it checks whether a device config file already exists
2. if no device ID exists, it generates a UUID and stores it
3. it initializes hardware components
4. it attempts to register the device with the backend
5. if the backend returns a pairing code, the code is shown on the LCD
6. the app begins monitoring pairing status

### 7.2 Pairing Workflow

During pairing:

- the device sends its ID to the backend
- the backend returns a pair code or indicates that the device is already paired
- the LCD is used to display pairing instructions or the pair code
- the device continues polling the backend until pairing completes or the process times out

### 7.3 Normal Operation

After pairing:

- the device can fetch the medication schedule
- reminders can be triggered at scheduled times
- button press events are captured and sent to the backend
- the Pi can continue to run while monitoring state in the background

### 7.4 Button Behavior

- short press: records an intake event and performs the local motor response
- long press: re-enters or refreshes the pairing workflow

---

## 8. Backend Integration Details

The Pi communicates with a backend API over HTTP. The integration is implemented in `api/DeviceManager.py`.

### 8.1 Device Identity

The device stores a persistent UUID in `device_config.json`.

Example:

```json
{
  "deviceId": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "isPaired": true
}
```

### 8.2 Required Backend Endpoints

The backend is expected to support the following API calls:

| Method | Endpoint | Purpose |
|---|---|---|
| POST | `/api/devices/register` | Registers a device and returns pairing status / code |
| GET | `/api/devices/{deviceId}/pairing-status` | Checks whether the device is paired |
| GET | `/api/devices/{deviceId}/schedule` | Fetches dose schedule data |
| POST | `/api/devices/{deviceId}/intake-events` | Records intake events |

### 8.3 Example Requests

#### Register device

```json
{
  "deviceId": "f47ac10b-58cc-4372-a567-0e02b2c3d479"
}
```

#### Pairing status response

```json
{
  "paired": false,
  "pairCode": "483921"
}
```

#### Intake event request

```json
{
  "actualIntakeTime": "2024-05-17T14:30:45.123Z",
  "source": "BUTTON"
}
```

### 8.4 Retry and Error Handling

The device client uses automatic retry logic:

- up to 3 attempts
- 2-second delay between retries
- 10-second request timeout
- retries on connection errors, timeouts, and server-side failures
- no retry for client-side errors such as 4xx responses

This makes the device behave well in unreliable network environments.

---

## 9. Website and Local Web Interfaces

This repository contains multiple web-facing surfaces, but they are all local to the device rather than hosted on the public internet.

### 9.1 Credential Portal (`api/static/index.html`)

The file `api/static/index.html` contains a simple HTML form for entering credentials. It is served by the FastAPI-based `DeviceConfigurator` on port `8000`.

It is a basic local page intended for pairing or configuration.

### 9.2 Bundled UI (`ui/`)

The `ui/` folder contains a prebuilt frontend bundle. It looks like a compiled web app, likely intended for setup or Wi-Fi connection workflows.

This is not a remote cloud website. It is static content that can be served from the Pi or another local web server if needed.

### 9.3 Wi-Fi Portal (`wifi_portal.py`)

This is the main user-facing web setup portal during initial device configuration. It serves a form that allows the user to enter home Wi-Fi credentials.

---

## 10. Hotspot Mode

Hotspot mode is one of the most important features of this project.

### 10.1 What It Does

When the Pi is in setup mode, it can broadcast a temporary Wi-Fi access point named `PiSetupHotspot`.

The user can connect to that hotspot and browse to:

```text
http://192.168.4.1
```

From there, the user enters their normal Wi-Fi network name and password.

### 10.2 How It Works

The Flask app in `wifi_portal.py`:

- serves an HTML form over port `80`
- accepts the SSID and password
- starts a background process to connect the Pi to the chosen network using `nmcli`
- disconnects the hotspot once the connection process begins

This allows setup without a keyboard, mouse, or monitor.

### 10.3 Important Notes

- hotspot mode depends on `nmcli` being available on the Raspberry Pi
- the code assumes the Wi-Fi interface is `wlan0`
- the portal is intended for initial provisioning, not as a permanent network service

---

## 11. How It Is Hosted

The application is hosted locally on the Raspberry Pi itself.

There is no separate public hosting setup in this repository. Instead:

- the main Python application runs directly on the Pi
- local web pages are served from the Pi over its own network interfaces
- backend communication uses outbound HTTP requests to a remote or networked backend server

### 11.1 Local Hosting Model

The current hosting model is:

- `main.py` runs as the main device application
- `wifi_portal.py` serves the hotspot page on port `80`
- `DeviceConfigurator` serves a simple local config form on port `8000`
- the device interacts with the backend API over HTTP

### 11.2 Accessing the Local Pages

Depending on the operating mode:

- hotspot page: `http://192.168.4.1`
- local config page: `http://<pi-ip>:8000/`
- the Pi can also be reached on its local LAN IP if it is already connected to Wi-Fi

### 11.3 Production Deployment Considerations

For a more reliable production setup, the Python services should ideally be launched as system services (for example with `systemd`) so they start automatically on boot and continue running in the background.

---

## 12. Installation and Setup

### 12.1 Install Dependencies

```bash
pip install -r requirements.txt
```

### 12.2 Enable I2C

As described earlier, enable I2C for the LCD.

### 12.3 Configure Environment Variables

The project uses environment variables such as:

```env
BACKEND_URL="http://your-backend-url.com"
DEVICE_CONFIG_PATH="./device_config.json"
```

### 12.4 Run the Main Application

```bash
python main.py
```

### 12.5 Run the Wi-Fi Portal

```bash
sudo python wifi_portal.py
```

### 12.6 Run the Device Configuration Portal

The FastAPI server is started from the Python code in `api/DeviceConfigurator.py` when used by the app.

---

## 13. Testing

The repository includes several test scripts for different components:

- `test_backend_integration.py`
- `test_button.py`
- `test_buzzer.py`
- `test_components.py`
- `test_lcd.py`
- `test_led.py`
- `test_stepper.py`

Example:

```bash
python test_stepper.py
python test_backend_integration.py
```

These tests help verify the core functionality without depending entirely on live hardware.

---

## 14. Troubleshooting

### 14.1 LCD Not Showing Output

Possible causes:

- I2C not enabled
- wrong LCD address
- missing Python packages
- hardware not connected correctly

### 14.2 Device Not Pairing

Possible causes:

- backend URL incorrect
- network unavailable
- backend service not running
- pairing workflow timed out

### 14.3 Wi-Fi Portal Not Working

Possible causes:

- `nmcli` unavailable
- wrong interface name
- hotspot not started correctly
- network policy restrictions

### 14.4 Motor Not Rotating

The motor is separate from backend event posting. A motor failure does not necessarily stop the device from sending intake events.

---

## 15. Security and Design Notes

The design keeps device identity simple and uses a persistent UUID as the main device identifier.

Key design points:

- the device ID is stored locally and reused
- backend decisions such as patient association are handled server-side
- the app avoids storing sensitive data beyond the necessary local configuration
- the setup portal is intended for local, physical access, not open public exposure

---

## 16. Summary

This repository is a Raspberry Pi-based medication dispenser application with:

- hardware control for LED, buzzer, button, LCD, and stepper motor
- backend communication for registration, pairing, schedules, and intake events
- local setup pages for configuration and Wi-Fi provisioning
- hotspot-based onboarding for initial network setup
- a simple, embedded-style deployment model that runs locally on the device

In short, the project is a self-contained device application that bridges the gap between physical hardware and a backend service while remaining practical to deploy on a Raspberry Pi.

---

## 17. Recommended Next Steps

If you want to take this project further, the next logical steps would be:

- package the Python services as systemd services
- make the hotspot name and credentials configurable
- improve the local web UI and make it more polished
- add stronger logging and health monitoring
- add persistent service status and remote diagnostics
- deploy the device against a real backend implementation
