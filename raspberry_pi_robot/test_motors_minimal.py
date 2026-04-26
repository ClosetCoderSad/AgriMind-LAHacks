#!/usr/bin/env python3
"""
Minimal standalone motor test (separate from main.py).

Usage:
  python3 test_motors_minimal.py
"""

import time

from motors import MotorController


def run_test() -> None:
    m = MotorController()
    try:
        print("Forward (70%) for 2s")
        m.forward(70)
        time.sleep(2)

        print("Stop for 1s")
        m.stop()
        time.sleep(1)

        print("Reverse (70%) for 2s")
        m.reverse(70)
        time.sleep(2)

        print("Stop for 1s")
        m.stop()
        time.sleep(1)

        print("Turn left (60%) for 1.5s")
        m.turn_left(60)
        time.sleep(1.5)

        print("Stop for 1s")
        m.stop()
        time.sleep(1)

        print("Turn right (60%) for 1.5s")
        m.turn_right(60)
        time.sleep(1.5)

        print("Final stop")
        m.stop()
        print("Motor minimal test complete.")
    finally:
        m.cleanup()


if __name__ == "__main__":
    run_test()
