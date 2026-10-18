"""Select departure locations with a user-selected fleet and uniform service."""
from copy import deepcopy
from dataclasses import asdict, replace
from datetime import datetime, timezone
import hashlib
from itertools import combinations, product
from pathlib import Path
import statistics
import time

from engine import (Config, DEFAULT_DESIGN_SEED, ROOT, create_scene, generate_orders,
                    is_blocked, route_catalog, simulate, xy)
from facility import PlanningCancelled, check_cancel, training_seeds, _objective
from map_import import load_scene_file
from reporting import export_result, write_csv, write_json

SITE_NAMES = {"fixed": "固定位置", "distance": "距离优先", "combined": "运行优选"}
SCENARIOS = ("normal", "peak")
MAX_LAYOUTS = 5000


def location_scene(config, scene_input=None):
    """Old facility metadata does not constrain or score location selection."""
    scene = deepcopy(scene_input) if isinstance(scene_input, dict) else load_scene_file(scene_input or ROOT/'data/demo_scene.json')
    scene.pop('facility_planning', None)
    for pad in scene.get('pads', []):
        if isinstance(pad, dict):
            pad.pop('allowed_levels', None)
            pad.pop('site_cost', None)
    return create_scene(config, scene)


def layout_label(candidate):
    return ' + '.join(f"{p} {candidate['fleet_allocation'][p]}架" for p in candidate['pad_ids'])


