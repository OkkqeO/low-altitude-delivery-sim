"""CSV / JSON / SVG output, usable without third-party plotting libraries."""
from __future__ import annotations

import csv
from html import escape
import json
from pathlib import Path
import statistics

from engine import PLAN_NAMES, risk_at
from map_geometry import svg_path

COLORS = {"fixed": "#8392a9", "distance": "#3869e8", "combined": "#079d8a"}
SCENARIOS = {"normal": "正常配送", "peak": "高峰订单", "closure": "局部空域关闭"}
METRICS = ("mean_delivery", "mean_exposure", "total_distance", "mean_pad_waiting", "on_time_rate", "completion_rate", "failed_orders",
           "mean_airspace_delay", "air_conflict_count", "air_conflict_duration", "airspace_failed_orders")
FONT = "'Microsoft YaHei','Noto Sans CJK SC',sans-serif"


def comparison_rows(result: dict) -> list[dict]:
    return [{"scenario": result["config"]["scenario"], "evaluation_seed": result["evaluation_seed"],
             "design_seed": result["design_seed"], "plan": key, "plan_name": plan["name"],
             "dispatch": "staggered" if result["config"].get("deconflict", False) else "baseline",
             "pads": "+".join(plan["pad_ids"]), **plan["stats"]} for key, plan in result["plans"].items()]


def write_csv(path: str | Path, rows: list[dict]) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not rows:
        raise ValueError("没有可导出的数据")
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: str | Path, data: dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def svg_document(width: int, height: int, body: list[str]) -> str:
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">'
            f'<rect width="100%" height="100%" fill="#f6f8fc"/><g font-family="{FONT}">' + "".join(body) + '</g></svg>')


def text(x, y, content, size=14, color="#243451", anchor="start"):
    return f'<text x="{x}" y="{y}" font-size="{size}" fill="{color}" text-anchor="{anchor}">{escape(str(content))}</text>'


def map_svg(result: dict, plan_key="combined") -> str:
    scene, plan = result["scene"], result["plans"][plan_key]
    width, height = scene["width"], scene["height"]
    scale = min(1056 / width, 704 / height)
    map_w, map_h = width * scale, height * scale
    schematic = scene.get("map_presentation") == "schematic"
    body = [text(40, 38, f"{plan['name']} · {SCENARIOS[result['config']['scenario']]}", 23),
            text(40, 66, "园区场景 / 固定高度风险航路 / 坐标单位：米"),
            '<g transform="translate(40 90)">']
    background = None if schematic else scene.get("image_background", {}).get("png_base64")
    if background:
        body.append(f'<image width="{map_w}" height="{map_h}" href="data:image/png;base64,{background}"/>')
    for y in range(0, 0 if schematic else int(height) + 1, 16):
        for x in range(0, int(width) + 1, 16):
            r = risk_at(scene, (x + 8, y + 8))
            color = f"#{round(240 + 12 * r):02x}{round(247 - 105 * r):02x}{round(245 - 100 * r):02x}"
            body.append(f'<rect x="{x * scale:.2f}" y="{y * scale:.2f}" width="{min(16, width-x)*scale:.2f}" height="{min(16, height-y)*scale:.2f}" fill="{color}" fill-opacity="{.25 if background else 1}"/>')
    for feature in scene.get("map_features", []):
        if feature["kind"] != "road":
            continue
        path = svg_path(feature, scale) if feature.get("polygon") else f'M{feature["x"]*scale},{feature["y"]*scale} h{feature["w"]*scale} v{feature["h"]*scale} h{-feature["w"]*scale} Z'
        body.append(f'<path d="{path}" fill="#e6ebf1" fill-rule="evenodd" stroke="#adbaca" stroke-width=".7"/>')
    for b in scene["buildings"]:
        blocked = b["height"] + scene["vertical_clearance"] >= scene["altitude"]
        body.append(f'<g class="building" data-building-id="{escape(b["id"], quote=True)}">')
        body.append('<title>'+escape(f'{b["name"]} · {b["height"]:g}米 · '+('需绕行' if blocked else '可从上方通过'))+'</title>')
        if b.get("polygon"):
            body.append(f'<path d="{svg_path(b, scale)}" fill="{"#D5E0EE" if blocked else "#EDF2F7"}" fill-opacity=".5" fill-rule="evenodd" stroke="{"#597594" if blocked else "#A6B7C9"}"/>')
        else:
            body.append(f'<rect x="{b["x"]*scale}" y="{b["y"]*scale}" width="{b["w"]*scale}" height="{b["h"]*scale}" fill="{"#D5E0EE" if blocked else "#EDF2F7"}" stroke="{"#597594" if blocked else "#A6B7C9"}"/>')
        if not schematic:
            body.append(text((b["x"]+b["w"]/2)*scale, (b["y"]+b["h"]/2)*scale, f'{b["name"]} {b["height"]}m', 11, anchor="middle"))
        body.append('</g>')
    if scene["closure"]:
        b = scene["closure"]
        body.append(f'<rect x="{b["x"]*scale}" y="{b["y"]*scale}" width="{b["w"]*scale}" height="{b["h"]*scale}" fill="#ffd5d5" fill-opacity=".7" stroke="#c34545" stroke-dasharray="7 4"/>')
        body.append(text(b["x"]*scale, (b["y"]-5)*scale, "整次运行关闭", 12, "#aa3030"))
    for pad_id in plan["pad_ids"]:
        for d in scene["deliveries"]:
            route = result["routes"].get(f'{pad_id}:{d["id"]}')
            if route:
                pts = " ".join(f"{x*scale:.2f},{y*scale:.2f}" for x,y in route["points"])
                body.append(f'<polyline points="{pts}" fill="none" stroke="{COLORS[plan_key]}" stroke-opacity=".65" stroke-width="1.8"/>')
    for d in scene["deliveries"]:
        x, y = d["x"]*scale, d["y"]*scale
        body.append(f'<path d="M{x},{y-5} L{x+5},{y} L{x},{y+5} L{x-5},{y} Z" fill="#b46531"/>')
        body.append(text(x+8, y+4, d["id"], 11))
    for p in scene["pads"]:
        selected = p["id"] in plan["pad_ids"]
        body.append(f'<circle cx="{p["x"]*scale}" cy="{p["y"]*scale}" r="{9 if selected else 5}" fill="{COLORS[plan_key] if selected else "#ffffff"}" stroke="#3869e8" stroke-width="2"/>')
        body.append(text(p["x"]*scale+12, p["y"]*scale+5, p["id"], 12))
    note = "深色建筑需绕行，浅色可飞越；显示全部建筑与道路。" if schematic else "橙色深浅表示模拟人员暴露；深色建筑需绕行，浅色可飞越。"
    body += ['</g>', text(40, map_h+120, f'选中场站：{" + ".join(plan["pad_ids"])}；巡航高度：{scene["altitude"]}m；{note}'),
             text(40, map_h+146, f"人员暴露为代理指标；同高度间距检测阈值 {result['config'].get('separation',20)}m，完整冲突记录见conflicts.csv。", 12, "#687790")]
    return svg_document(round(map_w+80), round(map_h+165), body)


