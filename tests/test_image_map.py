"""Image extraction checks use known footprints, distractors and manual completion."""
from pathlib import Path
import tempfile
import unittest

try:
    from PIL import Image, ImageDraw
except ImportError:
    Image = ImageDraw = None

from engine import Config, create_scene, evaluate_plans
from image_map import BACKGROUND_EDGE, decode_background, encode_background, extract_buildings, read_image, scene_from_image
from map_document import MapDocument


@unittest.skipUnless(Image, "Optional Pillow image dependency is not installed")
class ImageMapTests(unittest.TestCase):
    def schematic(self):
        image = Image.new("RGB", (600, 400), "#f6f7f4")
        draw = ImageDraw.Draw(image)
        draw.rectangle((0, 175, 599, 210), fill="white")  # road
        draw.rectangle((400, 20, 580, 140), fill="#abd6a3")  # park
        draw.rectangle((50, 40, 145, 130), fill="#c8cdd4")
        draw.rectangle((215, 45, 325, 125), fill="#dfd0b7")
        draw.rectangle((55, 255, 155, 350), fill="#b9bec5")
        draw.text((70, 75), "Building A", fill="#444444")
        draw.text((215, 190), "ROAD 100", fill="#7c7c7c")
        draw.line((10, 10, 590, 10), fill="#aaaaaa", width=2)
        return image

    def test_footprints_detected_without_road_text_or_park(self):
        buildings, metadata = extract_buildings(self.schematic(), 600)
        self.assertEqual(len(buildings), 3)
        expected = ((50, 40, 96, 91), (215, 45, 111, 81), (55, 255, 101, 96))
        for building, bounds in zip(buildings, expected):
            for field, value in zip(("x", "y", "w", "h"), bounds):
                self.assertAlmostEqual(building[field], value, delta=2)
            self.assertFalse(building["height_confirmed"])
        self.assertFalse(metadata["recognition_truncated"])

    def test_color_pick_extracts_nonstandard_building_fill(self):
        image = Image.new("RGB", (300, 220), "white")
        ImageDraw.Draw(image).rectangle((60, 40, 160, 150), fill=(156, 99, 202))
        self.assertEqual(extract_buildings(image, 300)[0], [])
        buildings, _ = extract_buildings(image, 300, "color", (156, 99, 202), 12)
        self.assertEqual(len(buildings), 1)
        with self.assertRaises(ValueError):
            extract_buildings(image, 300, "color")

    def test_image_round_trip_keeps_background_and_requires_manual_values(self):
        with tempfile.TemporaryDirectory() as folder:
            original = Path(folder) / "园区图片.png"
            self.schematic().save(original)
            scene = scene_from_image(original)
            self.assertEqual(len(scene["buildings"]), 3)
            document = MapDocument(scene)
            with self.assertRaisesRegex(ValueError, "尺度"):
                document.ready_scene()
            document.set_width(600)
            with self.assertRaisesRegex(ValueError, "楼高"):
                document.ready_scene()
            document.set_heights(30)
            original.unlink()
            saved = Path(folder) / "地图.json"
            document.save(saved)
            loaded = create_scene(scene_path=saved)
            self.assertEqual(decode_background(loaded).size, (600, 400))
            self.assertEqual(loaded["buildings"][0]["height"], 30)
            result = evaluate_plans(Config(order_count=2), saved)
            self.assertEqual(result["candidate_count"], 15)
            self.assertTrue(all(p["stats"]["delivered_orders"] == 2 for p in result["plans"].values()))

    def test_suggested_points_do_not_intersect_detected_footprints(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "map.png"
            self.schematic().save(path)
            scene = scene_from_image(path)
        for point in scene["pads"] + scene["deliveries"]:
            for building in scene["buildings"]:
                padding = scene["clearance"]
                self.assertFalse(building["x"]-padding <= point["x"] <= building["x"]+building["w"]+padding
                                 and building["y"]-padding <= point["y"] <= building["y"]+building["h"]+padding)
            self.assertTrue(point["suggested"])
        self.assertEqual(scene["risk_zones"], [])

    def test_transparent_background_becomes_white_and_edge_geometry_stays_in_bounds(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "transparent.png"
            image = Image.new("RGBA", (1331, 697), (0, 0, 0, 0))
            ImageDraw.Draw(image).rectangle((1200, 590, 1330, 696), fill=(180, 185, 190, 255))
            image.save(path)
            read = read_image(path)
            self.assertEqual(read.getpixel((0, 0)), (255, 255, 255))
            buildings, _ = extract_buildings(read, 1000)
            self.assertEqual(len(buildings), 1)
            building = buildings[0]
            self.assertLessEqual(building["x"] + building["w"], 1000 + 1e-6)
            self.assertLessEqual(building["y"] + building["h"], 1000*697/1331 + 1e-6)

    def test_background_keeps_native_detail_and_limits_large_images(self):
        # A high density map used to be reduced to 1280 px even when the
        # displayed canvas was wider. Preserve it and accept its round trip.
        image = Image.new("RGB", (2560, 2048), "white")
        ImageDraw.Draw(image).line((1800, 0, 1800, 2047), fill="black", width=1)
        decoded = decode_background({"image_background": encode_background(image, "native.png")})
        self.assertEqual(decoded.size, image.size)
        self.assertEqual(decoded.getpixel((1800, 1024)), (0, 0, 0))
        large = Image.new("RGB", (4096, 1024), "white")
        decoded = decode_background({"image_background": encode_background(large, "large.png")})
        self.assertEqual(decoded.size, (BACKGROUND_EDGE, BACKGROUND_EDGE // 4))


if __name__ == "__main__":
    unittest.main()
