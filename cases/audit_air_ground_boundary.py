import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT/'cases')]
from airspace import Segment, segment_violation
from verify_continuous_model import check

HERE = ROOT/'.verification/competition_20261018'
HERE.mkdir(parents=True, exist_ok=True)
study = json.loads((ROOT/'results/sites_v1/study.json').read_text(encoding='utf-8'))
a = Segment(0., 10., 0., 0., 0., 0.)
b = Segment(10., 20., 0., 0., 1., 0.)
assert segment_violation(a, b, 20.) is None
c = Segment(9.99, 20., 0., 0., 1., 0.)
event = segment_violation(a, c, 20.)
assert event is not None and event['end'] > event['start']
independent = check([(0.,10.,(0.,0.),(0.,0.),'U1','A'),
                     (10.,20.,(0.,0.),(10.,0.),'U2','B')], 20.)
assert independent['overlapping_segment_pairs_checked'] == 0
try:
    check([(0.,10.,(0.,0.),(0.,0.),'U1','A'),
           (9.99,20.,(0.,0.),(10.01,0.),'U2','B')], 20.)
except AssertionError:
    positive_overlap_detected = True
else:
    raise AssertionError('Independent audit failed to detect positive overlap')
contacts = []
for result in study['results']:
    for key, plan in result['plans'].items():
        for landing in plan['jobs']:
            for departure in plan['jobs']:
                if (landing['drone_id'] != departure['drone_id'] and
                        landing['pad_id'] == departure['pad_id'] and
                        abs(landing['land_start']-departure['depart']) <= 1e-9):
                    contacts.append({'scenario': result['config']['scenario'],
                                     'evaluation_seed': result['evaluation_seed'], 'plan': key,
                                     'pad_id': landing['pad_id'], 'shared_instant': landing['land_start'],
                                     'arriving_order': landing['order_id'], 'arriving_drone': landing['drone_id'],
                                     'arriving_airborne_end': landing['land_start'],
                                     'landing_ground_service_end': landing['end'],
                                     'departing_order': departure['order_id'], 'departing_drone': departure['drone_id'],
                                     'departure_ground_preparation_start': departure['prep_start'],
                                     'departure_airborne_start': departure['depart']})
assert contacts
output = {'zero_duration_production_event': None, 'positive_duration_production_event': event,
          'independent_zero_duration_check': independent,
          'independent_positive_duration_violation_detected': positive_overlap_detected,
          'actual_zero_duration_air_ground_handoffs': contacts,
          'definition_unchanged': True,
          'source_evidence': 'airspace.py segment_violation docstring and hi-lo<=1e-9; tests/test_airspace.py test_parallel_tangent_and_nonoverlapping_times; test_landing_hold_and_ground_exclusion',
          'limit': 'Model excludes takeoff preparation and landing service from airborne occupancy. Actual same-station ground/air interactions and climb/descent have not been modeled.'}
(HERE/'boundary_audit_round1.json').write_text(json.dumps(output, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
print(f'Existing event convention confirmed; {len(contacts)} zero-duration air-ground handoffs found. Positive overlaps detected by both checks. No detector definition changed.')
