# Backend Integration Guide

## Overview

This document describes the backend integration for the Raspberry Pi Medication Dispenser. The system maintains a persistent device identity, handles device registration and pairing, and tracks medication intake events.

## Features

### 1. Persistent Device Identity

- **Auto-generated UUID**: On first launch, the system generates a unique device ID (UUID)
- **Local Storage**: Device ID is stored in `device_config.json`
- **Persistence**: Device ID survives power loss, reboots, and Wi-Fi changes
- **No regeneration**: Once created, the same ID is used for all future launches

**Configuration File Example:**
```json
{
  "deviceId": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
  "isPaired": true
}
```

### 2. Device Registration

**Endpoint:** `POST /api/devices/register`

**Request:**
```json
{
  "deviceId": "f47ac10b-58cc-4372-a567-0e02b2c3d479"
}
```

**Behavior:**
- Registers the device with the backend
- If device is not yet paired, backend will respond with a pairing code
- Pairing code is displayed on the LCD for user to scan/enter in the mobile app

### 3. Pairing Status

**Endpoint:** `GET /api/devices/{deviceId}/pairing-status`

**Response (Not Paired):**
```json
{
  "paired": false,
  "pairCode": "483921"
}
```

**Response (Paired):**
```json
{
  "paired": true
}
```

**Polling:** The system polls every 3 seconds during the pairing process and every 60 seconds during normal operation.

### 4. Medication Schedule

**Endpoint:** `GET /api/devices/{deviceId}/schedule`

**Response:**
```json
{
  "schedules": [
    {
      "scheduleId": "abc123",
      "medicationName": "Aspirin",
      "dosage": "500mg",
      "time": "09:00",
      "instructions": "Take with food"
    }
  ]
}
```

**Polling:** Fetched every 5 minutes when device is paired.

### 5. Intake Events

**Endpoint:** `POST /api/devices/{deviceId}/intake-events`

**Request:**
```json
{
  "actualIntakeTime": "2024-05-17T14:30:45.123Z",
  "source": "BUTTON"
}
```

**Important Notes:**
- Do NOT send `patientId` - backend determines patient from `deviceId`
- `actualIntakeTime` must be in ISO 8601 format
- `source` should be "BUTTON" for manual intake or "AUTO" for automated
- Includes automatic retry logic with exponential backoff

## Configuration

### Environment Variables

Create or update `.env` file:

```env
# Backend API URL
BACKEND_URL="http://your-backend-url.com"

# Device configuration file path
DEVICE_CONFIG_PATH="./config/device_config.json"

# Legacy Firebase configuration (optional)
FIREBASE_PATH="./config/firebase_tokens.json"
```

### Creating Config Directory

The system automatically creates the config directory if it doesn't exist. Ensure the Raspberry Pi has write permissions:

```bash
mkdir -p ./config
chmod 755 ./config
```

## Application Flow

### On First Launch

1. Generate UUID for device ID
2. Save to `device_config.json`
3. Display "Starting up..." on LCD
4. Attempt device registration
5. Display pairing code on LCD: `PAIR DEVICE\n483921`
6. Poll pairing status every 3 seconds (up to 5 minute timeout)
7. Once paired, display "Device paired\nReady"
8. Wait for button press or hold button to pair

### On Subsequent Launches

1. Load device ID from `device_config.json`
2. Check pairing status in config
3. If paired, display "Device Ready"
4. If not paired, restart pairing workflow
5. Start background monitoring threads

### Button Interactions

**Short Press:** Record medication intake
- Sends intake event to backend
- Rotates motor to dispense medication
- Displays "Intake recorded\nTaken"

**Long Press (3+ seconds):** Manual pairing
- Triggers pairing workflow
- Useful if device was unpaired or needs to re-pair
- Displays pairing code on LCD

### Background Tasks

**Pairing Status Monitor** (every 60 seconds)
- Checks if device is paired
- Updates status if pairing is completed
- Logs any errors

**Schedule Fetcher** (every 5 minutes)
- Fetches medication schedule from backend
- Updates local state
- Ready for future schedule-based alerts

## Error Handling

### Retry Logic

The system includes automatic retry logic for network failures:

