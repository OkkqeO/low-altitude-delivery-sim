"""Reproduce a case from the user's 300 m wide real-map screenshot.

Run with Python from the repository root. No core algorithm is changed here.
"""
from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
CASE = ROOT / "cases/user_map_300m"
OUTPUT = ROOT / "results/user_map_300m"

from airspace import detect_conflicts
from engine import Config, create_scene, is_blocked, xy
from map_document import MapDocument
from reporting import write_csv, write_json
from site_selection import export_site_study, run_site_study


def prepare():
    from PIL import Image
    from image_map import encode_background, extract_buildings, scene_from_image

    a = json.loads((CASE / "annotations.json").read_text(encoding="utf-8"))
    image = Image.open(CASE / "original.jpg").convert("RGB")
    assert image.size == (a["image_width"], a["image_height"])
    scale = a["width_metres"] / image.width
    buildings = []
    for group in a["building_groups"]:
        for part, (x1, y1, x2, y2) in enumerate(group["boxes"], 1):
            buildings.append({
                "id": f"{group['id']}_{part}", "name": f"轮廓{group['id']}·块{part}",
                "x": x1*scale, "y": y1*scale, "w": (x2-x1)*scale, "h": (y2-y1)*scale,
                "height": a["height_upper_bound_metres"], "height_confirmed": True,
                "height_source": "用户说明楼高均不超过30米；本案例用30米上界做保守情景，非逐栋实测",
                "height_is_upper_bound": True, "footprint_source": "原始截图人工近似描绘；U/L形拆为矩形块",
                "footprint_needs_review": True, "locator_occluded": group.get("occluded", False),
                "footprint_group": group["id"], "pixel_box": [x1, y1, x2, y2]})
    # Roads are visual centerline strips, not a restriction on aerial routes.
    roads = []
    for line in a["road_lines"]:
        for (x1, y1), (x2, y2) in zip(line, line[1:]):
            dx, dy = x2-x1, y2-y1
            length = math.hypot(dx, dy)
            nx, ny = -dy/length*3, dx/length*3
            ring = [[min(image.width, max(0., x))*scale, min(image.height, max(0., y))*scale]
                    for x, y in ((x1+nx,y1+ny),(x2+nx,y2+ny),(x2-nx,y2-ny),(x1-nx,y1-ny))]
            left, top = min(p[0] for p in ring), min(p[1] for p in ring)
            roads.append({"id": f"F{len(roads)+1}", "name": "手描道路示意", "kind": "road",
                          "x": left, "y": top, "w": max(p[0] for p in ring)-left,
                          "h": max(p[1] for p in ring)-top, "polygon": ring,
                          "schematic_outline": True, "recognition_source": "截图人工描绘中心线，宽度为显示假设"})
    pads = [{"id": f"S{i}", "name": f"测试起飞点{i}", "x": x*scale, "y": y*scale,
             "suggested": True, "source": "人工布置测试点，非已核实起降设施"}
            for i, (x,y) in enumerate(a["pad_pixels"], 1)]
    deliveries = [{"id": f"D{i}", "name": f"模拟配送点{i}", "x": x*scale, "y": y*scale,
                   "demand": 1., "suggested": True, "source": "截图建筑附近测试点，入口及需求待核实"}
                  for i,(x,y) in enumerate(a["delivery_pixels"], 1)]
    risks = [{"id": f"R{i}", "name": f"模拟人群热点{i}",
              **{k: z[k]*scale for k in ("x","y","rx","ry")}, "weight": z["weight"],
              "source": "人为设定的测试风险场；无人流实测依据"}
             for i,z in enumerate(a["risk_zones_pixels"], 1)]
    scene = {"name": "用户真实地图·300米·上界楼高测试", "width": a["width_metres"],
             "height": image.height*scale, "step": 2., "clearance": 3., "vertical_clearance": 5.,
             "buildings": buildings, "pads": pads, "deliveries": deliveries, "risk_zones": risks,
             "map_features": roads, "map_presentation": "schematic",
             "source": "用户提供真实地图截图；横向300米由用户提供；楼高≤30米，按30米上界试跑；轮廓、点位、人群与订单为近似或模拟",
             "image_background": encode_background(image, "original.jpg"),
             "image_import": {"scale_confirmed": True, "scale_source": "用户提供整图横向宽度300米",
                              "metres_per_pixel": scale, "recognition_mode": "manual_case_review",
                              "recognition_count": len(buildings), "group_count": len(a["building_groups"])},
             "case_provenance": {"image_sha256": hashlib.sha256((CASE/"original.jpg").read_bytes()).hexdigest(),
                                 "location_name": "未提供，不能仅据道路文字认定园区名称",
                                 "height_mode": "30米上界情景，不是所有楼实际都为30米",
                                 "assumptions": a["notes"] + ["3米平面、5米垂直间距为试跑参数，不是法规标准",
                                                           "订单、需求权重、起降服务时间及速度沿用模拟设定"]}}
    MapDocument(scene).save(CASE / "scene.json")
    for altitude in (30,45):
        runtime = create_scene(Config(altitude=altitude), scene)
        assert all(not is_blocked(runtime, xy(p)) for p in [*pads, *deliveries]), "测试点落在障碍范围内"
    # Keep import diagnostics; the correction lives in this case, not generic recognition.
    auto = scene_from_image(CASE / "original.jpg")
    colored, metadata = extract_buildings(image, 300, mode="color", color=image.getpixel((180,180)),
                                         tolerance=5, min_area=120)
    write_json(CASE / "recognition_diagnostics.json", {
        "automatic": {"buildings": len(auto["buildings"]), "pads": len(auto["pads"]),
                      "deliveries": len(auto["deliveries"]), "metadata": auto["image_import"]},
        "color_selection": {"buildings": len(colored), "metadata": metadata},
        "manual_review": {"visible_groups": len(a["building_groups"]), "rectangle_parts": len(buildings)},
        "note": "低对比建筑漏检；蓝色定位标记误分为水体。手描几何用于本案例，自动识别器未针对截图硬编码。"})
    print(f"Scene ready: {scene['width']} x {scene['height']:.2f} m, {len(buildings)} rectangle parts", flush=True)
    return scene


