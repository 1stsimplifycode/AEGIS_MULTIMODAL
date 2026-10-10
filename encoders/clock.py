"""Capture clock: media time -> wall-clock (air) time with an explicit uncertainty, from the capture's own validation.json.

wall(t_media) = wall_at_media0 + slope * t_media + sntp_offset
uncertainty u = p95 residual of the media->wall fit + one HLS segment (live-edge ambiguity)
The broadcaster's own ingest delay is NOT known from transport and is handled as an assumption range in the verifier.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass
class CaptureClock:
    wall_at_media0: float
    slope: float
    sntp_offset_s: float
    resid_p95_s: float
    live_edge_s: float
    source: str

    def wall(self, t_media: float) -> float:
        return self.wall_at_media0 + self.slope * t_media + self.sntp_offset_s

    @property
    def uncertainty_s(self) -> float:
        return round(self.resid_p95_s + self.live_edge_s, 2)

    def as_dict(self):
        d = asdict(self)
        d["uncertainty_s"] = self.uncertainty_s
        return d

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: d[k] for k in ("wall_at_media0", "slope", "sntp_offset_s", "resid_p95_s", "live_edge_s", "source")})


def from_validation(path: Path, channel: str) -> CaptureClock:
    v = json.loads(Path(path).read_text(encoding="utf-8"))
    ch = v["channels"][channel]
    m = ch["media_to_wall"]
    if not m.get("ok"):
        raise ValueError(f"no trustworthy media->wall mapping for {channel} in {path}")
    return CaptureClock(wall_at_media0=float(m["wall_at_media0"]), slope=float(m["slope"]),
                        sntp_offset_s=float(v.get("clock", {}).get("sntp_offset_median_s", 0.0)),
                        resid_p95_s=float(m["resid_p95_s"]), live_edge_s=float(ch.get("hls", {}).get("segment_s", 5.0)),
                        source=f"{Path(path).as_posix()} [{channel}]")
