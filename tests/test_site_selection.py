"""Location-only decisions and actual user-selected fleet size."""
from copy import deepcopy
from dataclasses import replace
import json
from pathlib import Path
import tempfile
import unittest

from airspace import detect_conflicts
from engine import Config
from facility import PlanningCancelled
from site_selection import build_site_design, evaluate_site_design, run_site_study, export_site_study
from test_facility import small_scene


class SiteSelectionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = Config(order_count=6, seed=101)
        cls.design = build_site_design(cls.config, small_scene(), design_seed=900, design_seed_count=2)

    def test_user_fleet_counts_are_used_in_all_candidates_and_actual_drones(self):
        for count in (1, 3, 5, 8, 20):
            with self.subTest(drones=count):
                design = build_site_design(replace(self.config, drone_count=count), small_scene(), design_seed=900, design_seed_count=1)
                for candidate in design['candidates']:
                    allocation = list(candidate['fleet_allocation'].values())
                    self.assertEqual(sum(allocation), count)
                    self.assertEqual(len(allocation), min(2, count))
                    self.assertLessEqual(max(allocation)-min(allocation), 1)
                result = evaluate_site_design(design, 101, 'peak')
                for plan in result['plans'].values():
                    self.assertEqual(len(plan['drones']), count)
                    self.assertEqual(len(plan['pad_ids']), min(2, count))
                    for p, n in plan['site_configuration']['fleet_allocation'].items():
                        self.assertEqual(sum(d['pad_id']==p for d in plan['drones']), n)

    def test_cost_grade_and_capacity_metadata_have_no_effect_on_selection(self):
        scene = small_scene()
        original = deepcopy(scene)
        scene['facility_planning'] = {'budget': 0, 'levels': []}
        for pad in scene['pads']:
            pad.update(allowed_levels=[], site_cost=1e10)
        modified = build_site_design(self.config, scene, design_seed=900, design_seed_count=2)
        self.assertEqual(modified['choices'], self.design['choices'])
        self.assertNotIn('facility_planning', modified['scene'])
        self.assertTrue(all('site_cost' not in p and 'allowed_levels' not in p for p in modified['scene']['pads']))
        self.assertIn('facility_planning', scene)
        self.assertNotIn('facility_planning', original)

    def test_optimum_and_configurations_are_frozen_for_independent_scenarios(self):
        self.assertEqual(self.design['choices']['combined']['objective'], min(v['objective'] for v in self.design['candidates']))
        before = deepcopy(self.design['choices'])
        for seed in (101, 102):
            for scenario in ('normal', 'peak'):
                result = evaluate_site_design(self.design, seed, scenario)
                for key, plan in result['plans'].items():
                    self.assertEqual(plan['site_configuration']['fleet_allocation'], before[key]['fleet_allocation'])
                    self.assertEqual(plan['pad_ids'], before[key]['pad_ids'])
                self.assertEqual(result['plans']['fixed']['orders'], result['plans']['combined']['orders'])
        self.assertEqual(self.design['choices'], before)

    def test_all_design_seeds_are_excluded_from_evaluation_and_cancel_is_honoured(self):
        for seed in self.design['design_seeds']:
            with self.assertRaisesRegex(ValueError, '设计种子'):
                evaluate_site_design(self.design, seed)
        for seeds in ([], [101, 101], [True], [-1], [900]):
            with self.subTest(seeds=seeds), self.assertRaises(ValueError):
                run_site_study(self.config, small_scene(), seeds, design_seed=900)
        with self.assertRaises(PlanningCancelled):
            build_site_design(self.config, small_scene(), cancel=lambda: True)
        for count in (0, 21):
            with self.assertRaises(ValueError):
                build_site_design(replace(self.config, drone_count=count), small_scene())

    def test_schedule_passes_independent_separation_and_resource_checks(self):
        result = evaluate_site_design(self.design, 101, 'peak')
        for plan in result['plans'].values():
            self.assertEqual(detect_conflicts(plan['jobs'], result['routes'], self.config.speed, self.config.separation), [])
            for calendar in plan['calendars'].values():
                self.assertTrue(all(a['end'] <= b['start']+1e-8 for a, b in zip(calendar, calendar[1:])))
            for drone in plan['drones']:
                jobs = sorted((j for j in plan['jobs'] if j['drone_id']==drone['id']), key=lambda j: j['prep_start'])
                self.assertTrue(all(a['end'] <= b['prep_start']+1e-8 for a, b in zip(jobs, jobs[1:])))

    def test_exports_contain_user_fleet_count_and_locations_without_costs(self):
        study = run_site_study(replace(self.config, drone_count=8), small_scene(), [101, 102], design_seed=900, design_seed_count=1)
        with tempfile.TemporaryDirectory() as folder:
            output = export_site_study(study, folder)
            restored = json.loads((output/'study.json').read_text(encoding='utf-8'))
            self.assertEqual(restored['base_config']['drone_count'], 8)
            self.assertEqual(len(restored['raw_metrics']), 12)
            self.assertEqual(len(restored['summary']), 6)
            self.assertNotIn('budget', restored)
            self.assertNotIn('cost', (output/'summary.csv').read_text(encoding='utf-8-sig').splitlines()[0])
            self.assertTrue((output/'runs/peak_101/site_configurations.csv').exists())
            self.assertIn('运行优选', (output/'runs/peak_101/map.svg').read_text(encoding='utf-8'))
            self.assertEqual(json.loads((output/'scene.json').read_text(encoding='utf-8')), restored['scene'])


if __name__ == '__main__':
    unittest.main()