def segment_hits_box(a, b, box, padding):
    """Independent continuous line/AABB check, more strict than sampled checks."""
    low, high = 0., 1.
    for axis, key, size in ((0,"x","w"),(1,"y","h")):
        left, right = box[key]-padding, box[key]+box[size]+padding
        delta = b[axis]-a[axis]
        if abs(delta) < 1e-12:
            if not left <= a[axis] <= right:
                return False
        else:
            t1, t2 = sorted(((left-a[axis])/delta, (right-a[axis])/delta))
            low, high = max(low,t1), min(high,t2)
            if low > high+1e-10:
                return False
    return low <= high+1e-10


def audit(study):
    scene = study["scene"]
    obstacles = [b for b in scene["buildings"] if b["height"]+scene["vertical_clearance"] >= scene["altitude"]]
    route_checks = 0
    for key, route in study["results"][0]["routes"].items():
        if not route:
            continue
        for a,b in zip(route["points"],route["points"][1:]):
            assert not any(segment_hits_box(a,b,box,scene["clearance"]) for box in obstacles), f"Route intersects padded building: {key}"
            route_checks += 1
    jobs_checked = 0
    for result in study["results"]:
        expected_orders = None
        for key,plan in result["plans"].items():
            assert len(plan["drones"]) == result["config"]["drone_count"]
            assert plan["site_configuration"]["pad_ids"] == study["choices"][key]["pad_ids"]
            if expected_orders is None:
                expected_orders = plan["orders"]
            assert plan["orders"] == expected_orders
            conflicts = detect_conflicts(plan["jobs"], result["routes"], result["config"]["speed"], result["config"]["separation"])
            assert not conflicts, f"Independent separation audit failed: {key}"
            for calendar in plan["calendars"].values():
                assert all(a["end"] <= b["start"]+1e-8 for a,b in zip(calendar,calendar[1:]))
            for drone in plan["drones"]:
                jobs = sorted((j for j in plan["jobs"] if j["drone_id"]==drone["id"]), key=lambda j:j["prep_start"])
                assert all(a["end"] <= b["prep_start"]+1e-8 for a,b in zip(jobs,jobs[1:]))
            jobs_checked += len(plan["jobs"])
    return {"route_segments_checked": route_checks, "jobs_checked": jobs_checked,
            "active_rectangle_obstacles": len(obstacles), "independent_conflicts": 0,
            "calendar_and_drone_overlaps": 0, "frozen_layout_and_same_orders": True}


