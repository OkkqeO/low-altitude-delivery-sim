"""Continuous-time separation checks for piecewise-linear, same-height flight.

The model includes cruise, destination hover and landing-queue hover. Takeoff
preparation and the landing service itself are ground operations. Thresholds
are experiment parameters, not a claim about regulatory or physical safety.
"""
from __future__ import annotations

from dataclasses import dataclass
import math


@dataclass(frozen=True, slots=True)
class Segment:
    start: float
    end: float
    x: float
    y: float
    vx: float
    vy: float

    def position(self, time: float) -> tuple[float, float]:
        return self.x + self.vx * (time - self.start), self.y + self.vy * (time - self.start)


def flight_segments(job: dict, route: dict, speed: float) -> list[Segment]:
    segments = []
    points, cumulative = route["points"], route["cumulative"]
    for i, (a, b) in enumerate(zip(points, points[1:])):
        length = cumulative[i + 1] - cumulative[i]
        if length <= 1e-10:
            continue
        duration = length / speed
        t0 = job["depart"] + cumulative[i] / speed
        segments.append(Segment(t0, t0 + duration, a[0], a[1], (b[0] - a[0]) / duration, (b[1] - a[1]) / duration))
    if job["return_start"] > job["arrived_dest"]:
        x, y = points[-1]
        segments.append(Segment(job["arrived_dest"], job["return_start"], x, y, 0., 0.))
    for i in range(len(points) - 1, 0, -1):
        a, b = points[i], points[i - 1]
        length = cumulative[i] - cumulative[i - 1]
        if length <= 1e-10:
            continue
        duration = length / speed
        t0 = job["return_start"] + (route["distance"] - cumulative[i]) / speed
        segments.append(Segment(t0, t0 + duration, a[0], a[1], (b[0] - a[0]) / duration, (b[1] - a[1]) / duration))
    if job["land_start"] > job["return_arrival"] + 1e-10:
        x, y = points[0]
        segments.append(Segment(job["return_arrival"], job["land_start"], x, y, 0., 0.))
    return segments


def segment_violation(a: Segment, b: Segment, separation: float) -> dict | None:
    """Solve |relative_position + relative_velocity*t| < separation exactly.

    Strict tangency and zero-duration overlaps do not constitute an episode.
    All values refer to this idealized linear model, with floating-point tolerance.
    """
    lo, hi = max(a.start, b.start), min(a.end, b.end)
    if hi - lo <= 1e-9:
        return None
    ax, ay = a.position(lo)
    bx, by = b.position(lo)
    rx, ry, vx, vy = ax - bx, ay - by, a.vx - b.vx, a.vy - b.vy
    vv = vx * vx + vy * vy
    rr = rx * rx + ry * ry
    duration = hi - lo
    if vv < 1e-18:
        if rr >= separation * separation - 1e-9:
            return None
        begin, end, closest = 0., duration, 0.
    else:
        center = -(rx * vx + ry * vy) / vv
        closest = min(duration, max(0., center))
        min_squared = (rx + vx * closest)**2 + (ry + vy * closest)**2
        if min_squared >= separation * separation - 1e-9:
            return None
        perpendicular_squared = max(0., rr - (rx * vx + ry * vy)**2 / vv)
        radius = math.sqrt(max(0., separation * separation - perpendicular_squared) / vv)
        begin, end = max(0., center - radius), min(duration, center + radius)
        if end - begin <= 1e-9:
            return None
    closest_time = lo + closest
    ap, bp = a.position(closest_time), b.position(closest_time)
    return {"start": lo + begin, "end": lo + end, "closest_time": closest_time,
            "min_distance": math.dist(ap, bp), "x": (ap[0] + bp[0]) / 2, "y": (ap[1] + bp[1]) / 2}


def iter_violations(a: list[Segment], b: list[Segment], separation: float):
    """Traverse sorted segment lists with two pointers, without time sampling."""
    i, j = 0, 0
    while i < len(a) and j < len(b):
        sa, sb = a[i], b[j]
        if sa.start < sb.end and sb.start < sa.end:
            violation = segment_violation(sa, sb, separation)
            if violation is not None:
                yield violation
        if sa.end <= sb.end:
            i += 1
        if sb.end <= sa.end:
            j += 1


def has_conflict(segments: list[Segment], accepted: list[tuple[dict, list[Segment]]],
                 drone_id: str, separation: float) -> bool:
    if not segments:
        return False
    for job, other in accepted:
        if job["drone_id"] == drone_id or not other:
            continue
        if segments[-1].end <= other[0].start or other[-1].end <= segments[0].start:
            continue
        if next(iter_violations(segments, other, separation), None) is not None:
            return True
    return False


def detect_conflicts(jobs: list[dict], routes: dict, speed: float, separation: float) -> list[dict]:
    """Count contiguous below-threshold episodes per pair of delivery jobs."""
    if not math.isfinite(separation) or separation <= 0:
        raise ValueError("间距阈值须为正有限数值")
    flights = [(job, flight_segments(job, routes[job["route_key"]], speed)) for job in jobs]
    conflicts = []
    for i, (job_a, a) in enumerate(flights):
        if not a:
            continue
        for job_b, b in flights[i + 1:]:
            if job_a["drone_id"] == job_b["drone_id"] or not b or a[-1].end <= b[0].start or b[-1].end <= a[0].start:
                continue
            episodes = []
            for violation in iter_violations(a, b, separation):
                if episodes and violation["start"] <= episodes[-1]["end"] + 1e-7:
                    previous = episodes[-1]
                    end = max(previous["end"], violation["end"])
                    if violation["min_distance"] < previous["min_distance"]:
                        for field in ("closest_time", "min_distance", "x", "y"):
                            previous[field] = violation[field]
                    previous["end"] = end
                else:
                    episodes.append(dict(violation))
            for episode in episodes:
                conflicts.append({**episode, "drone_a": job_a["drone_id"], "drone_b": job_b["drone_id"],
                                  "order_a": job_a["order_id"], "order_b": job_b["order_id"]})
    return sorted(conflicts, key=lambda item: (item["start"], item["order_a"], item["order_b"]))
