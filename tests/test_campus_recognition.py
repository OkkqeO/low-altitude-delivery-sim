"""Independent map landmarks, semantic distractors and polygon editing checks."""
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest

from engine import Config, create_scene, is_blocked, segment_clear
from map_document import MapDocument
from map_geometry import contains

try:
    from PIL import Image, ImageDraw
    from campus_recognition import vision
    vision()
except (ImportError, ValueError):
    Image = ImageDraw = None

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = Path(__file__).with_name("fixtures")/"tsinghua_landmarks.json"


@unittest.skipUnless(Image, "Optional map image dependencies are not installed")
class CampusRecognitionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from image_map import read_image, scene_from_image
        from campus_recognition import extract_map
        cls.reference = json.loads(FIXTURE.read_text(encoding="utf-8"))
        cls.scene = scene_from_image(ROOT/cls.reference["image"])
        cls.detected_buildings, cls.detected_features, _ = extract_map(read_image(ROOT/cls.reference["image"]), 1000, labels=[])

    def test_real_map_manually_identified_landmarks(self):
        scale = self.scene["width"]/2400
        for landmark in self.reference["landmarks"]:
            point = tuple(v*scale for v in landmark["point"])
            found = {"building" for b in self.detected_buildings if contains(b, point)}
            found.update(f["kind"] for f in self.detected_features if contains(f, point))
            with self.subTest(landmark=landmark["name"]):
                self.assertEqual(found, {landmark["kind"]} if landmark["kind"] != "none" else set())

    def test_full_resolution_official_image_and_no_160_building_limit(self):
        from image_map import scene_from_image
        scene = scene_from_image(ROOT/"data/真实校园地图/清华大学/清华大学_校园地图_官网原图_2025年12月.jpg")
        self.assertGreater(len(scene["buildings"]), 160)
        self.assertFalse(scene["image_import"]["recognition_truncated"])
        self.assertGreater(scene["image_import"]["feature_counts"]["road"], 0)
        self.assertTrue(all(f["kind"] == "road" for f in scene["map_features"]))
        self.assertTrue(all("polygon" not in b for b in scene["buildings"]))
        MapDocument(scene)

    def test_rotated_footprint_fields_lines_and_railway_distractor(self):
        from campus_recognition import extract_map
        image = Image.new("RGB", (640, 440), (217, 213, 210))
        draw = ImageDraw.Draw(image)
        draw.polygon([(60, 100), (110, 70), (180, 170), (130, 200)], fill=(139, 194, 188))
        draw.rectangle((220, 30, 290, 110), fill=(162, 120, 168))
        draw.rectangle((340, 40, 400, 100), fill=(182, 208, 147))
        draw.polygon([(30, 260), (110, 230), (150, 300), (70, 330)], fill=(154, 184, 212))
        draw.rectangle((450, 150, 610, 330), fill=(232, 220, 50))
        draw.rectangle((465, 170, 595, 310), fill=(182, 208, 147))
        draw.line((465, 240, 595, 240), fill="white", width=4)
        draw.line((310, 0, 310, 439), fill="white", width=14)
        draw.line((170, 350, 600, 425), fill=(227, 163, 55), width=4)
        buildings, features, _ = extract_map(image, 640, labels=[])
        self.assertTrue(any(contains(b, (100, 120)) for b in buildings))
        self.assertFalse(any(contains(b, (65, 75)) for b in buildings))
        self.assertFalse(any(contains(b, (390, 388)) for b in buildings))
        def kinds(point):
            return {f["kind"] for f in features if contains(f, point)}
        self.assertIn("sports", kinds((530, 240)))
        self.assertNotIn("road", kinds((530, 240)))
        self.assertNotIn("green", kinds((530, 240)))
        self.assertIn("road", kinds((310, 180)))
        self.assertIn("water", kinds((80, 280)))

    def test_printed_court_label_disambiguates_solid_yellow_structure(self):
        from campus_recognition import extract_map
        image = Image.new("RGB", (400, 300), (217, 213, 210))
        draw = ImageDraw.Draw(image)
        draw.rectangle((20, 20, 90, 80), fill=(139, 194, 188))
        draw.rectangle((120, 20, 190, 80), fill=(162, 120, 168))
        draw.rectangle((230, 20, 300, 80), fill=(182, 208, 147))
        draw.rectangle((150, 150, 280, 260), fill=(232, 220, 50))
        labels = [{"text": "排球场", "x": 180, "y": 190, "w": 60, "h": 20}]
        buildings, features, _ = extract_map(image, 400, labels=labels)
        self.assertFalse(any(contains(b, (210, 210)) for b in buildings))
        self.assertTrue(any(f["kind"] == "sports" and f["name"] == "排球场" and contains(f, (210, 210)) for f in features))

    def test_recognition_draft_remains_uncalibrated_with_manual_heights(self):
        document = MapDocument(self.scene)
        with self.assertRaisesRegex(ValueError, "尺度"):
            document.ready_scene()
        document.set_width(1200)
        with self.assertRaisesRegex(ValueError, "楼高"):
            document.ready_scene()
        document.set_heights(30)
        scene = document.ready_scene()
        self.assertEqual(scene["map_features"], document.scene["map_features"])
        self.assertEqual(scene["risk_zones"], [])


