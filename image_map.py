"""Local semantic/shape extraction for plan maps; heights stay manual.

Uses optional Pillow, NumPy and OpenCV. Images are processed on this computer.
Colored campus plans retain polygon footprints and classified land regions.
"""
from __future__ import annotations

import base64
from collections import deque
from io import BytesIO
from pathlib import Path

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
MODES = {"自动": "auto", "灰色建筑": "gray", "暖色建筑": "warm", "蓝灰建筑": "blue", "取色识别": "color"}
BACKGROUND_EDGE = 3072
BACKGROUND_PIXELS = BACKGROUND_EDGE ** 2
BACKGROUND_BASE64_LIMIT = 40_000_000


def pillow():
    try:
        from PIL import Image, ImageFilter, ImageOps
    except ImportError as error:
        raise ValueError("图片导入需要Pillow。请运行：python -m pip install -r requirements-image.txt") from error
    return Image, ImageFilter, ImageOps


def read_image(path):
    Image, _, ImageOps = pillow()
    path = Path(path)
    if path.stat().st_size > 64_000_000:
        raise ValueError("图片过大，请将地图裁剪或缩小至64MB以内")
    try:
        with Image.open(path) as original:
            if original.width * original.height > 80_000_000:
                raise ValueError("图片像素过多，请缩小至8000万像素以内")
            image = ImageOps.exif_transpose(original).convert("RGBA")
            background = Image.new("RGBA", image.size, "white")
            background.alpha_composite(image)
            return background.convert("RGB")
    except (OSError, Image.DecompressionBombError) as error:
        raise ValueError("无法读取地图图片，请选择有效的PNG、JPG、WebP或BMP文件") from error


def encode_background(image, name):
    Image, _, _ = pillow()
    thumbnail = image.copy()
    thumbnail.thumbnail((BACKGROUND_EDGE, BACKGROUND_EDGE), Image.Resampling.LANCZOS)
    buffer = BytesIO()
    thumbnail.save(buffer, format="PNG")
    return {"png_base64": base64.b64encode(buffer.getvalue()).decode("ascii"),
            "pixel_width": thumbnail.width, "pixel_height": thumbnail.height, "source_name": name}


def decode_background(scene):
    background = scene.get("image_background")
    if not background:
        return None
    if not isinstance(background, dict):
        raise ValueError("地图底图信息格式无效")
    Image, _, _ = pillow()
    encoded = background.get("png_base64", "")
    if not isinstance(encoded, str) or len(encoded) > BACKGROUND_BASE64_LIMIT:
        raise ValueError("地图底图数据过大或无效")
    try:
        data = base64.b64decode(encoded, validate=True)
        with Image.open(BytesIO(data)) as image:
            if image.width * image.height > BACKGROUND_PIXELS:
                raise ValueError("地图底图像素过多")
            return image.convert("RGB")
    except (OSError, ValueError) as error:
        raise ValueError("地图底图已损坏，请重新导入图片") from error


def extract_buildings(image, width, mode="auto", color=None, tolerance=35, min_area=100):
    Image, ImageFilter, _ = pillow()
    if mode not in MODES.values():
        raise ValueError("无法识别的建筑提取方式")
    if mode == "color" and color is None:
        raise ValueError("请先选择“取色”，再点击一栋建筑的填充区域")
    tolerance, min_area = int(tolerance), int(min_area)
    if not 5 <= tolerance <= 100 or not 20 <= min_area <= 10000:
        raise ValueError("取色容差须为5—100，最小面积须为20—10000像素")
    sample = image.copy()
    sample.thumbnail((840, 840), Image.Resampling.LANCZOS)
    sw, sh = sample.size
    pixels = bytearray(sw * sh)
    flat_pixels = sample.get_flattened_data() if hasattr(sample, "get_flattened_data") else sample.getdata()
    for i, (r, g, b) in enumerate(flat_pixels):
        spread, mean = max(r, g, b) - min(r, g, b), (r + g + b) / 3
        gray = spread <= 25 and 105 <= mean <= 235
        warm = r >= 150 and 0 <= r - g <= 45 and 7 <= g - b <= 45 and r - b >= 14 and mean <= 235
        blue = 130 <= r <= 230 and 140 <= g <= 235 and 5 <= b - r <= 45 and 0 <= b - g <= 25
        match = ((gray or warm) if mode == "auto" else gray if mode == "gray" else warm if mode == "warm"
                 else blue if mode == "blue" else max(abs(r - color[0]), abs(g - color[1]), abs(b - color[2])) <= tolerance)
        pixels[i] = 255 if match else 0
    # Opening removes labels and thin road outlines before component extraction.
    mask = Image.frombytes("L", (sw, sh), bytes(pixels)).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.MaxFilter(3))
    pixels = bytearray(mask.tobytes())
    candidates = []
    for seed, active in enumerate(pixels):
        if not active:
            continue
        pixels[seed] = 0
        pending = deque([seed])
        left = right = seed % sw
        top = bottom = seed // sw
        area = 0
        while pending:
            index = pending.popleft()
            x, y = index % sw, index // sw
            left, right, top, bottom = min(left, x), max(right, x), min(top, y), max(bottom, y)
            area += 1
            for neighbor in ((index - 1 if x else -1), (index + 1 if x + 1 < sw else -1),
                             (index - sw if y else -1), (index + sw if y + 1 < sh else -1)):
                if neighbor >= 0 and pixels[neighbor]:
                    pixels[neighbor] = 0
                    pending.append(neighbor)
        bw, bh = right - left + 1, bottom - top + 1
        if area >= min_area and min(bw, bh) >= 6 and area / (bw * bh) >= .38 and bw * bh <= sw * sh * .20 and max(bw / bh, bh / bw) <= 12:
            candidates.append((area, left, top, bw, bh))
    candidates.sort(reverse=True)
    truncated = len(candidates) > 160
    candidates = sorted(candidates[:160], key=lambda v: (v[2], v[1]))
    scale, scale_y = float(width) / sw, float(width) * image.height / image.width / sh
    buildings = [{"id": f"B{i}", "name": f"识别建筑{i}", "x": x * scale, "y": y * scale_y,
                  "w": bw * scale, "h": bh * scale_y, "height": 0., "height_confirmed": False,
                  "height_source": "待用户填写", "footprint_source": "图片颜色与形状提取，矩形近似"}
                 for i, (_, x, y, bw, bh) in enumerate(candidates, 1)]
    return buildings, {"recognition_mode": mode, "min_component_pixels": min_area,
                       "recognition_count": len(buildings), "recognition_truncated": truncated}


