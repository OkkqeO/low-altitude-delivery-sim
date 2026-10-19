"""Decision diagnostics must expose service failure, trade-offs and unknowns."""
from copy import deepcopy
import csv
import json
from pathlib import Path
import tempfile
import unittest

from decision_support import (diagnose_site_study, decision_diagnostics_text,
                              export_decision_diagnostics)


def fixture():
    rows = []
    for scenario in ('normal', 'peak'):
        for seed in (101, 102):
            for plan, punctual, seconds, exposure in (('fixed', .8, 100., 1.),
                                                       ('distance', .85, 90., .8),
                                                       ('combined', .9, 80., .7)):
                rows.append({'scenario': scenario, 'evaluation_seed': seed, 'plan': plan,
                             'failed_orders': 0, 'total_orders': 20, 'on_time_rate': punctual,
                             'mean_delivery': seconds, 'mean_exposure': exposure})
    choices = {p: {'objective': [0., late, 2., 100.],
                   'design_stats': {s: {'completion_rate': 1., 'on_time_rate': 1-late,
                                        'mean_delivery': 100., 'mean_exposure': 1.}
                                    for s in ('normal', 'peak')}}
               for p, late in (('fixed', .2), ('distance', .15), ('combined', .1))}
    return {'version': '0.7.0-sites', 'evaluation_seeds': [101, 102],
            'design_seeds': [900], 'raw_metrics': rows, 'choices': choices}


