"""Local, legend-aware semantic extraction for colored campus plan maps.

Colors carry cartographic meaning, not measured heights or population data.
All output is editable candidate geometry; no coordinates are special-cased.
"""
from __future__ import annotations

from pathlib import Path
import sys

from map_geometry import FEATURE_TYPES

MAX_EDGE = 2400
# Published plan-map legend colors, with JPEG/antialiasing tolerance.
PALETTE = {"academic": [(162, 120, 168), (155, 124, 183)],
           "dormitory": [(139, 194, 188)], "residential": [(227, 163, 55)],
           "green": [(182, 208, 147)], "sports": [(232, 220, 50)],
           "water": [(154, 184, 212)], "paved": [(217, 213, 210)]}
BUILDING_NAMES = {"academic": "教学办公建筑", "dormitory": "宿舍建筑", "residential": "居住建筑", "sports_building": "体育建筑候选"}


def vision():
    try:
        import cv2
        import numpy as np
    except ImportError:
        local = Path(__file__).resolve().parent / ".image-deps"
        if local.is_dir() and str(local) not in sys.path:
            sys.path.insert(0, str(local))
        try:
            import cv2
            import numpy as np
        except ImportError as error:
            raise ValueError("多类地图识别需要图像依赖。请运行：python -m pip install -r requirements-image.txt") from error
    return cv2, np


def sample_image(image):
    from PIL import Image
    sample = image.copy()
    sample.thumbnail((MAX_EDGE, MAX_EDGE), Image.Resampling.LANCZOS)
    return sample


def palette_masks(rgb):
    _, np = vision()
    signed = rgb.astype(np.int16)
    return {key: np.logical_or.reduce([np.max(np.abs(signed-color), axis=2) <= 18 for color in colors])
            for key, colors in PALETTE.items()}


def campus_palette(image):
    _, np = vision()
    sample = image.copy()
    sample.thumbnail((400, 400))
    masks = palette_masks(np.array(sample.convert("RGB")))
    # Require the distinctive building colors AND ground color. A single purple
    # object or a green park alone must not trigger an unrelated campus palette.
    ratios = {k: float(v.mean()) for k, v in masks.items()}
    return (ratios["paved"] > .025 and ratios["dormitory"]+ratios["academic"] > .006
            and sum(ratios[k] > .001 for k in ("academic", "dormitory", "residential", "sports", "green", "water")) >= 3)


def contours(mask, width, height, minimum, kind):
    cv2, np = vision()
    mask = np.uint8(mask)*255
    # Repair lettering holes without reducing a rotated building to its box.
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    thickness = cv2.distanceTransform(mask, cv2.DIST_L2, 3) if kind in BUILDING_NAMES else None
    found, hierarchy = cv2.findContours(mask, cv2.RETR_CCOMP, cv2.CHAIN_APPROX_SIMPLE)
    if hierarchy is None:
        return []
    sh, sw = mask.shape
    sx, sy = width/sw, height/sh
    output = []
    for i, contour in enumerate(found):
        if hierarchy[0][i][3] != -1:
            continue
        area = cv2.contourArea(contour)
        x, y, w, h = cv2.boundingRect(contour)
        if area < minimum or min(w, h) < 3:
            continue
        if kind in BUILDING_NAMES and (area/max(1., cv2.arcLength(contour, True)**2) < .0025
                                      or thickness[y:y+h, x:x+w].max() < 2.8):
            continue
        outer = cv2.approxPolyDP(contour, .8, True).reshape(-1, 2)
        if len(outer) < 3:
            continue
        holes = []
        child = hierarchy[0][i][2]
        while child != -1:
            hole = found[child]
            hole_area = cv2.contourArea(hole)
            # Text, small pictograms and antialiasing are not courtyards.
            if hole_area >= max(20, minimum*.25) and (kind in ("road", "sports", "paved") or hole_area > area*.035):
                approx = cv2.approxPolyDP(hole, .8, True).reshape(-1, 2)
                if len(approx) >= 3:
                    holes.append([[float(a)*sx, float(b)*sy] for a, b in approx])
            child = hierarchy[0][child][0]
        polygon = [[float(a)*sx, float(b)*sy] for a, b in outer]
        px, py = min(p[0] for p in polygon), min(p[1] for p in polygon)
        item = {"x": px, "y": py, "w": max(p[0] for p in polygon)-px,
                "h": max(p[1] for p in polygon)-py, "polygon": polygon, "holes": holes,
                "recognition_source": "本地颜色分割与多边形轮廓", "candidate": True,
                "pixel_area": round(area), "fill_ratio": area/(w*h)}
        if min(item["w"], item["h"]) > 0:
            output.append(item)
    return sorted(output, key=lambda b: (b["y"], b["x"]))


