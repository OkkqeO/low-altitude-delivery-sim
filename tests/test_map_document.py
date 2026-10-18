"""Scene editing must preserve geometry, manual heights and simulation inputs."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from engine import Config, create_scene, evaluate_plans
from map_document import MapDocument


class MapDocumentTests(unittest.TestCase):
    def setUp(self):
        self.document = MapDocument(create_scene())

    def test_geometry_failure_is_atomic_and_undo_redo_restore_content(self):
        original = deepcopy(self.document.scene)
        with self.assertRaises(ValueError):
            self.document.update("buildings", "B1", {"w": 99999})
        self.assertEqual(self.document.scene, original)
        self.assertFalse(self.document.undo_stack)
        self.document.update("buildings", "B1", {"height": 77})
        changed = deepcopy(self.document.scene)
        self.assertTrue(self.document.undo())
        self.assertEqual(self.document.scene, original)
        self.assertTrue(self.document.redo())
        self.assertEqual(self.document.scene, changed)
        self.document.undo()
        self.document.update("buildings", "B1", {"name": "修改名称"})
        self.assertFalse(self.document.redo())

    def test_height_is_manual_and_zero_is_a_deliberate_valid_value(self):
        identity = self.document.add("buildings", {"x": 10., "y": 10., "w": 12., "h": 14.})
        with self.assertRaisesRegex(ValueError, "楼高尚未填写"):
            self.document.ready_scene()
        self.document.update("buildings", identity, {"name": "待量楼高"})
        self.assertIn(identity, self.document.pending_heights)
        self.document.update("buildings", identity, {"height": 0})
        self.assertNotIn(identity, self.document.pending_heights)
        self.assertEqual(next(b for b in self.document.ready_scene()["buildings"] if b["id"] == identity)["height"], 0)

    def test_scale_changes_planar_coordinates_not_building_height(self):
        before = deepcopy(self.document.scene)
        self.document.set_width(before["width"] * 1.8)
        after = self.document.ready_scene()
        for collection in ("buildings", "pads", "deliveries", "risk_zones"):
            for old, new in zip(before[collection], after[collection]):
                self.assertAlmostEqual(new["x"], old["x"] * 1.8)
                self.assertAlmostEqual(new["y"], old["y"] * 1.8)
                if collection == "buildings":
                    self.assertEqual(new["height"], old["height"])
                if collection == "risk_zones":
                    self.assertAlmostEqual(new["rx"], old["rx"] * 1.8)
        self.assertEqual(after["clearance"], before["clearance"])
        self.assertEqual(after["vertical_clearance"], before["vertical_clearance"])

    def test_components_can_be_added_moved_duplicated_and_removed(self):
        for collection, values in (("pads", {"x": 2., "y": 3.}), ("deliveries", {"x": 3., "y": 4.}),
                                   ("risk_zones", {"x": 5., "y": 6., "rx": 10., "ry": 12., "weight": .3})):
            identity = self.document.add(collection, values)
            duplicate = self.document.duplicate(collection, identity)
            self.assertNotEqual(identity, duplicate)
            self.document.move(collection, duplicate, 99999, -99)
            item = self.document.item(collection, duplicate)
            self.assertEqual(item["x"], self.document.scene["width"])
            self.assertEqual(item["y"], 0)
            self.document.delete(collection, duplicate)
            self.assertTrue(self.document.undo())
            self.assertEqual(self.document.item(collection, duplicate)["id"], duplicate)

    def test_manual_height_changes_obstacle_and_saved_scene_is_same(self):
        scene = {"width": 240., "height": 160., "step": 10., "clearance": 3., "vertical_clearance": 5.,
                 "buildings": [{"id": "B1", "name": "建筑", "x": 95., "y": 45., "w": 50., "h": 70., "height": 10.}],
                 "pads": [{"id": "S1", "x": 20., "y": 80.}, {"id": "S2", "x": 20., "y": 125.}],
                 "deliveries": [{"id": "D1", "x": 220., "y": 80., "demand": 1.}], "risk_zones": [], "source": "测试"}
        document = MapDocument(scene)
        low = evaluate_plans(Config(order_count=2), document.scene)
        document.update("buildings", "B1", {"height": 70})
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "编辑地图.json"
            document.save(path)
            high = evaluate_plans(Config(order_count=2), path)
            self.assertEqual(high["scene"]["buildings"], document.scene["buildings"])
            self.assertGreater(high["routes"]["S1:D1"]["distance"], low["routes"]["S1:D1"]["distance"])
            self.assertNotIn("altitude", json.loads(path.read_text(encoding="utf-8")))

    def test_pending_scale_blocks_direct_file_simulation(self):
        self.document.scene["image_import"] = {"scale_confirmed": False}
        with self.assertRaisesRegex(ValueError, "尚未校准尺度"):
            self.document.ready_scene()
        self.document.set_width(self.document.scene["width"])
        self.assertTrue(self.document.ready_scene()["image_import"]["scale_confirmed"])

    def test_malformed_draft_fields_report_validation_errors(self):
        for field, value in (("width", "1000"), ("width", float("nan")), ("buildings", ["invalid"])):
            scene = deepcopy(self.document.scene)
            scene[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                MapDocument(scene)


if __name__ == "__main__":
    unittest.main()
