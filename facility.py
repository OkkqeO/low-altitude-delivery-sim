"""Simulation-driven selection of two graded facilities and a fixed-size fleet.

One configuration is frozen for both normal and peak independent evaluation.
Only the standard library is required. Existing simulation remains the audit.
"""
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
from itertools import combinations, product
import math
import hashlib
from pathlib import Path
import statistics
import time

from engine import Config, DEFAULT_DESIGN_SEED, build_design, create_scene, generate_orders, simulate
from facility_schema import facility_inputs, number
from reporting import export_result, write_csv, write_json

FACILITY_NAMES = {"fixed": "预算基线", "distance": "配比优化", "combined": "分级联合优化"}
SCENARIOS = ("normal", "peak")
MAX_CONFIGURATIONS = 5000


def training_seeds(design_seed, count=3):
    if isinstance(design_seed, bool) or not isinstance(design_seed, int) or not 0 <= design_seed < 2**32:
        raise ValueError("设计种子须为32位非负整数")
    if isinstance(count, bool) or not isinstance(count, int) or not 1 <= count <= 5:
        raise ValueError("设计种子数须为1至5的整数")
    return [(design_seed+i*104729) % 2**32 for i in range(count)]


class PlanningCancelled(Exception):
    pass


def check_cancel(cancel):
    if cancel is not None and cancel():
        raise PlanningCancelled("已取消分级选址计算")


def configurations(scene, config, budget):
    inputs = facility_inputs(scene)
    number(budget, "设施预算", positive=True)
    levels = {v["id"]: v for v in inputs["levels"]}
    from engine import is_blocked, xy
    pads = [p for p in scene["pads"] if not is_blocked(scene, xy(p))]
    output = []
    for a, b in combinations(pads, 2):
        for ka, kb in product(a.get("allowed_levels", levels), b.get("allowed_levels", levels)):
            la, lb = levels[ka], levels[kb]
            cost = la["cost"] + lb["cost"] + a.get("site_cost", 0.) + b.get("site_cost", 0.)
            if cost > budget + 1e-8:
                continue
            for na in range(1, config.drone_count):
                nb = config.drone_count-na
                if na > la["max_drones"] or nb > lb["max_drones"]:
                    continue
                output.append({"pad_ids": [a["id"], b["id"]], "levels": {a["id"]: ka, b["id"]: kb},
                               "fleet_allocation": {a["id"]: na, b["id"]: nb}, "cost": cost,
                               "pad_services": {a["id"]: {k: la[k] for k in ("takeoff_service", "landing_service")},
                                                b["id"]: {k: lb[k] for k in ("takeoff_service", "landing_service")}}})
                if len(output) > MAX_CONFIGURATIONS:
                    raise ValueError(f"可行配置超过{MAX_CONFIGURATIONS}种，请减少候选点或等级数量后再计算")
    if not output:
        raise ValueError("预算、允许等级和驻机上限下无可行的两站配置；请调整预算或机队数量（至少2架）")
    return output


def configuration_label(candidate, levels):
    names = {v["id"]: v["name"] for v in levels}
    return " + ".join(f"{p} {names[candidate['levels'][p]]} {candidate['fleet_allocation'][p]}架" for p in candidate["pad_ids"])


def _tie(candidate):
    return (candidate["cost"], tuple(candidate["pad_ids"]), tuple(candidate["levels"].values()),
            tuple(candidate["fleet_allocation"].values()))


def _objective(stats):
    # Equal weight per scenario. Missing successful-order metrics use zero only
    # after failure rate has ranked the candidate; no Infinity in saved JSON.
    return [statistics.mean(s["failed_orders"]/s["total_orders"] for s in stats),
            statistics.mean(1-s["on_time_rate"] for s in stats),
            statistics.mean((s["mean_tardiness"] or 0.)*s["delivered_orders"]/s["total_orders"] for s in stats),
            statistics.mean((s["mean_delivery"] or 0.) + 30*(s["mean_exposure"] or 0.) for s in stats)]