class DecisionSupportTests(unittest.TestCase):
    def test_all_below_service_target_gives_no_recommendation(self):
        d = diagnose_site_study(fixture(), .95)
        self.assertTrue(all(s['recommendation_status'] == 'not_recommended' for s in d['scenarios']))
        self.assertIn('不推荐采用任何方案', decision_diagnostics_text(d))

    def test_meeting_mean_target_does_not_automatically_choose_a_winner(self):
        d = diagnose_site_study(fixture())
        for scenario in d['scenarios']:
            self.assertEqual(scenario['recommendation_status'], 'comparison_required')
            self.assertEqual(scenario['plans'][2]['service_status'], 'meets')
        self.assertNotIn('selected_plan', d)

    def test_four_metric_pareto_dominance_is_reported(self):
        plans = diagnose_site_study(fixture())['scenarios'][0]['plans']
        self.assertEqual(plans[0]['pareto_status'], 'dominated')
        self.assertEqual(plans[0]['dominated_by'], ['distance', 'combined'])
        self.assertEqual(plans[2]['pareto_status'], 'non_dominated')
        self.assertEqual(plans[2]['baseline_differences']['fixed']['on_time_rate'], .9-.8)

    def test_tradeoff_is_non_dominated_and_not_called_universally_best(self):
        study = fixture()
        for row in study['raw_metrics']:
            if row['plan'] == 'combined':
                row['mean_delivery'] = 110.
        plans = diagnose_site_study(study)['scenarios'][0]['plans']
        self.assertEqual(plans[1]['pareto_status'], 'non_dominated')
        self.assertEqual(plans[2]['pareto_status'], 'non_dominated')

    def test_equal_vectors_do_not_strictly_dominate_each_other(self):
        study = fixture()
        for row in study['raw_metrics']:
            row.update(on_time_rate=.8, mean_delivery=100., mean_exposure=1.)
        self.assertTrue(all(p['pareto_status'] == 'non_dominated'
                            for s in diagnose_site_study(study)['scenarios'] for p in s['plans']))

    def test_missing_nan_infinite_or_boolean_metric_makes_pareto_pending(self):
        for invalid in (None, float('nan'), float('inf'), True):
            with self.subTest(invalid=invalid):
                study = fixture()
                study['raw_metrics'][0]['mean_exposure'] = invalid
                d = diagnose_site_study(study)
                self.assertIsNone(d['scenarios'][0]['plans'][0]['metrics']['mean_exposure'])
                self.assertTrue(all(p['pareto_status'] == 'pending' for p in d['scenarios'][0]['plans']))
                json.dumps(d, allow_nan=False)

    def test_missing_punctuality_makes_service_pending(self):
        study = fixture()
        study['raw_metrics'][0]['on_time_rate'] = None
        scenario = diagnose_site_study(study)['scenarios'][0]
        self.assertEqual(scenario['plans'][0]['service_status'], 'pending')
        self.assertEqual(scenario['recommendation_status'], 'pending')

    def test_failure_rate_is_mean_of_run_ratios_not_ratio_of_totals(self):
        study = fixture()
        rows = [r for r in study['raw_metrics'] if r['scenario'] == 'normal' and r['plan'] == 'fixed']
        rows[0].update(failed_orders=1, total_orders=2, on_time_rate=.5)
        rows[1].update(failed_orders=1, total_orders=10, on_time_rate=.8)
        value = diagnose_site_study(study)['scenarios'][0]['plans'][0]['metrics']['failure_rate']
        self.assertAlmostEqual(value, .3)
        self.assertNotAlmostEqual(value, 2/12)

    def test_missing_or_duplicate_seed_does_not_appear_complete(self):
        for duplicate in (False, True):
            study = fixture()
            if duplicate:
                study['raw_metrics'][3]['evaluation_seed'] = 101
            else:
                study['raw_metrics'].pop(3)
            p = diagnose_site_study(study)['scenarios'][0]['plans'][0]
            self.assertFalse(p['evaluation_runs_complete'])
            self.assertEqual(p['metric_status'], 'pending')
            self.assertEqual(p['service_status'], 'pending')

    def test_exact_float_decision_is_distinct_from_diagnostic_tolerance(self):
        study = fixture()
        study['choices']['combined']['objective'] = [0., .22499999999999998, 99., 999.]
        study['choices']['fixed']['objective'] = [0., .225, 1., 1.]
        c = diagnose_site_study(study)['design_comparisons'][0]
        self.assertEqual(c['first_difference_layer'], 2)
        self.assertEqual(c['design_direction'], 'combined_better')
        self.assertTrue(c['near_tie_at_first_difference'])
        self.assertEqual(c['first_substantive_difference_layer'], 3)
        self.assertEqual(c['substantive_direction'], 'combined_worse')
        self.assertIn('近似平局', decision_diagnostics_text(diagnose_site_study(study)))

    def test_design_to_evaluation_reversal_is_observation_not_causal_claim(self):
        study = fixture()
        for row in study['raw_metrics']:
            if row['plan'] == 'combined':
                row['on_time_rate'] = .7
        d = diagnose_site_study(study)
        reversals = d['design_comparisons'][0]['evaluation_reversals']
        self.assertTrue(any(r['metric'] == 'on_time_rate' for r in reversals))
        self.assertIn('不推断原因', decision_diagnostics_text(d))

    def test_diagnosis_and_exports_preserve_study(self):
        study, before = fixture(), fixture()
        diagnose_site_study(study)
        with tempfile.TemporaryDirectory() as tmp:
            output = export_decision_diagnostics(study, tmp, .95)
            self.assertIsInstance(output, Path)
            restored = json.loads((output/'decision_diagnostics.json').read_text(encoding='utf-8'))
            self.assertEqual(restored['minimum_on_time_rate'], .95)
            with (output/'decision_comparisons.csv').open(encoding='utf-8-sig', newline='') as handle:
                rows = list(csv.DictReader(handle))
                self.assertEqual(len(rows), 6)
                self.assertTrue(all(row['minimum_on_time_rate'] == '0.95' for row in rows))
                self.assertTrue(all(row['evaluation_seeds'] == '101,102' for row in rows))
                self.assertTrue(all('失败率' in row['difference_definition'] for row in rows))
        self.assertEqual(study, before)

    def test_invalid_targets_are_rejected(self):
        for target in (True, float('nan'), float('inf'), -.1, 1.1, '90%'):
            with self.subTest(target=target), self.assertRaises(ValueError):
                diagnose_site_study(fixture(), target)

    def test_empty_study_is_pending_without_invented_zero_metrics(self):
        d = diagnose_site_study({})
        self.assertTrue(all(s['recommendation_status'] == 'pending' for s in d['scenarios']))
        self.assertTrue(all(v is None for s in d['scenarios'] for p in s['plans'] for v in p['metrics'].values()))


if __name__ == '__main__':
    unittest.main()
