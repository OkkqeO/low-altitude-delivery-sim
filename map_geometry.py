"""Polygon geometry shared by recognition, editing, routing and export (stdlib)."""
from __future__ import annotations

import math

FEATURE_TYPES = {"road": "道路", "water": "水体", "green": "绿地", "sports": "运动场", "paved": "公共空地"}
FEATURE_COLORS = {"road": "#89949F", "water": "#4C91C4", "green": "#5C9D68", "sports": "#C4A823", "paved": "#B5A69A"}


def ring_area(ring):
    return abs(sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(ring, ring[1:]+ring[:1]))) / 2


def shape_area(item):
    return (ring_area(item["polygon"]) - sum(ring_area(r) for r in item.get("holes", []))
            if item.get("polygon") else item["w"]*item["h"])


def point_in_ring(point, ring):
    x, y = point
    inside = False
    for a, b in zip(ring, ring[1:]+ring[:1]):
        if (a[1] > y) != (b[1] > y) and x < (b[0]-a[0])*(y-a[1])/(b[1]-a[1])+a[0]:
            inside = not inside
    return inside


def edge_distance(point, a, b):
    dx, dy = b[0]-a[0], b[1]-a[1]
    t = min(1., max(0., ((point[0]-a[0])*dx+(point[1]-a[1])*dy)/(dx*dx+dy*dy))) if dx or dy else 0.
    return math.hypot(point[0]-a[0]-t*dx, point[1]-a[1]-t*dy)


def contains(item, point, padding=0.):
    x, y = point
    if not (item["x"]-padding <= x <= item["x"]+item["w"]+padding
            and item["y"]-padding <= y <= item["y"]+item["h"]+padding):
        return False
    if not item.get("polygon"):
        return True
    rings = [item["polygon"], *item.get("holes", [])]
    if point_in_ring(point, rings[0]) and not any(point_in_ring(point, r) for r in rings[1:]):
        return True
    return any(edge_distance(point, a, b) <= padding+1e-9 for r in rings for a, b in zip(r, r[1:]+r[:1]))


def transform_shape(item, changes):
    """Keep contours and interior holes aligned when moving/resizing a component."""
    result = dict(item, **changes)
    if item.get("polygon") and any(k in changes for k in ("x", "y", "w", "h")):
        sx, sy = result["w"]/item["w"], result["h"]/item["h"]
        def transform(ring):
            return [[result["x"]+(x-item["x"])*sx, result["y"]+(y-item["y"])*sy] for x, y in ring]
        result["polygon"] = transform(item["polygon"])
        result["holes"] = [transform(r) for r in item.get("holes", [])]
    return result


def validate_shape(item, width, height):
    if not item.get("polygon"):
        if "polygon" in item or item.get("holes"):
            raise ValueError("多边形轮廓不能为空")
        return
    holes = item.get("holes", [])
    if not isinstance(holes, list) or len(holes) > 1000:
        raise ValueError("区域内部轮廓格式无效")
    for ring in [item["polygon"], *holes]:
        if not isinstance(ring, list) or not 3 <= len(ring) <= 8192:
            raise ValueError("多边形须包含3至8192个顶点")
        for p in ring:
            if (not isinstance(p, (list, tuple)) or len(p) != 2
                    or any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) for v in p)):
                raise ValueError("多边形顶点须为有限坐标")
            if not (-1e-7 <= p[0] <= width+1e-7 and -1e-7 <= p[1] <= height+1e-7
                    and item["x"]-1e-7 <= p[0] <= item["x"]+item["w"]+1e-7
                    and item["y"]-1e-7 <= p[1] <= item["y"]+item["h"]+1e-7):
                raise ValueError("多边形顶点超出组件或地图边界")
        if ring_area(ring) <= 1e-9:
            raise ValueError("多边形面积须大于0")


def svg_path(item, scale=1.):
    rings = [item["polygon"], *item.get("holes", [])]
    return " ".join("M"+" L".join(f"{x*scale:.3f},{y*scale:.3f}" for x, y in ring)+" Z" for ring in rings)


def canvas_polygon(canvas, item, scale, ox, oy, *, fill="", outline="", width=1, **options):
    """Draw holes transparently, preserving terrain underneath a courtyard.

    Tk accepts one ring per polygon. Traversing each connecting bridge in both
    directions gives a compound region without painting holes in a guessed
    background color. Opposite winding also works with Windows' winding fill.
    Draw only real ring edges as outlines.
    """
    rings = [item["polygon"], *item.get("holes", [])]
    def points(ring):
        return [c for x, y in ring for c in (ox+x*scale, oy+y*scale)]
    if len(rings) == 1:
        return [canvas.create_polygon(*points(rings[0]), fill=fill, outline=outline, width=width, **options)]
    anchor = rings[0][0]
    joined = rings[0]+[anchor]
    def winding(ring):
        return sum(a[0]*b[1]-b[0]*a[1] for a, b in zip(ring, ring[1:]+ring[:1]))
    for ring in rings[1:]:
        if winding(ring)*winding(rings[0]) > 0:
            ring = list(reversed(ring))
        joined.extend(ring+[ring[0], anchor])
    items = [canvas.create_polygon(*points(joined), fill=fill, outline="", **options)]
    if outline:
        items.extend(canvas.create_line(*points(ring+[ring[0]]), fill=outline, width=width)
                     for ring in rings)
    return items
