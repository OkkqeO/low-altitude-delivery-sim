"""Paired baseline/staggered experiments with explicit completion tradeoffs."""
from pathlib import Path
import statistics

from engine import PLAN_NAMES
from reporting import SCENARIOS


def paired_comparison(rows: list[dict]) -> list[dict]:
    groups = {}
    for row in rows:
        key = row["scenario"], row["evaluation_seed"], row["plan"]
        modes = groups.setdefault(key, {})
        if row["dispatch"] in modes:
            raise ValueError("存在重复的配对运行")
        modes[row["dispatch"]] = row
    result = []
    for (scenario, seed, plan), modes in groups.items():
        if set(modes) != {"baseline", "staggered"}:
            raise ValueError("每个场景、种子、方案都需要基线和错峰两种运行")
        before, after = modes["baseline"], modes["staggered"]
        if before["pads"] != after["pads"] or before["design_seed"] != after["design_seed"]:
            raise ValueError("配对实验的场站与设计种子须一致")
        pair = {"scenario": scenario, "evaluation_seed": seed, "plan": plan,
                "pads": before["pads"], "design_seed": before["design_seed"]}
        for metric in ("air_conflict_count", "air_conflict_duration", "mean_delivery", "mean_exposure",
                       "total_distance", "mean_airspace_delay", "on_time_rate", "completion_rate",
                       "failed_orders", "airspace_failed_orders"):
            a, b = before[metric], after[metric]
            pair["baseline_" + metric] = a
            pair["staggered_" + metric] = b
            pair["delta_" + metric] = b - a if a is not None and b is not None else None
        result.append(pair)
    return result


