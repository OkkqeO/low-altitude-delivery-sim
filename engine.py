"""Risk-aware routing, site selection and discrete-event delivery simulation.

Only the Python standard library is required. Coordinates are metres, times
are seconds. Exposure is a synthetic proxy, never an accident probability.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from itertools import combinations
from copy import deepcopy
import math
from pathlib import Path
from airspace import detect_conflicts, flight_segments, has_conflict
from map_import import load_scene_file
from map_geometry import FEATURE_TYPES, contains, validate_shape

ROOT = Path(__file__).resolve().parent
PLAN_NAMES = {"fixed": "固定布局", "distance": "距离优先", "combined": "综合风险"}
SCORE_WEIGHTS = {"mean_exposure": .45, "mean_delivery": .30,
                 "total_distance": .15, "mean_pad_waiting": .10}
DEFAULT_DESIGN_SEED = 20365744
Point = tuple[float, float]


@dataclass(frozen=True)
class Config:
    scenario: str = "normal"
    order_count: int = 30
    altitude: float = 45
    risk_weight: float = 2
    seed: int = 20261015
    drone_count: int = 5
    speed: float = 9
    takeoff_service: float = 25
    landing_service: float = 20
    delivery_service: float = 20
    deadline: float = 600
    deconflict: bool = True
    separation: float = 20
    departure_step: float = 5
    max_airspace_delay: float = 600

    def validated(self) -> Config:
        if self.scenario not in ("normal", "peak", "closure"):
            raise ValueError("场景必须为 normal、peak 或 closure")
        for key, value in asdict(self).items():
            if key not in ("scenario", "deconflict") and (isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)):
                raise ValueError(f"参数 {key} 必须是有限数值")
        if not isinstance(self.deconflict, bool):
            raise ValueError("deconflict 必须为布尔值")
        for key, low, high in (("order_count", 1, 200), ("drone_count", 1, 20), ("seed", 0, 2**32 - 1)):
            value = getattr(self, key)
            if not isinstance(value, int) or not low <= value <= high:
                raise ValueError(f"{key} 必须为 {low}—{high} 范围内的整数")
        if not 15 <= self.altitude <= 120 or not 0 <= self.risk_weight <= 20:
            raise ValueError("高度范围为15—120米，风险权重范围为0—20")
        if min(self.speed, self.takeoff_service, self.landing_service, self.deadline) <= 0 or self.delivery_service < 0:
            raise ValueError("速度、起降服务时间和时限须大于0，配送服务时间须非负")
        if not 0 < self.separation <= 200 or not 0 < self.departure_step <= 60 or not 0 <= self.max_airspace_delay <= 3600:
            raise ValueError("间距须为(0,200]米，错峰步长为(0,60]秒，最大额外等待为[0,3600]秒")
        if self.max_airspace_delay / self.departure_step > 10000:
            raise ValueError("错峰搜索超过1万次，请增大步长或缩短最大等待")
        return self


def random_generator(seed: int):
    """Mulberry32, matching the existing JavaScript prototype's order stream."""
    state = seed & 0xffffffff

    def random() -> float:
        nonlocal state
        state = (state + 0x6D2B79F5) & 0xffffffff
        t = ((state ^ (state >> 15)) * (state | 1)) & 0xffffffff
        t ^= (t + (((t ^ (t >> 7)) * (t | 61)) & 0xffffffff)) & 0xffffffff
        return ((t ^ (t >> 14)) & 0xffffffff) / 4294967296
    return random


