"""
Central configuration for Raspberry Pi robot.
Edit this file for pin changes, calibration, and tuning.
"""

# -----------------------------
# Motor pins (BCM numbering)
# L298N connections:
# ENA, IN1, IN2 => left motor
# ENB, IN3, IN4 => right motor
# -----------------------------
MOTOR_ENA_PIN = 18
MOTOR_IN1_PIN = 17
MOTOR_IN2_PIN = 27

MOTOR_ENB_PIN = 13
MOTOR_IN3_PIN = 23
MOTOR_IN4_PIN = 24

PWM_FREQUENCY = 1000

# Motor tuning (0 to 100)
LEFT_MOTOR_BASE_SPEED = 55
RIGHT_MOTOR_BASE_SPEED = 55

# Adjust to compensate mechanical mismatch between motors.
LEFT_MOTOR_TRIM = 0
RIGHT_MOTOR_TRIM = 0
# Many TT motors will not start reliably below this duty cycle.
# Keep at 0 to disable this behavior.
MOTOR_MIN_EFFECTIVE_DUTY = 65
# Briefly apply a stronger duty to break static friction at startup.
MOTOR_START_BOOST_DUTY = 90
MOTOR_START_BOOST_SECONDS = 0.12

# -----------------------------
# Grove sensor channels
# Using Grove analog channels:
# A0=0, A1=1, A2=2, A3=3
# -----------------------------
LIGHT_CHANNEL = 0
TEMPERATURE_CHANNEL = 1
MOISTURE_CHANNEL = 2
AIR_QUALITY_CHANNEL = 3

# -----------------------------
# Sensor calibration
# -----------------------------
# Light scaling (depends on sensor board and ADC range)
LIGHT_GAIN = 1.0
LIGHT_OFFSET = 0.0

# Temperature thermistor constants
TEMP_BETA = 4275.0
TEMP_R0 = 100000.0
TEMP_ADC_MAX = 1023.0
TEMP_OFFSET_C = 0.0

# Moisture mapping (raw ADC -> percent)
# Set after calibration:
# - MOISTURE_RAW_DRY: reading in dry air
# - MOISTURE_RAW_WET: reading in water-soaked soil
MOISTURE_RAW_DRY = 800.0
MOISTURE_RAW_WET = 350.0
MOISTURE_OFFSET_PCT = 0.0

# Air quality normalization
AIR_RAW_CLEAN = 200.0
AIR_RAW_POLLUTED = 700.0
AIR_QUALITY_OFFSET = 0.0

# -----------------------------
# Demo sensor overrides
# -----------------------------
# Set these to True for hackathon demos when sensors are unstable.
USE_DEMO_MOISTURE_VALUE = True
DEMO_MOISTURE_PCT = 34.0

USE_DEMO_AIR_QUALITY_VALUE = True
DEMO_AIR_QUALITY_INDEX = 78.0

# -----------------------------
# Camera
# -----------------------------
CAMERA_INDEX = 0
# If CAMERA_INDEX fails, try these indices in order.
CAMERA_INDEX_FALLBACKS = (1, 2, 3, 4, 5)
CAPTURE_WIDTH = 1280
CAPTURE_HEIGHT = 720
CAPTURE_DIR = "captures"

# -----------------------------
# SenseCAP Indicator (optional)
# -----------------------------
SENSECAP_ENABLED = True
# Serial ports tried in order. Prefer USB first for SenseCAP Indicator.
SENSECAP_SERIAL_PORTS = (
    "/dev/ttyACM0",
    "/dev/ttyUSB0",
    "/dev/serial0",
    "/dev/ttyAMA0",
    "/dev/ttyS0",
)
SENSECAP_BAUDRATE = 115200
SENSECAP_SERIAL_TIMEOUT_SECONDS = 1.0
SENSECAP_SERIAL_WRITE_TIMEOUT_SECONDS = 1.0
# If send fails, retry by reconnecting after this many seconds.
SENSECAP_RECONNECT_COOLDOWN_SECONDS = 2.0
# Use compact payload by default for easier Indicator-side parsing.
SENSECAP_SIMPLE_PAYLOAD = True

# -----------------------------
# App behavior
# -----------------------------
LOOP_INTERVAL_SECONDS = 2.0
AUTO_CAPTURE_EVERY_N_LOOPS = 10

# -----------------------------
# Supercomputer upload settings
# -----------------------------
UPLOAD_ENABLED = True
SUPERCOMPUTER_ANALYZE_UPLOAD_URL = "http://<SUPERCOMPUTER_IP>:8000/analyze_upload"
DEVICE_ID = "pi-robot-01"
# Demo presets:
# - Diseased sample flow: use tomato images -> set CROP_TYPE = "tomato"
# - Healthy sample flow: use corn images -> set CROP_TYPE = "corn"
CROP_TYPE = "tomato"
GPS_OR_ROW_ID = "row-7"
UPLOAD_TIMEOUT_SECONDS = 45