def report(rows, audits):
    lines = ["# 用户真实地图：300米宽园区试跑", "",
             "底图为用户提供的真实地图截图；宽度300米、楼高不超过30米由用户提供。按等比例换算，图高约392.68米。地点名称尚未提供。", "",
             "本次属于真实空间截图下的假设参数仿真，不能写成实测运营或真实飞行验证。", "",
             "## 输入与模型", "",
             "- 16组可见轮廓近似分成22个矩形障碍块；局部轮廓被原图定位标记遮挡，需要现场或无标记原图核对。",
             "- 6个候选起飞点、10个配送点与3个人群热点均为试跑设置，未核实场地可用性、真实入口或人流。",
             "- 每栋建筑按用户提供的30米上限建模；这不等于每栋实际都是30米。",
             "- 30米巡航为保守绕楼情景；45米巡航高于楼高上限加5米垂直间距，模型中不把这些建筑视为障碍。",
             "- 网格2米、平面间距3米、垂直间距5米；20米多机间距、9米/秒速度、25/20/20秒起飞/降落/配送服务均为模型参数。",
             "- 正常30单/1200秒，高峰60单/800秒，600秒为准时时限。订单由模型生成；所有订单可从任一所选站发出。",
             "- 3个设计种子与5个独立评价种子；每种数量与高度重新设计，正常/高峰冻结同一布局。各方案机队总数相同，不考虑成本。", "",
             "## 独立评价均值", "",
             "|巡航/米|无人机|场景|方案|起飞点与分配|准时率|配送/秒|暴露代理值|完成率|失败/次|间距事件/次|",
             "|---:|---:|---|---|---|---:|---:|---:|---:|---:|---:|"]
    for r in rows:
        lines.append(f"|{r['altitude']:g}|{r['drone_count']}|{'正常' if r['scenario']=='normal' else '高峰'}|{r['plan_name']}|{r['configuration']}|{r['on_time_rate']:.2%}|{r['mean_delivery']:.2f}|{r['mean_exposure']:.3f}|{r['completion_rate']:.2%}|{r['failed_orders']:.2f}|{r['air_conflict_count']:.2f}|")
    lines += ["", "## 本次发现", ""]
    for altitude in (30,45):
        fixed = next(r for r in rows if r['altitude']==altitude and r['drone_count']==5 and r['scenario']=='peak' and r['plan']=='fixed')
        combined = next(r for r in rows if r['altitude']==altitude and r['drone_count']==5 and r['scenario']=='peak' and r['plan']=='combined')
        lines.append(f"- {altitude}米、5架机的高峰独立评价：运行优选准时率{combined['on_time_rate']:.2%}，固定位置{fixed['on_time_rate']:.2%}；平均配送分别为{combined['mean_delivery']:.2f}秒、{fixed['mean_delivery']:.2f}秒。该样本下运行优选没有取得时效优势。")
    lines += ["- 运行优选只保证在设计样本中按当前目标排序最优，不保证独立样本最优。选址对样本与机队数量敏感，不能用本次案例声称算法普遍优于基线。",
              "- 8架机时运行优选的高峰均值有所改善；仅5个独立评价种子，不能据此宣称统计显著或适用于其他园区。",
              "- 本次主要验证导入、地图表达、不同机队和高度的选址仿真及导出流程，并暴露高峰积压和选址泛化不足。", "",
              "![地图与选址](地图与选址.png)", "", "![高峰容量对比](高峰容量对比.png)",
              "", "## 核验与解释", "",
              f"共核验{sum(a['jobs_checked'] for a in audits)}条成功任务记录。独立复算连续间距、场站日历、无人机任务不重叠，并核验航路与建筑扩张矩形的连续线段相交。具体见 audit.json。",
              "同一订单在不同方案和参数组中重复评价；上述任务记录数量不等于独立真实订单数量。",
              "", "平均时间、暴露及P95按成功订单统计，需同时查看完成率和失败数。准时率为含失败订单的全部订单口径；表格为跨运行均值。",
              "", "比较30米和45米的差异时，同时改变了障碍条件；不能把差异全部归因于选址算法。更多无人机也可能受单站服务位和空中间距约束限制。",
              "", "自动导入诊断见 cases/user_map_300m/recognition_diagnostics.json：默认识别漏检且未产生足够点位，本次由取色检查与人工近似描绘完成案例，不代表自动识别已解决。",
              "", "## 打开与复现", "",
              "双击根目录“启动真实地图测试.cmd”查看已算好的5架机、30米保守绕楼结果；打开起飞点优选工作台可调整无人机数量与巡航高度。",
              "", "也可导入 cases/user_map_300m/scene.json，或运行：", "",
              "```powershell", "python cases/run_user_map_case.py", "python cases/run_user_map_case.py --gui", "```", "",
              "压缩全量研究结果保存在 studies/*.json.gz，程序可直接读取；各参数组的逐次JSON/CSV导出目录可由脚本重建。", "",
              "正式参赛还需补充地点名称、地图来源与日期、无遮挡建筑轮廓、逐栋高度或楼层依据、真实候选点与配送需求依据。"]
    (OUTPUT/"测试报告.md").write_text("\n".join(lines)+"\n",encoding="utf-8")


