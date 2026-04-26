from datetime import datetime, timezone

from agrimind.fusion import fuse_sensor_and_vision
from agrimind.schemas import CaptureEvent, SensorValues, Severity, VLMOutput


def test_fusion_flags_and_score() -> None:
    capture = CaptureEvent(
        scan_id="scan-1",
        timestamp=datetime.now(timezone.utc),
        gps_or_row_id="row-a",
        image_uri="https://example.com/image.jpg",
        sensor_values=SensorValues(
            moisture_pct=20,
            air_quality_index=170,
            light_lux=6000,
            temperature_c=35,
        ),
    )
    vlm = VLMOutput(
        disease_or_stress_label="nitrogen_deficiency",
        severity=Severity.high,
        confidence=0.81,
        visual_evidence=["leaf yellowing"],
    )
    out = fuse_sensor_and_vision(capture, vlm)
    assert out.risk_score > 0.8
    assert out.irrigation_flag is True
    assert out.fertilizer_flag is True