def write_study_report(output: Path, raw: list[dict], summary: list[dict], pairs: list[dict], config) -> None:
    seeds = sorted({row["evaluation_seed"] for row in raw})
    baseline = [row for row in raw if row["dispatch"] == "baseline"]
    staggered = [row for row in raw if row["dispatch"] == "staggered"]
    conflicts_before = sum(r["air_conflict_count"] for r in baseline)
    conflicts_after = sum(r["air_conflict_count"] for r in staggered)
    failures_before = sum(r["failed_orders"] for r in baseline)
    failures_after = sum(r["failed_orders"] for r in staggered)
    index = {(r["scenario"],r["plan"],r["dispatch"]):r for r in summary}
    lines = ["# 多机间距检测与错峰起飞：配对实验记录", "",
             "本报告由实际模型输出自动生成。园区、建筑、人群和订单均为模拟数据。", "",
             "## 实验设计", "",
             f"- 3种场景 × {len(seeds)}个评价种子 × 3种场站布局 × 2种调度，共{len(raw)}条运行指标、{len(pairs)}组配对比较。",
             f"- 评价种子：{', '.join(map(str,seeds))}；设计种子：{raw[0]['design_seed']}。",
             "- 每个场景使用独立设计订单和基线调度选择站点；该场景的所有评价种子与两种调度共用相同站点。",
             "- 每组配对共用场景、评价订单、航路、机队、速度与起降服务参数；区别为是否启用错峰。",
             f"- 同高度间距阈值{config.separation:g}米，出发搜索步长{config.departure_step:g}秒，单次候选调度最大额外等待{config.max_airspace_delay:g}秒。参数是研究设定，不是法规间距。",
             "- 冲突次数指：一对配送任务之间，距离严格小于阈值的一段连续时间；跨航路折点的连续片段合并。累计时长为各任务对的冲突秒数之和，同一时刻多对接近会分别计数。", "",
             "## 结果", "",
             f"在本次{len(pairs)}组配对方案运行中，间距不足事件由 **{conflicts_before}次** 变为 **{conflicts_after}次**；失败订单评价次数由{failures_before}变为{failures_after}。不同方案重复评价同一组订单，上述总数不是独立真实订单数量。", "",
             "下表为跨种子的均值；冲突次数同时报告样本标准差。配送时间、暴露按成功订单计算，必须同时检查完成率和失败数。", "",
             "| 场景 / 方案 | 基线冲突 / 次 | 错峰冲突 / 次 | 配送时间 / 秒（基线→错峰） | 暴露指数（基线→错峰） | 错峰等待 / 秒每单 | 准时率（基线→错峰） | 完成率（基线→错峰） |",
             "|---|---:|---:|---:|---:|---:|---:|---:|"]

    def fmt(value, digits=2):
        return "无有效值" if value is None else f"{value:.{digits}f}"

    for scenario in SCENARIOS:
        for plan in PLAN_NAMES:
            a, b = index[(scenario,plan,"baseline")], index[(scenario,plan,"staggered")]
            lines.append(f"| {SCENARIOS[scenario]} / {PLAN_NAMES[plan]} | "
                         f"{fmt(a['air_conflict_count_mean'])} ± {fmt(a['air_conflict_count_std'])} | "
                         f"{fmt(b['air_conflict_count_mean'])} ± {fmt(b['air_conflict_count_std'])} | "
                         f"{fmt(a['mean_delivery_mean'])} → {fmt(b['mean_delivery_mean'])} | "
                         f"{fmt(a['mean_exposure_mean'],3)} → {fmt(b['mean_exposure_mean'],3)} | "
                         f"{fmt(b['mean_airspace_delay_mean'])} | "
                         f"{a['on_time_rate_mean']:.1%} → {b['on_time_rate_mean']:.1%} | "
                         f"{a['completion_rate_mean']:.1%} → {b['completion_rate_mean']:.1%} |")
    valid_deltas = [p["delta_mean_delivery"] for p in pairs if p["delta_mean_delivery"] is not None]
    if valid_deltas:
        lines += ["", f"按每组运行等权平均，平均配送时间变化为{statistics.mean(valid_deltas):+.2f}秒（有效配对{len(valid_deltas)}组）；该统计量不是按订单量加权的均值。"]
    lines += ["", "## 检测与调度方法", "",
              "将每次任务的去程、配送悬停、返程和返场排队悬停分解为线性运动区间。在重叠区间中求相对运动的二次不等式 `||r + v·t||² < separation²`，解析计算接近区间、最小间距和最接近时刻；不是每秒采样。",
              "", "按订单时间依次调度。对每架候选无人机，从场站最早可用起飞时隙开始，若与已预约任务发生间距不足，则按搜索步长推迟准备时间并重新检查去程、悬停、返程和返场等待。选择最早可送达的可行候选。最大额外等待内找不到时隙的订单明确计为失败。",
              "", "错峰等待定义为相对该候选无人机原本最早场站服务时隙的额外推迟；场站等待定义为原本的起飞排队加返场排队。两者分列，不能把错峰时间隐藏在场站等待中。一次任务结束后，新任务仍需满足同一无人机不可重叠的约束。",
              "", "## 结论边界与下一步", "",
              "- 结果只验证当前固定高度、匀速折线与悬停模型的间距约束；起飞准备和降落服务视为地面阶段，没有模拟实际爬升、下降、导航误差或真实航空避碰。",
              "- 错峰采用按订单顺序的预约式调度及有限步长搜索，不保证全局最短等待或最优吞吐量。后续订单不能改变已有预约。",
              "- 悬停等待的电耗与人群暴露尚未纳入能耗和路径暴露指标；不能将这些结果解释为总能耗或真实事故概率。",
              "- 本实验每种场景分别选址，不能据此宣称同一布局应对突发空域关闭的鲁棒性。",
              "- 5个评价种子用于初步稳定性检查，均值与标准差不构成统计显著性证明。",
              "- 下一步应接入指定校园/园区的建筑与候选场站数据，记录来源和估计规则，再做参数敏感性与更多种子实验。", "",
              "## 可复现文件", "",
              "- `raw_metrics.csv`：两种调度的每次指标。",
              "- `paired_comparison.csv`：固定场景、种子、布局下的配对差值。",
              "- `summary.csv`：均值、样本标准差、有效样本数。",
              "- `runs/`：包含航路、任务、冲突时间及位置、失败原因的完整JSON。",
              "- `manifest.json`：配置、种子和实验方法。",
              "- 可选：运行 `python plot_study.py` 生成Matplotlib PNG/PDF图。", "",
              "## 制作说明", "",
              "模型代码、测试和说明文字使用生成式AI辅助编写；本报告的表格和结论数值由保存的仿真输出自动汇总。数据均为模拟输入，参赛者仍需人工审查模型假设、参数依据和数据来源，并在正式材料中按赛事要求披露AI使用情况。", ""]
    (output / "实验分析.md").write_text("\n".join(lines),encoding="utf-8")
