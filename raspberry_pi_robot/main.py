import json
import time
from datetime import datetime

import config
from camera import CameraCapture
from sensors import SensorSuite
from uploader import SupercomputerUploader


def print_help() -> None:
    print("\nCommands:")
    print("  c  -> capture image")
    print("  u  -> capture + upload to supercomputer")
    print("  q  -> quit")


def main() -> None:
    sensors = SensorSuite()
    camera = None
    try:
        camera = CameraCapture()
    except RuntimeError as exc:
        print(f"Camera disabled: {exc}")
    uploader = SupercomputerUploader()

    loop_count = 0
    print("Robot controller started.")
    print_help()

    try:
        while True:
            loop_count += 1
            sensor_data = sensors.read_all()
            sensor_data["timestamp"] = datetime.now().isoformat()
            print("Sensors:", json.dumps(sensor_data))

            if camera is not None and loop_count % config.AUTO_CAPTURE_EVERY_N_LOOPS == 0:
                img_path = camera.snap(prefix="auto")
                print(f"Auto capture saved: {img_path}")
                if config.UPLOAD_ENABLED:
                    try:
                        result = uploader.send_capture(img_path, sensor_data)
                        print("Upload response:", json.dumps(result))
                    except Exception as exc:
                        print(f"Upload failed: {exc}")

            cmd = input("Enter command (c/u/q or Enter to continue): ").strip().lower()
            if cmd == "c":
                if camera is None:
                    print("Capture skipped: camera not available.")
                else:
                    img_path = camera.snap(prefix="manual")
                    print(f"Manual capture saved: {img_path}")
            elif cmd == "u":
                if camera is None:
                    print("Upload skipped: camera not available.")
                else:
                    img_path = camera.snap(prefix="upload")
                    print(f"Upload capture saved: {img_path}")
                    try:
                        result = uploader.send_capture(img_path, sensor_data)
                        print("Upload response:", json.dumps(result))
                    except Exception as exc:
                        print(f"Upload failed: {exc}")
            elif cmd == "q":
                break

            time.sleep(config.LOOP_INTERVAL_SECONDS)
    except KeyboardInterrupt:
        print("\nStopping robot...")
    finally:
        if camera is not None:
            camera.close()
        print("Clean shutdown done.")


if __name__ == "__main__":
    main()
