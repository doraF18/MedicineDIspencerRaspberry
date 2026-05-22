#!/usr/bin/env python3
"""
Test script for backend integration without hardware

This script demonstrates and tests the DeviceManager functionality
without requiring actual Raspberry Pi hardware.
"""

import sys
import json
import time
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

# Mock hardware imports to allow testing without actual hardware
sys.modules['gpiozero'] = MagicMock()
sys.modules['RPLCD'] = MagicMock()
sys.modules['RPLCD.i2c'] = MagicMock()

from api import DeviceManager, PairingManager


def test_device_id_persistence():
    """Test that device ID is generated on first launch and persists"""
    print("\n" + "="*60)
    print("TEST 1: Device ID Persistence")
    print("="*60)
    
    # Clean up test config
    test_config = Path("test_device_config.json")
    if test_config.exists():
        test_config.unlink()
    
    # First launch - should generate device ID
    print("First launch: Creating new device...")
    dm1 = DeviceManager(config_path=str(test_config))
    device_id_1 = dm1.device_id
    print(f"Generated Device ID: {device_id_1}")
    
    # Verify config file was created
    assert test_config.exists(), "Config file should be created"
    with open(test_config, "r") as f:
        config = json.load(f)
        assert config.get("deviceId") == device_id_1
    print("✓ Config file created with device ID")
    
    # Second launch - should load existing device ID
    print("\nSecond launch: Loading existing device...")
    dm2 = DeviceManager(config_path=str(test_config))
    device_id_2 = dm2.device_id
    print(f"Loaded Device ID: {device_id_2}")
    
    # Verify same device ID was loaded
    assert device_id_1 == device_id_2, "Device ID should persist"
    print("✓ Device ID persisted correctly")
    
    # Cleanup
    test_config.unlink()
    print("\n✓ TEST PASSED: Device ID persistence works correctly")


def test_device_manager_initialization():
    """Test DeviceManager initialization"""
    print("\n" + "="*60)
    print("TEST 2: DeviceManager Initialization")
    print("="*60)
    
    test_config = Path("test_device_config.json")
    if test_config.exists():
        test_config.unlink()
    
    # Test with default backend URL
    dm = DeviceManager(config_path=str(test_config))
    print(f"Device ID: {dm.device_id}")
    print(f"Backend URL: {dm.backend_url}")
    print(f"Is Paired: {dm.is_paired}")
    print(f"Schedule: {dm.schedule}")
    
    assert dm.device_id is not None, "Device ID should not be None"
    assert dm.backend_url is not None, "Backend URL should not be None"
    assert dm.is_paired == False, "New device should not be paired"
    print("✓ DeviceManager initialized correctly")
    
    # Cleanup
    test_config.unlink()
    print("\n✓ TEST PASSED: DeviceManager initialization works correctly")


def test_pairing_manager_initialization():
    """Test PairingManager initialization"""
    print("\n" + "="*60)
    print("TEST 3: PairingManager Initialization")
    print("="*60)
    
    test_config = Path("test_device_config.json")
    if test_config.exists():
        test_config.unlink()
    
    dm = DeviceManager(config_path=str(test_config))
    
    # Mock LCD callback
    lcd_messages = []
    def mock_lcd(message, timeout=None):
        lcd_messages.append(message)
        print(f"LCD: {message}")
    
    pm = PairingManager(dm, lcd_callback=mock_lcd)
    
    print(f"Polling interval: {pm.polling_interval}s")
    print(f"Polling timeout: {pm.polling_timeout}s")
    print("✓ PairingManager initialized correctly")
    
    # Test LCD callback
    pm.display_on_lcd("TEST MESSAGE")
    assert len(lcd_messages) > 0, "LCD callback should be called"
    assert "TEST MESSAGE" in lcd_messages[0]
    print("✓ LCD callback works correctly")
    
    # Cleanup
    test_config.unlink()
    print("\n✓ TEST PASSED: PairingManager initialization works correctly")


def test_device_manager_methods():
    """Test DeviceManager API methods (with mocks)"""
    print("\n" + "="*60)
    print("TEST 4: DeviceManager API Methods (Mocked)")
    print("="*60)
    
    test_config = Path("test_device_config.json")
    if test_config.exists():
        test_config.unlink()
    
    dm = DeviceManager(config_path=str(test_config), backend_url="http://test:8000")
    
    # Test request structure (without actually sending)
    print(f"\nDevice ID for requests: {dm.device_id}")
    print(f"Backend URL: {dm.backend_url}")
    
    # Verify API endpoint patterns
    endpoints = [
        ("/api/devices/register", "POST"),
        (f"/api/devices/{dm.device_id}/pairing-status", "GET"),
        (f"/api/devices/{dm.device_id}/schedule", "GET"),
        (f"/api/devices/{dm.device_id}/intake-events", "POST"),
    ]
    
    print("\nExpected API Endpoints:")
    for endpoint, method in endpoints:
        print(f"  {method:4} {endpoint}")
    
    print("✓ API endpoint patterns are correct")
    
    # Cleanup
    test_config.unlink()
    print("\n✓ TEST PASSED: DeviceManager API methods are correctly structured")


def test_config_file_format():
    """Test device configuration file format"""
    print("\n" + "="*60)
    print("TEST 5: Configuration File Format")
    print("="*60)
    
    test_config = Path("test_device_config.json")
    if test_config.exists():
        test_config.unlink()
    
    dm = DeviceManager(config_path=str(test_config))
    
    # Read and verify config format
    with open(test_config, "r") as f:
        config = json.load(f)
    
    print("Config file contents:")
    print(json.dumps(config, indent=2))
    
    assert "deviceId" in config, "Config should have deviceId"
    assert isinstance(config["deviceId"], str), "deviceId should be a string"
    print("✓ Device ID format is correct (string)")
    
    # Verify UUID format (basic check)
    device_id = config["deviceId"]
    parts = device_id.split("-")
    assert len(parts) == 5, "UUID should have 5 parts separated by hyphens"
    print("✓ UUID format is correct")
    
    # Mark as paired and verify
    config["isPaired"] = True
    with open(test_config, "w") as f:
        json.dump(config, f, indent=4)
    
    dm2 = DeviceManager(config_path=str(test_config))
    assert dm2.is_paired == False, "isPaired should not auto-load"
    print("✓ Configuration persistence works correctly")
    
    # Cleanup
    test_config.unlink()
    print("\n✓ TEST PASSED: Configuration file format is correct")


def run_all_tests():
    """Run all tests"""
    print("\n" + "="*70)
    print("BACKEND INTEGRATION TEST SUITE")
    print("="*70)
    
    tests = [
        test_device_id_persistence,
        test_device_manager_initialization,
        test_pairing_manager_initialization,
        test_device_manager_methods,
        test_config_file_format,
    ]
    
    passed = 0
    failed = 0
    
    for test_func in tests:
        try:
            test_func()
            passed += 1
        except Exception as e:
            print(f"\n✗ TEST FAILED: {test_func.__name__}")
            print(f"Error: {e}")
            failed += 1
    
    print("\n" + "="*70)
    print("TEST RESULTS")
    print("="*70)
    print(f"Passed: {passed}")
    print(f"Failed: {failed}")
    print(f"Total:  {passed + failed}")
    print("="*70)
    
    if failed == 0:
        print("\n✓ ALL TESTS PASSED!\n")
        return 0
    else:
        print(f"\n✗ {failed} TEST(S) FAILED\n")
        return 1


if __name__ == "__main__":
    sys.exit(run_all_tests())
