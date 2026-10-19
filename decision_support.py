"""Read-only, auditable diagnostics for frozen V0.7 independent evaluations.

This module neither optimizes layouts nor changes a study. The service target is
a team-defined research setting, never an official or regulatory requirement.
"""
from collections import defaultdict
import csv
import json
import math
from pathlib import Path
import statistics

TOLERANCE = 1e-8
METRIC_NAMES = {'failure_rate': '失败率', 'on_time_rate': '准时率',
                'mean_delivery': '平均配送秒数', 'mean_exposure': '路径暴露代理值'}
DIRECTIONS = {'failure_rate': -1, 'on_time_rate': 1, 'mean_delivery': -1, 'mean_exposure': -1}
PLAN_NAMES = {'fixed': '固定位置', 'distance': '距离优先', 'combined': '设计优选（原运行优选）'}
LAYER_NAMES = ['失败率', '非准时率', '每单超时秒数', '配送秒数＋30×路径暴露']


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _mean_complete(values, rate=False):
    if not values or any(not _number(v) or v < 0 or (rate and v > 1) for v in values):
        return None
    return statistics.mean(values)


def _metrics(rows):
    rates = []
    for row in rows:
        failed, total = row.get('failed_orders'), row.get('total_orders')
        valid = (_number(failed) and _number(total) and total > 0 and
                 int(failed) == failed and int(total) == total and 0 <= failed <= total)
        rates.append(failed/total if valid else None)
    return {'failure_rate': _mean_complete(rates, True),
            'on_time_rate': _mean_complete([r.get('on_time_rate') for r in rows], True),
            'mean_delivery': _mean_complete([r.get('mean_delivery') for r in rows]),
            'mean_exposure': _mean_complete([r.get('mean_exposure') for r in rows])}


def _design_metrics(candidate, scenario):
    stats = candidate.get('design_stats', {}).get(scenario, {})
    completion = stats.get('completion_rate')
    failure = 1-completion if _number(completion) and 0 <= completion <= 1 else None
    return {'failure_rate': failure,
            **{k: stats.get(k) if _number(stats.get(k)) and stats[k] >= 0 and
               (k != 'on_time_rate' or stats[k] <= 1) else None
               for k in ('on_time_rate', 'mean_delivery', 'mean_exposure')}}


def _difference(a, b):
    return a-b if _number(a) and _number(b) else None


def _dominates(a, b):
    advantages = [(a[k]-b[k])*DIRECTIONS[k] for k in METRIC_NAMES]
    return all(v >= -TOLERANCE for v in advantages) and any(v > TOLERANCE for v in advantages)


