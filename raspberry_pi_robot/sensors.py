import math

import config

try:
    from grove.adc import ADC  # type: ignore
except ImportError:
    ADC = None


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


class SensorSuite:
    def __init__(self) -> None:
        self.adc = ADC() if ADC is not None else None
        if self.adc is None:
            raise RuntimeError(
                "Grove ADC library not found. Install with: pip3 install grove.py "
                "and use Grove Base HAT."
            )

    def read_raw(self, channel: int) -> float:
        return float(self.adc.read(channel))

    def read_light(self) -> float:
        raw = self.read_raw(config.LIGHT_CHANNEL)
        lux = raw * config.LIGHT_GAIN + config.LIGHT_OFFSET
        return max(0.0, lux)

    def read_temperature_c(self) -> float:
        val = self.read_raw(config.TEMPERATURE_CHANNEL)
        if val <= 0:
            return 0.0
        resistance = (config.TEMP_ADC_MAX - val) * config.TEMP_R0 / val
        temperature_k = 1.0 / (
            (math.log(resistance / config.TEMP_R0) / config.TEMP_BETA) + (1.0 / 298.15)
        )
        temperature_c = temperature_k - 273.15 + config.TEMP_OFFSET_C
        return temperature_c

    def read_moisture_pct(self) -> float:
        if getattr(config, "USE_DEMO_MOISTURE_VALUE", False):
            return _clamp(float(getattr(config, "DEMO_MOISTURE_PCT", 34.0)), 0.0, 100.0)
        raw = self.read_raw(config.MOISTURE_CHANNEL)
        dry = config.MOISTURE_RAW_DRY
        wet = config.MOISTURE_RAW_WET
        if abs(dry - wet) < 1e-6:
            return 0.0
        pct = 100.0 * (dry - raw) / (dry - wet) + config.MOISTURE_OFFSET_PCT
        return _clamp(pct, 0.0, 100.0)

    def read_air_quality_index(self) -> float:
        if getattr(config, "USE_DEMO_AIR_QUALITY_VALUE", False):
            return _clamp(float(getattr(config, "DEMO_AIR_QUALITY_INDEX", 78.0)), 0.0, 500.0)
        raw = self.read_raw(config.AIR_QUALITY_CHANNEL)
        clean = config.AIR_RAW_CLEAN
        polluted = config.AIR_RAW_POLLUTED
        if abs(polluted - clean) < 1e-6:
            return 0.0
        index = 500.0 * (raw - clean) / (polluted - clean) + config.AIR_QUALITY_OFFSET
        return _clamp(index, 0.0, 500.0)

    def read_all(self) -> dict:
        return {
            "light_lux_est": round(self.read_light(), 2),
            "temperature_c": round(self.read_temperature_c(), 2),
            "moisture_pct": round(self.read_moisture_pct(), 2),
            "air_quality_index": round(self.read_air_quality_index(), 2),
        }
