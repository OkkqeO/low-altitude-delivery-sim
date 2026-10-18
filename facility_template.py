"""Extend the standard-library XLSX template with editable facility inputs."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
import xml.etree.ElementTree as ET

from facility_schema import DEFAULT_LEVELS, DEFAULT_SOURCE

M = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
R = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
P = "http://schemas.openxmlformats.org/package/2006/relationships"
C = "http://schemas.openxmlformats.org/package/2006/content-types"


def write_facility_template(destination):
    source = Path(__file__).parent/"data"/"地图填写模板.xlsx"
    destination = Path(destination)
    if destination.resolve() == source.resolve():
        raise ValueError("请另存为分级选址模板，不要覆盖原始模板")

    def cell(row, ref, value):
        node = ET.SubElement(row, f"{{{M}}}c", r=ref)
        if isinstance(value, (float, int)):
            ET.SubElement(node, f"{{{M}}}v").text = str(value)
        else:
            node.set("t", "inlineStr")
            ET.SubElement(ET.SubElement(node, f"{{{M}}}is"), f"{{{M}}}t").text = str(value)

    def row(sheet_data, index, values):
        node = ET.SubElement(sheet_data, f"{{{M}}}row", r=str(index))
        for i, value in enumerate(values):
            cell(node, f"{chr(65+i)}{index}", value)

    with ZipFile(source) as archive:
        files = {name: archive.read(name) for name in archive.namelist()}
    workbook = ET.fromstring(files["xl/workbook.xml"])
    sheets = workbook.find(f"{{{M}}}sheets")
    sheet_id = max(int(s.get("sheetId")) for s in sheets)+1
    relations = ET.fromstring(files["xl/_rels/workbook.xml.rels"])
    relation_id = "rIdFacility"
    while any(r.get("Id") == relation_id for r in relations):
        relation_id += "X"
    filename = f"sheet{sheet_id}.xml"
    while f"xl/worksheets/{filename}" in files:
        sheet_id += 1
        filename = f"sheet{sheet_id}.xml"
    ET.SubElement(sheets, f"{{{M}}}sheet", name="场站等级", sheetId=str(sheet_id), **{f"{{{R}}}id": relation_id})
    ET.SubElement(relations, f"{{{P}}}Relationship", Id=relation_id, Type=R+"/worksheet", Target="worksheets/"+filename)
    content = ET.fromstring(files["[Content_Types].xml"])
    ET.SubElement(content, f"{{{C}}}Override", PartName="/xl/worksheets/"+filename,
                  ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml")
    grades = ET.Element(f"{{{M}}}worksheet")
    cols = ET.SubElement(grades, f"{{{M}}}cols")
    ET.SubElement(cols, f"{{{M}}}col", min="1", max="6", width="23", customWidth="1")
    data = ET.SubElement(grades, f"{{{M}}}sheetData")
    row(data, 1, ["分级设施参数：黄色地图模板继续适用，本表参数为演示假设"])
    row(data, 2, ["预算（相对单位）", 260])
    row(data, 3, ["参数来源", DEFAULT_SOURCE])
    row(data, 5, ["等级编号", "等级名称", "建设成本", "驻机上限", "起飞服务秒数", "降落服务秒数"])
    for i, level in enumerate(DEFAULT_LEVELS, 6):
        row(data, i, [level[k] for k in ("id", "name", "cost", "max_drones", "takeoff_service", "landing_service")])
    # Locate the pad sheet through workbook relationships, not a sheet index.
    pad_sheet = next(s for s in sheets if s.get("name") == "起降场")
    target = next(r.get("Target") for r in relations if r.get("Id") == pad_sheet.get(f"{{{R}}}id"))
    pad_path = target.lstrip("/") if target.startswith("/") else "xl/"+target
    pad_tree = ET.fromstring(files[pad_path])
    pad_data = pad_tree.find(f"{{{M}}}sheetData")
    for node in pad_data:
        index = int(node.get("r"))
        if index == 5:
            cell(node, "D5", "允许等级")
            cell(node, "E5", "场地附加成本")
        elif index >= 6 and any(
                c.find(f"{{{M}}}v") is not None or c.find(f"{{{M}}}is") is not None
                for c in node.findall(f"{{{M}}}c")):
            cell(node, f"D{index}", "standard,enhanced")
            cell(node, f"E{index}", 0)
    dimension = pad_tree.find(f"{{{M}}}dimension")
    if dimension is not None:
        dimension.set("ref", f"A1:E{max(int(n.get('r')) for n in pad_data)}")
    files.update({"xl/workbook.xml": ET.tostring(workbook), "xl/_rels/workbook.xml.rels": ET.tostring(relations),
                  "[Content_Types].xml": ET.tostring(content), pad_path: ET.tostring(pad_tree),
                  f"xl/worksheets/{filename}": ET.tostring(grades)})
    destination.parent.mkdir(parents=True, exist_ok=True)
    with ZipFile(destination, "w", ZIP_DEFLATED) as archive:
        for name, value in files.items():
            archive.writestr(name, value)
    return destination