class PolygonDocumentTests(unittest.TestCase):
    def setUp(self):
        self.scene = create_scene()
        self.scene["buildings"] = [{"id": "B1", "name": "三角建筑", "x": 40., "y": 40., "w": 40., "h": 40.,
                                    "height": 80., "polygon": [[40., 40.], [80., 40.], [40., 80.]], "holes": []}]
        self.scene["clearance"] = 0.
        self.scene["map_features"] = [{"id": "F1", "name": "环形区域", "kind": "road", "x": 100., "y": 100., "w": 80., "h": 80.,
                                        "polygon": [[100., 100.], [180., 100.], [180., 180.], [100., 180.]],
                                        "holes": [[[120., 120.], [160., 120.], [160., 160.], [120., 160.]]]}]
        self.doc = MapDocument(self.scene)

    def test_routing_uses_actual_polygon_not_its_bounding_rectangle(self):
        self.assertTrue(is_blocked(self.scene, (50, 50)))
        self.assertFalse(is_blocked(self.scene, (75, 75)))
        self.assertTrue(segment_clear(self.scene, (65, 70), (90, 70)))
        self.scene["clearance"] = 3
        self.assertTrue(is_blocked(self.scene, (62, 62)))

    def test_schematic_map_uses_same_boxes_for_routing_and_keeps_only_roads(self):
        from flight_map import schematic_scene, flight_obstacles
        source = deepcopy(self.scene)
        source["map_features"].append(dict(source["map_features"][0], id="F2", kind="green"))
        simplified = create_scene(scene_path=schematic_scene(source))
        self.assertEqual([f["kind"] for f in simplified["map_features"]], ["road"])
        self.assertNotIn("polygon", simplified["buildings"][0])
        self.assertTrue(is_blocked(simplified, (75, 75)))
        self.assertFalse(is_blocked(simplified, (110, 110)))
        self.assertEqual(len(flight_obstacles(simplified)), 1)
        self.assertIn("polygon", source["buildings"][0])
        simplified["buildings"][0]["height"] = 20
        self.assertFalse(flight_obstacles(simplified))
        self.assertFalse(is_blocked(simplified, (50, 50)))
        lower = create_scene(Config(altitude=25), simplified)
        self.assertEqual(len(flight_obstacles(lower)), 1)
        self.assertTrue(is_blocked(lower, (50, 50)))

    def test_schematic_road_discards_small_letter_holes_but_preserves_courtyard(self):
        from flight_map import schematic_scene
        source = deepcopy(self.scene)
        road = source["map_features"][0]
        road["polygon"] = [[100.,100.],[140.,100.1],[180.,100.],[179.9,140.],[180.,180.],
                           [140.,179.9],[100.,180.],[100.1,140.]]
        road["holes"].append([[105.,105.],[107.,105.],[107.,107.],[105.,107.]])
        simple = schematic_scene(source)
        self.assertEqual(len(simple["map_features"][0]["polygon"]), 4)
        self.assertEqual(len(simple["map_features"][0]["holes"]), 1)
        self.assertFalse(contains(simple["map_features"][0], (140,140)))
        self.assertEqual(schematic_scene(simple), simple)

    def test_move_resize_duplicate_scale_and_json_preserve_holes(self):
        self.assertFalse(contains(self.doc.item("map_features", "F1"), (140, 140)))
        self.doc.move("map_features", "F1", 200, 200)
        self.doc.update("map_features", "F1", {"w": 160, "h": 160})
        moved = deepcopy(self.doc.item("map_features", "F1"))
        self.assertFalse(contains(moved, (280, 280)))
        self.assertTrue(contains(moved, (210, 210)))
        clone = self.doc.duplicate("map_features", "F1")
        self.assertFalse(contains(self.doc.item("map_features", clone), (292, 292)))
        self.doc.set_width(self.doc.scene["width"]*2)
        self.assertFalse(contains(self.doc.item("map_features", "F1"), (560, 560)))
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/"map.json"
            self.doc.save(path)
            loaded = MapDocument(json.loads(path.read_text(encoding="utf-8")))
            self.assertEqual(loaded.scene, self.doc.scene)

    def test_reclassification_and_vertex_edits_are_undoable(self):
        original = deepcopy(self.doc.scene)
        self.doc.update("map_features", "F1", {"kind": "water"})
        identity = self.doc.convert_feature_to_building("F1")
        self.assertIn(identity, self.doc.pending_heights)
        new_id = self.doc.convert_building_to_feature(identity, "sports")
        self.assertEqual(self.doc.item("map_features", new_id)["kind"], "sports")
        for _ in range(3): self.doc.undo()
        self.assertEqual(self.doc.scene, original)
        self.doc.set_polygon("buildings", "B1", [[40., 40.], [90., 40.], [40., 90.]])
        self.assertTrue(contains(self.doc.item("buildings", "B1"), (60, 60)))
        self.doc.undo()
        self.assertEqual(self.doc.scene, original)

    def test_invalid_polygon_is_rejected_atomically(self):
        original = deepcopy(self.doc.scene)
        with self.assertRaises(ValueError):
            self.doc.set_polygon("buildings", "B1", [[-10., 40.], [90., 40.], [40., 90.]])
        self.assertEqual(self.doc.scene, original)
        bad = deepcopy(self.scene)
        bad["buildings"][0]["polygon"][0][0] = float("nan")
        with self.assertRaises(ValueError):
            create_scene(Config(), bad)


if __name__ == "__main__":
    unittest.main()
