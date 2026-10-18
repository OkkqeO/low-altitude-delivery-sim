"""Editable scene documents, independent of Tk and image libraries."""
from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path
import tempfile
from map_geometry import FEATURE_TYPES, transform_shape, validate_shape

COLLECTIONS = {"buildings": ("建筑", "B"), "pads": ("起降场", "S"),
               "deliveries": ("配送点", "D"), "risk_zones": ("人群区", "R"), "map_features": ("地物", "F")}
FIELDS = {"buildings": ("x", "y", "w", "h", "height"), "pads": ("x", "y"),
          "deliveries": ("x", "y", "demand"), "risk_zones": ("x", "y", "rx", "ry", "weight"),
          "map_features": ("x", "y", "w", "h")}


def finite(value, label):
    if isinstance(value, bool):
        raise ValueError(f"{label}须为有限数字")
    try:
        value = float(value)
    except (TypeError, ValueError) as error:
        raise ValueError(f"{label}须填写数字") from error
    if not math.isfinite(value):
        raise ValueError(f"{label}须为有限数字")
    return value


class MapDocument:
    def __init__(self, scene):
        if not isinstance(scene, dict):
            raise ValueError("地图须为一个JSON对象")
        self.scene = deepcopy(scene)
        for key in ("altitude", "closure"):
            self.scene.pop(key, None)
        for collection, (label, prefix) in COLLECTIONS.items():
            self.scene.setdefault(collection, [])
            if not isinstance(self.scene[collection], list) or any(not isinstance(item, dict) for item in self.scene[collection]):
                raise ValueError(f"{label}列表格式无效")
            used = {item.get("id") for item in self.scene[collection]}
            for i, item in enumerate(self.scene[collection], 1):
                if not item.get("id"):
                    number = i
                    while f"{prefix}{number}" in used:
                        number += 1
                    item["id"] = f"{prefix}{number}"
                    used.add(item["id"])
                item.setdefault("name", item["id"])
        self.undo_stack, self.redo_stack = [], []
        self._validate(self.scene)

    @staticmethod
    def _validate(scene):
        from facility_schema import validate_optional_facilities
        validate_optional_facilities(scene)
        for field in ("width", "height", "step", "clearance", "vertical_clearance"):
            if isinstance(scene.get(field), bool) or not isinstance(scene.get(field), (int, float)):
                raise ValueError(f"{field}须为数值")
            value = finite(scene.get(field), field)
            if value < 0 or field in ("width", "height", "step") and value <= 0:
                raise ValueError("地图尺寸和网格须大于0，间距须非负")
        if (scene["width"] / scene["step"] + 1) * (scene["height"] / scene["step"] + 1) > 200000:
            raise ValueError("网格过密，请增大网格间距")
        for collection in COLLECTIONS:
            ids = set()
            for item in scene[collection]:
                if not isinstance(item.get("id"), str) or not item["id"] or item["id"] in ids:
                    raise ValueError("组件编号不能为空或重复")
                ids.add(item["id"])
                for field in FIELDS[collection]:
                    if isinstance(item.get(field), bool) or not isinstance(item.get(field), (int, float)):
                        raise ValueError(f"{field}须为数值")
                    finite(item.get(field), field)
                if not 0 <= item["x"] <= scene["width"] or not 0 <= item["y"] <= scene["height"]:
                    raise ValueError("组件坐标超出地图边界")
                if collection in ("buildings", "map_features") and (min(item["w"], item["h"]) <= 0 or item.get("height", 0) < 0
                        or item["x"] + item["w"] > scene["width"] + 1e-7
                        or item["y"] + item["h"] > scene["height"] + 1e-7):
                    raise ValueError("区域长宽须大于0、楼高须非负，区域不能超出地图")
                if collection in ("buildings", "map_features"):
                    validate_shape(item, scene["width"], scene["height"])
                if collection == "map_features" and item.get("kind") not in FEATURE_TYPES:
                    raise ValueError("地物类型须为道路、水体、绿地、运动场或公共空地")
                if collection == "deliveries" and item["demand"] <= 0:
                    raise ValueError("需求权重须大于0")
                if collection == "risk_zones" and (min(item["rx"], item["ry"]) <= 0 or not 0 <= item["weight"] <= 1):
                    raise ValueError("人群区半径须大于0，强度须在0到1之间")

    def change(self, operation):
        candidate = deepcopy(self.scene)
        result = operation(candidate)
        self._validate(candidate)
        if candidate != self.scene:
            self.undo_stack.append(self.scene)
            self.undo_stack = self.undo_stack[-60:]
            self.redo_stack.clear()
            self.scene = candidate
        return result

    def item(self, collection, identity):
        return next(item for item in self.scene[collection] if item["id"] == identity)

    def update(self, collection, identity, changes):
        allowed = {"name", *FIELDS[collection]}
        if collection == "pads":
            allowed.update(("allowed_levels", "site_cost"))
        if collection == "map_features":
            allowed.add("kind")
        if set(changes) - allowed:
            raise ValueError("不能修改组件编号或未知字段")
        values = {}
        for key, value in changes.items():
            if key == "allowed_levels":
                values[key] = ([v.strip() for v in value.replace("，", ",").split(",") if v.strip()]
                               if isinstance(value, str) else deepcopy(value))
            else:
                values[key] = str(value).strip() if key in ("name", "kind") else finite(value, key)
        def operation(scene):
            item = next(item for item in scene[collection] if item["id"] == identity)
            item.update(transform_shape(item, values) if collection in ("buildings", "map_features") else values)
            if not item.get("name"):
                item["name"] = identity
            if collection == "buildings" and "height" in values:
                item.update(height_confirmed=True, height_source="用户手动填写")
        self.change(operation)

    def add(self, collection, values):
        prefix = COLLECTIONS[collection][1]
        used = {item["id"] for item in self.scene[collection]}
        number = 1
        while f"{prefix}{number}" in used:
            number += 1
        item = dict(values, id=f"{prefix}{number}")
        item.setdefault("name", f"{COLLECTIONS[collection][0]}{number}")
        if collection == "buildings":
            item.setdefault("height", 0.)
            item.setdefault("height_confirmed", False)
        if collection == "deliveries":
            item.setdefault("demand", 1.)
        if collection == "map_features":
            item.setdefault("kind", "green")
        self.change(lambda scene: scene[collection].append(item))
        return item["id"]

    def delete(self, collection, identity):
        self.change(lambda scene: scene[collection].__setitem__(slice(None), [item for item in scene[collection] if item["id"] != identity]))

    def move(self, collection, identity, x, y):
        item = self.item(collection, identity)
        limit_x = self.scene["width"] - (item["w"] if collection in ("buildings", "map_features") else 0)
        limit_y = self.scene["height"] - (item["h"] if collection in ("buildings", "map_features") else 0)
        self.update(collection, identity, {"x": min(limit_x, max(0., x)), "y": min(limit_y, max(0., y))})

    def duplicate(self, collection, identity):
        item = deepcopy(self.item(collection, identity))
        item.pop("id")
        item["name"] += " 副本"
        x = min(self.scene["width"] - (item["w"] if collection in ("buildings", "map_features") else 0), item["x"] + 12)
        y = min(self.scene["height"] - (item["h"] if collection in ("buildings", "map_features") else 0), item["y"] + 12)
        item = transform_shape(item, {"x": x, "y": y}) if collection in ("buildings", "map_features") else dict(item, x=x, y=y)
        return self.add(collection, item)

    def set_heights(self, height):
        height = finite(height, "楼高")
        if height < 0:
            raise ValueError("楼高须非负")
        def operation(scene):
            for item in scene["buildings"]:
                item.update(height=height, height_confirmed=True, height_source="用户手动批量填写")
        self.change(operation)

    def set_width(self, width):
        width = finite(width, "实际地图宽度")
        if width <= 0:
            raise ValueError("实际地图宽度须大于0")
        def operation(scene):
            factor = width / scene["width"]
            scene["width"] = width
            scene["height"] *= factor
            scene["step"] = max(1., width / 60)
            for collection in COLLECTIONS:
                for item in scene[collection]:
                    for field in ("x", "y", "w", "h", "rx", "ry"):
                        if field in item:
                            item[field] *= factor
                    if item.get("polygon"):
                        item["polygon"] = [[x*factor, y*factor] for x, y in item["polygon"]]
                        item["holes"] = [[[x*factor, y*factor] for x, y in r] for r in item.get("holes", [])]
            if "image_import" in scene:
                scene["image_import"]["scale_confirmed"] = True
        self.change(operation)

    def settings(self, values):
        values = {key: str(value).strip() if key == "source" else finite(value, key) for key, value in values.items()}
        if set(values) - {"source", "step", "clearance", "vertical_clearance"}:
            raise ValueError("未知地图参数")
        self.change(lambda scene: scene.update(values))

    def replace_buildings(self, buildings, recognition):
        def operation(scene):
            scene["buildings"] = deepcopy(buildings)
            scene.setdefault("image_import", {}).update(recognition)
        self.change(operation)

    def replace_recognition(self, buildings, features, recognition):
        def operation(scene):
            scene["buildings"] = deepcopy(buildings)
            scene["map_features"] = deepcopy(features)
            scene.setdefault("image_import", {}).update(recognition)
        self.change(operation)

    def convert_feature_to_building(self, identity):
        feature = deepcopy(self.item("map_features", identity))
        feature.pop("kind", None)
        used = {b["id"] for b in self.scene["buildings"]}
        number = 1
        while f"B{number}" in used:
            number += 1
        feature.update(id=f"B{number}", height=0., height_confirmed=False, height_source="待用户填写")
        def operation(scene):
            scene["map_features"] = [f for f in scene["map_features"] if f["id"] != identity]
            scene["buildings"].append(feature)
        self.change(operation)
        return feature["id"]

    def set_polygon(self, collection, identity, polygon):
        if collection not in ("buildings", "map_features"):
            raise ValueError("该组件没有区域轮廓")
        def operation(scene):
            item = next(i for i in scene[collection] if i["id"] == identity)
            item["polygon"] = deepcopy(polygon)
            if not polygon:
                raise ValueError("多边形轮廓不能为空")
            xs, ys = zip(*polygon)
            item.update(x=min(xs), y=min(ys), w=max(xs)-min(xs), h=max(ys)-min(ys))
        self.change(operation)

    def convert_building_to_feature(self, identity, kind):
        if kind not in FEATURE_TYPES:
            raise ValueError("地物类型无效")
        feature = deepcopy(self.item("buildings", identity))
        used = {f["id"] for f in self.scene["map_features"]}
        number = 1
        while f"F{number}" in used:
            number += 1
        for key in ("height", "height_confirmed", "height_source"):
            feature.pop(key, None)
        feature.update(id=f"F{number}", kind=kind)
        def operation(scene):
            scene["buildings"] = [b for b in scene["buildings"] if b["id"] != identity]
            scene["map_features"].append(feature)
        self.change(operation)
        return feature["id"]

    def undo(self):
        if self.undo_stack:
            self.redo_stack.append(self.scene)
            self.scene = self.undo_stack.pop()
            return True
        return False

    def redo(self):
        if self.redo_stack:
            self.undo_stack.append(self.scene)
            self.scene = self.redo_stack.pop()
            return True
        return False

    @property
    def pending_heights(self):
        return [item["id"] for item in self.scene["buildings"] if item.get("height_confirmed") is False]

    def ready_scene(self, config=None):
        from engine import create_scene
        return create_scene(config, self.scene)

    def save(self, path):
        path = Path(path)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent, prefix=".map-", suffix=".tmp", delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(self.scene, handle, ensure_ascii=False, indent=2)
            temporary.replace(path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