def build_facility_design(config=None, scene_path=None, budget=None, design_seed=DEFAULT_DESIGN_SEED,
                          progress=None, cancel=None, design_seed_count=3):
    start = time.perf_counter()
    c = replace(config or Config(), scenario="normal").validated()
    if not c.deconflict:
        raise ValueError("分级选址第一版须开启错峰，所有配置使用同一间距约束")
    if c.drone_count < 2:
        raise ValueError("分级选址需要至少2架无人机，每站至少1架")
    design_seeds = training_seeds(design_seed, design_seed_count)
    check_cancel(cancel)
    if progress:
        progress(0, 0, "正在建立航路与预算基线……")
    # Reject infeasible / oversized searches before building expensive routes.
    scene = create_scene(c, scene_path)
    inputs = facility_inputs(scene)
    budget = inputs["budget"] if budget is None else number(budget, "设施预算", positive=True)
    scene["facility_planning"] = {**inputs, "budget": budget}
    candidates = configurations(scene, c, budget)
    # Legacy design supplies baseline scoring; only participating pads need routes.
    participating = {p for v in candidates for p in v["pad_ids"]}
    active_scene = deepcopy(scene)
    active_scene["pads"] = [p for p in scene["pads"] if p["id"] in participating]
    legacy = build_design(c, active_scene, design_seed)
    routes = legacy["routes"]
    legacy_scores = {tuple(v["pad_ids"]): v["combined_score"] for v in legacy["candidates"]}
    # Nearest-to-balanced allocation, legacy layout score, then least cost.
    baseline = min(candidates, key=lambda p: (abs(next(iter(p["fleet_allocation"].values()))-math.ceil(c.drone_count/2)),
                                              legacy_scores[tuple(p["pad_ids"])], _tie(p)))
    orders = {(seed, s): generate_orders(scene, replace(c, scenario=s), seed) for seed in design_seeds for s in SCENARIOS}
    cache = {}
    for i, candidate in enumerate(candidates):
        check_cancel(cancel)
        signature = (tuple(candidate["pad_ids"]), tuple(candidate["fleet_allocation"].values()),
                     tuple(tuple(v.values()) for v in candidate["pad_services"].values()))
        if signature not in cache:
            stats = {s: [] for s in SCENARIOS}
            for seed, scenario in product(design_seeds, SCENARIOS):
                check_cancel(cancel)
                run = simulate(scene, replace(c, scenario=scenario), candidate["pad_ids"], orders[seed, scenario], routes,
                               candidate["fleet_allocation"], candidate["pad_services"])
                stats[scenario].append(run["stats"])
            cache[signature] = stats
        samples = cache[signature]
        candidate["design_stats"] = {s: {k: statistics.mean(v[k] for v in samples[s] if v[k] is not None)
                                               if any(v[k] is not None for v in samples[s]) else None
                                         for k in samples[s][0]} for s in SCENARIOS}
        candidate["objective"] = _objective([v for scenario in SCENARIOS for v in samples[scenario]])
        if progress:
            progress(i+1, len(candidates), f"已评价{i+1}/{len(candidates)}种配置（正常＋高峰）")
    allocation_candidates = [p for p in candidates if p["pad_ids"] == baseline["pad_ids"] and p["levels"] == baseline["levels"]]
    allocation = min(allocation_candidates, key=lambda p: (p["objective"], _tie(p)))
    joint = min(candidates, key=lambda p: (p["objective"], _tie(p)))
    return {"config": c, "scene": scene, "routes": routes, "budget": budget, "design_seed": design_seed,
            "inputs": inputs, "candidates": candidates,
            "choices": {"fixed": baseline, "distance": allocation, "combined": joint},
            "design_seeds": design_seeds,
            "design_seconds": time.perf_counter()-start, "simulation_configurations": len(cache)}


def evaluate_facility_design(design, seed=None, scenario="normal", cancel=None):
    if scenario not in SCENARIOS:
        raise ValueError("分级设施评价场景须为normal或peak")
    c = replace(design["config"], scenario=scenario, seed=design["config"].seed if seed is None else seed).validated()
    if c.seed in design["design_seeds"]:
        raise ValueError("评价种子不能与任何设计种子相同")
    orders = generate_orders(design["scene"], c)
    plans = {}
    for key, candidate in design["choices"].items():
        check_cancel(cancel)
        run = simulate(design["scene"], c, candidate["pad_ids"], orders, design["routes"],
                       candidate["fleet_allocation"], candidate["pad_services"])
        plans[key] = {**run, "key": key, "name": FACILITY_NAMES[key],
                      "facility_configuration": {k: deepcopy(v) for k, v in candidate.items() if k not in ("design_stats", "objective")},
                      "configuration_label": configuration_label(candidate, design["inputs"]["levels"])}
    return {"version": "0.6.0-facility", "calculated_at": datetime.now(timezone.utc).isoformat(),
            "config": asdict(c), "scene": design["scene"], "routes": design["routes"],
            "design_seed": design["design_seed"], "evaluation_seed": c.seed,
            "candidate_count": len(design["candidates"]), "plans": plans,
            "facility_design": {"budget": design["budget"], "levels": design["inputs"]["levels"],
                                "design_seeds": design["design_seeds"],
                                "parameter_source": design["inputs"]["parameter_source"],
                                "design_scenarios": list(SCENARIOS), "configuration_frozen": True},
            "assumptions": ["固定两个配送无人机起降场、单站一个起降服务位；无人机固定归属场站",
                            "订单可由任意已选站发出；无库存、补货或站间运输模型",
                            "设施成本为相对单位；来源和等级服务参数见facility_design",
                            f"设计种子{design['design_seeds']}，正常和高峰各50%评价；独立评价冻结站点、等级与机队配比",
                            "目标依次最小化失败率、非准时率、每单超时秒数，再比较配送秒数+30×路径暴露",
                            "配比优化固定预算基线的站点、等级与成本；联合优化受同一预算上限约束，实际花费需同时报告",
                            "固定巡航高度、理想匀速折线与悬停；间距为模型参数，路径暴露为代理指标"]}


