#!/usr/bin/env python3
"""
Motor control for L298N dual H-bridge using Raspberry Pi GPIO (BCM pins).

Compatible interface for rover stack:
forward, reverse/backward, turn_left, turn_right, stop, read_wheel_ticks.
"""

from __future__ import annotations

import atexit
import time

import config

try:
    import RPi.GPIO as GPIO

    GPIO_AVAILABLE = True
except Exception:
    GPIO_AVAILABLE = False
    GPIO = None
    print("Warning: RPi.GPIO not available. Motor control running in simulation mode.")


class MotorController:
    """Controls left/right motor channels through an L298N."""

    STATE_IDLE = "idle"
    STATE_FORWARD = "forward"
    STATE_REVERSE = "reverse"
    STATE_TURN_RIGHT = "turn_right"
    STATE_TURN_LEFT = "turn_left"
    STATE_STOP = "stop"

    SPEED_FULL = 100
    SPEED_HIGH = 75
    SPEED_MEDIUM = 50
    SPEED_LOW = 25

    def __init__(
        self,
        left_in1=config.MOTOR_IN1_PIN,
        left_in2=config.MOTOR_IN2_PIN,
        left_en=config.MOTOR_ENA_PIN,
        right_in1=config.MOTOR_IN3_PIN,
        right_in2=config.MOTOR_IN4_PIN,
        right_en=config.MOTOR_ENB_PIN,
        pwm_hz=config.PWM_FREQUENCY,
        use_pwm=True,
        left_invert=False,
        right_invert=False,
    ):
        self.left_in1 = int(left_in1)
        self.left_in2 = int(left_in2)
        self.left_en = int(left_en)
        self.right_in1 = int(right_in1)
        self.right_in2 = int(right_in2)
        self.right_en = int(right_en)
        self.pwm_hz = max(50, int(pwm_hz))
        self.use_pwm = bool(getattr(config, "L298N_USE_PWM", use_pwm))
        self.left_invert = bool(getattr(config, "L298N_LEFT_INVERT", left_invert))
        self.right_invert = bool(getattr(config, "L298N_RIGHT_INVERT", right_invert))

        self.current_state = self.STATE_STOP
        self.current_speed = self._clamp_speed(getattr(config, "LEFT_MOTOR_BASE_SPEED", 60))
        self._warned_no_encoder = False
        self._gpio_ready = False
        self._pwm_left = None
        self._pwm_right = None

        if GPIO_AVAILABLE:
            try:
                GPIO.setwarnings(False)
                GPIO.setmode(GPIO.BCM)

                for pin in (
                    self.left_in1,
                    self.left_in2,
                    self.left_en,
                    self.right_in1,
                    self.right_in2,
                    self.right_en,
                ):
                    GPIO.setup(pin, GPIO.OUT, initial=GPIO.LOW)

                if self.use_pwm:
                    self._pwm_left = GPIO.PWM(self.left_en, self.pwm_hz)
                    self._pwm_right = GPIO.PWM(self.right_en, self.pwm_hz)
                    self._pwm_left.start(0)
                    self._pwm_right.start(0)
                else:
                    GPIO.output(self.left_en, GPIO.HIGH)
                    GPIO.output(self.right_en, GPIO.HIGH)

                self._gpio_ready = True
                print("L298N GPIO initialized (BCM mode).")
            except Exception as exc:
                print(f"Failed to initialize GPIO for L298N: {exc}")
                self._gpio_ready = False
        else:
            print("RPi.GPIO unavailable - simulation mode")

        self.stop()
        atexit.register(self.cleanup)

    @staticmethod
    def _clamp_speed(speed_percent) -> int:
        return max(0, min(100, int(speed_percent)))

    def _effective_duty(self, duty_percent: int) -> int:
        duty = self._clamp_speed(duty_percent)
        min_duty = self._clamp_speed(getattr(config, "MOTOR_MIN_EFFECTIVE_DUTY", 0))
        if 0 < duty < min_duty:
            return min_duty
        return duty

    def _set_enable_duty(self, left_duty: int, right_duty: int):
        left = self._effective_duty(left_duty)
        right = self._effective_duty(right_duty)
        if not self._gpio_ready:
            return
        if self.use_pwm:
            self._pwm_left.ChangeDutyCycle(left)
            self._pwm_right.ChangeDutyCycle(right)
        else:
            GPIO.output(self.left_en, GPIO.HIGH if left > 0 else GPIO.LOW)
            GPIO.output(self.right_en, GPIO.HIGH if right > 0 else GPIO.LOW)

    def _apply_side(self, is_left: bool, forward: bool, duty: int):
        if not self._gpio_ready:
            side = "LEFT" if is_left else "RIGHT"
            direction = "FWD" if forward else "REV"
            print(f"[SIM] {side} {direction} duty={self._effective_duty(duty)}")
            return

        if is_left:
            in1, in2 = self.left_in1, self.left_in2
            invert = self.left_invert
        else:
            in1, in2 = self.right_in1, self.right_in2
            invert = self.right_invert

        duty = self._effective_duty(duty)
        if duty <= 0:
            GPIO.output(in1, GPIO.LOW)
            GPIO.output(in2, GPIO.LOW)
            return

        logical_forward = not forward if invert else forward
        if logical_forward:
            GPIO.output(in1, GPIO.HIGH)
            GPIO.output(in2, GPIO.LOW)
        else:
            GPIO.output(in1, GPIO.LOW)
            GPIO.output(in2, GPIO.HIGH)

    def _startup_boost(self, left_speed: int, right_speed: int):
        boost_seconds = float(getattr(config, "MOTOR_START_BOOST_SECONDS", 0.0))
        boost_duty = self._clamp_speed(getattr(config, "MOTOR_START_BOOST_DUTY", 100))
        if boost_seconds <= 0.0:
            return
        self._set_enable_duty(max(left_speed, boost_duty), max(right_speed, boost_duty))
        time.sleep(boost_seconds)

    def _drive(self, left_forward: bool, right_forward: bool, speed_percent, state_name: str, sim_label: str):
        speed = self._clamp_speed(speed_percent if speed_percent is not None else self.current_speed)
        if speed <= 0:
            self.stop()
            return

        if not self._gpio_ready:
            print(f"[SIM] {sim_label} speed={speed}%")

        self._apply_side(True, left_forward, speed)
        self._apply_side(False, right_forward, speed)
        self._startup_boost(speed, speed)
        self._set_enable_duty(speed, speed)
        self.current_state = state_name
        self.current_speed = speed

    def stop(self):
        if self._gpio_ready:
            GPIO.output(self.left_in1, GPIO.LOW)
            GPIO.output(self.left_in2, GPIO.LOW)
            GPIO.output(self.right_in1, GPIO.LOW)
            GPIO.output(self.right_in2, GPIO.LOW)
            self._set_enable_duty(0, 0)
        else:
            print("[SIM] stop")
        self.current_state = self.STATE_STOP

    def idle(self):
        self.stop()
        self.current_state = self.STATE_IDLE

    def forward(self, speed_percent=None):
        self._drive(True, True, speed_percent, self.STATE_FORWARD, "forward")

    def reverse(self, speed_percent=None):
        self._drive(False, False, speed_percent, self.STATE_REVERSE, "reverse")

    # Backward alias for compatibility with existing main.py
    def backward(self, speed_percent=None):
        self.reverse(speed_percent)

    def turn_right(self, speed_percent=None):
        self._drive(True, False, speed_percent, self.STATE_TURN_RIGHT, "turn_right")

    def turn_left(self, speed_percent=None):
        self._drive(False, True, speed_percent, self.STATE_TURN_LEFT, "turn_left")

    def slow_down(self, target_speed_percent):
        self.set_speed(target_speed_percent)

        if self.current_state == self.STATE_FORWARD:
            self.forward()
        elif self.current_state == self.STATE_REVERSE:
            self.reverse()
        elif self.current_state == self.STATE_TURN_RIGHT:
            self.turn_right()
        elif self.current_state == self.STATE_TURN_LEFT:
            self.turn_left()

    def set_speed(self, speed_percent):
        self.current_speed = self._clamp_speed(speed_percent)

    def get_state(self):
        return self.current_state

    def get_speed(self):
        return self.current_speed

    def read_wheel_ticks(self):
        """
        L298N does not include encoder feedback.
        Return (0, 0) so pose code can use time-mode fallback.
        """
        if not self._warned_no_encoder:
            print("read_wheel_ticks(): no encoder interface on L298N backend; returning (0, 0).")
            self._warned_no_encoder = True
        return (0, 0)

    def demo_motion(self):
        self.forward(self.SPEED_MEDIUM)
        time.sleep(1.0)
        self.turn_left(self.SPEED_LOW)
        time.sleep(0.7)
        self.turn_right(self.SPEED_LOW)
        time.sleep(0.7)
        self.reverse(self.SPEED_MEDIUM)
        time.sleep(1.0)
        self.stop()

    def cleanup(self):
        try:
            self.stop()
        except Exception:
            pass

        if self._gpio_ready:
            try:
                if self._pwm_left is not None:
                    self._pwm_left.stop()
                if self._pwm_right is not None:
                    self._pwm_right.stop()
                GPIO.cleanup(
                    [
                        self.left_in1,
                        self.left_in2,
                        self.left_en,
                        self.right_in1,
                        self.right_in2,
                        self.right_en,
                    ]
                )
            except Exception:
                pass

        self._gpio_ready = False
