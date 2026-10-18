"""Portable facility inputs shared by the planner, map editor and importers."""
from copy import deepcopy
import math

DEFAULT_LEVELS = [
    {"id": "standard", "name": "标准站", "cost": 100., "max_drones": 3,
     "takeoff_service": 25., "landing_service": 20.},
    {"id": "enhanced", "name": "增强站", "cost": 160., "max_drones": 10,
     "takeoff_service": 25., "landing_service": 20.},
]
DEFAULT_SOURCE = "演示假设：成本为相对单位，驻机上限和起降服务时间为模型设定；单站1个起降服务位，非实际工程报价"


def number(value, label, minimum=0., positive=False):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise ValueError(f"{label}须为有限数值")
    if value < minimum or positive and value <= 0:
        raise ValueError(f"{label}须{'大于0' if positive else '不小于'+str(minimum)}")
    return value


def facility_inputs(scene):
    raw = scene.get("facility_planning", {})
    if not isinstance(raw, dict):
        raise ValueError("分级场站参数须为对象")
    levels = deepcopy(raw.get("levels", DEFAULT_LEVELS))
    if not isinstance(levels, list) or not 1 <= len(levels) <= 4:
        raise ValueError("请配置1至4种场站等级")
    ids = set()
    for level in levels:
        if not isinstance(level, dict) or not isinstance(level.get("id"), str) or not level["id"].strip():
            raise ValueError("场站等级须有非空编号")
        identity = level["id"]
        if identity in ids or any(char in identity for char in ",，;+ "):
            raise ValueError("场站等级编号须唯一，不能含空格或分隔符")
        ids.add(identity)
        if not isinstance(level.get("name"), str) or not level["name"].strip():
            raise ValueError(f"等级{identity}须填写名称")
        number(level.get("cost"), f"等级{identity}成本")
        count = level.get("max_drones")
        if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 20:
            raise ValueError(f"等级{identity}驻机上限须为1至20的整数")
        for field in ("takeoff_service", "landing_service"):
            number(level.get(field), f"等级{identity}的{field}", positive=True)
    budget = number(raw.get("budget", 260.), "设施预算", positive=True)
    source = raw.get("parameter_source", DEFAULT_SOURCE)
    if not isinstance(source, str) or not source.strip():
        raise ValueError("请填写场站参数来源或演示假设")
    for pad in scene.get("pads", []):
        if not isinstance(pad, dict):
            raise ValueError("候选场站须为对象")
        allowed = pad.get("allowed_levels", list(ids))
        if not isinstance(allowed, list) or any(not isinstance(v, str) for v in allowed):
            raise ValueError(f"场站{pad.get('id','')}允许等级须为编号列表")
        if len(set(allowed)) != len(allowed) or not set(allowed) <= ids:
            raise ValueError(f"场站{pad.get('id','')}包含重复或未知的允许等级")
        number(pad.get("site_cost", 0.), f"场站{pad.get('id','')}场地附加成本")
    return {"levels": levels, "budget": budget, "parameter_source": source}


def validate_optional_facilities(scene):
    if "facility_planning" in scene or any("allowed_levels" in p or "site_cost" in p for p in scene.get("pads", []) if isinstance(p, dict)):
        facility_inputs(scene)
