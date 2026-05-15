from __future__ import annotations

NS_PER_MS = 1_000_000
NS_PER_US = 1_000

MIN_NS = 1_000_000_000_000_000_000  # 2001-09-09T01:46:40Z, well below any realistic ts
MAX_NS = 4_102_444_800_000_000_000  # 2100-01-01T00:00:00Z, upper guardrail


class TimeUnitError(ValueError):
    pass


def to_ns(value: int, unit: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TimeUnitError(f"ts must be int, got {type(value).__name__}")
    if value < 0:
        raise TimeUnitError(f"ts must be non-negative, got {value}")
    match unit:
        case "ns":
            return value
        case "us":
            return value * NS_PER_US
        case "ms":
            return value * NS_PER_MS
        case _:
            raise TimeUnitError(f"unsupported unit {unit!r}; expected one of: ns, us, ms")


def ensure_ns(value: int) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise TimeUnitError(f"ts_event must be int ns, got {type(value).__name__}")
    if value < MIN_NS or value > MAX_NS:
        raise TimeUnitError(
            f"ts_event={value} is outside the nanosecond range "
            f"[{MIN_NS}, {MAX_NS}]; likely passed in ms or us"
        )
    return value