def study_rows(results):
    rows = []
    for result in results:
        for key, plan in result["plans"].items():
            cfg = plan["facility_configuration"]
            rows.append({"scenario": result["config"]["scenario"], "evaluation_seed": result["evaluation_seed"],
                         "design_seed": result["design_seed"], "plan": key, "plan_name": plan["name"],
                         "configuration": plan["configuration_label"], "cost": cfg["cost"],
                         "budget": result["facility_design"]["budget"], **plan["stats"]})
    return rows


def study_summary(rows):
    output = []
    fields = ("mean_delivery", "p95_delivery", "on_time_rate", "completion_rate", "late_orders", "failed_orders",
              "mean_exposure", "mean_drone_wait", "mean_takeoff_wait", "mean_landing_wait", "mean_airspace_delay",
              "air_conflict_count", "mean_tardiness", "total_distance")
    for scenario, key in product(SCENARIOS, FACILITY_NAMES):
        group = [r for r in rows if r["scenario"] == scenario and r["plan"] == key]
        if not group:
            continue
        row = {k: group[0][k] for k in ("scenario", "plan", "plan_name", "configuration", "cost", "budget")}
        row["runs"] = len(group)
        for field in fields:
            values = [r[field] for r in group if r[field] is not None]
            row[field] = statistics.mean(values) if values else None
            row[field+"_std"] = statistics.stdev(values) if len(values)>1 else (0. if values else None)
            row[field+"_valid_runs"] = len(values)
        output.append(row)
    return output


def run_facility_study(config=None, scene_path=None, budget=None, seeds=None, design_seed=DEFAULT_DESIGN_SEED,
                       progress=None, cancel=None, design_seed_count=3):
    c = (config or Config()).validated()
    seeds = list(seeds if seeds is not None else [c.seed])
    design_seeds = training_seeds(design_seed, design_seed_count)
    if (not seeds or len(seeds) != len(set(seeds))
            or any(isinstance(s, bool) or not isinstance(s, int) or not 0 <= s < 2**32 or s in design_seeds for s in seeds)):
        raise ValueError("评价种子须为互不重复的32位非负整数，且与设计种子不同")
    design = build_facility_design(c, scene_path, budget, design_seed, progress, cancel, design_seed_count)
    results = []
    for i, (seed, scenario) in enumerate(product(seeds, SCENARIOS)):
        check_cancel(cancel)
        if progress:
            progress(i, len(seeds)*2, f"独立评价：种子{seed}，{'正常' if scenario=='normal' else '高峰'}订单")
        results.append(evaluate_facility_design(design, seed, scenario, cancel))
    raw = study_rows(results)
    return {"version": "0.6.0-facility", "budget": design["budget"], "design_seed": design_seed,
            "design_seeds": design_seeds,
            "evaluation_seeds": seeds, "scene": design["scene"], "base_config": asdict(c),
            "design_seconds": design["design_seconds"], "candidate_count": len(design["candidates"]),
            "simulation_configurations": design["simulation_configurations"],
            "choices": deepcopy(design["choices"]), "candidates": design["candidates"],
            "results": results, "raw_metrics": raw, "summary": study_summary(raw)}


