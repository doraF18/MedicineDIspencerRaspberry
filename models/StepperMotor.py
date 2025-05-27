from gpiozero import OutputDevice
from gpiozero.devices import Device
import time

class StepperMotor(Device):
    def __init__(self, pin1, pin2, pin3, pin4, steps_per_rev=2048, delay=0.01):
        super().__init__()
        self.pins = [
            OutputDevice(pin1),
            OutputDevice(pin2),
            OutputDevice(pin3),
            OutputDevice(pin4)
        ]
        self.steps_per_rev = steps_per_rev
        self.delay = delay

        # Half-step sequence for 28BYJ-48
        self.sequence = [
            [1, 0, 0, 1],
            [1, 0, 0, 0],
            [1, 1, 0, 0],
            [0, 1, 0, 0],
            [0, 1, 1, 0],
            [0, 0, 1, 0],
            [0, 0, 1, 1],
            [0, 0, 0, 1]
        ]

    def _set_step(self, step):
        for pin, value in zip(self.pins, step):
            pin.value = value

    def step(self, steps, direction=1):
        sequence = self.sequence if direction > 0 else self.sequence[::-1]
        for _ in range(steps):
            for step in sequence:
                self._set_step(step)
                time.sleep(self.delay)
        # self.release()

    def rotate(self, turns=1.0, direction=1):
        steps = int(self.steps_per_rev * turns)
        self.step(steps, direction)

    def half_turn(self, direction=1):
        self.rotate(0.5, direction)

    def release(self):
        for pin in self.pins:
            pin.off()

    def close(self):
        # self.release()
        for pin in self.pins:
            pin.close()
        super().close()
    
    def test(self):
        print("Testing stepper...")
        start_time = time.time()

        while time.time() - start_time < 10:
            for step in self.sequence:
                for p in range(4):
                    self.pins[p].value = step[p]
                time.sleep(self.delay)

        print("Stepper has been tested...")