def extract_map(image, width, min_area=100, legacy_buildings=None, labels=None):
    cv2, np = vision()
    min_area = int(min_area)
    if not 20 <= min_area <= 10000:
        raise ValueError("最小面积须为20—10000像素")
    sample = sample_image(image)
    rgb = np.array(sample.convert("RGB"))
    height = float(width)*image.height/image.width
    masks = palette_masks(rgb)
    campus = campus_palette(sample)
    if not campus:
        # Preserve the existing generic building detector and use broad hue
        # classes for terrain. No inferred people/demand/height values.
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV)
        hue, sat, val = (hsv[:, :, i] for i in range(3))
        masks = {"green": (hue >= 30)&(hue <= 85)&(sat > 35)&(val > 100),
                 "water": (hue >= 90)&(hue <= 120)&(sat > 35)&(val > 100),
                 "sports": (hue >= 22)&(hue < 30)&(sat > 110)&(val > 150),
                 "paved": np.zeros(hue.shape, dtype=bool)}
    sh, sw = rgb.shape[:2]
    # Derive the map domain from colored land and pavement, excluding poster
    # titles and margins. Exterior white paper is never blindly called a road.
    seed = np.logical_or.reduce(list(masks.values()))
    # Streets can split otherwise continuous land into disconnected blocks.
    # Join blocks across a street before tracing the mapped extent, so white
    # carriageways remain inside the domain even when they cross the whole map.
    kernel = max(5, int(max(sw, sh)*.025) | 1)
    domain = cv2.morphologyEx(np.uint8(seed)*255, cv2.MORPH_CLOSE, np.ones((kernel, kernel), np.uint8))
    count, component_labels, stats, _ = cv2.connectedComponentsWithStats(domain, connectivity=8)
    domain[:] = 0
    for i in range(1, count):
        if stats[i, cv2.CC_STAT_AREA] >= sw*sh*.008:
            region = np.uint8(component_labels == i)*255
            outer, _ = cv2.findContours(region, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            cv2.drawContours(domain, outer, -1, 255, cv2.FILLED)
    bright = (rgb.min(axis=2) >= 241)
    medium_gray = (np.max(np.abs(rgb.astype(np.int16)-(180, 180, 180)), axis=2) <= 12)
    masks["road"] = (bright | (medium_gray if campus else False)) & (domain > 0)
    def envelope(mask):
        closed = cv2.morphologyEx(np.uint8(mask)*255, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
        found, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        result = np.zeros((sh, sw), np.uint8)
        cv2.drawContours(result, found, -1, 255, cv2.FILLED)
        return result > 0
    sports_raw = masks["sports"].copy()
    original_green = masks["green"].copy()
    sports_envelope = envelope(sports_raw)
    # Football pitch markings and the green surface inside a running track are
    # parts of the sports facility, not roads or separate parks.
    masks["sports"] = sports_envelope
    masks["green"] &= ~sports_envelope
    excluded = sports_envelope | envelope(masks["water"])
    if campus:
        for k in ("academic", "dormitory", "residential"):
            excluded |= envelope(masks[k])
    masks["road"] &= ~excluded
    buildings = []
    if campus:
        for kind in BUILDING_NAMES:
            if kind == "sports_building":
                continue
            for item in contours(masks[kind], width, height, min_area, kind):
                # A tiny legend swatch is not a campus structure.
                cx, cy = round((item["x"]+item["w"]/2)/width*(sw-1)), round((item["y"]+item["h"]/2)/height*(sh-1))
                if domain[cy, cx]:
                    buildings.append(dict(item, building_use=kind))
    else:
        buildings = list(legacy_buildings or [])
    features = []
    for kind in FEATURE_TYPES:
        for item in contours(masks[kind], width, height, min_area if kind != "road" else max(40, min_area), kind):
            x, y = int(item["x"]/width*sw), int(item["y"]/height*sh)
            w, h = max(1, round(item["w"]/width*sw)), max(1, round(item["h"]/height*sh))
            green_fraction = 0.
            if kind == "sports" and campus:
                local = np.zeros((min(sh-y, h+1), min(sw-x, w+1)), np.uint8)
                polygon = np.array([[round(a/width*sw)-x, round(b/height*sh)-y] for a, b in item["polygon"]], np.int32)
                cv2.fillPoly(local, [polygon], 255)
                green_fraction = float(((original_green[y:y+local.shape[0], x:x+local.shape[1]]) & (local > 0)).sum()/max(1, (local > 0).sum()))
            if kind == "sports" and green_fraction < .06 and campus:
                buildings.append(dict(item, building_use="sports_building", structure_confirmation_required=True))
            else:
                features.append(dict(item, kind=kind))
    from map_ocr import label_for, read_labels
    ocr_engine = "not_requested"
    if campus and labels is None:
        labels, ocr_engine = read_labels(sample)
    labels = labels or []
    named = 0
    retained = []
    for item in buildings:
        name = label_for(item, labels, width/sw, height/sh)
        if name:
            item.update(name=name, name_source="本地OCR候选，需核对")
            named += 1
        # Text resolves the shared yellow legend: a volleyball court should not
        # acquire a fictitious roof just because it has a solid yellow fill.
        if item.get("building_use") == "sports_building" and name and "场" in name and "馆" not in name:
            item.pop("building_use", None)
            item.pop("structure_confirmation_required", None)
            features.append(dict(item, kind="sports"))
        else:
            retained.append(item)
    buildings = sorted(retained, key=lambda b: (b["y"], b["x"]))
    for i, item in enumerate(buildings, 1):
        use = item.get("building_use")
        item.update(id=f"B{i}", name=item.get("name") or (f"{BUILDING_NAMES[use]}{i}" if use else f"识别建筑{i}"),
                    height=0., height_confirmed=False, height_source="待用户填写",
                    footprint_source="图片多边形候选" if item.get("polygon") else "图片矩形候选")
    counts = {k: 0 for k in FEATURE_TYPES}
    for i, item in enumerate(features, 1):
        counts[item["kind"]] += 1
        keywords = {"sports": ("场", "馆"), "green": ("园", "林", "绿地"), "water": ("河", "湖", "渠"), "road": ("路", "街", "道"), "paved": ("广场",)}[item["kind"]]
        name = item.get("name") or label_for(item, labels, width/sw, height/sh, keywords)
        item.update(id=f"F{i}", name=name or f"{FEATURE_TYPES[item['kind']]}{counts[item['kind']]}")
    return buildings, features, {"recognition_profile": "campus_legend" if campus else "generic",
                                "recognition_mode": "semantic", "recognition_count": len(buildings),
                                "feature_counts": counts, "recognition_truncated": False,
                                "analysis_pixels": [sw, sh], "min_component_pixels": min_area,
                                "ocr_engine": ocr_engine, "ocr_label_count": len(labels), "named_candidate_count": named,
                                "recognition_note": "地物分类为地图配色候选，名称可编辑；楼高、尺度与人群仍需核实。"}