def finish_report(rows, audits):
    report(rows,audits)
    snapshots = {}
    (OUTPUT/'studies').mkdir(exist_ok=True)
    for altitude in (30,45):
        for drones in (3,5,8):
            source = OUTPUT/f'h{altitude}_d{drones}/study.json'
            target = OUTPUT/f'studies/h{altitude}_d{drones}.json.gz'
            target.write_bytes(gzip.compress(source.read_bytes(),mtime=0))
            snapshots[target.name] = hashlib.sha256(target.read_bytes()).hexdigest()
    files = [CASE/'original.jpg',CASE/'annotations.json',CASE/'scene.json',Path(__file__).resolve(),
             ROOT/'cases/plot_user_map_case.py',
             ROOT/'engine.py',ROOT/'site_selection.py',ROOT/'airspace.py']
    write_json(OUTPUT/'case_manifest.json', {
        'case': 'user_map_300m', 'scale_source': '用户提供横向300米',
        'height_source': '用户提供不超过30米；按上界建模',
        'altitudes': [30,45], 'drone_counts': [3,5,8], 'evaluation_seeds': list(range(20261015,20261020)),
        'summary_rows': len(rows), 'plan_evaluations': sum(r['runs'] for r in rows),
        'task_records_including_repeated_orders': sum(a['jobs_checked'] for a in audits),
        'compressed_study_sha256': snapshots,
        'source_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}})
    print(f"Report: {OUTPUT/'测试报告.md'}",flush=True)


def launch_case():
    import tkinter as tk
    from app import Application
    from site_ui import SiteWindow

    path = OUTPUT / "studies/h30_d5.json.gz"
    if not path.exists():
        raise SystemExit("请先运行 python cases/run_user_map_case.py 生成案例结果。")
    study = json.loads(gzip.decompress(path.read_bytes()).decode("utf-8"))
    config = Config(**study["base_config"])
    root = tk.Tk()
    app = Application(root, config, CASE/"scene.json", auto_calculate=False)
    result = next(v for v in study["results"] if v["config"]["scenario"]=="peak")
    app.show_facility_result(result, "combined")
    app.status.set("真实地图300米 · 楼高按30米上界 · 当前为30米保守绕楼试跑")
    workbench = SiteWindow(app)
    app.facility_window = workbench
    workbench.study, workbench.dirty = study, False
    workbench._show_results()
    workbench.export_button.configure(state="normal")
    workbench.replay_button.configure(state="normal")
    workbench.status.set("已加载真实地图测试；点位、需求为模拟，楼高采用用户提供的30米上界。")
    root.mainloop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gui",action="store_true",help="打开已计算的案例与起飞点优选工作台")
    parser.add_argument("--prepare-only",action="store_true")
    args = parser.parse_args()
    if args.gui:
        launch_case()
        return
    scene = prepare()
    if args.prepare_only:
        return
    OUTPUT.mkdir(parents=True,exist_ok=True)
    rows, audits = [], []
    for altitude in (30,45):
        for drones in (3,5,8):
            config = Config(altitude=altitude,drone_count=drones)
            folder = OUTPUT/f"h{altitude}_d{drones}"
            print(f"Starting altitude={altitude}, drones={drones}",flush=True)
            study = run_site_study(config,scene,list(range(20261015,20261020)))
            check = {"altitude": altitude,"drone_count": drones,**audit(study)}
            export_site_study(study,folder)
            for row in study["summary"]:
                rows.append({"altitude": altitude,"drone_count": drones,**row})
            audits.append(check)
            write_csv(OUTPUT/"summary.csv",rows)
            write_json(OUTPUT/"audit.json",audits)
            print(f"Verified and saved {folder.name}: {check}",flush=True)
    finish_report(rows,audits)


if __name__ == "__main__":
    if hasattr(sys.stdout,"reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
