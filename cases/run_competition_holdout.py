"""Freeze existing V0.7 layouts and evaluate 20 additional seeds on two maps.

Python 3.10+ standard library only. Run from the repository root:
python cases/run_competition_holdout.py
Use --output for another NEW directory; existing evidence is never overwritten.
"""
from copy import deepcopy
import argparse
import gzip
import hashlib
from itertools import product
import json
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from engine import Config
from reporting import write_csv, write_json
from site_selection import evaluate_site_design
from verify_continuous_model import audit_result

SEEDS = list(range(20261020, 20261040))
METRICS = {'on_time_rate': 'higher', 'mean_delivery': 'lower', 'p95_delivery': 'lower',
           'mean_exposure': 'lower', 'completion_rate': 'higher',
           'failed_orders': 'lower', 'air_conflict_count': 'lower'}
SOURCES = {'demo_5': ROOT/'results/sites_v1/study.json',
           'user_map_h30_d5': ROOT/'results/user_map_300m/studies/h30_d5.json.gz'}


def load(path):
    data = gzip.decompress(path.read_bytes()) if path.suffix == '.gz' else path.read_bytes()
    return json.loads(data.decode('utf-8-sig'))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT/'results/competition_v07')
    args = parser.parse_args()
    output = args.output
    if output.exists() and any(output.iterdir()):
        parser.error('输出目录非空，请选择新目录，保留既有证据')
    output.mkdir(parents=True, exist_ok=True)
    (output/'studies').mkdir()
    raw, pairs, audits, frozen, source_hashes = [], [], [], {}, {}
    for name, path in SOURCES.items():
        source_hashes[str(path.relative_to(ROOT)).replace('\\', '/')] = hashlib.sha256(path.read_bytes()).hexdigest()
        original = load(path)
        assert set(SEEDS).isdisjoint(original['design_seeds'])
        assert set(SEEDS).isdisjoint(original['evaluation_seeds'])
        design = {k: deepcopy(original[k]) for k in ('scene', 'design_seed', 'design_seeds', 'station_count', 'candidates', 'choices')}
        design['config'] = Config(**original['base_config'])
        design['routes'] = deepcopy(original['results'][0]['routes'])
        choices_before = deepcopy(design['choices'])
        frozen[name] = {'base_config': original['base_config'], 'design_seeds': original['design_seeds'],
                        'initial_evaluation_seeds': original['evaluation_seeds'],
                        'additional_evaluation_seeds': SEEDS,
                        'choices': {k: {field: v[field] for field in ('pad_ids', 'fleet_allocation')}
                                    for k, v in original['choices'].items()}}
        results = []
        for seed, scenario in product(SEEDS, ('normal', 'peak')):
            result = evaluate_site_design(design, seed, scenario)
            for key, plan in result['plans'].items():
                assert plan['site_configuration'] == frozen[name]['choices'][key]
                assert plan['orders'] == result['plans']['fixed']['orders']
                assert len(plan['drones']) == original['base_config']['drone_count']
            audits.append({'case': name, 'seed': seed, 'scenario': scenario, **audit_result(result)})
            results.append(result)
            print(f'{name}: new seed {seed}, {scenario}, independently audited', flush=True)
        assert design['choices'] == choices_before
        snapshot = {'case': name, 'frozen_design': frozen[name], 'results': results}
        (output/f'studies/{name}.json.gz').write_bytes(gzip.compress(json.dumps(snapshot, ensure_ascii=False).encode('utf-8'), mtime=0))
        for cohort, cohort_results in (('initial_5', original['results']), ('additional_20', results)):
            for result in cohort_results:
                for key, plan in result['plans'].items():
                    raw.append({'case': name, 'cohort': cohort, 'scenario': result['config']['scenario'],
                                'seed': result['evaluation_seed'], 'plan': key,
                                'configuration': plan['configuration_label'], **plan['stats']})
                for baseline in ('fixed', 'distance'):
                    a, b = result['plans']['combined']['stats'], result['plans'][baseline]['stats']
                    pairs.append({'case': name, 'cohort': cohort, 'scenario': result['config']['scenario'],
                                  'seed': result['evaluation_seed'], 'baseline': baseline,
                                  **{m+'_difference': a[m]-b[m] for m in METRICS}})
    summaries = []
    for name, cohort, scenario, baseline, metric in product(SOURCES, ('initial_5', 'additional_20'), ('normal', 'peak'), ('fixed', 'distance'), METRICS):
        rows = [r for r in pairs if (r['case'], r['cohort'], r['scenario'], r['baseline']) == (name, cohort, scenario, baseline)]
        values = [r[metric+'_difference'] for r in rows]
        direction = 1 if METRICS[metric] == 'higher' else -1
        signed = [v*direction for v in values]
        summaries.append({'case': name, 'cohort': cohort, 'scenario': scenario, 'baseline': baseline,
                          'metric': metric, 'preferred': METRICS[metric], 'runs': len(values),
                          'combined_better': sum(v > 1e-8 for v in signed),
                          'ties_within_1e_minus_8': sum(abs(v) <= 1e-8 for v in signed),
                          'combined_worse': sum(v < -1e-8 for v in signed),
                          'difference_mean': statistics.mean(values), 'difference_sample_std': statistics.stdev(values),
                          'difference_min': min(values), 'difference_max': max(values)})
    write_csv(output/'raw_metrics.csv', raw)
    write_csv(output/'paired_differences.csv', pairs)
    write_csv(output/'difference_summary.csv', summaries)
    write_json(output/'frozen_designs.json', frozen)
    write_json(output/'independent_audit.json', audits)
    for relative, digest in source_hashes.items():
        assert hashlib.sha256((ROOT/relative).read_bytes()).hexdigest() == digest
    source_files = ['engine.py', 'site_selection.py', 'airspace.py', 'reporting.py', 'facility.py',
                    'cases/run_competition_holdout.py', 'cases/verify_continuous_model.py']
    manifest = {'version': '0.7.0-sites', 'purpose': '追加独立种子评价；冻结布局、不调参，不是新地图外部验证或统计显著性检验',
                'new_evaluation_seeds': SEEDS, 'metric_directions': METRICS,
                'difference_definition': '运行优选减基线；各指标独立统计，无合成总胜率',
                'initial_and_additional_cohorts_separate': True, 'source_study_sha256': source_hashes,
                'source_sha256': {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in source_files},
                'output_sha256': {str(p.relative_to(output)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in output.rglob('*') if p.is_file()},
                'new_plan_runs': len(audits)*3, 'new_task_records_including_repeated_orders': sum(r['task_records'] for r in audits),
                'continuous_episode_definition': '正时长同高度空中区间内严格小于20米；零时长交接不计事件；地面起飞准备与降落服务排除',
                'limits': '模型生成订单；截图位置/实际点位/楼高/人流未核实；固定巡航高度理想运动，非真实飞行验证'}
    lines = ['# V0.7冻结布局追加独立种子检验', '',
             '以既有设计布局和参数固定后，追加20261020—20261039共20个评价种子。两张既有地图分别运行正常/高峰，合计240条新方案运行、10800条重复评价任务记录。既有5种子单列，不与新增样本混算胜负。', '',
             '这是新订单种子检验，未增加真实场地、实测需求或独立地图。所有指标分别统计；差值为运行优选减基线。胜/平/负按表中方向判断，平局容差1e-8；没有统计显著性检验或总胜率。', '',
             '|地图|场景|基线|指标|优/平/劣（20次）|差值均值|样本SD|差值范围|',
             '|---|---|---|---|---|---:|---:|---|']
    for row in summaries:
        if row['cohort'] == 'additional_20' and row['metric'] in ('on_time_rate', 'mean_delivery', 'mean_exposure'):
            lines.append(f"|{row['case']}|{row['scenario']}|{row['baseline']}|{row['metric']}|{row['combined_better']}/{row['ties_within_1e_minus_8']}/{row['combined_worse']}|{row['difference_mean']:.5f}|{row['difference_sample_std']:.5f}|[{row['difference_min']:.5f}, {row['difference_max']:.5f}]|")
    lines += ['', '准时率差值以比例表示（乘100为百分点）；配送时间单位秒；暴露为代理值。均值、P95按成功订单统计，同时报告完成率和失败数。', '',
              '独立检查不调用生产间距检测器，从导出路线点和任务时刻重建分段运动，用区间内相对运动最近点检查持续间距；检查服务日历和无人机任务不重叠。空中/地面切换同一瞬间的零时长交接按现有模型不计持续事件，此约定不能解释为真实起降安全。', '',
              '复现：`python cases/run_competition_holdout.py --output results/competition_v07_reproduction`。输出目录必须为空，旧结果不会被覆盖。源码/源研究/结果哈希见manifest.json；完整新任务在studies/*.json.gz中。']
    (output/'追加种子检验.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    manifest['output_sha256'] = {str(p.relative_to(output)).replace('\\', '/'): hashlib.sha256(p.read_bytes()).hexdigest()
                                  for p in output.rglob('*') if p.is_file()}
    write_json(output/'manifest.json', manifest)
    print(f'Saved: {output}; {manifest["new_plan_runs"]} new plan runs, {manifest["new_task_records_including_repeated_orders"]} task records', flush=True)


if __name__ == '__main__':
    main()
