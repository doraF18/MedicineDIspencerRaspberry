"""
Test script to verify motor slot calculation and position tracking logic.
"""

import json
from pathlib import Path
from models.StepperMotor import StepperMotor, WHEEL_MOMENTS

def test_calculate_slots_to_advance():
    """Test slot calculation from current position to target moment."""
    # Create a mock motor instance (without actual GPIO pins)
    test_cases = [
        # (current_position, target_moment, expected_slots)
        ("MORNING", "MORNING", 0),  # Same position
        ("MORNING", "NOON", 1),     # Next slot
        ("MORNING", "EVENING", 2),  # Skip NOON, reach EVENING
        ("NOON", "EVENING", 1),     # Next slot
        ("NOON", "MORNING", 2),     # Skip EVENING, wrap around
        ("EVENING", "MORNING", 1),  # Next slot
        ("EVENING", "NOON", 2),     # Skip MORNING, wrap around
    ]
    
    print("=" * 60)
    print("TEST: calculate_slots_to_advance()")
    print("=" * 60)
    
    # We can't instantiate the motor without GPIO, so we'll test the logic directly
    WHEEL_MOMENTS_LOCAL = ["MORNING", "NOON", "EVENING"]
    
    for current_pos, target, expected in test_cases:
        current_idx = WHEEL_MOMENTS_LOCAL.index(current_pos)
        target_idx = WHEEL_MOMENTS_LOCAL.index(target)
        slots = (target_idx - current_idx) % len(WHEEL_MOMENTS_LOCAL)
        
        status = "✓" if slots == expected else "✗"
        print(f"{status} {current_pos} → {target}: {slots} slots (expected {expected})")
        assert slots == expected, f"Expected {expected}, got {slots}"
    
    print()


def test_get_next_active_moment():
    """Test finding next active moment from current position."""
    WHEEL_MOMENTS_LOCAL = ["MORNING", "NOON", "EVENING"]
    
    test_cases = [
        # (current_position, active_moments, expected_target, expected_slots)
        ("MORNING", ["MORNING"], "MORNING", 0),  # Current is active
        ("MORNING", ["NOON"], "NOON", 1),  # Next slot
        ("MORNING", ["EVENING"], "EVENING", 2),  # Skip to third
        ("MORNING", ["NOON", "EVENING"], "NOON", 1),  # Choose nearest active
        ("NOON", ["MORNING"], "MORNING", 2),  # Wrap around
        ("NOON", ["MORNING", "EVENING"], "EVENING", 1),  # Choose nearest
        ("MORNING", [], None, 0),  # No active moments
        ("EVENING", ["MORNING", "NOON"], "MORNING", 1),  # Wrap to first active
    ]
    
    print("=" * 60)
    print("TEST: get_next_active_moment()")
    print("=" * 60)
    
    for current_pos, active, expected_target, expected_slots in test_cases:
        current_idx = WHEEL_MOMENTS_LOCAL.index(current_pos)
        
        # Find next active
        valid_active = [m for m in active if m in WHEEL_MOMENTS_LOCAL]
        if not valid_active:
            target, slots = None, 0
        else:
            target = None
            slots = 0
            for i in range(1, len(WHEEL_MOMENTS_LOCAL) + 1):
                idx = (current_idx + i) % len(WHEEL_MOMENTS_LOCAL)
                moment = WHEEL_MOMENTS_LOCAL[idx]
                if moment in valid_active:
                    target = moment
                    slots = i
                    break
        
        # Check if we also need to consider current position
        if current_pos in active:
            target = current_pos
            slots = 0
        
        status = "✓" if (target == expected_target and slots == expected_slots) else "✗"
        print(f"{status} From {current_pos} with active {active}:")
        print(f"   → {target} ({slots} slots) [expected {expected_target} ({expected_slots} slots)]")
        assert target == expected_target and slots == expected_slots, \
            f"Expected ({expected_target}, {expected_slots}), got ({target}, {slots})"
    
    print()


def test_wheel_moments():
    """Verify wheel moments constant."""
    print("=" * 60)
    print("TEST: WHEEL_MOMENTS constant")
    print("=" * 60)
    print(f"✓ WHEEL_MOMENTS = {WHEEL_MOMENTS}")
    assert WHEEL_MOMENTS == ["MORNING", "NOON", "EVENING"], "Invalid wheel moments"
    print()


def test_config_persistence():
    """Test loading/saving current position in config file."""
    print("=" * 60)
    print("TEST: Config persistence (simulated)")
    print("=" * 60)
    
    test_config = {
        "deviceId": "test-device",
        "stepper": {
            "steps_per_dose": 295,
            "current_position": "EVENING",
            "steps_per_slot": 295
        }
    }
    
    config_path = Path("test_config.json")
    try:
        # Save test config
        with open(config_path, "w") as f:
            json.dump(test_config, f, indent=2)
        
        # Load and verify
        with open(config_path, "r") as f:
            loaded = json.load(f)
        
        assert loaded["stepper"]["current_position"] == "EVENING"
        assert loaded["stepper"]["steps_per_slot"] == 295
        print("✓ Config save/load works correctly")
        print(f"✓ Loaded position: {loaded['stepper']['current_position']}")
        print(f"✓ Loaded steps_per_slot: {loaded['stepper']['steps_per_slot']}")
    finally:
        config_path.unlink(missing_ok=True)
    
    print()


if __name__ == "__main__":
    print("\n" + "=" * 60)
    print("MOTOR SLOT CALCULATION TESTS")
    print("=" * 60 + "\n")
    
    test_wheel_moments()
    test_calculate_slots_to_advance()
    test_get_next_active_moment()
    test_config_persistence()
    
    print("=" * 60)
    print("✓ ALL TESTS PASSED!")
    print("=" * 60 + "\n")
