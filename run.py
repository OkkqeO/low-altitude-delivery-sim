"""Entry points: GUI, single experiment, reproducible batch evaluation."""
from dataclasses import replace
from pathlib import Path
import argparse

from engine import Config, DEFAULT_DESIGN_SEED, ROOT, build_design, evaluate_design
from reporting import batch_svg, comparison_rows, export_result, summary_rows, write_csv, write_json


def main():
    parser = argparse.ArgumentParser(description="低空配送风险仿真与起降场选址（Python版）")
    parser.add_argument("--mode", choices=("gui", "single", "batch", "safety", "sites", "facility"), default="gui")
    parser.add_argument("--budget", type=float, help="分级选址预算（相对单位），默认读取地图或260")
    parser.add_argument("--design-seed-count", type=int, default=3, help="选址设计种子数量，1至5，默认3")
    parser.add_argument("--scenario", choices=("normal", "peak", "closure"), default="normal")
    parser.add_argument("--orders", type=int, default=30, help="基础订单量；高峰场景为其两倍")
    parser.add_argument("--altitude", type=float, default=45)
    parser.add_argument("--risk-weight", type=float, default=2)
    parser.add_argument("--drones", type=int, default=5)
    parser.add_argument("--seed", type=int, default=20261015)
    parser.add_argument("--design-seed", type=int, default=DEFAULT_DESIGN_SEED)
    parser.add_argument("--seeds", default="20261015,20261016,20261017,20261018,20261019", help="批量评价种子，逗号分隔")
    parser.add_argument("--scene", type=Path, help="Excel/JSON地图，或图形模式下导入的地图图片")
    parser.add_argument("--output", type=Path, help="输出目录")
    parser.add_argument("--deconflict", action=argparse.BooleanOptionalAction, default=True, help="开启或关闭错峰起飞；两种模式都检测冲突")
    parser.add_argument("--separation", type=float, default=20, help="同高度间距阈值，米；为模型参数")
    parser.add_argument("--departure-step", type=float, default=5, help="冲突时的起飞推迟搜索步长，秒")
    parser.add_argument("--max-airspace-delay", type=float, default=600)
    args = parser.parse_args()
    if args.mode == "sites":
        from site_selection import run_site_study, export_site_study
        try:
            if args.budget is not None:
                raise ValueError("起飞点优选使用--drones设置无人机数量，无需--budget参数")
            seeds = [int(v.strip()) for v in args.seeds.split(",") if v.strip()]
            c = Config(order_count=args.orders, altitude=args.altitude, risk_weight=args.risk_weight,
                       drone_count=args.drones, seed=args.seed, deconflict=args.deconflict,
                       separation=args.separation, departure_step=args.departure_step,
                       max_airspace_delay=args.max_airspace_delay).validated()
            study = run_site_study(c, args.scene, seeds, args.design_seed,
                                   progress=lambda done, total, message: print(message, flush=True),
                                   design_seed_count=args.design_seed_count)
            output = export_site_study(study, args.output or ROOT/"results/sites")
            for row in study["summary"]:
                print(f"{row['scenario']} | {row['plan_name']} | {row['configuration']} | 准时率{row['on_time_rate']:.1%} | 配送{row['mean_delivery']}秒")
            print(f"结果已保存：{output.resolve()}")
        except (ValueError, OSError) as error:
            parser.error(str(error))
        return
    if args.mode == "facility":
        from facility import run_facility_study, export_facility_study
        try:
            seeds = [int(v.strip()) for v in args.seeds.split(",") if v.strip()]
            c = Config(order_count=args.orders, altitude=args.altitude, risk_weight=args.risk_weight,
                       drone_count=args.drones, seed=args.seed, deconflict=args.deconflict,
                       separation=args.separation, departure_step=args.departure_step,
                       max_airspace_delay=args.max_airspace_delay).validated()
            last_progress = [-1]
            def progress(done, total, message):
                percent = int(done/max(1,total)*100)
                if not total or percent//10 != last_progress[0]:
                    print(message, flush=True)
                    last_progress[0] = percent//10
            study = run_facility_study(c, args.scene, args.budget, seeds, args.design_seed, progress,
                                       design_seed_count=args.design_seed_count)
            output = export_facility_study(study, args.output or ROOT/"results"/"facility")
            for row in study["summary"]:
                print(f"{row['scenario']} | {row['plan_name']} | {row['configuration']} | 成本{row['cost']:g} | 准时率{row['on_time_rate']:.1%} | 配送{row['mean_delivery']}秒")
            print(f"结果已保存：{output.resolve()}")
        except (ValueError, OSError) as error:
            parser.error(str(error))
        return
    if args.scene and args.mode != "gui":
        from image_map import IMAGE_SUFFIXES
        if args.scene.suffix.lower() in IMAGE_SUFFIXES:
            parser.error("图片地图请先用图形模式确认尺度和手动楼高，保存为JSON后再运行命令行实验")
    c = Config(scenario=args.scenario, order_count=args.orders, altitude=args.altitude,
               risk_weight=args.risk_weight, drone_count=args.drones, seed=args.seed,
               deconflict=args.deconflict, separation=args.separation, departure_step=args.departure_step,
               max_airspace_delay=args.max_airspace_delay).validated()
    if args.mode == "gui":
        from app import launch
        launch(c, args.scene, args.design_seed)
        return
    output = args.output or ROOT / "results" / args.mode
    if args.mode == "single":
        result = evaluate_design(build_design(c, args.scene, args.design_seed))
        export_result(result, output)
        for row in comparison_rows(result):
            seconds = row["mean_delivery"]
            print(f"{row['plan_name']} | {row['pads']} | 配送秒数 {seconds} | 暴露 {row['mean_exposure']} | 完成率 {row['completion_rate']:.1%} | 间距不足 {row['air_conflict_count']} 次 | 错峰 {row['mean_airspace_delay']} 秒/单")
    else:
        seeds = [int(value.strip()) for value in args.seeds.split(",") if value.strip()]
        if not seeds or len(set(seeds)) != len(seeds) or args.design_seed in seeds or any(seed < 0 or seed >= 2**32 for seed in seeds):
            parser.error("评价种子须为互不重复的32位非负整数，且与设计种子不同")
        raw = []
        for scenario in ("normal", "peak", "closure"):
            print(f"计算场景 {scenario} 的固定选址……", flush=True)
            design = build_design(replace(c, scenario=scenario), args.scene, args.design_seed)
            for seed in seeds:
                modes = (False, True) if args.mode == "safety" else (c.deconflict,)
                for deconflict in modes:
                    result = evaluate_design(design, seed, deconflict)
                    raw.extend(comparison_rows(result))
                    suffix = ("_staggered" if deconflict else "_baseline") if args.mode == "safety" else ""
                    write_json(output / "runs" / f"{scenario}_{seed}{suffix}.json", result)
                print(f"  完成评价 {seed}", flush=True)
        summary = summary_rows(raw)
        write_csv(output / "raw_metrics.csv", raw)
        write_csv(output / "summary.csv", summary)
        write_json(output / "manifest.json", {"design_seed": args.design_seed, "evaluation_seeds": seeds,
                   "scenarios": ["normal", "peak", "closure"], "base_config": vars(c),
                   "scene_file": str((args.scene or ROOT / "data" / "demo_scene.json").resolve()),
                   "method": "每场景用基线调度的设计订单选址一次，所有评价种子与错峰开关复用相同场站；均值与样本标准差",
                   "dispatch_modes": ["baseline", "staggered"] if args.mode=="safety" else ["staggered" if c.deconflict else "baseline"]})
        if args.mode == "safety":
            from study import paired_comparison, write_study_report
            pairs = paired_comparison(raw)
            write_csv(output / "paired_comparison.csv",pairs)
            write_study_report(output, raw, summary, pairs, c)
        else:
            (output / "batch_comparison.svg").write_text(batch_svg(summary), encoding="utf-8")
    print(f"结果已保存：{output.resolve()}")


if __name__ == "__main__":
    import sys
    if hasattr(sys.stdout,"reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
