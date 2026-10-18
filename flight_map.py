"""Simple flight diagrams: conservative building boxes and road outlines."""
from copy import deepcopy

from map_geometry import edge_distance, ring_area


def simplify_ring(ring, tolerance):
    """Simplify a closed outline while retaining its main turns (stdlib only)."""
    if len(ring) <= 4:
        return deepcopy(ring)
    split = max(range(1, len(ring)), key=lambda i: (ring[i][0]-ring[0][0])**2+(ring[i][1]-ring[0][1])**2)
    def arc(points):
        kept = {0, len(points)-1}
        pending = [(0, len(points)-1)]
        while pending:
            start, end = pending.pop()
            if end-start <= 1:
                continue
            furthest = max(range(start+1, end), key=lambda i: edge_distance(points[i], points[start], points[end]))
            if edge_distance(points[furthest], points[start], points[end]) > tolerance:
                kept.add(furthest)
                pending.extend(((start, furthest), (furthest, end)))
        return [points[i] for i in sorted(kept)]
    result = arc(ring[:split+1])[:-1]+arc(ring[split:]+ring[:1])[:-1]
    return deepcopy(result if len(result) >= 3 and ring_area(result) > 1e-9 else ring)


def schematic_components(buildings, features, width, height):
    boxes = []
    for building in buildings:
        box = deepcopy(building)
        if box.pop("polygon", None):
            box["footprint_source"] = "轮廓外接矩形，保守障碍近似"
        box.pop("holes", None)
        boxes.append(box)
    roads = []
    tolerance = max(width, height)*.0012
    for feature in features:
        if feature.get("kind") != "road":
            continue
        road = deepcopy(feature)
        if road.get("polygon") and not road.get("schematic_outline"):
            road["polygon"] = simplify_ring(road["polygon"], tolerance)
            road["holes"] = [simplify_ring(ring, tolerance) for ring in road.get("holes", [])
                             if ring_area(ring) >= width*height*.00008]
            # Scaling or loading an existing draft must not simplify it again.
            road["schematic_outline"] = True
        roads.append(road)
    return boxes, roads


def schematic_scene(scene):
    """Keep height records so lowering cruise altitude can reveal more obstacles."""
    result = deepcopy(scene)
    result["map_presentation"] = "schematic"
    result["buildings"], result["map_features"] = schematic_components(
        scene["buildings"], scene.get("map_features", []), scene["width"], scene["height"])
    return result


def flight_obstacles(scene):
    return [b for b in scene["buildings"]
            if b["height"]+scene["vertical_clearance"] >= scene["altitude"]]
