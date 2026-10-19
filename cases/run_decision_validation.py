"""Freeze a prospective protocol, then validate read-only V0.7 diagnostics.

First: python cases/run_decision_validation.py --freeze-protocol
Then:  python cases/run_decision_validation.py
Reproduction uses a new --output directory. Existing evidence is not overwritten.
"""
from copy import deepcopy
from dataclasses import replace
from datetime import datetime, timezone, timedelta
import argparse
import csv
import gzip
import hashlib
from itertools import product
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from decision_support import diagnose_site_study, export_decision_diagnostics
from engine import Config, generate_orders, simulate
from facility import _objective
from reporting import write_csv, write_json
from site_selection import evaluate_site_design, METRICS
from verify_continuous_model import audit_result

SOURCES = {'demo_5': 'results/sites_v1/study.json',
           'user_map_h30_d5': 'results/user_map_300m/studies/h30_d5.json.gz'}
NEW_SEEDS = list(range(20261040, 20261060))
RULE_SOURCES = ['decision_support.py', 'cases/run_decision_validation.py',
                'cases/verify_continuous_model.py', 'tests/test_decision_support.py']
CORE_SOURCES = ['engine.py', 'site_selection.py', 'facility.py', 'airspace.py', 'reporting.py']
PAIR_METRICS = ('failure_rate', 'on_time_rate', 'mean_delivery', 'mean_exposure')


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    data = gzip.decompress(path.read_bytes()) if path.suffix == '.gz' else path.read_bytes()
    return json.loads(data.decode('utf-8-sig'))


def close(a, b, context):
    if a is None or b is None:
        assert a is b, (context, a, b)
    else:
        assert math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-7), (context, a, b)


