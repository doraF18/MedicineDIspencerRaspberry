"""
Device Manager for Raspberry Pi Dispenser Backend Integration

Handles:
- Persistent device identity (UUID)
- Device registration with backend
- Pairing status polling
- Medication schedule fetching
- Intake event reporting
- Retry logic for network failures
"""

import os
import json
import uuid
import logging
import time
import requests
from pathlib import Path
from typing import Optional, Dict, Any
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class DeviceManager:
    """Manages device identity and backend API communication"""

    def __init__(self, config_path: str = "device_config.json", backend_url: Optional[str] = None):
        """
        Initialize DeviceManager

        Args:
            config_path: Path to device configuration file
            backend_url: Backend API base URL (defaults to env var BACKEND_URL)
        """
        self.config_path = Path(config_path)
        self.backend_url = backend_url or os.getenv("BACKEND_URL", "http://10.195.30.69:8080")
        self.device_id = self._get_or_create_device_id()
        self.pair_code = None
        self.is_paired = False
        self.schedule = None
        
        logger.info(f"Device Manager initialized with device_id: {self.device_id}")

    def _get_or_create_device_id(self) -> str:
        """
        Load existing device ID or create a new one on first launch

        Returns:
            Device ID (UUID)
        """
        if self.config_path.exists():
            try:
                with open(self.config_path, "r") as f:
                    config = json.load(f)
                    device_id = config.get("deviceId")
                    if device_id:
                        logger.info("Loaded existing device ID from config")
                        return device_id
            except Exception as e:
                logger.error(f"Error reading config file: {e}")

        # Generate new device ID on first launch
        new_id = str(uuid.uuid4())
        self._save_config({"deviceId": new_id})
        logger.info(f"Generated new device ID: {new_id}")
        return new_id

    def _save_config(self, config: Dict[str, Any]):
        """Save configuration to device_config.json"""
        try:
            self.config_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.config_path, "w") as f:
                json.dump(config, f, indent=4)
            logger.debug(f"Saved config to {self.config_path}")
        except Exception as e:
            logger.error(f"Error saving config: {e}")

    def _make_request(
        self,
        method: str,
        endpoint: str,
        json_data: Optional[Dict] = None,
        max_retries: int = 3,
        retry_delay: int = 2
    ) -> Optional[Dict]:
        """
        Make HTTP request with retry logic

        Args:
            method: HTTP method (GET, POST, PUT, etc.)
            endpoint: API endpoint path
            json_data: JSON body data
            max_retries: Maximum number of retry attempts
            retry_delay: Delay between retries in seconds

        Returns:
            Response JSON or None if failed
        """
        url = f"{self.backend_url}{endpoint}"
        
        for attempt in range(max_retries):
            try:
                logger.debug(f"[Attempt {attempt + 1}/{max_retries}] {method} {url}")
                
                if method.upper() == "GET":
                    response = requests.get(url, timeout=10)
                elif method.upper() == "POST":
                    response = requests.post(url, json=json_data, timeout=10)
                elif method.upper() == "PUT":
                    response = requests.put(url, json=json_data, timeout=10)
                else:
                    raise ValueError(f"Unsupported HTTP method: {method}")

                logger.info(f"{method} {url} - Status: {response.status_code}")

                if response.status_code in [200, 201]:
                    logger.debug(f"Response: {response.text}")
                    return response.json()
                else:
                    logger.warning(
                        f"Error {response.status_code}: {response.text}"
                    )
                    if response.status_code >= 500:
                        # Server error, retry
                        if attempt < max_retries - 1:
                            logger.info(f"Server error, retrying in {retry_delay}s...")
                            time.sleep(retry_delay)
                        continue
                    else:
                        # Client error, don't retry
                        return None

            except requests.exceptions.Timeout:
                logger.warning("Request timeout")
                if attempt < max_retries - 1:
                    logger.info(f"Timeout, retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                continue
            except requests.exceptions.ConnectionError:
                logger.warning("Connection error")
                if attempt < max_retries - 1:
                    logger.info(f"Connection error, retrying in {retry_delay}s...")
                    time.sleep(retry_delay)
                continue
            except Exception as e:
                logger.error(f"Request failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                continue

        logger.error(f"Failed after {max_retries} attempts: {method} {url}")
        return None

    def register_device(self) -> bool:
        """
        Register device with backend

        Returns:
            True if successful, False otherwise
        """
        logger.info("Registering device...")
        
        endpoint = "/api/devices/register"
        payload = {"deviceId": self.device_id}

        response = self._make_request("POST", endpoint, json_data=payload)
        
        if response:
            # Parse pair code and pairing status from response
            self.pair_code = response.get("pairCode")
            self.is_paired = response.get("paired", False)
            
            logger.info(f"Device registration successful")
            logger.info(f"Received pair code: {self.pair_code}")
            
            # Save pair code to config if not already paired
            if not self.is_paired:
                try:
                    config = {"deviceId": self.device_id}
                    if self.pair_code:
                        config["pairCode"] = self.pair_code
                    self._save_config(config)
                except Exception as e:
                    logger.error(f"Error saving pair code to config: {e}")
            
            return True
        else:
            logger.error("Device registration failed")
            return False

    def get_pairing_status(self) -> bool:
        """
        Poll pairing status from backend

        Returns:
            True if device is paired, False otherwise
        """
        endpoint = f"/api/devices/{self.device_id}/pairing-status"
        
        response = self._make_request("GET", endpoint)
        
        if response and "paired" in response:
            self.is_paired = response.get("paired", False)
            
            # Only update pair_code if it's in the response (don't overwrite with None)
            if "pairCode" in response:
                self.pair_code = response.get("pairCode")
                # Save pair code to config if received and not paired
                if self.pair_code and not self.is_paired:
                    try:
                        config = {"deviceId": self.device_id, "pairCode": self.pair_code}
                        self._save_config(config)
                    except Exception as e:
                        logger.error(f"Error saving pair code to config: {e}")
            
            if self.is_paired:
                logger.info("Device is paired!")
            else:
                logger.info(f"Device not paired. Pair code: {self.pair_code}")
            
            return self.is_paired
        else:
            logger.warning("Failed to get pairing status")
            return False

    def get_schedule(self) -> Optional[Dict]:
        """
        Fetch medication schedule from backend

        Returns:
            Schedule data or None if failed
        """
        if not self.is_paired:
            logger.warning("Device not paired, cannot fetch schedule")
            return None

        endpoint = f"/api/devices/{self.device_id}/schedule"
        
        response = self._make_request("GET", endpoint)
        
        if response:
            self.schedule = response
            logger.info(f"Schedule fetched: {response}")
            return response
        else:
            logger.warning("Failed to fetch schedule")
            return None

    def _parse_backend_datetime(self, value: Any) -> Optional[datetime]:
        """Parse backend datetime strings that may or may not include a timezone."""
        if not value:
            return None

        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"

        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    def _extract_response_record(self, data: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(data, dict):
            return None

        record = data.get("record")
        if isinstance(record, dict):
            return record

        records = data.get("records")
        if isinstance(records, list) and records:
            first_record = records[0]
            if isinstance(first_record, dict):
                return first_record

        return None

    def _extract_duplicate_moment(
        self,
        response_status: int,
        data: Any,
        response_text: str,
        request_actual_time: str,
    ) -> Optional[str]:
        """Detect duplicate intake responses from several backend response shapes."""
        if not isinstance(data, dict):
            return None

        normalized_text = f"{response_text} {data.get('message', '')} {data.get('status', '')}".lower()
        duplicate_flag = any(
            bool(data.get(key))
            for key in (
                "duplicate",
                "isDuplicate",
                "alreadyTaken",
                "already_taken",
                "alreadyRecorded",
                "already_recorded",
            )
        )

        if "already taken" in normalized_text or "already recorded" in normalized_text or "duplicate" in normalized_text:
            duplicate_flag = True

        if response_status == 200 and (
            isinstance(data.get("record"), dict)
            or isinstance(data.get("existingRecord"), dict)
            or data.get("matchedMoment")
            or data.get("moment")
        ):
            duplicate_flag = True

        response_record = self._extract_response_record(data)
        request_time = self._parse_backend_datetime(request_actual_time)
        response_time = None

        if isinstance(response_record, dict):
            response_time = self._parse_backend_datetime(
                response_record.get("actualIntakeTime")
                or response_record.get("takenAt")
                or response_record.get("createdAt")
            )

            response_status_text = str(response_record.get("status", "")).upper()
            if response_status_text in {"MISSED", "OVERDUE", "SKIPPED"}:
                duplicate_flag = True

        if (
            response_status == 201
            and request_time is not None
            and response_time is not None
            and abs((response_time - request_time).total_seconds()) > 2
        ):
            duplicate_flag = True

        if not duplicate_flag:
            return None

        candidate_moment = data.get("matchedMoment") or data.get("moment")

        if isinstance(response_record, dict):
            candidate_moment = candidate_moment or response_record.get("matchedMoment") or response_record.get("moment")

            if candidate_moment is None and response_record.get("status"):
                candidate_moment = str(response_record.get("status")).upper()

        existing_record = data.get("existingRecord")
        if isinstance(existing_record, dict):
            candidate_moment = candidate_moment or existing_record.get("matchedMoment") or existing_record.get("moment")

        return candidate_moment

    def post_intake_event(self, source: str = "BUTTON") -> dict:
        """
        Post medication intake event to backend.

        Returns:
            Dict with keys:
              - success: bool (True if accepted by backend)
              - duplicate: bool (True if already recorded)
              - matchedMoment: Optional[str] (e.g. 'MORNING','NOON','EVENING')
              - message: str
              - response: dict (backend JSON response, if any)
        """
        if not self.is_paired:
            logger.warning("Device not paired, cannot post intake event")
            return {"success": False, "duplicate": False, "matchedMoment": None, "message": "Device not paired", "response": None}

        url = f"{self.backend_url}/api/devices/{self.device_id}/intake-events"
        payload = {
            "actualIntakeTime": datetime.now().isoformat(timespec="seconds"),
            "source": source,
        }

        try:
            logger.info(f"Sending intake event: {payload}")
            response = requests.post(url, json=payload, timeout=10)
            logger.info(f"Intake event response: {response.status_code}")
            # Log response body as requested
            try:
                logger.info(response.text)
            except Exception:
                logger.debug("Could not log response text")

            try:
                data = response.json()
            except Exception:
                data = None

            duplicate_moment = self._extract_duplicate_moment(
                response.status_code,
                data,
                response.text,
                payload["actualIntakeTime"],
            )
            if duplicate_moment is not None:
                return {
                    "success": True,
                    "duplicate": True,
                    "moment": duplicate_moment,
                    "response": data,
                }

            # If 201 Created -> new intake
            if response.status_code == 201:
                return {"success": True, "duplicate": False, "response": data}

            # Other success cases
            if response.status_code in (200, 201):
                return {"success": True, "duplicate": False, "response": data}

            # Non-success
            return {"success": False, "duplicate": False, "moment": None, "message": f"Backend error (HTTP {response.status_code})", "response": data}

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to post intake event: {e}")
            return {"success": False, "duplicate": False, "matchedMoment": None, "message": f"Network error: {str(e)}", "response": None}



class PairingManager:
    """Handles pairing workflow with LCD display"""

    def __init__(self, device_manager: DeviceManager, lcd_callback=None):
        """
        Initialize PairingManager

        Args:
            device_manager: DeviceManager instance
            lcd_callback: Callback function for LCD display (printToLCD)
        """
        self.device_manager = device_manager
        self.lcd_callback = lcd_callback or self._default_lcd_callback
        self.polling_interval = 3  # seconds
        self.polling_timeout = 300  # 5 minutes

    def _default_lcd_callback(self, message: str, timeout: Optional[int] = None):
        """Default LCD callback (prints to console)"""
        print(f"LCD: {message}")

    def display_on_lcd(self, message: str, timeout: Optional[int] = None):
        """Display message on LCD"""
        self.lcd_callback(message, timeout)

    def start_pairing(self) -> bool:
        """
        Start device pairing workflow

        Returns:
            True if paired successfully, False otherwise
        """
        logger.info("Starting pairing workflow...")
        self.display_on_lcd("Registering...", timeout=2)

        # Step 1: Register device and get pair code
        if not self.device_manager.register_device():
            self.display_on_lcd("Registration\nFailed", timeout=3)
            return False

        # If already paired during registration, return immediately
        if self.device_manager.is_paired:
            logger.info("Device already paired after registration!")
            self.display_on_lcd("Device paired\nReady", timeout=3)
            return True

        # Step 2: Display pairing code (from registration response)
        if self.device_manager.pair_code:
            message = f"PAIR DEVICE\n{self.device_manager.pair_code}"
            self.display_on_lcd(message)
            logger.info(f"Displaying pair code: {self.device_manager.pair_code}")
        else:
            self.display_on_lcd("No pair code\nreceived", timeout=3)
            logger.error("No pair code received from registration")
            return False

        # Step 3: Poll pairing status until paired or timeout
        logger.info(f"Polling pairing status for {self.polling_timeout}s...")
        start_time = time.time()
        while time.time() - start_time < self.polling_timeout:
            time.sleep(self.polling_interval)

            # Check pairing status (this will only update paired status, not pair_code)
            if self.device_manager.get_pairing_status():
                logger.info("Device successfully paired!")
                self.display_on_lcd("Device paired\nReady", timeout=3)
                return True

        logger.warning("Pairing timeout")
        self.display_on_lcd("Pairing timeout\nTry again", timeout=3)
        return False

    def check_and_complete_pairing(self) -> bool:
        """
        Check pairing status and complete if needed

        Returns:
            True if device is paired, False otherwise
        """
        if self.device_manager.is_paired:
            return True

        # Try to load existing configuration
        try:
            with open(self.device_manager.config_path, "r") as f:
                config = json.load(f)
                if config.get("isPaired"):
                    self.device_manager.is_paired = True
                    return True
        except:
            pass

        # Not paired, start pairing workflow
        return self.start_pairing()