def suggest_points(scene):
    """Suggest open locations, not real landing authorization or demand data."""
    width, height = scene["width"], scene["height"]
    padding = scene["clearance"] + 3
    candidates = [(width * x / 16, height * y / 12) for y in range(1, 12) for x in range(1, 16)]
    from map_geometry import contains
    features = scene.get("map_features", [])
    land = [f for f in features if f["kind"] in ("road", "paved")]
    candidates = [(x, y) for x, y in candidates
                  if not any(contains(b, (x, y), padding) for b in scene["buildings"])
                  and not any(contains(f, (x, y)) for f in features if f["kind"] in ("water", "sports"))
                  and (not land or any(contains(f, (x, y)) for f in land))]
    selected = []
    while candidates and len(selected) < 14:
        point = max(candidates, key=lambda p: min((p[0] - q[0]) ** 2 + (p[1] - q[1]) ** 2 for q in selected)) if selected else candidates[0]
        candidates.remove(point)
        selected.append(point)
    pads = [{"id": f"S{i}", "name": f"建议起降点{i}", "x": x, "y": y, "suggested": True} for i, (x, y) in enumerate(selected[:6], 1)]
    deliveries = [{"id": f"D{i}", "name": f"建议配送点{i}", "x": x, "y": y, "demand": 1., "suggested": True} for i, (x, y) in enumerate(selected[6:], 1)]
    return pads, deliveries


def recognize_map(image, width, mode="auto", color=None, tolerance=35, min_area=100):
    from campus_recognition import extract_map, campus_palette
    # Keep manual color modes and existing simple-map behavior available.
    legacy = None
    if mode != "auto" or not campus_palette(image):
        legacy, _ = extract_buildings(image, width, mode, color, tolerance, min_area)
    buildings, features, metadata = extract_map(image, width, min_area, legacy)
    if mode != "auto":
        buildings = legacy
        metadata.update(recognition_count=len(buildings), recognition_mode=mode)
    from flight_map import schematic_components
    buildings, features = schematic_components(buildings, features, width, width*image.height/image.width)
    metadata["detected_feature_counts"] = metadata["feature_counts"]
    metadata["feature_counts"] = {key: sum(f["kind"] == key for f in features) for key in metadata["feature_counts"]}
    metadata["recognition_note"] = "飞行简图：建筑矩形与道路；楼高和尺度待核实，计算后仅显示会阻挡巡航的建筑。"
    return buildings, features, metadata


def scene_from_image(path):
    image = read_image(path)
    width = 1000.
    buildings, features, recognition = recognize_map(image, width)
    scene = {"width": width, "height": width * image.height / image.width, "step": width / 60,
             "clearance": 8., "vertical_clearance": 5., "buildings": buildings,
             "pads": [], "deliveries": [], "risk_zones": [], "map_features": features, "map_presentation": "schematic",
             "source": f"图片：{Path(path).name}；建筑矩形与道路为识别候选，楼高和尺度由用户填写；点位为模拟建议",
             "image_background": encode_background(image, Path(path).name),
             "image_import": {"scale_confirmed": False, "method": "本地多类颜色分割与多边形轮廓提取", **recognition}}
    scene["pads"], scene["deliveries"] = suggest_points(scene)
    return scene