def study_report(study):
    def fmt(value, scale=1):
        return "—" if value is None else f"{value*scale:.2f}"
    lines = ["# 分级起降场选址与容量配置：独立评价", "",
             f"预算上限：{study['budget']:g}相对单位；设计种子：{study['design_seeds']}；评价种子：{study['evaluation_seeds']}。",
             f"可行配置{study['candidate_count']}种，去除等效服务配置后实际仿真{study['simulation_configurations']}种；设计耗时{study['design_seconds']:.2f}秒。", "",
             "同一套设施在正常与高峰评价中冻结。配比优化与预算基线使用相同站点、等级和实际成本；联合优化使用同一预算上限，实际成本单独报告。", "",
             "|场景|方案|设施与机队|成本|准时率|配送秒数|每次运行P95的均值/秒|暴露|失败数均值|间距事件均值|",
             "|---|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for r in study["summary"]:
        lines.append(f"|{'正常' if r['scenario']=='normal' else '高峰'}|{r['plan_name']}|{r['configuration']}|{r['cost']:g}|{fmt(r['on_time_rate'],100)}%|{fmt(r['mean_delivery'])}|{fmt(r['p95_delivery'])}|{fmt(r['mean_exposure'])}|{fmt(r['failed_orders'])}|{fmt(r['air_conflict_count'])}|")
    lines += ["", "均值按运行等权计算；P95采用成功订单的最近秩分位数，跨种子报告每次运行P95的均值；请同时检查失败数与完成率。样本标准差和有效运行数见summary.csv。", "",
              "## 等待分解（秒/成功订单）", "", "|场景|方案|等待无人机|起飞位排队|额外错峰|返场排队|", "|---|---|---:|---:|---:|---:|"]
    for r in study["summary"]:
        lines.append(f"|{'正常' if r['scenario']=='normal' else '高峰'}|{r['plan_name']}|{fmt(r['mean_drone_wait'])}|{fmt(r['mean_takeoff_wait'])}|{fmt(r['mean_airspace_delay'])}|{fmt(r['mean_landing_wait'])}|")
    lines += ["", "等待无人机包含前序任务各阶段的传导影响；返场排队影响下一次任务，不能直接加到本次配送送达时间中。", "",
              "## 参数与结论范围", "", study["scene"]["facility_planning"]["parameter_source"], "",
              "等级、预算和需求设定均需人工核实。当前为固定高度的园区配送研究仿真；所有订单可由任意已选站发出。目标依次比较失败率、非准时率、超时秒数，再比较配送时间+30×暴露；正常和高峰等权。没有滚动调度、多起降位、库存或站间运输。", "",
              "模型、代码及材料使用生成式AI辅助编写；本报告数值由实际运行结果汇总，需人工审查参数与适用范围。"]
    return "\n".join(lines)+"\n"


def export_facility_study(study, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output/"study.json", study)
    write_json(output/"scene.json", study["scene"])
    write_csv(output/"raw_metrics.csv", study["raw_metrics"])
    write_csv(output/"summary.csv", study["summary"])
    candidate_rows = []
    for i, candidate in enumerate(study["candidates"]):
        row = {"index": i, "configuration": configuration_label(candidate, study["scene"]["facility_planning"]["levels"]),
               "cost": candidate["cost"], **{f"objective_{j+1}": value for j, value in enumerate(candidate["objective"])}}
        for scenario, stats in candidate["design_stats"].items():
            row.update({f"{scenario}_{k}": v for k, v in stats.items()})
        candidate_rows.append(row)
    write_csv(output/"design_candidates.csv", candidate_rows)
    configs = [{"plan": key, "plan_name": FACILITY_NAMES[key],
                "configuration": configuration_label(v, study["scene"]["facility_planning"]["levels"]),
                "cost": v["cost"], "budget": study["budget"]} for key, v in study["choices"].items()]
    write_csv(output/"configurations.csv", configs)
    for result in study["results"]:
        export_result(result, output/"runs"/f"{result['config']['scenario']}_{result['evaluation_seed']}")
    (output/"实验分析.md").write_text(study_report(study), encoding="utf-8")
    manifest = {k: study[k] for k in ("version", "budget", "design_seed", "design_seeds", "evaluation_seeds", "base_config", "candidate_count", "design_seconds")}
    # Hashes describe the exporter source snapshot and exported inputs; they
    # allow a later reproduction to identify which files have changed.
    manifest["export_source_sha256"] = {name: hashlib.sha256(Path(__file__).with_name(name).read_bytes()).hexdigest()
                                        for name in ("engine.py", "airspace.py", "facility.py", "facility_schema.py", "map_geometry.py", "flight_map.py", "reporting.py")}
    manifest["scene_sha256"] = hashlib.sha256((output/"scene.json").read_bytes()).hexdigest()
    write_json(output/"manifest.json", manifest)
    return output
