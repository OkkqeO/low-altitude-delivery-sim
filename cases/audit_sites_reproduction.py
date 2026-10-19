"""Independent numerical/export audit of the existing and reproduced V0.7 study.

No engine, reporting or airspace functions are imported. Continuous separation is
checked from exported geometry and timestamps by closest approach on each pair
of overlapping linear intervals. This validates only the stated ideal model.
"""
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import statistics
import sys

ROOT = Path(__file__).resolve().parents[1]
HERE = ROOT/'.verification/competition_20261018'
SOURCE = ROOT / 'results/sites_v1'
REPRODUCTION = HERE / 'sites_reproduction'
VOLATILE = {'calculated_at', 'design_seconds'}


def stable(value):
    if isinstance(value, dict):
        return {k: stable(v) for k, v in value.items() if k not in VOLATILE}
    if isinstance(value, list):
        return [stable(v) for v in value]
    return value


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def close(a, b, context):
    assert math.isclose(a, b, rel_tol=1e-10, abs_tol=1e-7), (context, a, b)


def csv_matches(path, expected):
    with path.open(encoding='utf-8-sig', newline='') as handle:
        actual = list(csv.DictReader(handle))
    assert len(actual) == len(expected), (path, len(actual), len(expected))
    for row, wanted in zip(actual, expected):
        assert set(row) == set(wanted), path
        for k, v in wanted.items():
            assert row[k] == ('' if v is None else str(v)), (path, k, row[k], v)


def trajectory(job, points, speed):
    segments = []
    for route, begin in ((points, job['depart']), (list(reversed(points)), job['return_start'])):
        now = begin
        for a, b in zip(route, route[1:]):
            end = now + math.dist(a, b) / speed
            if end > now:
                segments.append((now, end, tuple(a), tuple(b), job['drone_id'], job['order_id']))
            now = end
        expected = job['arrived_dest'] if begin == job['depart'] else job['return_arrival']
        close(now, expected, 'reconstructed arrival')
    for begin, end, point in ((job['arrived_dest'], job['delivered_at'], points[-1]),
                              (job['return_arrival'], job['land_start'], points[0])):
        if end > begin:
            segments.append((begin, end, tuple(point), tuple(point), job['drone_id'], job['order_id']))
    return segments


def separation_check(segments, threshold):
    active, pairs, minimum = [], 0, math.inf
    for s in sorted(segments):
        active = [t for t in active if t[1] >= s[0]]
        for t in active:
            if s[4] == t[4]:
                continue
            begin, end = max(s[0], t[0]), min(s[1], t[1])
            # The model defines an episode as a positive-duration airborne
            # overlap; landing service and takeoff preparation are on ground.
            if end-begin <= 1e-9:
                continue
            positions, velocities = [], []
            for piece in (s, t):
                v = tuple((piece[3][i]-piece[2][i])/(piece[1]-piece[0]) for i in (0, 1))
                positions.append(tuple(piece[2][i]+v[i]*(begin-piece[0]) for i in (0, 1)))
                velocities.append(v)
            r = tuple(positions[0][i]-positions[1][i] for i in (0, 1))
            v = tuple(velocities[0][i]-velocities[1][i] for i in (0, 1))
            vv = sum(x*x for x in v)
            dt = min(end-begin, max(0., -sum(r[i]*v[i] for i in (0, 1))/vv)) if vv else 0.
            distance = math.hypot(*(r[i]+dt*v[i] for i in (0, 1)))
            minimum = min(minimum, distance)
            assert distance >= threshold-1e-6, ('separation violation', s, t, distance)
            pairs += 1
        active.append(s)
    return pairs, minimum


