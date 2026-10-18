"""Constraints, independent evaluation and portable graded-facility results."""
from copy import deepcopy
from dataclasses import replace
import json
import math
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from airspace import detect_conflicts
from engine import Config, create_scene, generate_orders, route_catalog, simulate
from facility import (PlanningCancelled, build_facility_design, configurations, evaluate_facility_design,
                      export_facility_study, run_facility_study, training_seeds)
from facility_schema import DEFAULT_LEVELS, facility_inputs
from facility_template import write_facility_template
from map_document import MapDocument
from map_import import NS, load_scene_file


def small_scene():
    return {"width": 160, "height": 120, "step": 20, "clearance": 0, "vertical_clearance": 5,
            "name": "设施模型测试", "source": "合成测试地图", "buildings": [], "risk_zones": [],
            "pads": [{"id": "S1", "name": "西站", "x": 10, "y": 20},
                     {"id": "S2", "name": "东站", "x": 150, "y": 20},
                     {"id": "S3", "name": "南站", "x": 80, "y": 110}],
            "deliveries": [{"id": "D1", "name": "西区", "x": 40, "y": 60, "demand": 1},
                           {"id": "D2", "name": "东区", "x": 120, "y": 60, "demand": 1}]}


class FacilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = Config(order_count=6, seed=101, drone_count=5)
        cls.design = build_facility_design(cls.config, small_scene(), budget=260, design_seed=900, design_seed_count=2)

    def test_default_inputs_do_not_mutate_old_scene(self):
        scene = small_scene()
        original = deepcopy(scene)
        settings = facility_inputs(scene)
        self.assertEqual(scene, original)
        self.assertEqual(len(settings["levels"]), 2)

    def test_every_candidate_obeys_budget_capacity_and_allowed_levels(self):
        scene = deepcopy(self.design["scene"])
        scene["pads"][0].update(allowed_levels=["standard"], site_cost=20)
        scene["pads"][2]["allowed_levels"] = []
        candidates = configurations(scene, self.config, 280)
        self.assertTrue(candidates)
        levels = {v["id"]: v for v in DEFAULT_LEVELS}
        for candidate in candidates:
            self.assertEqual(candidate["pad_ids"], ["S1", "S2"])
            self.assertEqual(candidate["levels"]["S1"], "standard")
            self.assertLessEqual(candidate["cost"], 280)
            self.assertEqual(sum(candidate["fleet_allocation"].values()), 5)
            for pad, n in candidate["fleet_allocation"].items():
                self.assertGreaterEqual(n, 1)
                self.assertLessEqual(n, levels[candidate["levels"][pad]]["max_drones"])
            self.assertEqual(candidate["cost"], sum(levels[k]["cost"] for k in candidate["levels"].values())+20)

    def test_infeasible_budget_and_one_drone_are_explicit_errors(self):
        with self.assertRaisesRegex(ValueError, "无可行"):
            configurations(self.design["scene"], self.config, 199)
        with self.assertRaisesRegex(ValueError, "至少2架"):
            build_facility_design(replace(self.config, drone_count=1), small_scene())

    def test_eight_drones_require_an_enhanced_station_under_260_budget(self):
        candidates = configurations(self.design["scene"], replace(self.config, drone_count=8), 260)
        self.assertTrue(candidates)
        self.assertTrue(all("enhanced" in p["levels"].values() for p in candidates))
        self.assertTrue(all(p["cost"] == 260 for p in candidates))

    def test_invalid_grade_inputs_are_rejected(self):
        for change in ({"cost": float("nan")}, {"max_drones": True}, {"max_drones": 2.5},
                       {"landing_service": 0}, {"takeoff_service": -1}, {"id": "bad,id"}):
            scene = small_scene()
            levels = deepcopy(DEFAULT_LEVELS)
            levels[0].update(change)
            scene["facility_planning"] = {"levels": levels}
            with self.subTest(change=change), self.assertRaises(ValueError):
                create_scene(self.config, scene)
        scene = small_scene()
        scene["pads"][0]["allowed_levels"] = ["unknown"]
        with self.assertRaisesRegex(ValueError, "未知"):
            MapDocument(scene)

    def test_baseline_uses_original_round_robin_when_feasible(self):
        cfg = self.design["choices"]["fixed"]
        self.assertEqual(list(cfg["fleet_allocation"].values()), [3, 2])

    def test_allocation_control_freezes_sites_grades_and_actual_cost(self):
        a, b = (self.design["choices"][k] for k in ("fixed", "distance"))
        for field in ("pad_ids", "levels", "cost", "pad_services"):
            self.assertEqual(a[field], b[field])
        self.assertLessEqual(b["objective"], a["objective"])

    def test_joint_choice_is_best_of_all_feasible_design_candidates(self):
        selected = self.design["choices"]["combined"]
        self.assertEqual(selected["objective"], min(c["objective"] for c in self.design["candidates"]))
        self.assertLessEqual(selected["objective"], self.design["choices"]["fixed"]["objective"])

    def test_eval_keeps_configuration_across_seeds_and_loads(self):
        original = deepcopy(self.design["choices"])
        for seed, scenario in ((101, "normal"), (102, "peak")):
            result = evaluate_facility_design(self.design, seed, scenario)
            for key, plan in result["plans"].items():
                self.assertEqual(plan["facility_configuration"]["fleet_allocation"], original[key]["fleet_allocation"])
                self.assertEqual(plan["pad_ids"], original[key]["pad_ids"])
                self.assertEqual(plan["stats"]["total_orders"], 6 if scenario == "normal" else 12)
            self.assertEqual(result["plans"]["fixed"]["orders"], result["plans"]["combined"]["orders"])
        self.assertEqual(self.design["choices"], original)

    def test_no_design_seed_can_be_used_for_evaluation(self):
        for seed in self.design["design_seeds"]:
            with self.assertRaisesRegex(ValueError, "设计种子"):
                evaluate_facility_design(self.design, seed)
        with self.assertRaisesRegex(ValueError, "设计种子"):
            run_facility_study(self.config, small_scene(), seeds=[training_seeds(900)[1]], design_seed=900)

    def test_explicit_default_allocation_matches_legacy_simulation(self):
        scene = self.design["scene"]
        orders = generate_orders(scene, self.config)
        routes = self.design["routes"]
        old = simulate(scene, self.config, ["S1", "S2"], orders, routes)
        new = simulate(scene, self.config, ["S1", "S2"], orders, routes, {"S1": 3, "S2": 2})
        self.assertEqual(old, new)

    def test_station_service_times_affect_actual_jobs_and_calendars(self):
        scene = self.design["scene"]
        services = {"S1": {"takeoff_service": 7., "landing_service": 11.},
                    "S2": {"takeoff_service": 13., "landing_service": 17.}}
        orders = [{"id": "O1", "destination_id": "D1", "created_at": 0, "due_at": 600}]
        plan = simulate(scene, self.config, ["S1", "S2"], orders, self.design["routes"], {"S1": 3, "S2": 2}, services)
        job = plan["jobs"][0]
        self.assertAlmostEqual(job["depart"]-job["prep_start"], services[job["pad_id"]]["takeoff_service"])
        self.assertAlmostEqual(job["end"]-job["land_start"], services[job["pad_id"]]["landing_service"])
        for entry in plan["calendars"][job["pad_id"]]:
            field = "takeoff_service" if entry["operation"] == "takeoff" else "landing_service"
            self.assertAlmostEqual(entry["end"]-entry["start"], services[job["pad_id"]][field])

    def test_invalid_allocation_and_service_durations_are_rejected(self):
        for allocation in ({"S1": 5}, {"S1": 0, "S2": 5}, {"S1": 3, "S2": 3}, {"S1": True, "S2": 4}):
            with self.subTest(allocation=allocation), self.assertRaises(ValueError):
                simulate(self.design["scene"], self.config, ["S1", "S2"], [], self.design["routes"], allocation)
        with self.assertRaises(ValueError):
            simulate(self.design["scene"], self.config, ["S1", "S2"], [], self.design["routes"],
                     pad_services={"S1": {"takeoff_service": 1, "landing_service": 0},
                                   "S2": {"takeoff_service": 1, "landing_service": 1}})

    def test_joint_schedule_passes_independent_audit_and_wait_decomposition(self):
        result = evaluate_facility_design(self.design, 101, "peak")
        plan = result["plans"]["combined"]
        self.assertEqual(detect_conflicts(plan["jobs"], result["routes"], self.config.speed, self.config.separation), [])
        for calendar in plan["calendars"].values():
            self.assertTrue(all(a["end"] <= b["start"]+1e-8 for a, b in zip(calendar, calendar[1:])))
        for drone in plan["drones"]:
            jobs = sorted((j for j in plan["jobs"] if j["drone_id"] == drone["id"]), key=lambda j: j["prep_start"])
            self.assertTrue(all(a["end"] <= b["prep_start"]+1e-8 for a, b in zip(jobs, jobs[1:])))
        for j in plan["jobs"]:
            self.assertAlmostEqual(j["delivered_at"]-j["created_at"],
                                   (j["ready"]-j["created_at"])+(j["prep_start"]-j["ready"])+
                                   (j["depart"]-j["prep_start"])+(j["arrived_dest"]-j["depart"])+self.config.delivery_service)
        times = sorted(j["delivered_at"]-j["created_at"] for j in plan["jobs"])
        self.assertEqual(plan["stats"]["p95_delivery"], times[math.ceil(.95*len(times))-1])

    def test_map_pad_fields_are_atomic_undoable_and_saved(self):
        doc = MapDocument(small_scene())
        doc.update("pads", "S1", {"allowed_levels": "standard", "site_cost": "20"})
        snapshot = deepcopy(doc.scene)
        with self.assertRaises(ValueError):
            doc.update("pads", "S1", {"allowed_levels": "unknown"})
        self.assertEqual(doc.scene, snapshot)
        doc.undo()
        self.assertNotIn("site_cost", doc.scene["pads"][0])
        doc.redo()
        self.assertEqual(doc.scene, snapshot)

    def test_extended_excel_template_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            scene = load_scene_file(write_facility_template(Path(folder)/"等级.xlsx"))
            self.assertEqual(scene["facility_planning"]["levels"], DEFAULT_LEVELS)
            self.assertEqual(scene["pads"][0]["allowed_levels"], ["standard", "enhanced"])
            self.assertEqual(scene["pads"][0]["site_cost"], 0)
            create_scene(self.config, scene)

    def test_excel_blank_site_disables_it_and_invalid_constraints_are_rejected(self):
        cases = ((3, "D6", None, False, None),
                 (3, "D5", "等级误写", False, "D5.*表头"),
                 (6, "C6", "100+60", True, "场站等级.*C6.*公式"))
        with tempfile.TemporaryDirectory() as folder:
            source = write_facility_template(Path(folder)/"模板.xlsx")
            for sheet, ref, value, formula, expected in cases:
                with self.subTest(ref=ref):
                    path = Path(folder)/"填写.xlsx"
                    with ZipFile(source) as original, ZipFile(path, "w") as target:
                        for member in original.infolist():
                            data = original.read(member.filename)
                            if member.filename == f"xl/worksheets/sheet{sheet}.xml":
                                doc = ET.fromstring(data)
                                cell = doc.find(f".//m:c[@r='{ref}']", NS)
                                cell.clear()
                                cell.set("r", ref)
                                if value is not None:
                                    tag = "f" if formula else "v"
                                    ET.SubElement(cell, "{"+NS["m"]+"}"+tag).text = value
                                data = ET.tostring(doc, encoding="utf-8")
                            target.writestr(member, data)
                    if expected:
                        with self.assertRaisesRegex(ValueError, expected):
                            load_scene_file(path)
                    else:
                        scene = load_scene_file(path)
                        self.assertEqual(scene["pads"][0]["allowed_levels"], [])
                        self.assertTrue(all("S1" not in c["pad_ids"] for c in configurations(create_scene(self.config, scene), self.config, 260)))

    def test_study_exports_configuration_results_and_custom_svg_names(self):
        study = run_facility_study(self.config, small_scene(), seeds=[101, 102], design_seed=900, design_seed_count=1)
        self.assertEqual(len(study["summary"]), 6)
        self.assertTrue(all(row["runs"] == 2 for row in study["summary"]))
        with tempfile.TemporaryDirectory() as folder:
            output = export_facility_study(study, folder)
            restored = json.loads((output/"study.json").read_text(encoding="utf-8"))
            self.assertEqual(restored["evaluation_seeds"], [101, 102])
            self.assertEqual(restored["choices"], study["choices"])
            self.assertTrue((output/"design_candidates.csv").exists())
            self.assertTrue((output/"runs/peak_101/facility_configurations.csv").exists())
            self.assertIn("分级联合优化", (output/"runs/peak_101/map.svg").read_text(encoding="utf-8"))
            self.assertIn("配比优化", (output/"runs/peak_101/comparison.svg").read_text(encoding="utf-8"))
            self.assertEqual(create_scene(self.config, output/"scene.json")["facility_planning"]["budget"], 260)

    def test_cancellation_and_invalid_seed_lists(self):
        with self.assertRaises(PlanningCancelled):
            build_facility_design(self.config, small_scene(), cancel=lambda: True)
        for seeds in ([], [101, 101], [-1], [True]):
            with self.subTest(seeds=seeds), self.assertRaises(ValueError):
                run_facility_study(self.config, small_scene(), seeds=seeds)


if __name__ == "__main__":
    unittest.main()
