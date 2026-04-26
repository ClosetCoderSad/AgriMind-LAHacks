# Raspberry Pi Robot Code

This folder is standalone code for Raspberry Pi 4/5 robot control using:

- 2x TT DC motors via L298N
- Grove light, temperature, moisture, and air quality sensors
- Logitech USB camera
- SenseCAP Indicator (optional serial output)

Designed for beginner-friendly IDEs such as Thonny or Geany.

## Files

- `config.py`: all pins, channels, and calibration constants in one place
- `motors.py`: L298N motor control helpers
- `sensors.py`: sensor read + calibration logic
- `camera.py`: Logitech camera capture helpers
- `sensecap_indicator.py`: optional serial messaging
- `uploader.py`: sends sensor + image payload to supercomputer API
- `main.py`: run loop and demo behavior
- `pinout.txt`: wiring map for your hardware

## Install (on Pi)

```bash
sudo apt update
sudo apt install -y python3-pip python3-opencv
pip3 install RPi.GPIO pyserial requests
```

Optional for Grove Base HAT:

```bash
pip3 install grove.py
```

## Run

```bash
python3 main.py
```

Edit values in `config.py` to calibrate sensors and motor behavior.

## Send Data to Supercomputer

1. On supercomputer, run API:
   - `uvicorn agrimind.api:app --host 0.0.0.0 --port 8000`
2. On Pi, set in `config.py`:
   - `SUPERCOMPUTER_ANALYZE_UPLOAD_URL` to supercomputer IP (for example `http://192.168.1.50:8000/analyze_upload`)
   - `UPLOAD_ENABLED = True`
3. In `main.py`:
   - Auto-upload runs every `AUTO_CAPTURE_EVERY_N_LOOPS`
   - Manual upload command: `u`
