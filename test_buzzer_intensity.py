"""
Buzzer Intensity Test
Run this script to audition different buzzer volumes and pick the one you prefer.
"""

import time
import subprocess
from gpiozero import PWMOutputDevice
from hardware_common import BUZZER_PIN

# Kill any process holding /dev/gpiochip0 (main.py, other test scripts, etc.)
result = subprocess.run(["lsof", "-t", "/dev/gpiochip0"], capture_output=True, text=True)
for pid in result.stdout.strip().splitlines():
    subprocess.run(["kill", "-9", pid.strip()], capture_output=True)
subprocess.run(["pkill", "-9", "-f", "main.py"], capture_output=True)
time.sleep(2.0)  # give kernel time to release all pins

LEVELS = [
    # (label, frequency_hz, duty_cycle, duration_seconds)
    ("Level 1 - Quiet   (freq=1000, duty=0.3)", 1000, 0.3, 1.5),
    ("Level 2 - Medium  (freq=2000, duty=0.5)", 2000, 0.5, 1.5),
    ("Level 3 - Loud    (freq=2000, duty=0.8)", 2000, 0.8, 1.5),
    ("Level 4 - Louder  (freq=2500, duty=0.9)", 2500, 0.9, 1.5),
    ("Level 5 - Maximum (freq=3000, duty=1.0)", 3000, 1.0, 1.5),
]

def test_buzzer():
    buzzer = PWMOutputDevice(BUZZER_PIN, frequency=2000, initial_value=0)

    try:
        for label, freq, duty, duration in LEVELS:
            print(f"\nPlaying: {label}")
            buzzer.frequency = freq
            buzzer.value = duty
            time.sleep(duration)
            buzzer.off()
            time.sleep(0.5)  # pause between levels

        print("\n--- Test complete ---")
        print("Which level did you prefer? (1-5)")
    finally:
        buzzer.off()
        buzzer.close()

if __name__ == "__main__":
    test_buzzer()