def create_scene(config: Config | None = None, scene_path: str | Path | dict | None = None) -> dict:
    c = (config or Config()).validated()
    scene = deepcopy(scene_path) if isinstance(scene_path, dict) else load_scene_file(scene_path or ROOT / "data" / "demo_scene.json")
    for field in ("width", "height", "step", "clearance", "vertical_clearance"):
        value = scene.get(field)
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < 0:
            raise ValueError(f"场景字段 {field} 无效")
    if min(scene["width"], scene["height"], scene["step"]) <= 0:
        raise ValueError("场景尺寸和网格间距须大于0")
    if not isinstance(scene.get("image_import", {}), dict):
        raise ValueError("图片导入信息格式无效")
    if scene.get("image_import", {}).get("scale_confirmed") is False:
        raise ValueError("图片地图尚未校准尺度，请在地图编辑器的“地图”页填写实际宽度或两点定标")
    if (scene["width"] / scene["step"] + 1) * (scene["height"] / scene["step"] + 1) > 200000:
        raise ValueError("网格过密，请增大step，控制在20万个节点以内")
    scene.setdefault("map_features", [])
    for collection in ("pads", "deliveries", "buildings", "risk_zones", "map_features"):
        if not isinstance(scene.get(collection), list):
            raise ValueError(f"场景缺少列表 {collection}")
        ids = []
        for item in scene[collection]:
            if not isinstance(item, dict):
                raise ValueError(f"{collection} 中的每条记录须为对象")
            if collection == "buildings" and item.get("height_confirmed") is False:
                raise ValueError(f"建筑{item.get('name', item.get('id', ''))}的楼高尚未填写，请在地图编辑器中手动输入")
            fields = {"pads": ("x", "y"), "deliveries": ("x", "y", "demand"),
                      "buildings": ("x", "y", "w", "h", "height"),
                      "risk_zones": ("x", "y", "rx", "ry", "weight"), "map_features": ("x", "y", "w", "h")}[collection]
            for field in fields:
                value = item.get(field)
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
                    raise ValueError(f"{collection}.{field} 须为有限数值")
            if collection != "risk_zones":
                if not isinstance(item.get("id"), str) or not item["id"]:
                    raise ValueError(f"{collection} 中的对象须有非空字符串id")
                ids.append(item["id"])
                if not isinstance(item.get("name"), str) or not item["name"].strip():
                    item["name"] = item["id"]
            if not 0 <= item["x"] <= scene["width"] or not 0 <= item["y"] <= scene["height"]:
                raise ValueError(f"{collection} 的坐标超出场景范围")
            if collection == "deliveries" and item["demand"] <= 0:
                raise ValueError("配送点需求权重须大于0")
            if collection == "risk_zones" and (min(item["rx"], item["ry"]) <= 0 or item["weight"] < 0):
                raise ValueError("风险区半径须大于0，权重须非负")
            if collection == "buildings" and (min(item["w"], item["h"]) <= 0 or item["height"] < 0 or item["x"] + item["w"] > scene["width"] or item["y"] + item["h"] > scene["height"]):
                raise ValueError("建筑尺寸、高度或边界无效")
            if collection == "map_features" and (min(item["w"], item["h"]) <= 0
                    or item["x"]+item["w"] > scene["width"]+1e-7 or item["y"]+item["h"] > scene["height"]+1e-7
                    or item.get("kind") not in FEATURE_TYPES):
                raise ValueError("地物区域的尺寸、类型或边界无效")
            if collection in ("buildings", "map_features"):
                validate_shape(item, scene["width"], scene["height"])
        if len(set(ids)) != len(ids):
            raise ValueError(f"{collection} 存在重复id")
    if len(scene["pads"]) < 2 or not scene["deliveries"]:
        raise ValueError("场景至少需要两个候选场站及一个配送点")
    from facility_schema import validate_optional_facilities
    validate_optional_facilities(scene)
    scene["altitude"] = c.altitude
    scene["closure"] = ({"x": scene["width"] * 470 / 960, "y": scene["height"] * 200 / 640,
                         "w": scene["width"] * 75 / 960, "h": scene["height"] * 150 / 640}
                        if c.scenario == "closure" else None)
    if not isinstance(scene.get("source"), str) or not scene["source"].strip():
        scene["source"] = "用户提供的场景；请补充数据来源"
    if scene.get("map_presentation") == "schematic":
        from flight_map import schematic_scene
        scene = schematic_scene(scene)
    return scene


def inside_rect(point: Point, rect: dict, padding: float = 0) -> bool:
    x, y = point
    return rect["x"] - padding <= x <= rect["x"] + rect["w"] + padding and rect["y"] - padding <= y <= rect["y"] + rect["h"] + padding


def is_blocked(scene: dict, point: Point) -> bool:
    x, y = point
    if not 0 <= x <= scene["width"] or not 0 <= y <= scene["height"]:
        return True
    if scene["closure"] and inside_rect(point, scene["closure"], scene["clearance"]):
        return True
    return any(b["height"] + scene["vertical_clearance"] >= scene["altitude"] and contains(b, point, scene["clearance"]) for b in scene["buildings"])


def risk_at(scene: dict, point: Point) -> float:
    x, y = point
    return min(1., .035 + sum(z["weight"] * math.exp(-2 * ((x - z["x"])**2 / z["rx"]**2 + (y - z["y"])**2 / z["ry"]**2)) for z in scene["risk_zones"]))