def diagnose_site_study(study, minimum_on_time_rate=0.90):
    """Diagnose frozen independent evaluations without mutating study.

Failure rate is the equal-weight mean of each run's failed/total. A missing,
NaN, infinity or boolean observation leaves that metric pending, rather than
dropping observations or replacing them with zero. Pareto checks use 1e-8;
the recorded original lexicographic decision uses its exact float ordering.
"""
    if not _number(minimum_on_time_rate) or not 0 <= minimum_on_time_rate <= 1:
        raise ValueError('准时率目标须为0—1的有限数值，不能是布尔值')
    groups = defaultdict(list)
    for row in study.get('raw_metrics', []):
        if isinstance(row, dict):
            groups[row.get('scenario'), row.get('plan')].append(row)
    scenarios = []
    for scenario, name in (('normal', '正常'), ('peak', '高峰')):
        plans = []
        for key, label in PLAN_NAMES.items():
            rows = groups[scenario, key]
            values = _metrics(rows)
            expected_seeds = study.get('evaluation_seeds', [])
            actual_seeds = [row.get('evaluation_seed') for row in rows]
            complete_runs = (not expected_seeds or
                             (len(actual_seeds) == len(expected_seeds) and
                              len(set(actual_seeds)) == len(actual_seeds) and
                              set(actual_seeds) == set(expected_seeds)))
            if not complete_runs:
                values = {metric: None for metric in METRIC_NAMES}
            on_time = values['on_time_rate']
            status = 'pending' if on_time is None else ('meets' if on_time+TOLERANCE >= minimum_on_time_rate else 'below')
            plans.append({'plan': key, 'plan_name': label, 'metrics': values,
                          'runs': len(rows), 'evaluation_runs_complete': complete_runs,
                          'metric_status': 'verified' if all(v is not None for v in values.values()) else 'pending',
                          'service_status': status, 'pareto_status': 'pending', 'dominated_by': [],
                          'baseline_differences': {}})
        all_complete = all(p['metric_status'] == 'verified' for p in plans)
        for plan in plans:
            for baseline in ('fixed', 'distance'):
                other = next(p for p in plans if p['plan'] == baseline)
                plan['baseline_differences'][baseline] = {
                    m: _difference(plan['metrics'][m], other['metrics'][m]) for m in METRIC_NAMES}
            if all_complete:
                plan['dominated_by'] = [other['plan'] for other in plans
                                        if other is not plan and _dominates(other['metrics'], plan['metrics'])]
                plan['pareto_status'] = 'dominated' if plan['dominated_by'] else 'non_dominated'
        statuses = [p['service_status'] for p in plans]
        if all(s == 'below' for s in statuses):
            recommendation, message = 'not_recommended', f'三方案均未达到{minimum_on_time_rate:.1%}准时率研究目标，当前场景不推荐采用任何方案；需复核需求、机队或运行条件。'
        elif 'pending' in statuses:
            recommendation, message = 'pending', '存在准时率数据缺失，当前推荐判断待验证。'
        else:
            recommendation, message = 'comparison_required', '存在达到准时率研究目标的方案；仅列候选与指标取舍，不自动推荐最优。'
        if not all_complete:
            message += ' 四指标存在缺失，帕累托关系整体待验证。'
        scenarios.append({'scenario': scenario, 'scenario_name': name, 'plans': plans,
                          'recommendation_status': recommendation, 'message': message})
    comparisons = []
    choices = study.get('choices', {})
    combined = choices.get('combined', {})
    for baseline in ('fixed', 'distance'):
        other = choices.get(baseline, {})
        a, b = combined.get('objective'), other.get('objective')
        valid = (isinstance(a, (list, tuple)) and isinstance(b, (list, tuple)) and
                 len(a) == len(b) == 4 and all(_number(v) for v in [*a, *b]))
        layer, direction, near_tie = None, 'pending', False
        substantive_layer, substantive_direction = None, 'pending'
        if valid:
            direction = 'equal'
            for i, (x, y) in enumerate(zip(a, b)):
                if x != y:
                    layer, direction = i+1, 'combined_better' if x < y else 'combined_worse'
                    near_tie = abs(x-y) <= TOLERANCE
                    break
            substantive_direction = 'approximately_equal'
            for i, (x, y) in enumerate(zip(a, b)):
                if abs(x-y) > TOLERANCE:
                    substantive_layer = i+1
                    substantive_direction = 'combined_better' if x < y else 'combined_worse'
                    break
        reversals = []
        for scenario in scenarios:
            design_a = _design_metrics(combined, scenario['scenario'])
            design_b = _design_metrics(other, scenario['scenario'])
            evaluated = next(p for p in scenario['plans'] if p['plan'] == 'combined')
            for metric in METRIC_NAMES:
                design_delta = _difference(design_a[metric], design_b[metric])
                evaluation_delta = evaluated['baseline_differences'][baseline][metric]
                if (design_delta is not None and evaluation_delta is not None and
                        design_delta*DIRECTIONS[metric] > TOLERANCE and
                        evaluation_delta*DIRECTIONS[metric] < -TOLERANCE):
                    reversals.append({'scenario': scenario['scenario'], 'metric': metric,
                                      'design_difference': design_delta, 'evaluation_difference': evaluation_delta})
        comparisons.append({'baseline': baseline, 'first_difference_layer': layer,
                            'layer_name': LAYER_NAMES[layer-1] if layer else None,
                            'design_direction': direction, 'near_tie_at_first_difference': near_tie,
                            'first_substantive_difference_layer': substantive_layer,
                            'substantive_layer_name': LAYER_NAMES[substantive_layer-1] if substantive_layer else None,
                            'substantive_direction': substantive_direction,
                            'combined_objective': list(a) if valid else None,
                            'baseline_objective': list(b) if valid else None,
                            'evaluation_reversals': reversals})
    diagnostics = {
        'schema_version': '1.0', 'study_version': study.get('version'),
        'minimum_on_time_rate': float(minimum_on_time_rate),
        'threshold_basis': '团队可调研究目标；不是赛事、法规或已验证运营要求；只考察跨运行等权平均准时率',
        'data_role': '冻结布局的评价集诊断，不是新优化、调参或因果解释',
        'metric_basis': '失败率逐运行failed_orders/total_orders后等权；其他指标逐运行等权；任一观测无效则该指标待验证',
        'pareto_tolerance': TOLERANCE,
        'difference_definition': '当前方案减对应基线；失败率/秒数/暴露越低越好，准时率越高越好',
        'evaluation_seeds': list(study.get('evaluation_seeds', [])),
        'design_seeds': list(study.get('design_seeds', [])),
        'scenarios': scenarios, 'design_comparisons': comparisons,
        'limitations': ['服务门槛判断使用场景跨运行平均值，不保证每个种子或每个订单达标。',
                        '帕累托非劣仅相对于本次三方案和四指标，不证明全候选布局或真实世界最优。',
                        '原词典序按精确浮点首分歧解释；诊断比较使用1e-8容差，近似平局不能当作实质优势。',
                        '设计/评价反转只描述已有样本差异，不能据此推断因果或调整后重用评价集。',
                        '均配送与暴露按成功订单统计；固定高度理想运动，不含真实起降或飞行验证。']}
    # Fail explicitly instead of exporting NaN/Infinity or custom data objects.
    json.dumps(diagnostics, ensure_ascii=False, allow_nan=False)
    return diagnostics


def _formatted(metric, value):
    if value is None:
        return '待验证'
    if metric in ('failure_rate', 'on_time_rate'):
        return f'{value*100:+.2f}个百分点'
    return f'{value:+.4f}'