def comparison_svg(result: dict) -> str:
    body = [text(36, 42, "三种布局 · 独立订单评价", 24),
            text(36, 70, f"模拟数据 / 评价种子 {result['evaluation_seed']} / 所有方案使用相同规划器和订单", 13)]
    panels = [("mean_delivery", "平均配送时间 / 秒", 1), ("mean_exposure", "每单人员暴露指数", 1), ("total_distance", "总飞行航程 / km", .001)]
    for panel, (metric, title, factor) in enumerate(panels):
        x = 36 + panel * 360
        body.append(text(x, 116, title, 17))
        values = [(key, None if p["stats"][metric] is None else p["stats"][metric]*factor) for key,p in result["plans"].items()]
        maximum = max([value for _,value in values if value is not None]+[1e-6]) * 1.18
        for i,(key,value) in enumerate(values):
            y = 164 + i*77
            body.append(text(x, y, result["plans"][key]["name"], 13))
            if value is not None:
                body.append(f'<rect x="{x}" y="{y+12}" width="{max(1,value/maximum*270):.2f}" height="22" rx="5" fill="{COLORS[key]}"/>')
            body.append(text(x+310, y+29, "不可达" if value is None else f"{value:.3f}", 13, anchor="end"))
    body.append(text(36, 440, "单次仿真结果；指标越低越好，同时需检查完成率和失败订单。", 13, "#687790"))
    return svg_document(1130, 470, body)


def summary_rows(raw_rows: list[dict]) -> list[dict]:
    groups = {}
    for row in raw_rows:
        groups.setdefault((row["scenario"], row["plan"], row.get("dispatch", "unspecified")), []).append(row)
    summary = []
    for (scenario, key, dispatch), rows in groups.items():
        output = {"scenario": scenario, "plan": key, "plan_name": PLAN_NAMES[key],
                  "dispatch": dispatch,
                  "pads": rows[0]["pads"], "runs": len(rows)}
        for metric in METRICS:
            values = [r[metric] for r in rows if r.get(metric) is not None]
            output[metric+"_valid_runs"] = len(values)
            output[metric+"_mean"] = statistics.mean(values) if values else None
            output[metric+"_std"] = statistics.stdev(values) if len(values)>1 else (0. if values else None)
        summary.append(output)
    return summary