def segment_clear(scene: dict, a: Point, b: Point) -> bool:
    """Sample a segment at <=3 m intervals; not an exact CAD collision test."""
    n = max(1, math.ceil(math.dist(a, b) / 3))
    return all(not is_blocked(scene, (a[0] + (b[0] - a[0]) * i / n,
                                      a[1] + (b[1] - a[1]) * i / n)) for i in range(n + 1))


def create_grid(scene: dict) -> dict:
    step = scene["step"]
    cols, rows = int(scene["width"] // step) + 1, int(scene["height"] // step) + 1
    return {"cols": cols, "rows": rows,
            "blocked": [is_blocked(scene, (x * step, y * step)) for y in range(rows) for x in range(cols)]}


class MinHeap:
    """Match prototype tie-breaking so equal-cost routes remain reproducible."""
    def __init__(self):
        self.items = []

    def push(self, value):
        a = self.items
        a.append(value)
        i = len(a) - 1
        while i > 0:
            parent = (i - 1) // 2
            if a[parent]["f"] <= value["f"]:
                break
            a[i], i = a[parent], parent
        a[i] = value

    def pop(self):
        a = self.items
        first, last = a[0], a.pop()
        if a:
            i = 0
            while True:
                child = i * 2 + 1
                if child >= len(a):
                    break
                if child + 1 < len(a) and a[child + 1]["f"] < a[child]["f"]:
                    child += 1
                if a[child]["f"] >= last["f"]:
                    break
                a[i], i = a[child], child
            a[i] = last
        return first

    def __bool__(self):
        return bool(self.items)


def nearest_node(scene: dict, grid: dict, point: Point) -> int:
    if is_blocked(scene, point):
        return -1
    step, cols, rows = scene["step"], grid["cols"], grid["rows"]
    gx, gy = (math.floor(v / step + .5) for v in point)
    choices = []
    for dy in range(-2, 3):
        for dx in range(-2, 3):
            x, y = gx + dx, gy + dy
            if 0 <= x < cols and 0 <= y < rows:
                node = y * cols + x
                p = (x * step, y * step)
                if not grid["blocked"][node] and segment_clear(scene, point, p):
                    choices.append((math.dist(point, p), node))
    return min(choices)[1] if choices else -1


def measure_path(scene: dict, points: list[Point]) -> dict:
    distance, exposure, cumulative = 0., 0., [0.]
    for a, b in zip(points, points[1:]):
        length = math.dist(a, b)
        distance += length
        exposure += length * risk_at(scene, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2))
        cumulative.append(distance)
    return {"points": points, "distance": distance, "exposure": exposure, "cumulative": cumulative}


