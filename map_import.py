"""Read the Chinese map template using only the Python standard library.

XLSX is a ZIP of XML files. Only scalar values are accepted; formulas are
rejected so a stale Excel formula cache cannot silently change a simulation.
"""
from __future__ import annotations

import json
import math
from pathlib import Path
import posixpath
import re
import xml.etree.ElementTree as ET
from zipfile import BadZipFile, ZipFile

NS = {"m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
REL_ID = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id"
SETTINGS = {
    "地图宽度(m)": ("width", 960), "地图高度(m)": ("height", 640),
    "网格间距(m)": ("step", 16), "建筑平面间距(m)": ("clearance", 8),
    "建筑垂直间距(m)": ("vertical_clearance", 5),
}
TABLES = {
    "建筑": ("buildings", "B", ("名称", "X坐标(m)", "Y坐标(m)", "长度(m)", "宽度(m)", "楼高(m)"),
           ("name", "x", "y", "w", "h", "height")),
    "起降场": ("pads", "S", ("名称", "X坐标(m)", "Y坐标(m)"), ("name", "x", "y")),
    "配送点": ("deliveries", "D", ("名称", "X坐标(m)", "Y坐标(m)", "需求权重"),
            ("name", "x", "y", "demand")),
    "人群热点": ("risk_zones", "R", ("名称", "X坐标(m)", "Y坐标(m)", "X半径(m)", "Y半径(m)", "强度"),
             ("name", "x", "y", "rx", "ry", "weight")),
}


def _xlsx_sheets(path: Path) -> dict:
    try:
        with ZipFile(path) as archive:
            if sum(z.file_size for z in archive.infolist()) > 32_000_000:
                raise ValueError("地图表格过大，请仅保留地图数据（解压后不超过32MB）")
            shared = []
            if "xl/sharedStrings.xml" in archive.namelist():
                shared = ["".join(t.text or "" for t in n.findall(".//m:t", NS))
                          for n in ET.fromstring(archive.read("xl/sharedStrings.xml"))]
            rels = {r.attrib["Id"]: r.attrib["Target"] for r in
                    ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
                    if r.attrib.get("TargetMode") != "External"}
            workbook = ET.fromstring(archive.read("xl/workbook.xml"))
            result = {}
            for sheet in workbook.findall("m:sheets/m:sheet", NS):
                name = sheet.attrib["name"]
                if name not in ("地图设置", "场站等级", *TABLES):
                    continue
                target = rels[sheet.attrib[REL_ID]]
                member = target.lstrip("/") if target.startswith("/") else posixpath.normpath("xl/" + target)
                cells = {}
                for cell in ET.fromstring(archive.read(member)).findall(".//m:sheetData/m:row/m:c", NS):
                    ref = cell.attrib["r"]
                    match = re.fullmatch(r"([A-Z]+)([1-9][0-9]*)", ref)
                    if not match or int(match[2]) > 10005:
                        raise ValueError(f"“{name}”最多支持10000行数据")
                    if cell.find("m:f", NS) is not None:
                        raise ValueError(f"“{name}” {ref} 使用了公式，请复制并粘贴为数值")
                    kind = cell.attrib.get("t")
                    value = cell.find("m:v", NS)
                    if kind == "inlineStr":
                        value = "".join(n.text or "" for n in cell.findall(".//m:t", NS))
                    elif value is None:
                        value = None
                    elif kind == "s":
                        value = shared[int(value.text)]
                    elif kind in ("b", "e"):
                        raise ValueError(f"“{name}” {ref} 须填写文字或数字")
                    else:
                        value = value.text
                    if value is not None and str(value).strip():
                        cells[ref] = value
                result[name] = cells
            return result
    except (BadZipFile, ET.ParseError, KeyError, IndexError, TypeError) as error:
        raise ValueError("无法读取Excel地图，请使用提供的模板并另存为 .xlsx 格式") from error


def _number(value, location, default=None):
    if value is None or str(value).strip() == "":
        if default is not None:
            return default
        raise ValueError(f"{location} 未填写，请输入数字")
    try:
        number = float(value)
    except (ValueError, TypeError) as error:
        raise ValueError(f"{location} 须填写数字，例如 120；单位无需填入单元格") from error
    if not math.isfinite(number):
        raise ValueError(f"{location} 须填写有限数字")
    return number


def load_excel_scene(path: str | Path) -> dict:
    sheets = _xlsx_sheets(Path(path))
    for required in ("地图设置", "起降场", "配送点"):
        if required not in sheets:
            raise ValueError(f"缺少“{required}”工作表，请使用地图填写模板")
    settings = sheets["地图设置"]
    if settings.get("A5") != "参数" or settings.get("B5") != "数值":
        raise ValueError("“地图设置”第5行表头应为“参数、数值、说明”，请勿删除表头")
    scene = {key: default for key, default in SETTINGS.values()}
    scene["source"] = "用户填写的Excel地图；请补充数据来源"
    seen = set()
    for row in sorted({int(re.search(r"\d+", ref)[0]) for ref in settings}):
        if row < 6:
            continue
        label = settings.get(f"A{row}")
        if not label:
            if settings.get(f"B{row}") is not None:
                raise ValueError(f"“地图设置”第{row}行有数值但缺少参数名称")
            continue
        if label not in (*SETTINGS, "数据来源"):
            raise ValueError(f"“地图设置”第{row}行参数“{label}”无法识别，请保留模板中的参数名称")
        if label in seen:
            raise ValueError(f"“地图设置”第{row}行参数“{label}”重复")
        seen.add(label)
        value = settings.get(f"B{row}")
        if label == "数据来源":
            if value:
                scene["source"] = str(value)
        else:
            key, default = SETTINGS[label]
            scene[key] = _number(value, f"“地图设置”第{row}行 {label}", default)

    for sheet_name, (collection, prefix, headers, fields) in TABLES.items():
        scene[collection] = []
        cells = sheets.get(sheet_name)
        if cells is None:
            continue  # buildings and exposure zones may be absent
        for col, header in enumerate(headers):
            if cells.get(f"{chr(65+col)}5") != header:
                raise ValueError(f"“{sheet_name}”第5行表头应包含“{header}”，请保留原表头")
        if collection == "pads":
            for column, expected in (("D", "允许等级"), ("E", "场地附加成本")):
                if (any(ref.startswith(column) and int(re.search(r"\d+", ref)[0]) >= 5 for ref in cells)
                        and cells.get(column+"5") != expected):
                    raise ValueError(f"“起降场”{column}5表头须为“{expected}”，避免忽略设施约束")
        rows = sorted({int(re.search(r"\d+", ref)[0]) for ref in cells})
        for row in rows:
            if row < 6:
                continue
            values = [cells.get(f"{chr(65+col)}{row}") for col in range(len(fields))]
            has_facility_values = collection == "pads" and any(cells.get(f"{column}{row}") is not None for column in ("D", "E"))
            if all(v is None for v in values) and not has_facility_values:
                continue
            item = {"id": f"{prefix}{len(scene[collection])+1}"}
            for field, header, value in zip(fields, headers, values):
                item[field] = (str(value).strip() if value is not None else item["id"]) if field == "name" else _number(
                    value, f"“{sheet_name}”第{row}行 {header}", 1. if field == "demand" else None)
            location = f"“{sheet_name}”第{row}行"
            if not 0 <= item["x"] <= scene["width"] or not 0 <= item["y"] <= scene["height"]:
                raise ValueError(f"{location} 坐标超出地图范围，请检查X、Y及地图宽高")
            if collection == "buildings" and (min(item["w"], item["h"]) <= 0 or item["height"] < 0
                    or item["x"]+item["w"] > scene["width"] or item["y"]+item["h"] > scene["height"]):
                raise ValueError(f"{location} 建筑长宽须大于0、楼高须非负，且建筑不能超出地图边界")
            if collection == "deliveries" and item["demand"] <= 0:
                raise ValueError(f"{location} 需求权重须大于0；留空使用1")
            if collection == "risk_zones" and (min(item["rx"], item["ry"]) <= 0 or not 0 <= item["weight"] <= 1):
                raise ValueError(f"{location} 热点半径须大于0，强度须在0至1之间")
            if collection == "pads":
                if cells.get("D5") == "允许等级":
                    value = cells.get(f"D{row}")
                    item["allowed_levels"] = [v.strip() for v in str(value or "").replace("，", ",").split(",") if v.strip() and v.strip() != "禁用"]
                if cells.get("E5") == "场地附加成本":
                    item["site_cost"] = _number(cells.get(f"E{row}"), location+" 场地附加成本", 0.)
            scene[collection].append(item)
    if len(scene["pads"]) < 2 or not scene["deliveries"]:
        raise ValueError("请在“起降场”填写至少2个候选位置，在“配送点”填写至少1个位置")
    grade_cells = sheets.get("场站等级")
    if grade_cells is not None:
        headers = ("等级编号", "等级名称", "建设成本", "驻机上限", "起飞服务秒数", "降落服务秒数")
        if any(grade_cells.get(f"{chr(65+i)}5") != header for i, header in enumerate(headers)):
            raise ValueError("“场站等级”第5行表头不完整，请使用分级选址模板")
        levels = []
        for row in sorted({int(re.search(r"\d+", ref)[0]) for ref in grade_cells}):
            if row < 6:
                continue
            values = [grade_cells.get(f"{chr(65+i)}{row}") for i in range(6)]
            if all(value is None for value in values):
                continue
            level = {"id": str(values[0] or "").strip(), "name": str(values[1] or "").strip()}
            for field, value in zip(("cost", "max_drones", "takeoff_service", "landing_service"), values[2:]):
                level[field] = _number(value, f"“场站等级”第{row}行 {field}")
            if level["max_drones"].is_integer():
                level["max_drones"] = int(level["max_drones"])
            levels.append(level)
        from facility_schema import DEFAULT_SOURCE
        scene["facility_planning"] = {"levels": levels, "budget": _number(grade_cells.get("B2"), "“场站等级”B2预算", 260.),
                                      "parameter_source": str(grade_cells.get("B3") or DEFAULT_SOURCE)}
    from facility_schema import validate_optional_facilities
    validate_optional_facilities(scene)
    return scene


def load_scene_file(path: str | Path) -> dict:
    path = Path(path)
    if path.suffix.lower() == ".xlsx":
        return load_excel_scene(path)
    if path.suffix.lower() != ".json":
        raise ValueError("请选择填写好的 .xlsx 地图模板或 .json 地图；旧版 .xls 请先另存为 .xlsx")
    try:
        with path.open(encoding="utf-8-sig") as handle:
            scene = json.load(handle)
    except (json.JSONDecodeError, UnicodeError) as error:
        raise ValueError("JSON地图格式有误，请检查文件，或改用Excel模板") from error
    if not isinstance(scene, dict):
        raise ValueError("JSON地图的顶层须为一个对象")
    return scene
