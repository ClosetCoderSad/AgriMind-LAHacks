from datetime import datetime
from pathlib import Path

import cv2

import config


class CameraCapture:
    def __init__(self) -> None:
        self.out_dir = Path(config.CAPTURE_DIR)
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.capture = None
        camera_indexes = [config.CAMERA_INDEX, *getattr(config, "CAMERA_INDEX_FALLBACKS", ())]
        tried = []
        for index in camera_indexes:
            if index in tried:
                continue
            tried.append(index)
            cap = cv2.VideoCapture(index, cv2.CAP_V4L2)
            if not cap.isOpened():
                cap.release()
                continue
            cap.set(cv2.CAP_PROP_FRAME_WIDTH, config.CAPTURE_WIDTH)
            cap.set(cv2.CAP_PROP_FRAME_HEIGHT, config.CAPTURE_HEIGHT)
            ok, _ = cap.read()
            if ok:
                self.capture = cap
                print(f"Camera connected on index {index}")
                break
            cap.release()

        if self.capture is None:
            tried_text = ", ".join(str(idx) for idx in tried)
            raise RuntimeError(f"Camera not detected on indices [{tried_text}].")

    def snap(self, prefix: str = "crop") -> str:
        # Drop a few buffered frames so the saved image reflects current view.
        for _ in range(4):
            self.capture.grab()
        ok, frame = self.capture.read()
        if not ok:
            raise RuntimeError("Failed to capture frame from camera.")
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        out_path = self.out_dir / f"{prefix}_{ts}.jpg"
        cv2.imwrite(str(out_path), frame)
        return str(out_path)

    def close(self) -> None:
        self.capture.release()
