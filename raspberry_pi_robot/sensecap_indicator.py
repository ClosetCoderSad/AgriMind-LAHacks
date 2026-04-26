import json
import time
from datetime import datetime

import config

try:
    import serial  # type: ignore
except ImportError:
    serial = None


class SenseCAPIndicator:
    def __init__(self) -> None:
        self.enabled = config.SENSECAP_ENABLED
        self.ser = None
        self.last_connect_attempt_ts = 0.0
        if not self.enabled:
            return
        if serial is None:
            print("pyserial not installed. SenseCAP output disabled.")
            self.enabled = False
            return
        self._connect()

    def _get_ports(self):
        ports = getattr(config, "SENSECAP_SERIAL_PORTS", ())
        # Backward compatibility with older config that used one port string.
        if not ports:
            single_port = getattr(config, "SENSECAP_SERIAL_PORT", None)
            ports = (single_port,) if single_port else ()
        return ports

    def _connect(self) -> bool:
        self.last_connect_attempt_ts = time.time()
        ports = self._get_ports()
        for port in ports:
            candidate_ser = None
            try:
                candidate_ser = serial.Serial(
                    port,
                    config.SENSECAP_BAUDRATE,
                    timeout=getattr(config, "SENSECAP_SERIAL_TIMEOUT_SECONDS", 1.0),
                    write_timeout=getattr(config, "SENSECAP_SERIAL_WRITE_TIMEOUT_SECONDS", 1.0),
                )
                print(f"SenseCAP connected on {port}")
                self.ser = candidate_ser
                return True
            except Exception as exc:
                if candidate_ser is not None and candidate_ser.is_open:
                    candidate_ser.close()
                print(f"SenseCAP open failed on {port}: {exc}")
                continue

        if self.ser is None:
            print("SenseCAP serial open failed on all configured ports.")
            return False
        return True

    def send_status(self, payload: dict) -> None:
        if not self.enabled:
            return
        if getattr(config, "SENSECAP_SIMPLE_PAYLOAD", False):
            message = {
                "t": payload.get("temperature_c"),
                "m": payload.get("moisture_pct"),
                "aq": payload.get("air_quality_index"),
                "l": payload.get("light_lux_est"),
            }
        else:
            message = {
                "ts": datetime.now().isoformat(),
                "type": "robot_status",
                "data": payload,
            }
        line = json.dumps(message) + "\n"
        if self.ser is None:
            cooldown = float(getattr(config, "SENSECAP_RECONNECT_COOLDOWN_SECONDS", 2.0))
            if time.time() - self.last_connect_attempt_ts < cooldown:
                return
            if not self._connect():
                return
        try:
            print("SenseCAP TX:", line.strip())
            self.ser.write(line.encode("utf-8"))
            self.ser.flush()
        except Exception as exc:
            print(f"SenseCAP write failed: {exc}. Reconnecting...")
            self.close()

    def close(self) -> None:
        if self.ser is not None and self.ser.is_open:
            self.ser.close()
        self.ser = None