- **Max Retries:** 3 attempts per request
- **Retry Delay:** 2 seconds between attempts
- **Timeout:** 10 seconds per request
- **Server Errors (5xx):** Automatically retried
- **Client Errors (4xx):** Not retried
- **Connection Errors:** Automatically retried

### LCD Error Messages

- `Device not ready` - Device not yet initialized
- `Not paired\nHold to pair` - Device not paired, long press button to pair
- `Backend error\nRetry` - Backend unavailable, will retry
- `Error occurred\nTry again` - General error, try the action again
- `Pairing Failed\nRetry: Hold button` - Pairing workflow timeout

## Logging

All events are logged to the console with timestamps:

```
2024-05-17 14:30:45 - Device Manager - INFO - Device ID: f47ac10b-58cc-4372-a567-0e02b2c3d479
2024-05-17 14:30:46 - Device Manager - INFO - Device registration successful
2024-05-17 14:30:47 - Device Manager - INFO - Displaying pair code: 483921
2024-05-17 14:31:03 - Device Manager - INFO - Device is paired!
2024-05-17 14:31:05 - Device Manager - INFO - Intake event posted successfully
```

## Testing

### Manual Testing

1. **Test Device ID Persistence:**
   ```bash
   # Run application, note device ID
   python main.py
   # Stop application (Ctrl+C)
   # Run again, should see same device ID
   python main.py
   ```

2. **Test Pairing Workflow:**
   - Run application
   - Long press button (3+ seconds)
   - Observe pairing code on LCD
   - Simulate pairing in backend
   - Application should display "Device paired\nReady"

3. **Test Intake Event:**
   - Ensure device is paired
   - Short press button
   - Check backend for intake event record
   - Motor should rotate

### Backend Requirements

The backend API must implement these endpoints:

```
POST /api/devices/register
GET  /api/devices/{deviceId}/pairing-status
GET  /api/devices/{deviceId}/schedule
POST /api/devices/{deviceId}/intake-events
```

## Troubleshooting

### Device continuously asks for pairing

**Potential Causes:**
- Backend unavailable or not responding
- Network connectivity issues
- Configuration file permissions

**Solutions:**
1. Check `BACKEND_URL` in `.env` is correct
2. Verify network connectivity: `ping backend-url.com`
3. Check logs for specific error messages
4. Verify write permissions on config directory

### Intake events not being recorded

**Potential Causes:**
- Device not paired
- Backend unavailable
- Motor rotation failure doesn't block event posting

**Solutions:**
1. Check if device is paired (LCD should show "Device Ready")
2. Check backend logs for API errors
3. Check network connectivity
4. Review application logs for specific errors

### Motor not rotating on button press

**Note:** Motor failure does not prevent intake event from being posted to backend. The motor rotation is separate from the event recording.

**Solutions:**
1. Verify motor connections
2. Check GPIO pins in `hardware_common.py`
3. Test motor independently: `python test_stepper.py`
4. Check for motor error messages in logs

## Development Notes

### Key Classes

**DeviceManager**
- Manages device identity and backend API communication
- Handles persistent device ID storage
- Implements retry logic for all API calls
- Methods:
  - `register_device()` - POST device to backend
  - `get_pairing_status()` - Check pairing status
  - `get_schedule()` - Fetch medication schedule
  - `post_intake_event()` - Record intake event

**PairingManager**
- Handles the pairing workflow with user
- Manages LCD display during pairing
- Methods:
  - `start_pairing()` - Complete pairing workflow
  - `check_and_complete_pairing()` - Check and complete if needed

### Extending the System

To add new backend API endpoints:

1. Add method to `DeviceManager` class
2. Use `_make_request()` for HTTP calls (includes retry logic)
3. Log all requests and responses
4. Update `main.py` to call the new method

Example:
```python
def get_medication_reminder(self) -> Optional[Dict]:
    endpoint = f"/api/devices/{self.device_id}/reminder"
    response = self._make_request("GET", endpoint)
    if response:
        logger.info(f"Reminder received: {response}")
        return response
```

## References

- Device ID format: UUID v4 (RFC 4122)
- Date/Time format: ISO 8601 (RFC 3339)
- HTTP Status Codes: RFC 7231