def decision_diagnostics_text(diagnostics):
    target = diagnostics['minimum_on_time_rate']
    lines = [f'可解释决策诊断｜准时率研究目标{target:.1%}', diagnostics['threshold_basis'],
             diagnostics['data_role'], '']
    for scenario in diagnostics['scenarios']:
        lines += [f"【{scenario['scenario_name']}】{scenario['message']}"]
        for plan in scenario['plans']:
            m = plan['metrics']
            punctual = '待验证' if m['on_time_rate'] is None else f"{m['on_time_rate']:.2%}"
            service = {'meets': '达到平均准时率目标', 'below': '未达平均准时率目标', 'pending': '门槛待验证'}[plan['service_status']]
            relation = {'dominated': '被'+ '/'.join(PLAN_NAMES[k] for k in plan['dominated_by'])+'支配',
                        'non_dominated': '四指标非劣候选（可能存在取舍）', 'pending': '四指标比较待验证'}[plan['pareto_status']]
            lines.append(f"{plan['plan_name']}：准时率{punctual}，{service}；{relation}。")
        combined = next(p for p in scenario['plans'] if p['plan'] == 'combined')
        for baseline, differences in combined['baseline_differences'].items():
            lines.append('设计优选−'+PLAN_NAMES[baseline]+'：'+'；'.join(METRIC_NAMES[m]+_formatted(m, v) for m, v in differences.items()))
        lines.append('')
    for comparison in diagnostics['design_comparisons']:
        layer = comparison['first_difference_layer']
        if layer:
            detail = f"原精确浮点排序首分歧为第{layer}层（{comparison['layer_name']}）"
            if comparison['near_tie_at_first_difference']:
                detail += '，差值处于诊断容差内，属于近似平局，不解释为实质优势'
        else:
            detail = '设计目标完全相同' if comparison['design_direction'] == 'equal' else '设计目标待验证'
        substantive = comparison['first_substantive_difference_layer']
        if substantive:
            detail += f"；跳过容差内差异后的首实质分歧为第{substantive}层（{comparison['substantive_layer_name']}）"
        elif comparison['substantive_direction'] == 'approximately_equal':
            detail += '；四层目标在诊断容差内均近似相同'
        lines.append('设计阶段原运行优选与'+PLAN_NAMES[comparison['baseline']]+'：'+detail+'。')
        for reversal in comparison['evaluation_reversals']:
            lines.append(f"设计/评价反转：{reversal['scenario']}的{METRIC_NAMES[reversal['metric']]}设计差{_formatted(reversal['metric'], reversal['design_difference'])}、评价差{_formatted(reversal['metric'], reversal['evaluation_difference'])}；仅描述样本，不推断原因。")
    lines += ['', '限制：', *diagnostics['limitations']]
    return '\n'.join(lines)


def export_decision_diagnostics(study, output, minimum_on_time_rate=0.90):
    """Write additional diagnostics only; return output Path, preserving study."""
    diagnostics = diagnose_site_study(study, minimum_on_time_rate)
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    (output/'decision_diagnostics.json').write_text(json.dumps(diagnostics, ensure_ascii=False, indent=2, allow_nan=False)+'\n', encoding='utf-8')
    rows = []
    for scenario in diagnostics['scenarios']:
        for plan in scenario['plans']:
            rows.append({'diagnostics_schema_version': diagnostics['schema_version'],
                         'study_version': diagnostics['study_version'],
                         'scene_name': study.get('scene', {}).get('name', ''),
                         'evaluation_seeds': ','.join(str(v) for v in diagnostics['evaluation_seeds']),
                         'design_seeds': ','.join(str(v) for v in diagnostics['design_seeds']),
                         'minimum_on_time_rate': diagnostics['minimum_on_time_rate'],
                         'threshold_basis': diagnostics['threshold_basis'],
                         'data_role': diagnostics['data_role'], 'metric_basis': diagnostics['metric_basis'],
                         'pareto_four_metrics': 'failure_rate↓|on_time_rate↑|mean_delivery↓|mean_exposure↓',
                         'pareto_tolerance': diagnostics['pareto_tolerance'],
                         'difference_definition': diagnostics['difference_definition'],
                         'scenario': scenario['scenario'], 'plan': plan['plan'], 'plan_name': plan['plan_name'],
                         **plan['metrics'], 'runs': plan['runs'], 'service_status': plan['service_status'],
                         'evaluation_runs_complete': plan['evaluation_runs_complete'],
                         'pareto_status': plan['pareto_status'], 'dominated_by': '|'.join(plan['dominated_by']),
                         'scenario_recommendation_status': scenario['recommendation_status'],
                         **{baseline+'_'+m+'_difference': value
                            for baseline, values in plan['baseline_differences'].items() for m, value in values.items()}})
    with (output/'decision_comparisons.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    (output/'decision_diagnostics.md').write_text('# 起飞点方案决策诊断\n\n'+decision_diagnostics_text(diagnostics)+'\n', encoding='utf-8')
    return output