def batch_svg(summary: list[dict]) -> str:
    body = [text(32, 40, "多场景、多种子评价 · 均值与样本标准差", 22),
            text(32, 68, "每个场景固定设计订单与场站布局，误差线表示评价订单变化带来的波动。", 13)]
    metrics = [("mean_delivery", "配送时间 / 秒",1), ("mean_exposure", "人员暴露指数",1), ("total_distance", "航程 / km",.001)]
    for row_index, scenario in enumerate(SCENARIOS):
        for col,(metric,label,factor) in enumerate(metrics):
            x,y = 32+col*370,110+row_index*240
            body.append(text(x,y,f"{SCENARIOS[scenario]} · {label}",15))
            entries = [r for r in summary if r["scenario"]==scenario]
            maximum = max([(r[metric+"_mean"]+r[metric+"_std"])*factor for r in entries if r[metric+"_mean"] is not None]+[1e-6])*1.15
            for i,r in enumerate(entries):
                key,mean,std = r["plan"],r[metric+"_mean"],r[metric+"_std"]
                baseline = y+163
                bx = x+40+i*100
                body.append(text(bx+20,baseline+22,PLAN_NAMES[key],12,anchor="middle"))
                if mean is None:
                    body.append(text(bx+20,baseline-10,"无有效值",11,anchor="middle"))
                    continue
                bh = mean*factor/maximum*125
                eh = std*factor/maximum*125
                body += [f'<rect x="{bx}" y="{baseline-bh}" width="40" height="{bh}" rx="3" fill="{COLORS[key]}"/>',
                         f'<path d="M{bx+20},{baseline-bh-eh} V{baseline-bh+eh} M{bx+12},{baseline-bh-eh} h16 M{bx+12},{baseline-bh+eh} h16" stroke="#243451" fill="none"/>',
                         text(bx+20,baseline-bh-eh-9,f"{mean*factor:.2f}",11,anchor="middle")]
    body.append(text(32,845,"模拟数据；空值排除数见summary.csv；标准差不是置信区间，需同时报告完成率。",12,"#687790"))
    return svg_document(1150,875,body)


def export_result(result: dict, output: str | Path) -> Path:
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output / "result.json", result)
    write_csv(output / "comparison.csv", comparison_rows(result))
    if "site_design" in result:
        write_csv(output/"site_configurations.csv", [
            {"plan": key, "plan_name": plan["name"], "pad_id": p, "drones": n,
             "total_drones": result["config"]["drone_count"]}
            for key, plan in result["plans"].items()
            for p, n in plan["site_configuration"]["fleet_allocation"].items()])
    if "facility_design" in result:
        facility_rows = []
        levels = {v["id"]: v for v in result["facility_design"]["levels"]}
        for key, plan in result["plans"].items():
            configuration = plan["facility_configuration"]
            for pad in plan["pad_ids"]:
                level = levels[configuration["levels"][pad]]
                facility_rows.append({"plan": key, "plan_name": plan["name"], "pad_id": pad,
                                      "level_id": level["id"], "level_name": level["name"],
                                      "drones": configuration["fleet_allocation"][pad],
                                      "max_drones": level["max_drones"], **configuration["pad_services"][pad],
                                      "total_cost": configuration["cost"], "budget": result["facility_design"]["budget"]})
        write_csv(output/"facility_configurations.csv", facility_rows)
    jobs = [{"plan": key, **job} for key,p in result["plans"].items() for job in p["jobs"]]
    if jobs:
        write_csv(output / "jobs.csv", jobs)
    else:
        with (output / "jobs.csv").open("w",encoding="utf-8-sig",newline="") as handle:
            csv.writer(handle).writerow(["plan","order_id","drone_id","pad_id","destination_id","route_key",
                "created_at","due_at","ready","prep_start","depart","arrived_dest","delivered_at",
                "return_start","return_arrival","land_start","end","distance","exposure","pad_waiting","airspace_delay"])
    failed = [{"plan": key, **order} for key,p in result["plans"].items() for order in p["failed"]]
    # Always write failures, including an empty table, so old exports cannot survive.
    with (output / "failed.csv").open("w",encoding="utf-8-sig",newline="") as handle:
        fields = ["plan","id","destination_id","created_at","due_at","failure_type","reason"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(failed)
    with (output / "conflicts.csv").open("w",encoding="utf-8-sig",newline="") as handle:
        fields = ["plan","start","end","closest_time","min_distance","x","y","drone_a","drone_b","order_a","order_b"]
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows({"plan":key, **conflict} for key,p in result["plans"].items() for conflict in p.get("conflicts",[]))
    (output / "map.svg").write_text(map_svg(result), encoding="utf-8")
    (output / "comparison.svg").write_text(comparison_svg(result), encoding="utf-8")
    return output