def build_site_design(config=None, scene_path=None, design_seed=DEFAULT_DESIGN_SEED,
                      progress=None, cancel=None, design_seed_count=3):
    started = time.perf_counter()
    c = replace(config or Config(), scenario='normal').validated()
    if not c.deconflict:
        raise ValueError('起飞点优选须开启错峰，各位置使用同一间距约束')
    design_seeds = training_seeds(design_seed, design_seed_count)
    check_cancel(cancel)
    scene = location_scene(c, scene_path)
    available = [p['id'] for p in scene['pads'] if not is_blocked(scene, xy(p))]
    count = min(2, c.drone_count)
    if len(available) < count:
        raise ValueError(f'当前高度下不足{count}个可用起飞位置')
    layout_count = len(available) if count == 1 else len(available)*(len(available)-1)//2
    if layout_count > MAX_LAYOUTS:
        raise ValueError(f'候选布局超过{MAX_LAYOUTS}种，请减少候选起飞点')
    if progress:
        progress(0, 0, '正在建立候选起飞位置的航路……')
    routes = route_catalog(scene, c)
    orders = {(seed, s): generate_orders(scene, replace(c, scenario=s), seed)
              for seed, s in product(design_seeds, SCENARIOS)}
    candidates = []
    for pair in combinations(available, count):
        check_cancel(cancel)
        allocation = {p: c.drone_count//count + int(i < c.drone_count % count) for i, p in enumerate(pair)}
        samples = {s: [] for s in SCENARIOS}
        for seed, scenario in product(design_seeds, SCENARIOS):
            check_cancel(cancel)
            samples[scenario].append(simulate(scene, replace(c, scenario=scenario), list(pair),
                                             orders[seed, scenario], routes, allocation)['stats'])
        stats = {s: {k: statistics.mean(v[k] for v in values if v[k] is not None)
                     if any(v[k] is not None for v in values) else None for k in values[0]}
                 for s, values in samples.items()}
        candidate = {'pad_ids': list(pair), 'fleet_allocation': allocation, 'design_stats': stats,
                     'objective': _objective([v for values in samples.values() for v in values])}
        candidates.append(candidate)
        if progress:
            progress(len(candidates), layout_count, f'已比较{len(candidates)}/{layout_count}种起飞布局（正常＋高峰）')
    fixed_ids = [p for p in ('S1', 'S5') if p in available][:count]
    fixed_ids += [p for p in available if p not in fixed_ids][:count-len(fixed_ids)]
    fixed = next(v for v in candidates if set(v['pad_ids']) == set(fixed_ids))
    distance = min(candidates, key=lambda v: (v['design_stats']['normal']['failed_orders'],
                                             v['design_stats']['normal']['total_distance'], tuple(v['pad_ids'])))
    best = min(candidates, key=lambda v: (v['objective'], tuple(v['pad_ids'])))
    return {'config': c, 'scene': scene, 'routes': routes, 'design_seed': design_seed,
            'design_seeds': design_seeds, 'station_count': count, 'candidates': candidates,
            'choices': {'fixed': fixed, 'distance': distance, 'combined': best},
            'design_seconds': time.perf_counter()-started}


def evaluate_site_design(design, seed=None, scenario='normal', cancel=None):
    if scenario not in SCENARIOS:
        raise ValueError('起飞点评价场景须为normal或peak')
    c = replace(design['config'], scenario=scenario, seed=design['config'].seed if seed is None else seed).validated()
    if c.seed in design['design_seeds']:
        raise ValueError('评价种子不能与任何设计种子相同')
    orders = generate_orders(design['scene'], c)
    plans = {}
    for key, candidate in design['choices'].items():
        check_cancel(cancel)
        run = simulate(design['scene'], c, candidate['pad_ids'], orders, design['routes'], candidate['fleet_allocation'])
        plans[key] = {**run, 'key': key, 'name': SITE_NAMES[key],
                      'site_configuration': {k: deepcopy(candidate[k]) for k in ('pad_ids', 'fleet_allocation')},
                      'configuration_label': layout_label(candidate)}
    return {'version': '0.7.0-sites', 'calculated_at': datetime.now(timezone.utc).isoformat(),
            'config': asdict(c), 'scene': design['scene'], 'routes': design['routes'],
            'design_seed': design['design_seed'], 'evaluation_seed': c.seed,
            'candidate_count': len(design['candidates']), 'plans': plans,
            'site_design': {'station_count': design['station_count'], 'design_seeds': design['design_seeds'],
                            'configuration_frozen': True, 'allocation_policy': '按候选点顺序均衡分配，奇数时前站多一架'},
            'assumptions': ['无人机总数可设置1—20架；同一次选址比较的各布局使用相同总数',
                            '1架选择1个起飞点，2—20架选择2个起飞点；各点起降服务参数相同',
                            '站点内均衡分配，无人机固定归属场站；正常与高峰冻结同一位置与配比',
                            '目标依次比较失败率、非准时率、每单超时秒数，再比较配送秒数+30×路径暴露',
                            '固定高度、理想匀速飞行；路径暴露为代理指标；所有订单可从任一已选站发出']}


METRICS = ('mean_delivery', 'p95_delivery', 'on_time_rate', 'completion_rate', 'failed_orders',
           'mean_exposure', 'mean_drone_wait', 'mean_takeoff_wait', 'mean_landing_wait',
           'mean_airspace_delay', 'air_conflict_count', 'total_distance')


def run_site_study(config=None, scene_path=None, seeds=None, design_seed=DEFAULT_DESIGN_SEED,
                   progress=None, cancel=None, design_seed_count=3):
    c = (config or Config()).validated()
    seeds = list([c.seed] if seeds is None else seeds)
    design_seeds = training_seeds(design_seed, design_seed_count)
    if (not seeds or any(isinstance(v, bool) or not isinstance(v, int) or not 0 <= v < 2**32 or v in design_seeds for v in seeds)
            or len(set(seeds)) != len(seeds)):
        raise ValueError('评价种子须为互不重复的32位非负整数，且与设计种子不同')
    design = build_site_design(c, scene_path, design_seed, progress, cancel, design_seed_count)
    results, rows = [], []
    for i, (seed, scenario) in enumerate(product(seeds, SCENARIOS)):
        check_cancel(cancel)
        if progress:
            progress(i, len(seeds)*2, f'独立评价：种子{seed}，{"正常" if scenario == "normal" else "高峰"}')
        result = evaluate_site_design(design, seed, scenario, cancel)
        results.append(result)
        for key, plan in result['plans'].items():
            rows.append({'scenario': scenario, 'evaluation_seed': seed, 'plan': key,
                         'plan_name': SITE_NAMES[key], 'configuration': plan['configuration_label'], **plan['stats']})
    summary = []
    for scenario, key in product(SCENARIOS, SITE_NAMES):
        group = [r for r in rows if r['scenario'] == scenario and r['plan'] == key]
        row = {k: group[0][k] for k in ('scenario', 'plan', 'plan_name', 'configuration')}
        row['runs'] = len(group)
        for metric in METRICS:
            values = [r[metric] for r in group if r[metric] is not None]
            row[metric] = statistics.mean(values) if values else None
            row[metric+'_std'] = statistics.stdev(values) if len(values) > 1 else (0. if values else None)
            row[metric+'_valid_runs'] = len(values)
        summary.append(row)
    return {'version': '0.7.0-sites', 'base_config': asdict(c), 'scene': design['scene'],
            'design_seed': design_seed, 'design_seeds': design_seeds, 'evaluation_seeds': seeds,
            'station_count': design['station_count'], 'candidate_count': len(design['candidates']),
            'design_seconds': design['design_seconds'], 'choices': deepcopy(design['choices']),
            'candidates': design['candidates'], 'results': results, 'raw_metrics': rows, 'summary': summary}


def site_report(study):
    def fmt(v, scale=1):
        return '—' if v is None else f'{v*scale:.2f}'
    lines = ['# 起飞点优选：正常与高峰独立评价', '',
             f"无人机总数{study['base_config']['drone_count']}架，启用{study['station_count']}个起飞点，比较{study['candidate_count']}种布局。",
             f"设计种子{study['design_seeds']}；评价种子{study['evaluation_seeds']}；设计耗时{study['design_seconds']:.2f}秒。", '',
             '各布局总机队相同，按候选点顺序均衡分配；正常和高峰复用同一位置与配比。', '',
             '|场景|方案|起飞点与无人机|准时率|配送秒数|每次P95的均值/秒|暴露|失败数均值|间距事件均值|',
             '|---|---|---|---:|---:|---:|---:|---:|---:|']
    for r in study['summary']:
        lines.append(f"|{'正常' if r['scenario']=='normal' else '高峰'}|{r['plan_name']}|{r['configuration']}|{fmt(r['on_time_rate'],100)}%|{fmt(r['mean_delivery'])}|{fmt(r['p95_delivery'])}|{fmt(r['mean_exposure'])}|{fmt(r['failed_orders'])}|{fmt(r['air_conflict_count'])}|")
    lines += ['', '固定位置优先S1、S5，不可用时按候选点顺序补足。距离优先先比较正常设计样本失败数，再比较总航程。运行优选在正常、高峰等权设计样本上依次比较失败率、非准时率、每单超时秒数、配送秒数+30×暴露；30为人为权衡系数。', '',
              '均值按运行等权；P95为每次运行成功订单最近秩P95的均值，样本标准差不是置信区间。独立评价冻结位置；改变无人机数量后需重新选址。', '',
              '固定高度与理想运动仿真，各站1个起降服务位。所有订单可从任一已选站发出。等级、成本及预算未参与本流程；无滚动调度、库存或真实飞行验证。']
    return '\n'.join(lines)+'\n'


def export_site_study(study, output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    write_json(output/'study.json', study)
    write_json(output/'scene.json', study['scene'])
    write_csv(output/'raw_metrics.csv', study['raw_metrics'])
    write_csv(output/'summary.csv', study['summary'])
    write_csv(output/'design_candidates.csv', [
        {'configuration': layout_label(v), **{f'objective_{i+1}': x for i, x in enumerate(v['objective'])},
         **{f'{s}_{k}': x for s, stats in v['design_stats'].items() for k, x in stats.items()}}
        for v in study['candidates']])
    write_csv(output/'configurations.csv', [{'plan': k, 'plan_name': SITE_NAMES[k], 'configuration': layout_label(v)}
                                            for k, v in study['choices'].items()])
    for result in study['results']:
        export_result(result, output/'runs'/f"{result['config']['scenario']}_{result['evaluation_seed']}")
    (output/'实验分析.md').write_text(site_report(study), encoding='utf-8')
    manifest = {k: study[k] for k in ('version', 'base_config', 'design_seeds', 'evaluation_seeds', 'candidate_count', 'station_count')}
    manifest['scene_sha256'] = hashlib.sha256((output/'scene.json').read_bytes()).hexdigest()
    manifest['export_source_sha256'] = {name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
                                        for name in ('site_selection.py', 'engine.py', 'airspace.py', 'reporting.py', 'facility.py')}
    write_json(output/'manifest.json', manifest)
    return output