def astar(scene: dict, start: Point, goal: Point, risk_weight: float = 2,
          grid: dict | None = None) -> dict | None:
    if not math.isfinite(risk_weight) or risk_weight < 0:
        raise ValueError("风险权重须为非负有限数值")
    grid = grid or create_grid(scene)
    cols, rows, blocked = grid["cols"], grid["rows"], grid["blocked"]
    start_id, goal_id = nearest_node(scene, grid, start), nearest_node(scene, grid, goal)
    if min(start_id, goal_id) < 0:
        return None
    step = scene["step"]
    goal_x, goal_y = goal_id % cols, goal_id // cols

    def heuristic(x, y):
        return math.hypot(goal_x - x, goal_y - y) * step

    costs, parents, closed = [math.inf] * (cols * rows), [-1] * (cols * rows), set()
    costs[start_id] = 0.
    heap = MinHeap()
    heap.push({"id": start_id, "g": 0., "f": heuristic(start_id % cols, start_id // cols)})
    directions = ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1))
    while heap:
        cur = heap.pop()
        if cur["id"] in closed or cur["g"] > costs[cur["id"]] + 1e-9:
            continue
        if cur["id"] == goal_id:
            route, node = [], goal_id
            while node != -1:
                route.append((node % cols * step, node // cols * step))
                node = parents[node]
            raw = [tuple(start), *reversed(route), tuple(goal)]
            points = [p for i, p in enumerate(raw) if i == 0 or math.dist(p, raw[i - 1]) > 1e-9]
            return measure_path(scene, points)
        closed.add(cur["id"])
        x, y = cur["id"] % cols, cur["id"] // cols
        for dx, dy in directions:
            nx, ny = x + dx, y + dy
            if not 0 <= nx < cols or not 0 <= ny < rows:
                continue
            node = ny * cols + nx
            if blocked[node] or node in closed:
                continue
            if dx and dy and (blocked[y * cols + nx] or blocked[ny * cols + x]):
                continue
            a, b = (x * step, y * step), (nx * step, ny * step)
            if not segment_clear(scene, a, b):
                continue
            g = cur["g"] + math.hypot(dx, dy) * step * (1 + risk_weight * risk_at(scene, ((a[0] + b[0]) / 2, (a[1] + b[1]) / 2)))
            if g + 1e-9 < costs[node]:
                costs[node], parents[node] = g, cur["id"]
                heap.push({"id": node, "g": g, "f": g + heuristic(nx, ny)})
    return None


def xy(item: dict) -> Point:
    return item["x"], item["y"]


def route_catalog(scene: dict, config: Config) -> dict:
    grid = create_grid(scene)
    return {f"{p['id']}:{d['id']}": astar(scene, xy(p), xy(d), config.risk_weight, grid)
            for p in scene["pads"] for d in scene["deliveries"]}


def generate_orders(scene: dict, config: Config, seed: int | None = None) -> list[dict]:
    c = config.validated()
    rng = random_generator(c.seed if seed is None else seed)
    count, span = (c.order_count * 2, 800) if c.scenario == "peak" else (c.order_count, 1200)
    total_demand = sum(d["demand"] for d in scene["deliveries"])
    orders = []
    for i in range(count):
        pick, destination = rng() * total_demand, scene["deliveries"][-1]
        for d in scene["deliveries"]:
            pick -= d["demand"]
            if pick <= 0:
                destination = d
                break
        created = math.floor(rng() * span)
        orders.append({"id": f"O{i + 1:03d}", "destination_id": destination["id"],
                       "created_at": created, "due_at": created + c.deadline})
    return sorted(orders, key=lambda o: (o["created_at"], o["id"]))


def earliest_slot(calendar: list[dict], ready: float, duration: float) -> float:
    begin = ready
    for entry in calendar:
        if begin + duration <= entry["start"] + 1e-8:
            break
        if begin < entry["end"] - 1e-8:
            begin = entry["end"]
    return begin


def simulate(scene: dict, config: Config, pad_ids: list[str], orders: list[dict],
             routes: dict | None = None, fleet_allocation: dict | None = None,
             pad_services: dict | None = None) -> dict:
    c = config.validated()
    known_pads = {p["id"] for p in scene["pads"]}
    if not pad_ids or len(set(pad_ids)) != len(pad_ids) or not set(pad_ids) <= known_pads:
        raise ValueError("起降场布局无效")
    routes = routes if routes is not None else route_catalog(scene, c)
    calendars = {pad: [] for pad in pad_ids}
    if fleet_allocation is None:
        assignments = [pad_ids[i % len(pad_ids)] for i in range(c.drone_count)]
    else:
        if (not isinstance(fleet_allocation, dict) or set(fleet_allocation) != set(pad_ids)
                or any(isinstance(n, bool) or not isinstance(n, int) or n < 1 for n in fleet_allocation.values())
                or sum(fleet_allocation.values()) != c.drone_count):
            raise ValueError("机队配比须覆盖所选场站，每站至少1架且合计等于无人机总数")
        assignments = [pad for i in range(max(fleet_allocation.values())) for pad in pad_ids if i < fleet_allocation[pad]]
    services = {pad: {"takeoff_service": c.takeoff_service, "landing_service": c.landing_service} for pad in pad_ids}
    if pad_services is not None:
        if not isinstance(pad_services, dict) or set(pad_services) != set(pad_ids):
            raise ValueError("场站服务参数须覆盖所选场站")
        for pad, values in pad_services.items():
            if not isinstance(values, dict) or set(values) != {"takeoff_service", "landing_service"}:
                raise ValueError("场站服务须包含起飞和降落时间")
            for field, value in values.items():
                if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
                    raise ValueError("场站起降服务时间须为正有限数值")
            services[pad] = values
    drones = [{"id": f"U{i + 1}", "pad_id": pad, "available_at": 0.} for i, pad in enumerate(assignments)]
    jobs, failed, events, accepted_air = [], [], [], []
    for order in sorted(orders, key=lambda o: (o["created_at"], o["id"])):
        best = None
        has_route = False
        for drone in drones:
            key = f"{drone['pad_id']}:{order['destination_id']}"
            route = routes.get(key)
            if route is None:
                continue
            has_route = True
            ready = max(order["created_at"], drone["available_at"])
            calendar = calendars[drone["pad_id"]]
            takeoff = services[drone["pad_id"]]["takeoff_service"]
            landing = services[drone["pad_id"]]["landing_service"]
            baseline_prep = earliest_slot(calendar, ready, takeoff)
            requested_prep, candidate = baseline_prep, None
            while requested_prep <= baseline_prep + c.max_airspace_delay + 1e-8:
                prep = earliest_slot(calendar, requested_prep, takeoff)
                if c.deconflict and prep - baseline_prep > c.max_airspace_delay + 1e-8:
                    break
                depart = prep + takeoff
                arrived = depart + route["distance"] / c.speed
                delivered = arrived + c.delivery_service
                returned = delivered + route["distance"] / c.speed
                land = earliest_slot(calendar, returned, landing)
                trial = {"order_id": order["id"], "drone_id": drone["id"], "pad_id": drone["pad_id"],
                         "destination_id": order["destination_id"], "route_key": key,
                         "created_at": order["created_at"], "due_at": order["due_at"], "ready": ready,
                         "prep_start": prep, "depart": depart, "arrived_dest": arrived,
                         "delivered_at": delivered, "return_start": delivered, "return_arrival": returned,
                         "land_start": land, "end": land + landing,
                         "distance": route["distance"] * 2, "exposure": route["exposure"] * 2 / 100,
                         "pad_waiting": baseline_prep - ready + land - returned,
                         "airspace_delay": prep - baseline_prep}
                if not c.deconflict or not has_conflict(flight_segments(trial, route, c.speed), accepted_air, drone["id"], c.separation):
                    candidate = trial
                    break
                requested_prep = prep + c.departure_step
            if candidate is None:
                continue
            delivered = candidate["delivered_at"]
            if best is None or delivered < best["delivered_at"] - 1e-8 or (abs(delivered - best["delivered_at"]) < 1e-8 and drone["id"] < best["drone_id"]):
                best = candidate
        if best is None:
            reason = "airspace_delay_limit" if has_route else "unreachable"
            failed.append({**order, "failure_type": reason, "reason":
                           f"在{c.max_airspace_delay:g}秒最大额外等待内未找到无冲突出发时隙" if has_route else "所选场站到配送点无可通行航路"})
            events.append({"time": order["created_at"], "type": "failed", "order_id": order["id"]})
            continue
        chosen_service = services[best["pad_id"]]
        for start, duration, operation in ((best["prep_start"], chosen_service["takeoff_service"], "takeoff"), (best["land_start"], chosen_service["landing_service"], "landing")):
            calendars[best["pad_id"]].append({"start": start, "end": start + duration, "order_id": order["id"], "operation": operation})
        calendars[best["pad_id"]].sort(key=lambda entry: entry["start"])
        next(d for d in drones if d["id"] == best["drone_id"])["available_at"] = best["end"]
        jobs.append(best)
        if c.deconflict:
            accepted_air.append((best, flight_segments(best, routes[best["route_key"]], c.speed)))
        for event_type, field in (("created", "created_at"), ("preparing", "prep_start"), ("departed", "depart"), ("delivered", "delivered_at"), ("returned", "return_arrival"), ("ready", "end")):
            events.append({"type": event_type, "time": best[field], "order_id": order["id"], "drone_id": best["drone_id"], "pad_id": best["pad_id"], "destination_id": best["destination_id"]})
    n, total = len(jobs), len(orders)
    total_distance, total_exposure = sum(j["distance"] for j in jobs), sum(j["exposure"] for j in jobs)
    # Audit the finished schedule independently, including baseline conflicts.
    conflicts = detect_conflicts(jobs, routes, c.speed, c.separation)
    stats = {"total_orders": total, "delivered_orders": n, "failed_orders": len(failed),
             "total_distance": total_distance, "total_exposure": total_exposure,
             "mean_exposure": total_exposure / n if n else None,
             "mean_delivery": sum(j["delivered_at"] - j["created_at"] for j in jobs) / n if n else None,
             "mean_pad_waiting": sum(j["pad_waiting"] for j in jobs) / n if n else None,
             "mean_airspace_delay": sum(j["airspace_delay"] for j in jobs) / n if n else None,
             "air_conflict_count": len(conflicts),
             "air_conflict_pair_count": len({(e["order_a"], e["order_b"]) for e in conflicts}),
             "air_conflict_duration": sum(e["end"] - e["start"] for e in conflicts),
             "airspace_failed_orders": sum(o["failure_type"] == "airspace_delay_limit" for o in failed),
             "unreachable_orders": sum(o["failure_type"] == "unreachable" for o in failed),
             "on_time_rate": sum(j["delivered_at"] <= j["due_at"] + 1e-8 for j in jobs) / total if total else 0,
             "completion_rate": n / total if total else 0,
             "duration": max([1., *[j["end"] for j in jobs], *[o["created_at"] for o in failed]])}
    delivery_times = sorted(j["delivered_at"] - j["created_at"] for j in jobs)
    stats.update(
        late_orders=sum(j["delivered_at"] > j["due_at"] + 1e-8 for j in jobs),
        p95_delivery=delivery_times[math.ceil(.95*n)-1] if n else None,
        mean_tardiness=sum(max(0., j["delivered_at"]-j["due_at"]) for j in jobs)/n if n else None,
        mean_drone_wait=sum(j["ready"]-j["created_at"] for j in jobs)/n if n else None,
        mean_takeoff_wait=sum(j["prep_start"]-j["ready"]-j["airspace_delay"] for j in jobs)/n if n else None,
        mean_landing_wait=sum(j["land_start"]-j["return_arrival"] for j in jobs)/n if n else None)
    return {"pad_ids": list(pad_ids), "orders": orders, "jobs": jobs, "failed": failed, "conflicts": conflicts,
            "events": sorted(events, key=lambda e: (e["time"], e["order_id"])), "calendars": calendars,
            "drones": [{"id": d["id"], "pad_id": d["pad_id"]} for d in drones], "stats": stats}


def build_design(config: Config | None = None, scene_path: str | Path | dict | None = None,
                 design_seed: int = DEFAULT_DESIGN_SEED) -> dict:
    """Select sites on design orders only. Reuse this design for all test seeds."""
    c = (config or Config()).validated()
    if not isinstance(design_seed, int) or isinstance(design_seed, bool) or not 0 <= design_seed < 2**32:
        raise ValueError("设计种子须为32位非负整数")
    scene = create_scene(c, scene_path)
    routes = route_catalog(scene, c)
    orders = generate_orders(scene, c, design_seed)
    feasible = [p["id"] for p in scene["pads"] if not is_blocked(scene, xy(p))]
    # Keep site design independent of the operational safety toggle. Paired
    # experiments therefore isolate dispatch changes on identical layouts.
    design_config = replace(c, deconflict=False)
    candidates = [{"pad_ids": list(pair), "stats": simulate(scene, design_config, list(pair), orders, routes)["stats"]} for pair in combinations(feasible, 2)]
    if not candidates:
        raise ValueError("当前高度与空域条件下不足两个可用起降场")
    ranges = {}
    for field in SCORE_WEIGHTS:
        values = [p["stats"][field] for p in candidates if p["stats"][field] is not None]
        ranges[field] = (min(values), max(values)) if values else (0., 1.)

    def normalize(value, field):
        if value is None:
            return 1.
        low, high = ranges[field]
        return 0. if high - low < 1e-9 else (value - low) / (high - low)

    for candidate in candidates:
        stats = candidate["stats"]
        penalty = stats["failed_orders"] * 1000
        candidate["combined_score"] = penalty + sum(weight * normalize(stats[field], field) for field, weight in SCORE_WEIGHTS.items())
        candidate["distance_score"] = penalty + normalize(stats["total_distance"], "total_distance")
    combined = min(candidates, key=lambda p: (p["combined_score"], ",".join(p["pad_ids"])))
    distance = min(candidates, key=lambda p: (p["distance_score"], ",".join(p["pad_ids"])))
    fixed = [pad for pad in ("S1", "S5") if pad in feasible]
    fixed += [pad for pad in feasible if pad not in fixed][:2 - len(fixed)]
    return {"config": c, "scene": scene, "routes": routes, "design_seed": design_seed,
            "design_dispatch": "baseline", "candidates": candidates,
            "choices": {"fixed": fixed, "distance": distance["pad_ids"], "combined": combined["pad_ids"]}}


def evaluate_design(design: dict, seed: int | None = None, deconflict: bool | None = None) -> dict:
    c = design["config"] if seed is None else replace(design["config"], seed=seed).validated()
    if deconflict is not None:
        c = replace(c, deconflict=deconflict).validated()
    if c.seed == design["design_seed"]:
        raise ValueError("评价种子不能与设计种子相同，请使用独立订单")
    scene, routes = design["scene"], design["routes"]
    orders = generate_orders(scene, c)
    plans = {key: {"key": key, "name": PLAN_NAMES[key], **simulate(scene, c, pads, orders, routes)} for key, pads in design["choices"].items()}
    return {"version": "0.4.0-python", "calculated_at": datetime.now(timezone.utc).isoformat(),
            "config": asdict(c), "scene": scene, "routes": routes, "design_seed": design["design_seed"],
            "evaluation_seed": c.seed, "score_weights": SCORE_WEIGHTS, "candidate_count": len(design["candidates"]),
            "design_dispatch": design["design_dispatch"],
            "candidates": design["candidates"], "plans": plans,
            "assumptions": ["地图数据来源见scene.source；订单为随机生成的仿真数据", "风险为地面人员暴露代理值，不是事故概率",
                            f"固定巡航高度；{scene['vertical_clearance']:g}米垂直间距、{scene['clearance']:g}米平面间距为模型参数，非监管标准",
                            "三种方案共用评价订单、航路规划与最早送达调度", "每场站一个起降服务位；无人机任务不重叠",
                            "设计种子固定；跨评价种子复用选址结果", "关闭区域在整次运行中生效",
                            "选址使用基线调度的设计订单；错峰开关不改变站点布局",
                            "连续时间检查同高度线性轨迹间距，包含配送悬停与返场等待；起飞准备与降落服务视为地面阶段",
                            "错峰按离散步长搜索起飞时隙，超出额外等待上限的订单明确计为失败",
                            "间距阈值为仿真参数，尚未模拟真实动力学、天气、电池、爬升下降与在途重规划"]}


def evaluate_plans(config: Config | None = None, scene_path: str | Path | dict | None = None,
                   design_seed: int = DEFAULT_DESIGN_SEED) -> dict:
    return evaluate_design(build_design(config, scene_path, design_seed))


def point_on_route(route: dict, progress: float) -> dict:
    target = min(1., max(0., progress)) * route["distance"]
    for i, (a, b) in enumerate(zip(route["points"], route["points"][1:]), 1):
        if route["cumulative"][i] >= target:
            segment = route["cumulative"][i] - route["cumulative"][i - 1]
            ratio = (target - route["cumulative"][i - 1]) / segment if segment else 0
            return {"x": a[0] + (b[0] - a[0]) * ratio, "y": a[1] + (b[1] - a[1]) * ratio,
                    "angle": math.atan2(b[1] - a[1], b[0] - a[0])}
    return {"x": route["points"][-1][0], "y": route["points"][-1][1], "angle": 0.}


def drone_at_time(result: dict, plan_key: str, drone_id: str, time: float) -> dict:
    plan = result["plans"][plan_key]
    drone = next(d for d in plan["drones"] if d["id"] == drone_id)
    pad = next(p for p in result["scene"]["pads"] if p["id"] == drone["pad_id"])
    job = next((j for j in plan["jobs"] if j["drone_id"] == drone_id and j["prep_start"] <= time < j["end"]), None)
    stationary = {"x": pad["x"], "y": pad["y"], "angle": 0., "drone_id": drone_id}
    if job is None:
        return {**stationary, "state": "idle"}
    route = result["routes"][job["route_key"]]
    if time < job["depart"]:
        return {**stationary, "state": "preparing"}
    if time < job["arrived_dest"]:
        point = point_on_route(route, (time - job["depart"]) / (job["arrived_dest"] - job["depart"]))
        return {**point, "state": "outbound", "drone_id": drone_id}
    if time < job["return_start"]:
        return {"x": route["points"][-1][0], "y": route["points"][-1][1], "angle": 0., "state": "delivery", "drone_id": drone_id}
    if time < job["return_arrival"]:
        point = point_on_route(route, 1 - (time - job["return_start"]) / (job["return_arrival"] - job["return_start"]))
        return {**point, "angle": point["angle"] + math.pi, "state": "returning", "drone_id": drone_id}
    return {**stationary, "state": "landing"}
