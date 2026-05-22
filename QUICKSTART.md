# Quick Start Guide - Backend Integration

## Prerequisites

1. Raspberry Pi 5 with GPIO pins configured
2. Python 3.7+
3. All hardware components connected (LCD, button, motor, buzzer, LED)
4. Backend server running and accessible

## Setup Steps

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment

```bash
# Copy example configuration
cp .env.example .env

# Edit .env with your backend URL
nano .env
```

Update `BACKEND_URL` to point to your backend:
```env
BACKEND_URL="https://your-backend-url.com"
DEVICE_CONFIG_PATH="./config/device_config.json"
```

### 3. Create Config Directory

```bash
mkdir -p config
chmod 755 config
```

### 4. Test Backend Connectivity

Before running the full application, test that your backend is accessible:

```bash
# Test if backend is reachable
curl http://your-backend-url.com/health

# You should receive a response from your backend
```

### 5. Run the Application

```bash
python main.py
```

## First Launch Behavior

On first launch:

1. Device generates a unique UUID
2. Saves device ID to `config/device_config.json`
3. Registers with backend
4. Displays pairing code on LCD: `PAIR DEVICE\n483921`
5. Polls backend until device is paired via mobile app
6. Once paired, displays `Device paired\nReady`

## Operational Workflows

### Normal Operation (Device Already Paired)

1. Application starts
2. Loads device ID from config
3. Checks pairing status
4. Displays `Device Ready`
5. Waits for button press or hold

### When Button is Pressed

- **Short Press:** Records medication intake and rotates motor
- **Long Press (3+ sec):** Triggers manual pairing workflow

### Background Tasks

- **Every 60 seconds:** Check if device is paired (when not paired)
- **Every 5 minutes:** Fetch medication schedule (when paired)

## LCD Display Messages

| Message | Meaning | Action |
|---------|---------|--------|
| `Starting up...` | Device initializing | Wait |
| `PAIR DEVICE\n483921` | Pairing code ready | Scan code or enter in app |
| `Device paired\nReady` | Device is paired | Normal operation ready |
| `Device not ready` | Device not initialized | Wait |
| `Not paired\nHold to pair` | Device not paired | Long press button |
| `Intake recorded\nTaken` | Medication intake recorded | Success |
| `Backend error\nRetry` | Backend unavailable | Will retry automatically |

## Monitoring Application Logs

The application logs all important events:

```bash
# Run and show logs
python main.py 2>&1 | tee app.log

# View logs in real-time
tail -f app.log
```

Look for these log lines:

```
Starting Medication Dispenser Application
Device ID: f47ac10b-58cc-4372-a567-0e02b2c3d479
Device registration successful
Displaying pair code: 483921
Device is paired!
Button pressed - recording medication intake...
Intake event posted successfully
```

## Troubleshooting

### Backend Not Connected

**Error:** `Connection error` in logs

**Solution:**
1. Verify `BACKEND_URL` in `.env`
2. Check network connectivity: `ping backend-url.com`
3. Ensure backend server is running
4. Check firewall rules

### Device Keeps Asking to Pair

**Cause:** Backend connection issues

**Solution:**
1. Check backend logs for errors
2. Verify backend is accepting POST to `/api/devices/register`
3. Test manually:
   ```bash
   curl -X POST http://your-backend/api/devices/register \
     -H "Content-Type: application/json" \
     -d '{"deviceId":"test-uuid"}'
   ```

### Device ID Regenerated After Reboot

**Cause:** Config file not being saved or permissions issue

**Solution:**
1. Check config directory permissions: `ls -la config/`
2. Verify write permissions: `touch config/test.txt`
3. Check logs for save errors
4. Manually verify `config/device_config.json` exists after first run

## Development Tips

### Testing with Mock Backend

If backend is not ready, you can create a simple mock in test script:

```python
from api import DeviceManager

# Test device initialization
dm = DeviceManager(backend_url="http://localhost:8000")
print(f"Device ID: {dm.device_id}")

# Test API calls (will fail if backend not running)
try:
    dm.register_device()
except:
    print("Backend not available")
```

### Checking Persistent Config

```bash
# View device config
cat config/device_config.json

# Expected output:
# {
#   "deviceId": "f47ac10b-58cc-4372-a567-0e02b2c3d479",
#   "isPaired": false
# }
```

## Next Steps

1. Deploy backend server
2. Configure DNS/URL for backend
3. Deploy application to Raspberry Pi
4. Pair device via mobile app
5. Test intake event recording
6. Monitor logs for any issues

## Support

For issues or questions:
1. Check BACKEND_INTEGRATION.md for detailed API documentation
2. Review application logs
3. Verify all hardware connections
4. Test individual components: `python test_*.py`