def freeze(protocol_path):
    if protocol_path.exists():
        raise ValueError('协议已存在；不得事后覆盖预注册，请另存修订并说明原因')
    cases = {}
    for name, relative in SOURCES.items():
        study = load(ROOT/relative)
        previous_seeds = set(study['evaluation_seeds']) | set(study['design_seeds'])
        previous_seeds |= set(load(ROOT/'results/competition_v07/frozen_designs.json')[name]['additional_evaluation_seeds'])
        assert previous_seeds.isdisjoint(NEW_SEEDS)
        cases[name] = {'source_study': relative, 'source_study_sha256': digest(ROOT/relative),
                       'base_config': study['base_config'], 'design_seeds': study['design_seeds'],
                       'choices': {k: {field: deepcopy(v[field]) for field in ('pad_ids', 'fleet_allocation')}
                                   for k, v in study['choices'].items()},
                       'scenarios': ['normal', 'peak'], 'new_evaluation_seeds': NEW_SEEDS}
    protocol = {'protocol_version': '1.0',
                'frozen_at_beijing': datetime.now(timezone(timedelta(hours=8))).isoformat(),
                'state': '事前冻结；仅在本文件落盘后开始新增种子评价',
                'objective': '验证评价后决策诊断的可审计性、服务门槛与四指标帕累托，不优化核心模型或选择布局',
                'minimum_on_time_rate': .90,
                'threshold_basis': '团队可调研究目标；非赛事/法规；按每场景跨运行等权平均准时率，不保证每种子达标',
                'four_pareto_metrics': {'failure_rate': 'lower', 'on_time_rate': 'higher',
                                        'mean_delivery': 'lower', 'mean_exposure': 'lower'},
                'failure_rate_definition': '逐运行failed_orders/total_orders，然后运行等权；不使用汇总计数比值',
                'diagnostic_tolerance': 1e-8,
                'original_design_decision': '保持原精确浮点词典序，同时报告first_difference_layer与跳过1e-8内差异的first_substantive_difference_layer；不重新排序原候选',
                'missing_value_rule': '缺失、NaN、Infinity、bool或缺少评价种子均待验证；不零填；任一方案四指标不全则场景帕累托整体待验证',
                'no_automatic_winner': '三方案均未达标即不推荐；有达标方案仅列候选与取舍，不自动优选',
                'sample_separation': '新20261040—59不与旧20261015—39混算；不根据新增结果调参或重选布局',
                'cases': cases,
                'expected_new_plan_runs': 240, 'expected_new_task_records_including_repeats': 10800,
                'design_stability': {'candidate_layouts': 43, 'design_seeds_per_map': 3, 'scenarios': ['normal', 'peak'],
                                     'expected_layout_runs': 258,
                                     'subsets': '全3种子及逐次留出1种子的3个子集；保存全部候选原目标得分/排序',
                                     'decision': '保持原精确float排序；仅分析设计样本敏感性，不更新choice，不作为独立提升证据'},
                'core_source_sha256': {name: digest(ROOT/name) for name in CORE_SOURCES},
                'rule_source_sha256': {name: digest(ROOT/name) for name in RULE_SOURCES},
                'independent_checks': ['逐任务指标重算', '不调用生产检测器的连续轨迹与资源检查',
                                       '独立重算门槛、四指标支配关系与配对差值', '源研究/布局/规则与协议哈希冻结'],
                'limitations': '两张既有地图的新随机订单检验；不是新场地、实测运营或真实飞行验证；90%不代表官方通过线'}
    protocol_path.parent.mkdir(parents=True, exist_ok=True)
    protocol_path.write_text(json.dumps(protocol, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    print(f'Frozen before evaluation: {protocol_path}; SHA256={digest(protocol_path)}', flush=True)


def verified_metrics(plan):
    jobs, failed, orders = plan['jobs'], plan['failed'], plan['orders']
    assert len(jobs)+len(failed) == len(orders)
    total, successful = len(orders), len(jobs)
    return {'failure_rate': len(failed)/total,
            'on_time_rate': sum(j['delivered_at'] <= j['due_at']+1e-8 for j in jobs)/total,
            'mean_delivery': statistics.mean(j['delivered_at']-j['created_at'] for j in jobs) if successful else None,
            'mean_exposure': statistics.mean(j['exposure'] for j in jobs) if successful else None}


def objective_difference(a, b):
    exact = next((i+1 for i, (x, y) in enumerate(zip(a, b)) if x != y), None)
    substantive = next((i+1 for i, (x, y) in enumerate(zip(a, b)) if abs(x-y) > 1e-8), None)
    return {'exact_first_difference_layer': exact, 'first_substantive_difference_layer': substantive,
            'exact_difference': a[exact-1]-b[exact-1] if exact else 0.,
            'substantive_difference': a[substantive-1]-b[substantive-1] if substantive else 0.}


def design_stability(case, source, design):
    seeds, scenarios = source['design_seeds'], ('normal', 'peak')
    orders = {(seed, scenario): generate_orders(design['scene'], replace(design['config'], scenario=scenario), seed)
              for seed, scenario in product(seeds, scenarios)}
    samples, raw = {}, []
    for index, candidate in enumerate(source['candidates']):
        key = tuple(candidate['pad_ids'])
        samples[key] = {}
        for seed, scenario in product(seeds, scenarios):
            stats = simulate(design['scene'], replace(design['config'], scenario=scenario),
                             candidate['pad_ids'], orders[seed, scenario], design['routes'],
                             candidate['fleet_allocation'])['stats']
            samples[key][seed, scenario] = stats
            raw.append({'case': case, 'configuration': '+'.join(key), 'design_seed': seed,
                        'scenario': scenario, **stats})
        full = _objective([samples[key][seed, scenario] for scenario in scenarios for seed in seeds])
        assert full == candidate['objective'], ('Full design objective changed', case, key, full, candidate['objective'])
        print(f'{case}: design replay {index+1}/{len(source["candidates"])} layouts', flush=True)
    original = tuple(source['choices']['combined']['pad_ids'])
    scores, selections = [], []
    for omitted in (None, *seeds):
        included = [s for s in seeds if s != omitted]
        ranked = sorted(({'pad_ids': list(key), 'objective': _objective([values[seed, scenario] for scenario in scenarios for seed in included])}
                         for key, values in samples.items()), key=lambda c: (c['objective'], tuple(c['pad_ids'])))
        for rank, candidate in enumerate(ranked, 1):
            scores.append({'case': case, 'subset': 'full' if omitted is None else f'leave_out_{omitted}',
                           'included_design_seeds': ','.join(str(s) for s in included),
                           'omitted_design_seed': omitted, 'rank': rank, 'configuration': '+'.join(candidate['pad_ids']),
                           **{f'objective_{i+1}': v for i, v in enumerate(candidate['objective'])}})
        winner = ranked[0]
        original_scored = next(c for c in ranked if tuple(c['pad_ids']) == original)
        if omitted is None:
            assert tuple(winner['pad_ids']) == original
        selections.append({'case': case, 'omitted_design_seed': omitted, 'included_design_seeds': included,
                           'selected_pad_ids': winner['pad_ids'], 'original_pad_ids': list(original),
                           'selection_changed': tuple(winner['pad_ids']) != original,
                           'selected_objective': winner['objective'], 'original_objective_in_subset': original_scored['objective'],
                           'winner_vs_original': objective_difference(winner['objective'], original_scored['objective']),
                           'winner_vs_runner_up': objective_difference(winner['objective'], ranked[1]['objective'])})
    return raw, scores, selections


def audit_diagnostics(study, diagnostics):
    # Reference decisions are computed here from jobs, not the diagnostic helper.
    by_scenario = {}
    for scenario in ('normal', 'peak'):
        results = [r for r in study['results'] if r['config']['scenario'] == scenario]
        means = {}
        for plan in ('fixed', 'distance', 'combined'):
            values = [verified_metrics(r['plans'][plan]) for r in results]
            means[plan] = {m: statistics.mean(v[m] for v in values) if all(v[m] is not None for v in values) else None
                           for m in PAIR_METRICS}
        by_scenario[scenario] = means
        actual = next(s for s in diagnostics['scenarios'] if s['scenario'] == scenario)
        statuses = []
        for plan, expected in means.items():
            candidate = next(p for p in actual['plans'] if p['plan'] == plan)
            for metric in PAIR_METRICS:
                close(candidate['metrics'][metric], expected[metric], f'{scenario}/{plan}/{metric}')
            status = 'meets' if expected['on_time_rate']+1e-8 >= diagnostics['minimum_on_time_rate'] else 'below'
            assert candidate['service_status'] == status
            statuses.append(status)
            dominators = []
            for other, values in means.items():
                if other == plan:
                    continue
                improvements = [values['failure_rate']-expected['failure_rate'],
                                expected['on_time_rate']-values['on_time_rate'],
                                values['mean_delivery']-expected['mean_delivery'],
                                values['mean_exposure']-expected['mean_exposure']]
                if all(x <= 1e-8 for x in improvements) and any(x < -1e-8 for x in improvements):
                    dominators.append(other)
            assert candidate['dominated_by'] == dominators
            assert candidate['pareto_status'] == ('dominated' if dominators else 'non_dominated')
        assert actual['recommendation_status'] == ('not_recommended' if all(s == 'below' for s in statuses) else 'comparison_required')
    return {'job_based_metric_gate_and_pareto_checks': 'passed', 'scenario_means': by_scenario,
            'diagnostics_do_not_optimize': True}


def evaluate(protocol, output):
    if output.exists() and any(output.iterdir()):
        raise ValueError('输出目录须为空；请选新目录保留已有证据')
    for field in ('core_source_sha256', 'rule_source_sha256'):
        for name, expected in protocol[field].items():
            assert digest(ROOT/name) == expected, ('Frozen source changed', name)
    output.mkdir(parents=True, exist_ok=True)
    (output/'studies').mkdir()
    rows, pairs, trajectory_audits, diagnostic_audits = [], [], [], []
    stability_raw, stability_scores, stability_selections = [], [], []
    for case, info in protocol['cases'].items():
        source_path = ROOT/info['source_study']
        assert digest(source_path) == info['source_study_sha256']
        source = load(source_path)
        design = {k: deepcopy(source[k]) for k in ('scene', 'design_seed', 'design_seeds', 'station_count', 'candidates', 'choices')}
        design['config'] = Config(**info['base_config'])
        design['routes'] = deepcopy(source['results'][0]['routes'])
        before = deepcopy(design['choices'])
        replay, scores, selections = design_stability(case, source, design)
        stability_raw.extend(replay)
        stability_scores.extend(scores)
        stability_selections.extend(selections)
        results, raw = [], []
        for seed, scenario in product(info['new_evaluation_seeds'], info['scenarios']):
            result = evaluate_site_design(design, seed, scenario)
            reference_orders = result['plans']['fixed']['orders']
            for plan, data in result['plans'].items():
                assert data['site_configuration'] == info['choices'][plan]
                assert data['orders'] == reference_orders
                assert len(data['drones']) == info['base_config']['drone_count']
                values = verified_metrics(data)
                for metric in ('on_time_rate', 'mean_delivery', 'mean_exposure'):
                    close(values[metric], data['stats'][metric], metric)
                raw.append({'scenario': scenario, 'evaluation_seed': seed, 'plan': plan,
                            'plan_name': data['name'], 'configuration': data['configuration_label'], **data['stats']})
            trajectory_audits.append({'case': case, 'scenario': scenario, 'evaluation_seed': seed, **audit_result(result)})
            for baseline in ('fixed', 'distance'):
                a, b = verified_metrics(result['plans']['combined']), verified_metrics(result['plans'][baseline])
                pairs.append({'case': case, 'scenario': scenario, 'evaluation_seed': seed, 'baseline': baseline,
                              **{m+'_difference': a[m]-b[m] if a[m] is not None and b[m] is not None else None for m in PAIR_METRICS}})
            results.append(result)
            print(f'{case}: {seed}/{scenario}, new frozen evaluation and independent audit passed', flush=True)
        assert before == design['choices']
        summary = []
        for scenario, plan in product(info['scenarios'], ('fixed', 'distance', 'combined')):
            group = [r for r in raw if r['scenario'] == scenario and r['plan'] == plan]
            row = {k: group[0][k] for k in ('scenario', 'plan', 'plan_name', 'configuration')}
            row['runs'] = len(group)
            for metric in METRICS:
                values = [r[metric] for r in group if r[metric] is not None]
                row[metric] = statistics.mean(values) if values else None
                row[metric+'_std'] = statistics.stdev(values) if len(values) > 1 else (0. if values else None)
                row[metric+'_valid_runs'] = len(values)
            summary.append(row)
        study = {k: deepcopy(source[k]) for k in ('version', 'base_config', 'scene', 'design_seed', 'design_seeds',
                                                  'station_count', 'candidate_count', 'design_seconds', 'choices', 'candidates')}
        study.update(evaluation_seeds=info['new_evaluation_seeds'], results=results, raw_metrics=raw,
                     summary=summary, diagnostic_case=case, design_provenance='沿用历史设计耗时与候选评分，不重新设计')
        serialized_before = json.dumps(study, ensure_ascii=False, sort_keys=True)
        diagnostics = diagnose_site_study(study, protocol['minimum_on_time_rate'])
        diagnostic_audits.append({'case': case, **audit_diagnostics(study, diagnostics)})
        export_decision_diagnostics(study, output/case, protocol['minimum_on_time_rate'])
        assert json.dumps(study, ensure_ascii=False, sort_keys=True) == serialized_before
        write_csv(output/case/'raw_metrics.csv', raw)
        write_csv(output/case/'summary.csv', summary)
        (output/f'studies/{case}.json.gz').write_bytes(gzip.compress(json.dumps(study, ensure_ascii=False, allow_nan=False).encode('utf-8'), mtime=0))
        rows.extend({'case': case, **r} for r in raw)
        assert digest(source_path) == info['source_study_sha256']
    write_csv(output/'raw_metrics.csv', rows)
    write_csv(output/'paired_differences.csv', pairs)
    difference_summary = []
    for case, scenario, baseline, metric in product(protocol['cases'], ('normal', 'peak'), ('fixed', 'distance'), PAIR_METRICS):
        values = [r[metric+'_difference'] for r in pairs if (r['case'], r['scenario'], r['baseline']) == (case, scenario, baseline)]
        valid = [v for v in values if v is not None]
        sign = 1 if metric == 'on_time_rate' else -1
        difference_summary.append({'case': case, 'scenario': scenario, 'baseline': baseline, 'metric': metric,
                                   'runs': len(values), 'valid_runs': len(valid),
                                   'combined_better': sum(v*sign > 1e-8 for v in valid),
                                   'ties_within_1e_minus_8': sum(abs(v) <= 1e-8 for v in valid),
                                   'combined_worse': sum(v*sign < -1e-8 for v in valid),
                                   'difference_mean': statistics.mean(valid) if valid else None,
                                   'difference_sample_std': statistics.stdev(valid) if len(valid) > 1 else None,
                                   'difference_min': min(valid) if valid else None, 'difference_max': max(valid) if valid else None})
    write_csv(output/'difference_summary.csv', difference_summary)
    write_json(output/'independent_trajectory_audit.json', trajectory_audits)
    write_json(output/'independent_diagnostic_audit.json', diagnostic_audits)
    write_csv(output/'design_seed_stats.csv', stability_raw)
    write_csv(output/'design_subset_candidate_scores.csv', stability_scores)
    write_json(output/'design_stability.json', stability_selections)
    assert len(stability_raw) == protocol['design_stability']['expected_layout_runs']
    assert len(rows) == protocol['expected_new_plan_runs']
    assert sum(a['task_records'] for a in trajectory_audits) == protocol['expected_new_task_records_including_repeats']
    return rows, difference_summary, trajectory_audits


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--protocol', type=Path, default=ROOT/'docs/参赛验收/第二轮实验协议.json')
    parser.add_argument('--output', type=Path, default=ROOT/'results/decision_v07_round2')
    parser.add_argument('--freeze-protocol', action='store_true')
    args = parser.parse_args()
    if args.freeze_protocol:
        freeze(args.protocol)
        return
    if not args.protocol.is_file():
        parser.error('须先--freeze-protocol事前冻结协议，不能先运行评价后补写')
    protocol_bytes = args.protocol.read_bytes()
    protocol = json.loads(protocol_bytes)
    started = datetime.now(timezone(timedelta(hours=8)))
    if started <= datetime.fromisoformat(protocol['frozen_at_beijing']):
        parser.error('评价开始时间必须晚于协议冻结时间')
    rows, differences, audits = evaluate(protocol, args.output)
    assert args.protocol.read_bytes() == protocol_bytes
    lines = ['# 第二轮事前冻结的新种子与决策诊断验证', '',
             '新增评价种子20261040—20261059；两张既有地图、冻结旧布局/参数。240条方案评价、10800条重复任务，未与旧5/20种子混算，未根据新结果调参。', '',
             '90%为团队可调平均准时率研究目标，不是赛事或法规要求。四指标帕累托为评价后比较，不产生自动最优布局。', '',
             '|地图|高峰基线|指标|设计优选优/平/劣|差值均值|样本SD|范围|', '|---|---|---|---|---:|---:|---|']
    for r in differences:
        if r['scenario'] == 'peak':
            lines.append(f"|{r['case']}|{r['baseline']}|{r['metric']}|{r['combined_better']}/{r['ties_within_1e_minus_8']}/{r['combined_worse']}|{r['difference_mean']:.6f}|{r['difference_sample_std']:.6f}|[{r['difference_min']:.6f}, {r['difference_max']:.6f}]|")
    lines += ['', '差值=设计优选（原运行优选）减基线；准时率/失败率为比例，配送为秒，暴露为代理值。旧研究和不利反例原样保留。', '',
              '每图decision_diagnostics.json/decision_comparisons.csv/decision_diagnostics.md保存可追溯目标、每方案服务状态、四指标基线差、帕累托及原设计首分歧层。原始任务在studies/*.json.gz。', '',
              '复现：python cases/run_decision_validation.py --output results/decision_v07_round2_reproduction。原协议和规则/核心源码哈希必须匹配；若修复诊断代码，应保留原结果、说明协议修订并使用新版本证据。']
    (args.output/'第二轮新增种子验证.md').write_text('\n'.join(lines)+'\n', encoding='utf-8')
    for field in ('core_source_sha256', 'rule_source_sha256'):
        for name, expected in protocol[field].items():
            assert digest(ROOT/name) == expected
    manifest = {'protocol_path': str(args.protocol.relative_to(ROOT)).replace('\\', '/'),
                'protocol_sha256': hashlib.sha256(protocol_bytes).hexdigest(),
                'evaluation_started_at_beijing': started.isoformat(),
                'evaluation_finished_at_beijing': datetime.now(timezone(timedelta(hours=8))).isoformat(),
                'new_evaluation_seeds': NEW_SEEDS, 'new_plan_runs': len(rows),
                'new_task_records_including_repeats': sum(a['task_records'] for a in audits),
                'core_source_sha256': protocol['core_source_sha256'], 'rule_source_sha256': protocol['rule_source_sha256'],
                'old_source_studies_unchanged': True, 'diagnostic_did_not_mutate_studies': True,
                'previous_counterexamples_retained': ['results/sites_v1', 'results/user_map_300m', 'results/competition_v07'],
                'output_sha256': {str(p.relative_to(args.output)).replace('\\', '/'): digest(p)
                                  for p in args.output.rglob('*') if p.is_file()}}
    write_json(args.output/'manifest.json', manifest)
    print(f'Saved {args.output}: {len(rows)} plan runs, {sum(a["task_records"] for a in audits)} repeated task records', flush=True)


if __name__ == '__main__':
    main()
