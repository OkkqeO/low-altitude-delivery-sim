"""Import checks use the actual user-facing workbook, including Excel XML variants."""
from copy import deepcopy
from pathlib import Path
import tempfile
import unittest
import xml.etree.ElementTree as ET
from zipfile import ZipFile

from engine import Config, ROOT, create_scene, evaluate_plans
from map_import import NS, load_scene_file

TEMPLATE = ROOT / "data" / "地图填写模板.xlsx"
M = "{" + NS["m"] + "}"


def edit_cell(document, ref, value=None, formula=None, shared=None):
    cell = document.find(f".//m:c[@r='{ref}']", NS)
    if cell is None:
        raise AssertionError(ref)
    cell.clear()
    cell.set("r", ref)
    if formula is not None:
        ET.SubElement(cell, M + "f").text = formula
    if shared is not None:
        cell.set("t", "s")
        ET.SubElement(cell, M + "v").text = str(shared)
    elif value is not None:
        cell.set("t", "inlineStr")
        ET.SubElement(ET.SubElement(cell, M + "is"), M + "t").text = str(value)


def changed_template(path, sheet_number, changes, extra=None):
    """Mutate test ZIP members without any spreadsheet authoring dependencies."""
    with ZipFile(TEMPLATE) as original, ZipFile(path, "w") as target:
        for member in original.infolist():
            data = original.read(member.filename)
            if member.filename == f"xl/worksheets/sheet{sheet_number}.xml":
                document = ET.fromstring(data)
                for ref, kwargs in changes.items():
                    edit_cell(document, ref, **kwargs)
                data = ET.tostring(document, encoding="utf-8")
            if not extra or member.filename not in extra:
                target.writestr(member.filename, data)
        for name, data in (extra or {}).items():
            target.writestr(name, data)


class MapImportTests(unittest.TestCase):
    def test_actual_template_produces_same_simulation_as_json(self):
        config = Config(order_count=6)
        imported = evaluate_plans(config, TEMPLATE)
        original = evaluate_plans(config)
        self.assertEqual(imported["plans"], original["plans"])
        self.assertEqual(imported["candidate_count"], 28)
        self.assertEqual(len(imported["scene"]["buildings"]), 10)

    def test_bad_cell_and_bounds_identify_sheet_row(self):
        for value, expected in (("120米", "数字"), ("NaN", "有限"), ("9999", "范围")):
            with self.subTest(value=value), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "map.xlsx"
                changed_template(path, 3, {"B6": {"value": value}})
                with self.assertRaisesRegex(ValueError, f"起降场.*第6行.*{expected}"):
                    create_scene(scene_path=path)

    def test_formulas_rejected_instead_of_using_stale_cache(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "map.xlsx"
            changed_template(path, 3, {"B6": {"formula": "40+38", "value": 78}})
            with self.assertRaisesRegex(ValueError, "起降场.*B6.*公式"):
                create_scene(scene_path=path)

    def test_blank_optional_name_and_demand_get_defaults(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "map.xlsx"
            changed_template(path, 4, {"A6": {}, "D6": {}})
            scene = create_scene(scene_path=path)
            self.assertEqual(scene["deliveries"][0]["name"], "D1")
            self.assertEqual(scene["deliveries"][0]["demand"], 1)

    def test_shared_strings_excel_save_variant(self):
        shared = (f'<sst xmlns="{NS["m"]}"><si><r><t>新场</t></r><r><t>站名</t></r></si></sst>').encode()
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "map.xlsx"
            changed_template(path, 3, {"A6": {"shared": 0}}, {"xl/sharedStrings.xml": shared})
            self.assertEqual(create_scene(scene_path=path)["pads"][0]["name"], "新场站名")

    def test_missing_header_and_setting_typo_are_explained(self):
        for sheet, changes, text in ((3, {"B5": {"value": "经度"}}, "起降场.*表头"),
                                     (1, {"A6": {"value": "地图宽"}}, "地图设置.*第6行.*无法识别")):
            with self.subTest(sheet=sheet), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / "map.xlsx"
                changed_template(path, sheet, changes)
                with self.assertRaisesRegex(ValueError, text):
                    create_scene(scene_path=path)

    def test_snapshot_is_copied_and_closure_scales_to_map(self):
        scene = create_scene()
        scene["width"], scene["height"] = 1920, 1280
        original = deepcopy(scene)
        closed = create_scene(Config(scenario="closure"), scene)
        self.assertEqual(scene, original)
        self.assertEqual(closed["closure"], {"x": 940, "y": 400, "w": 150, "h": 300})

    def test_invalid_file_format_has_actionable_message(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "broken.xlsx"
            path.write_text("not a zip", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "模板"):
                load_scene_file(path)
        with self.assertRaisesRegex(ValueError, "另存为"):
            load_scene_file("old.xls")


if __name__ == "__main__":
    unittest.main()