def main():
    global SOURCE, REPRODUCTION, HERE
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reference', type=Path, default=SOURCE)
    parser.add_argument('--reproduction', type=Path, default=REPRODUCTION)
    parser.add_argument('--output', type=Path, default=HERE)
    args = parser.parse_args()
    SOURCE, REPRODUCTION, HERE = args.reference, args.reproduction, args.output
    HERE.mkdir(parents=True, exist_ok=True)
    reference, reproduced = read_json(SOURCE/'study.json'), read_json(REPRODUCTION/'study.json')
    assert stable(reference) == stable(reproduced), 'Study changed beyond timestamps/timing'
    a = {str(p.relative_to(SOURCE)) for p in SOURCE.rglob('*') if p.is_file()}
    b = {str(p.relative_to(REPRODUCTION)) for p in REPRODUCTION.rglob('*') if p.is_file()}
    assert a == b, (a-b, b-a)
    equal, normalized, timing_only = [], [], []
    for relative in sorted(a):
        first, second = SOURCE/relative, REPRODUCTION/relative
        if first.read_bytes() == second.read_bytes():
            equal.append(relative)
        elif first.suffix == '.json':
            assert stable(read_json(first)) == stable(read_json(second)), relative
            normalized.append(relative)
        elif first.name == '实验分析.md':
            lines_a, lines_b = first.read_text(encoding='utf-8').splitlines(), second.read_text(encoding='utf-8').splitlines()
            assert [x for x in lines_a if '设计耗时' not in x] == [x for x in lines_b if '设计耗时' not in x]
            timing_only.append(relative)
        else:
            raise AssertionError(('unexpected file difference', relative))

    manifest = read_json(SOURCE/'manifest.json')
    assert hashlib.sha256((SOURCE/'scene.json').read_bytes()).hexdigest() == manifest['scene_sha256']
    for name, digest in manifest['export_source_sha256'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest, name
    assert set(reference['design_seeds']).isdisjoint(reference['evaluation_seeds'])
    csv_matches(SOURCE/'raw_metrics.csv', reference['raw_metrics'])
    csv_matches(SOURCE/'summary.csv', reference['summary'])
    jobs, intervals, pairs, minimum = 0, 0, 0, math.inf
    metrics_checked = set()
    for result in reference['results']:
        folder = SOURCE/'runs'/f"{result['config']['scenario']}_{result['evaluation_seed']}"
        assert read_json(folder/'result.json') == result
        expected_jobs = []
        for key, plan in result['plans'].items():
            assert plan['orders'] == result['plans']['fixed']['orders']
            assert plan['site_configuration']['fleet_allocation'] == reference['choices'][key]['fleet_allocation']
            assert plan['pad_ids'] == reference['choices'][key]['pad_ids']
            assert len(plan['drones']) == reference['base_config']['drone_count']
            assert sum(plan['site_configuration']['fleet_allocation'].values()) == len(plan['drones'])
            segments = []
            for job in plan['jobs']:
                segments.extend(trajectory(job, result['routes'][job['route_key']]['points'], result['config']['speed']))
            pair_count, local_min = separation_check(segments, result['config']['separation'])
            minimum, pairs = min(minimum, local_min), pairs+pair_count
            intervals += len(segments)
            delivered = plan['jobs']
            n, total = len(delivered), len(plan['orders'])
            assert n + len(plan['failed']) == total
            assert set(j['order_id'] for j in delivered).isdisjoint(j['id'] for j in plan['failed'])
            times = sorted(j['delivered_at']-j['created_at'] for j in delivered)
            recomputed = {
                'delivered_orders': n, 'failed_orders': len(plan['failed']),
                'mean_delivery': statistics.mean(times),
                'p95_delivery': times[math.ceil(.95*n)-1],
                'on_time_rate': sum(j['delivered_at'] <= j['due_at']+1e-8 for j in delivered)/total,
                'completion_rate': n/total,
                'mean_exposure': statistics.mean(j['exposure'] for j in delivered),
                'total_distance': sum(j['distance'] for j in delivered),
                'mean_airspace_delay': statistics.mean(j['airspace_delay'] for j in delivered),
                'air_conflict_count': 0,
            }
            for metric, value in recomputed.items():
                close(value, plan['stats'][metric], metric)
                metrics_checked.add(metric)
            for calendar in plan['calendars'].values():
                assert all(x['end'] <= y['start']+1e-8 for x, y in zip(calendar, calendar[1:]))
            for drone in plan['drones']:
                tasks = sorted((j for j in delivered if j['drone_id'] == drone['id']), key=lambda j: j['prep_start'])
                assert all(x['end'] <= y['prep_start']+1e-8 for x, y in zip(tasks, tasks[1:]))
            expected_jobs.extend({'plan': key, **j} for j in delivered)
            jobs += n
        csv_matches(folder/'jobs.csv', expected_jobs)

    for summary in reference['summary']:
        rows = [r for r in reference['raw_metrics'] if r['scenario'] == summary['scenario'] and r['plan'] == summary['plan']]
        assert summary['runs'] == len(rows)
        for key in summary:
            if key.endswith('_valid_runs'):
                metric = key[:-11]
                values = [r[metric] for r in rows if r[metric] is not None]
                assert summary[key] == len(values)
                close(summary[metric], statistics.mean(values), key)
                close(summary[metric+'_std'], statistics.stdev(values), key+'_std')
    output = {
        'status': 'passed', 'python': sys.version, 'file_count': len(a),
        'byte_identical_files': equal, 'json_time_fields_only': normalized,
        'markdown_elapsed_time_only': timing_only,
        'layouts': reference['candidate_count'], 'plan_runs': len(reference['raw_metrics']),
        'completed_jobs': jobs, 'trajectory_segments': intervals,
        'overlapping_segment_pairs_checked': pairs,
        'minimum_independently_reconstructed_distance_m': minimum,
        'recomputed_job_metrics': sorted(metrics_checked),
        'source_and_scene_hashes_match': True,
        'summary_mean_sample_std_valid_counts_match': True,
        'limit': 'Fixed-height ideal piecewise linear model only; no real flight validation.'
    }
    (HERE/'sites_audit_round1.json').write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({k: v for k, v in output.items() if not isinstance(v, list)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
