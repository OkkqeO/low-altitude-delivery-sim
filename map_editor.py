"""Component editor for image, Excel and JSON scenes."""
from __future__ import annotations

from copy import deepcopy
import math
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from display import px, window_geometry
from map_document import COLLECTIONS, FIELDS, MapDocument, finite
from map_geometry import FEATURE_TYPES, FEATURE_COLORS, canvas_polygon, contains, transform_shape
from ui import BG, BLUE, FONT, INK, LINE, MUTED, NAVY

LABELS = {"name": "名称", "x": "X 坐标 / 米", "y": "Y 坐标 / 米", "w": "长度 / 米",
          "h": "宽度 / 米", "height": "楼高 / 米（手动）", "demand": "需求权重",
          "rx": "X 半径 / 米", "ry": "Y 半径 / 米", "weight": "人群强度 / 0—1"}
COLORS = {"buildings": "#597594", "pads": "#2878CA", "deliveries": "#E09B32", "risk_zones": "#C87157", "map_features": "#5C9D68"}


class MapEditor:
    def __init__(self, parent, scene, config=None, path=None, *, view=None):
        view = view or {}
        self.document = MapDocument(scene)
        self.config = config
        self.path = Path(path) if path else None
        self.document.scene.setdefault("name", self.path.stem if self.path else "编辑地图")
        self.saved_path = self.path if self.path and self.path.suffix.lower() == ".json" else None
        self.result = None
        self.baseline = deepcopy(self.document.scene)
        self.selected = None
        self.drag = None
        self.photo = None
        self.bg_cache = None
        self.item_refs = {}
        self.form_vars, self.form_original = {}, {}
        self.calibration_points = []
        self.picked_color = None
        self.transform = (1., 0., 0.)
        self.zoom = 1.
        self.pan = (0., 0.)
        self.window = tk.Toplevel(parent)
        self.window.title("地图组件编辑器 · 楼高手动填写")
        self.window.geometry(window_geometry(self.window, 1320, 900, margin=70, x=40, y=40))
        self.window.minsize(px(1000), px(650))
        self.window.configure(bg=BG)
        self.window.transient(parent)
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.window.rowconfigure(2, weight=1)
        self.window.columnconfigure(0, weight=1)
        self.tool = tk.StringVar(self.window, "select")
        # Reopening a flight diagram starts with the same plain basemap.
        # Image drafts still show their source image for tracing/calibration.
        draft = (scene.get("image_import", {}).get("scale_confirmed") is False
                 or any(b.get("height_confirmed") is False for b in scene.get("buildings", [])))
        self.show_background = tk.BooleanVar(self.window, view.get("background", draft or scene.get("map_presentation") != "schematic"))
        self.show_labels = tk.BooleanVar(self.window, view.get("labels", len(scene.get("buildings", [])) < 40))
        self.layers = {k: tk.BooleanVar(self.window, view.get(k, True)) for k in ("buildings", "risk_zones", *FEATURE_TYPES)}
        self.feature_kind = tk.StringVar(self.window, "绿地")
        self.status = tk.StringVar(self.window)
        self.mode = tk.StringVar(self.window, "自动")
        self.min_area = tk.StringVar(self.window, "100")
        self.tolerance = tk.StringVar(self.window, "35")
        self.width_var = tk.StringVar(self.window)
        self.batch_height = tk.StringVar(self.window)
        self.selected_text = tk.StringVar(self.window, "选择地图组件")
        self.color_text = tk.StringVar(self.window, "尚未取色")
        self.background = None
        try:
            if scene.get("image_background"):
                from image_map import decode_background
                self.background = decode_background(scene)
            self._build()
            self.refresh()
        except Exception:
            self.window.destroy()
            raise
        self.window.bind("<Control-z>", lambda event: self.history(False))
        self.window.bind("<Control-y>", lambda event: self.history(True))
        self.window.bind("<Delete>", self.delete_key)
        self.window.bind("<Escape>", lambda event: self.set_tool("select"))
        self.window.bind("<MouseWheel>", self.scroll_side, add="+")
        self.window.bind("<Configure>", lambda event: self.status_label.configure(wraplength=max(px(230), self.window.winfo_width()-px(390))) if event.widget is self.window else None, add="+")

    def _build(self):
        header = ttk.Frame(self.window, style="Header.TFrame", padding=px((18, 12)))
        header.grid(row=0, column=0, sticky="ew")
        ttk.Label(header, text="地图组件编辑器", style="Header.TLabel").pack(side="left")
        ttk.Label(header, text="识别轮廓 → 校准尺度 → 手填楼高 → 应用仿真", style="HeaderSub.TLabel").pack(side="right")
        tools = ttk.Frame(self.window, padding=px((12, 8)))
        tools.grid(row=1, column=0, sticky="ew")
        tools.columnconfigure(0, weight=1)
        modes = ttk.Frame(tools)
        modes.grid(row=0, column=0, sticky="w")
        for key, label in (("select", "选择 / 拖动"), ("buildings", "画建筑"), ("pads", "起降场"),
                           ("deliveries", "配送点"), ("risk_zones", "人群区"), ("map_features", "画地物"),
                           ("vertices", "顶点"), ("color", "取色"), ("calibrate", "两点定标")):
            ttk.Radiobutton(modes, text=label, variable=self.tool, value=key, command=lambda k=key: self.set_tool(k)).pack(side="left", padx=px((0, 8)))
        actions = ttk.Frame(tools)
        actions.grid(row=2, column=1, sticky="e", pady=px((7, 0)))
        self.undo_button = ttk.Button(actions, text="撤销", command=lambda: self.history(False))
        self.undo_button.pack(side="left", padx=px(2))
        self.redo_button = ttk.Button(actions, text="重做", command=lambda: self.history(True))
        self.redo_button.pack(side="left", padx=px(2))
        ttk.Button(actions, text="适应窗口", command=self.fit).pack(side="left", padx=px(2))
        recognition = ttk.Frame(tools)
        recognition.grid(row=1, column=0, columnspan=2, sticky="ew", pady=px((9, 0)))
        ttk.Label(recognition, text="地图识别").pack(side="left", padx=px((0, 6)))
        self.mode_box = ttk.Combobox(recognition, textvariable=self.mode, values=("自动", "灰色建筑", "暖色建筑", "蓝灰建筑", "取色识别"), width=10, state="readonly")
        self.mode_box.pack(side="left", padx=px((0, 10)))
        ttk.Label(recognition, text="最小区域 / 像素").pack(side="left")
        ttk.Spinbox(recognition, textvariable=self.min_area, from_=20, to=10000, width=6).pack(side="left", padx=px((5, 10)))
        ttk.Label(recognition, text="取色容差").pack(side="left")
        ttk.Spinbox(recognition, textvariable=self.tolerance, from_=5, to=100, width=4).pack(side="left", padx=px((5, 10)))
        self.recognize_button = ttk.Button(recognition, text="重新识别全部", command=self.recognize)
        self.recognize_button.pack(side="left")
        ttk.Label(recognition, textvariable=self.color_text, foreground=MUTED).pack(side="left", padx=px(10))
        layers = ttk.Frame(tools)
        layers.grid(row=2, column=0, sticky="w", pady=px((7, 0)))
        for key, label in (("buildings", "建筑"), ("risk_zones", "人群区"), *FEATURE_TYPES.items()):
            ttk.Checkbutton(layers, text=label, variable=self.layers[key], command=self.draw).pack(side="left", padx=px((0, 5)))
        ttk.Checkbutton(layers, text="名称", variable=self.show_labels, command=self.draw).pack(side="left")
        ttk.Label(layers, text="  新地物").pack(side="left")
        ttk.Combobox(layers, textvariable=self.feature_kind, values=list(FEATURE_TYPES.values()), state="readonly", width=8).pack(side="left")
        if self.background is None:
            self.recognize_button.configure(state="disabled")
            self.mode_box.configure(state="disabled")

        content = ttk.Frame(self.window, padding=px((12, 0, 12, 8)))
        content.grid(row=2, column=0, sticky="nsew")
        content.columnconfigure(0, weight=1)
        content.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(content, bg="#E8EDF5", highlightthickness=px(0))
        self.canvas.grid(row=0, column=0, sticky="nsew", padx=px((0, 10)))
        self.canvas.bind("<Configure>", lambda event: self.draw())
        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.motion)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.canvas.bind("<MouseWheel>", self.wheel)
        self.canvas.bind("<ButtonPress-3>", self.pan_start)
        self.canvas.bind("<B3-Motion>", self.pan_motion)
        side = ttk.Frame(content, width=px(286))
        side.grid(row=0, column=1, sticky="ns")
        side.grid_propagate(False)
        side.rowconfigure(0, weight=1)
        side.columnconfigure(0, weight=1)
        self.tabs = ttk.Notebook(side)
        self.tabs.grid(row=0, column=0, sticky="nsew")
        self.property_tab = ttk.Frame(self.tabs, style="Card.TFrame", padding=px(12))
        self.list_tab = ttk.Frame(self.tabs, style="Card.TFrame", padding=px(8))
        self.settings_tab = ttk.Frame(self.tabs, style="Card.TFrame", padding=px(12))
        for tab, title in ((self.property_tab, "属性"), (self.list_tab, "组件"), (self.settings_tab, "地图")):
            self.tabs.add(tab, text=title)
        self.property_body, self.property_scroll = self.scrollable(self.property_tab)
        self.settings_body, self.settings_scroll = self.scrollable(self.settings_tab)
        parent = self.property_body
        ttk.Label(parent, textvariable=self.selected_text, style="Section.TLabel", wraplength=px(235)).pack(anchor="w", pady=px((0, 8)))
        self.property_fields = ttk.Frame(parent, style="Card.TFrame")
        self.property_fields.pack(fill="x")
        ttk.Button(parent, text="应用属性修改", style="Primary.TButton", command=self.apply_properties).pack(fill="x", pady=px((10, 8)))
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill="x")
        ttk.Button(row, text="复制组件", command=self.duplicate).pack(side="left", fill="x", expand=True, padx=px((0, 4)))
        ttk.Button(row, text="删除组件", command=self.delete).pack(side="left", fill="x", expand=True)
        self.convert_button = ttk.Button(parent, text="将选中地物转为建筑", command=self.convert_feature)
        self.convert_button.pack(fill="x", pady=px((8, 0)))
        ttk.Separator(parent).pack(fill="x", pady=px(12))
        ttk.Label(parent, text="楼高不会由图片推算", style="Card.TLabel", font=(FONT, 10, "bold")).pack(anchor="w")
        ttk.Label(parent, text="橙色建筑表示楼高待填写。\n可在“地图”页一次填写全部楼高，\n再逐栋修改不同高度。\n\n拖动组件移动位置；选中建筑或\n人群区后拖动右下角控制点缩放。\n滚轮缩放，按住鼠标右键平移。", style="Muted.TLabel", justify="left", wraplength=px(235)).pack(anchor="w", pady=px((7, 0)))

        self.list_tab.rowconfigure(0, weight=1)
        self.list_tab.columnconfigure(0, weight=1)
        self.tree = ttk.Treeview(self.list_tab, columns=("type", "name", "height"), show="headings", selectmode="browse")
        for key, title, width in (("type", "类型", 52), ("name", "名称", 115), ("height", "楼高", 58)):
            self.tree.heading(key, text=title)
            self.tree.column(key, width=px(width), minwidth=px(40), stretch=key == "name")
        self.tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(self.list_tab, orient="vertical", command=self.tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.tag_configure("pending", foreground="#BA761B")
        self.tree.bind("<<TreeviewSelect>>", self.tree_selected)
        self._build_settings()

        footer = ttk.Frame(self.window, style="Card.TFrame", padding=px((14, 10)))
        footer.grid(row=3, column=0, sticky="ew")
        footer.columnconfigure(0, weight=1)
        self.status_label = ttk.Label(footer, textvariable=self.status, style="Muted.TLabel", justify="left", wraplength=px(690))
        self.status_label.grid(row=0, column=0, sticky="w", padx=px((0, 12)))
        ttk.Button(footer, text="保存地图 JSON", command=self.save).grid(row=0, column=1, padx=px((0, 8)))
        ttk.Button(footer, text="取消", command=self.close).grid(row=0, column=2, padx=px((0, 8)))
        ttk.Button(footer, text="应用并计算", style="Primary.TButton", command=self.apply).grid(row=0, column=3)

    def _build_settings(self):
        parent = self.settings_body
        ttk.Label(parent, text="实际尺度", style="Section.TLabel").pack(anchor="w")
        ttk.Label(parent, text="整张图片对应的实际宽度 / 米", style="Muted.TLabel").pack(anchor="w", pady=px((8, 4)))
        ttk.Entry(parent, textvariable=self.width_var).pack(fill="x")
        self.scale_text = tk.StringVar(self.window)
        ttk.Label(parent, textvariable=self.scale_text, style="Muted.TLabel", wraplength=px(245)).pack(anchor="w", pady=px(5))
        ttk.Button(parent, text="确认宽度并等比定标", command=self.set_width).pack(fill="x")
        ttk.Label(parent, text="也可用顶部“两点定标”：点击两个\n已知位置，再填写它们的实际距离。", style="Muted.TLabel").pack(anchor="w", pady=px(7))
        ttk.Checkbutton(parent, text="显示原始地图底图", variable=self.show_background, command=self.draw).pack(anchor="w", pady=px((0, 10)))
        ttk.Separator(parent).pack(fill="x", pady=px((0, 10)))
        ttk.Label(parent, text="批量填写楼高 / 米", style="Card.TLabel").pack(anchor="w")
        row = ttk.Frame(parent, style="Card.TFrame")
        row.pack(fill="x", pady=px((5, 5)))
        ttk.Entry(row, textvariable=self.batch_height, width=9).pack(side="left", fill="x", expand=True, padx=px((0, 5)))
        ttk.Button(row, text="应用全部", command=self.set_all_heights).pack(side="left")
        ttk.Label(parent, text="会覆盖所有建筑楼高，可撤销。", style="Muted.TLabel").pack(anchor="w")
        ttk.Separator(parent).pack(fill="x", pady=px(10))
        self.setting_vars = {}
        for key, label in (("step", "网格间距 / 米"), ("clearance", "建筑平面间距 / 米"), ("vertical_clearance", "建筑垂直间距 / 米"), ("source", "数据来源说明")):
            ttk.Label(parent, text=label, style="Muted.TLabel").pack(anchor="w", pady=px((3, 2)))
            var = tk.StringVar(self.window, str(self.document.scene.get(key, "")))
            self.setting_vars[key] = var
            ttk.Entry(parent, textvariable=var).pack(fill="x")
        ttk.Button(parent, text="应用地图参数", command=self.set_settings).pack(fill="x", pady=px((9, 0)))

    def scrollable(self, parent):
        canvas = tk.Canvas(parent, background="white", highlightthickness=px(0), width=px(230))
        canvas.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scroll.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=scroll.set)
        body = ttk.Frame(canvas, style="Card.TFrame")
        content = canvas.create_window(0, 0, window=body, anchor="nw")
        body.bind("<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure(content, width=event.width))
        return body, canvas

    def scroll_side(self, event):
        for canvas in (self.property_scroll, self.settings_scroll):
            if (canvas.winfo_viewable() and canvas.winfo_rootx() <= event.x_root < canvas.winfo_rootx()+canvas.winfo_width()
                    and canvas.winfo_rooty() <= event.y_root < canvas.winfo_rooty()+canvas.winfo_height()):
                if canvas.bbox("all") and canvas.bbox("all")[3] > canvas.winfo_height():
                    canvas.yview_scroll(-int(event.delta/120), "units")
                return "break"

    def show(self):
        self.window.grab_set()
        self.window.wait_window()
        return self.result

    def update_status(self, hint=None):
        scene = self.document.scene
        scale = "尺度待确认" if scene.get("image_import", {}).get("scale_confirmed") is False else "尺度已确认"
        counts = {k: sum(f["kind"] == k for f in scene.get("map_features", [])) for k in FEATURE_TYPES}
        features = " · ".join(f"{FEATURE_TYPES[k]} {n}" for k, n in counts.items() if n)
        text = f"建筑 {len(scene['buildings'])}（楼高待填 {len(self.document.pending_heights)}） · {features or '无地物区域'} · {scale}"
        self.status.set(text + "\n" + (hint or "识别结果是可编辑候选；起降点、配送点需结合实际位置核对。"))

    def refresh(self, hint=None):
        self.undo_button.configure(state="normal" if self.document.undo_stack else "disabled")
        self.redo_button.configure(state="normal" if self.document.redo_stack else "disabled")
        self.width_var.set(f"{self.document.scene['width']:.6g}")
        self.scale_text.set(f"地图高 {self.document.scene['height']:.6g} 米；定标不改变手填楼高")
        for key, var in self.setting_vars.items():
            value = self.document.scene.get(key, "")
            var.set(value if key == "source" else f"{value:.6g}")
        selected = self.selected
        if selected and not any(item["id"] == selected[1] for item in self.document.scene[selected[0]]):
            selected = self.selected = None
        self.row_refs = {}
        self.rebuilding_tree = True
        self.tree.delete(*self.tree.get_children())
        for collection, (label, _) in COLLECTIONS.items():
            for i, item in enumerate(self.document.scene[collection]):
                key = f"{collection}:{i}"
                self.row_refs[key] = (collection, item["id"])
                pending = collection == "buildings" and item.get("height_confirmed") is False
                height = ("待填" if pending else f"{item['height']:g}m") if collection == "buildings" else "—"
                item_label = FEATURE_TYPES[item["kind"]] if collection == "map_features" else label
                self.tree.insert("", "end", iid=key, values=(item_label, item["name"], height), tags=("pending",) if pending else ())
                if self.row_refs[key] == selected:
                    self.tree.selection_set(key)
        self.rebuilding_tree = False
        self.fill_properties()
        self.draw()
        self.update_status(hint)

    def fill_properties(self):
        for child in self.property_fields.winfo_children():
            child.destroy()
        self.form_vars, self.form_original = {}, {}
        convertible = self.selected and self.selected[0] in ("map_features", "buildings")
        self.convert_button.configure(state="normal" if convertible else "disabled",
                                      text="转为“新地物”所选类别" if self.selected and self.selected[0] == "buildings" else "将选中地物转为建筑")
        if not self.selected:
            self.selected_text.set("选择地图组件")
            ttk.Label(self.property_fields, text="点击地图上的组件，或切换\n到“组件”页从列表中选择。", style="Muted.TLabel").pack(anchor="w", pady=px(8))
            return
        collection, identity = self.selected
        item = self.document.item(collection, identity)
        self.selected_text.set(f"{COLLECTIONS[collection][0]} · {identity}")
        if collection == "map_features":
            value = FEATURE_TYPES[item["kind"]]
            var = tk.StringVar(self.window, value)
            self.form_vars["kind"], self.form_original["kind"] = var, value
            ttk.Label(self.property_fields, text="地物类型", style="Muted.TLabel").pack(anchor="w")
            ttk.Combobox(self.property_fields, textvariable=var, values=list(FEATURE_TYPES.values()), state="readonly").pack(fill="x")
        for key in ("name", *FIELDS[collection]):
            value = item.get(key, "")
            value = str(value) if key == "name" else "" if key == "height" and item.get("height_confirmed") is False else f"{value:.9g}"
            var = tk.StringVar(self.window, value)
            self.form_vars[key] = var
            self.form_original[key] = value
            ttk.Label(self.property_fields, text=LABELS[key], style="Muted.TLabel").pack(anchor="w", pady=px((5, 2)))
            entry = ttk.Entry(self.property_fields, textvariable=var)
            entry.pack(fill="x")
            entry.bind("<Return>", lambda event: self.apply_properties())
        if collection == "pads" and "facility_planning" in self.document.scene:
            from facility_schema import facility_inputs
            levels = facility_inputs(self.document.scene)["levels"]
            for key, label, value in (("allowed_levels", "允许等级编号（逗号分隔，空白禁用）", ",".join(item.get("allowed_levels", [v["id"] for v in levels]))),
                                      ("site_cost", "场地附加成本（相对单位）", str(item.get("site_cost", 0)))):
                var = tk.StringVar(self.window, value)
                self.form_vars[key], self.form_original[key] = var, value
                ttk.Label(self.property_fields, text=label, style="Muted.TLabel", wraplength=px(225)).pack(anchor="w", pady=px((5, 2)))
                ttk.Entry(self.property_fields, textvariable=var).pack(fill="x")

    def commit_form(self):
        if self.selected:
            changes = {key: var.get() for key, var in self.form_vars.items() if var.get() != self.form_original[key]}
            if changes:
                if "kind" in changes:
                    changes["kind"] = next(k for k, v in FEATURE_TYPES.items() if v == changes["kind"])
                self.document.update(*self.selected, changes)
                self.form_original.update({key: var.get() for key, var in self.form_vars.items()})

    def select(self, reference, switch_tab=False):
        if reference != self.selected:
            try:
                self.commit_form()
            except ValueError as error:
                messagebox.showerror("属性未应用", str(error), parent=self.window)
                return False
            self.selected = reference
            if reference:
                collection, identity = reference
                item = next(i for i in self.document.scene[collection] if i["id"] == identity)
                key = item["kind"] if collection == "map_features" else collection
                if key in self.layers:
                    self.layers[key].set(True)
            self.refresh()
        if switch_tab:
            self.tabs.select(self.property_tab)
        return True

    def tree_selected(self, event=None):
        if getattr(self, "rebuilding_tree", False):
            return
        selection = self.tree.selection()
        if selection:
            self.select(self.row_refs.get(selection[0]))

    def apply_properties(self):
        try:
            self.commit_form()
            self.refresh("组件属性已更新。")
        except ValueError as error:
            messagebox.showerror("属性未应用", str(error), parent=self.window)

    def set_tool(self, tool):
        self.tool.set(tool)
        if tool in self.layers:
            self.layers[tool].set(True)
        self.drag = None
        self.calibration_points = []
        self.canvas.configure(cursor="arrow" if tool == "select" else "crosshair")
        self.update_status({"select": "拖动移动；右下角控制点调整尺寸；Delete删除。", "buildings": "按住左键拖出建筑矩形，之后手动填写楼高。",
                            "pads": "在空地点击放置候选起降场。", "deliveries": "点击放置配送点，需求权重可在属性修改。",
                            "risk_zones": "按住左键拖出人群区域，其范围和强度可编辑。", "color": "点击建筑填充色，再点击“重新识别全部”；地物仍按地图配色提取。",
                            "map_features": "选择“新地物”类型，拖出区域；识别区域可在属性页修改类别。",
                            "vertices": "先选择建筑或地物，再拖动轮廓上的方形顶点；支持撤销。",
                            "calibrate": "依次点击两个位置，再输入它们之间的真实距离。"}[tool])
        self.draw()

    def world(self, x, y, clamp=True):
        scale, ox, oy = self.transform
        x, y = (x - ox) / scale, (y - oy) / scale
        if clamp:
            x = max(0., min(self.document.scene["width"], x))
            y = max(0., min(self.document.scene["height"], y))
        return x, y

    def press(self, event):
        self.canvas.focus_set()
        x, y = self.world(event.x, event.y, False)
        scene = self.document.scene
        if not 0 <= x <= scene["width"] or not 0 <= y <= scene["height"]:
            return
        tool = self.tool.get()
        try:
            self.commit_form()
            if tool == "color":
                if self.background is None:
                    self.update_status("当前地图没有图片底图，请先导入图片。")
                    return
                self.picked_color = self.background.getpixel((min(self.background.width-1, int(x/scene["width"]*self.background.width)), min(self.background.height-1, int(y/scene["height"]*self.background.height))))
                self.mode.set("取色识别")
                self.color_text.set("RGB " + ", ".join(map(str, self.picked_color)))
                self.update_status("已选中建筑颜色，点击“重新识别全部”生成组件。")
            elif tool == "calibrate":
                self.calibration_points.append((x, y))
                if len(self.calibration_points) == 2:
                    distance = math.dist(*self.calibration_points)
                    if distance < 1e-6:
                        raise ValueError("定标的两个位置不能重合")
                    actual = simpledialog.askfloat("两点定标", "这两个位置的实际距离是多少米？", minvalue=.01, parent=self.window)
                    if actual is not None:
                        self.document.set_width(scene["width"] * actual / distance)
                        self.fit()
                        self.refresh("尺度已按两点距离校准；手填楼高保持原数值。")
                    self.set_tool("select")
                self.draw()
            elif tool in ("pads", "deliveries"):
                identity = self.document.add(tool, {"x": x, "y": y})
                self.selected = (tool, identity)
                self.refresh()
                self.tabs.select(self.property_tab)
            elif tool in ("buildings", "risk_zones", "map_features"):
                self.drag = {"kind": "draw", "collection": tool, "start": (x, y), "end": (x, y)}
            else:
                hits = self.canvas.find_overlapping(event.x-px(3), event.y-px(3), event.x+px(3), event.y+px(3))
                handle = any("resize" in self.canvas.gettags(hit) for hit in hits)
                vertex = next((int(tag.split(":")[1]) for hit in hits for tag in self.canvas.gettags(hit) if tag.startswith("vertex:")), None)
                reference = next((self.item_refs[hit] for hit in reversed(hits) if hit in self.item_refs), None)
                if reference and reference[0] in ("buildings", "map_features") and not handle and vertex is None:
                    if not contains(self.document.item(*reference), (x, y), 3/self.transform[0]):
                        reference = None
                if reference is None and not handle and vertex is None:
                    reference = next(((c, i["id"]) for c in ("buildings", "map_features")
                                      for i in reversed(scene[c]) if self.visible(c, i) and contains(i, (x, y))), None)
                if vertex is not None and self.selected:
                    self.drag = {"kind": "vertex", "reference": self.selected, "vertex": vertex,
                                 "start": (x, y), "original": deepcopy(self.document.item(*self.selected))}
                    return
                if handle and self.selected:
                    reference = self.selected
                if self.select(reference, True) and reference:
                    self.drag = {"kind": "resize" if handle else "move", "reference": reference, "start": (x, y), "original": deepcopy(self.document.item(*reference))}
        except ValueError as error:
            self.calibration_points = []
            messagebox.showerror("操作未完成", str(error), parent=self.window)

    def motion(self, event):
        if not self.drag:
            return
        x, y = self.world(event.x, event.y)
        if self.drag["kind"] == "draw":
            self.drag["end"] = (x, y)
        else:
            collection, _ = self.drag["reference"]
            original = self.drag["original"]
            item = deepcopy(original)
            scene = self.document.scene
            if self.drag["kind"] == "move":
                dx, dy = x-self.drag["start"][0], y-self.drag["start"][1]
                item["x"] = min(scene["width"]-(item["w"] if collection in ("buildings", "map_features") else 0), max(0., original["x"]+dx))
                item["y"] = min(scene["height"]-(item["h"] if collection in ("buildings", "map_features") else 0), max(0., original["y"]+dy))
            elif self.drag["kind"] == "vertex":
                item["polygon"][self.drag["vertex"]] = [x, y]
                xs, ys = zip(*item["polygon"])
                item.update(x=min(xs), y=min(ys), w=max(xs)-min(xs), h=max(ys)-min(ys))
            elif collection in ("buildings", "map_features"):
                item["w"] = min(scene["width"]-item["x"], max(.1, x-item["x"]))
                item["h"] = min(scene["height"]-item["y"], max(.1, y-item["y"]))
            elif collection == "risk_zones":
                item["rx"], item["ry"] = max(.1, abs(x-item["x"])), max(.1, abs(y-item["y"]))
            self.drag["preview"] = (transform_shape(original, {k: item[k] for k in ("x", "y", "w", "h")})
                                    if collection in ("buildings", "map_features") and self.drag["kind"] != "vertex" else item)
        self.draw()

    def release(self, event):
        if not self.drag:
            return
        self.motion(event)
        drag, self.drag = self.drag, None
        try:
            if drag["kind"] == "draw":
                x1, x2 = sorted((drag["start"][0], drag["end"][0]))
                y1, y2 = sorted((drag["start"][1], drag["end"][1]))
                if min(x2-x1, y2-y1)*self.transform[0] >= px(4):
                    collection = drag["collection"]
                    values = {"x": x1, "y": y1, "w": x2-x1, "h": y2-y1} if collection in ("buildings", "map_features") else {"x": (x1+x2)/2, "y": (y1+y2)/2, "rx": (x2-x1)/2, "ry": (y2-y1)/2, "weight": .5}
                    if collection == "map_features":
                        values["kind"] = next(k for k, v in FEATURE_TYPES.items() if v == self.feature_kind.get())
                    identity = self.document.add(collection, values)
                    self.selected = (collection, identity)
                    self.tabs.select(self.property_tab)
            elif "preview" in drag:
                collection, identity = drag["reference"]
                if drag["kind"] == "vertex":
                    self.document.set_polygon(collection, identity, drag["preview"]["polygon"])
                else:
                    keys = ("x", "y") if drag["kind"] == "move" else ("w", "h") if collection in ("buildings", "map_features") else ("rx", "ry")
                    self.document.update(collection, identity, {key: drag["preview"][key] for key in keys})
            self.refresh()
        except ValueError as error:
            self.refresh()
            messagebox.showerror("组件未修改", str(error), parent=self.window)

    def visible(self, collection, item):
        key = item["kind"] if collection == "map_features" else collection
        return key not in self.layers or self.layers[key].get()

    def draw(self):
        if not hasattr(self, "canvas"):
            return
        canvas = self.canvas
        canvas.delete("all")
        self.item_refs = {}
        scene = self.document.scene
        cw, ch = max(px(50), canvas.winfo_width()), max(px(50), canvas.winfo_height())
        scale = max(.0001, min((cw-px(40))/scene["width"], (ch-px(40))/scene["height"])) * self.zoom
        ox, oy = (cw-scene["width"]*scale)/2+self.pan[0], (ch-scene["height"]*scale)/2+self.pan[1]
        self.transform = scale, ox, oy
        canvas.create_rectangle(ox, oy, ox+scene["width"]*scale, oy+scene["height"]*scale, fill="white", outline="#BCCBDD")
        if self.background is not None and self.show_background.get():
            from PIL import Image, ImageTk
            # Resample only the visible part. Capping the full image size would
            # shift the background relative to editable objects at high zoom.
            image_w, image_h = scene["width"]*scale, scene["height"]*scale
            left, top = max(0, math.ceil(ox)), max(0, math.ceil(oy))
            right, bottom = min(cw, math.floor(ox+image_w)), min(ch, math.floor(oy+image_h))
            cache = (left, top, right, bottom, ox, oy, image_w, image_h)
            if right > left and bottom > top:
                if self.bg_cache != cache:
                    box = ((left-ox)/image_w*self.background.width, (top-oy)/image_h*self.background.height,
                           (right-ox)/image_w*self.background.width, (bottom-oy)/image_h*self.background.height)
                    self.photo = ImageTk.PhotoImage(self.background.resize((right-left, bottom-top), Image.Resampling.LANCZOS, box=box), master=self.window)
                    self.bg_cache = cache
                canvas.create_image(left, top, anchor="nw", image=self.photo)
        for collection in ("map_features", "risk_zones", "buildings", "pads", "deliveries"):
            for original in scene[collection]:
                if not self.visible(collection, original):
                    continue
                reference = (collection, original["id"])
                item = self.drag["preview"] if self.drag and self.drag.get("reference") == reference and "preview" in self.drag else original
                x, y = ox+item["x"]*scale, oy+item["y"]*scale
                selected = reference == self.selected
                color = BLUE if selected else FEATURE_COLORS[item["kind"]] if collection == "map_features" else COLORS[collection]
                pending = collection == "buildings" and item.get("height_confirmed") is False
                options = {"outline": "#AE6B10" if pending and not selected else color, "width": px(2.5 if selected else 1.4)}
                if collection in ("buildings", "map_features"):
                    x2, y2 = x+item["w"]*scale, y+item["h"]*scale
                    fill = "" if self.background is not None and self.show_background.get() else (color if collection == "map_features" else "#F7DC9E" if pending else "#CDDEED")
                    if item.get("polygon"):
                        shapes = canvas_polygon(canvas, item, scale, ox, oy, fill=fill, **options)
                        shape = shapes[0]
                        self.item_refs.update({part: reference for part in shapes})
                    else:
                        shape = canvas.create_rectangle(x, y, x2, y2, fill=fill, **options)
                    label = (f"{item['name']}\n{'楼高待填' if pending else str(round(item['height'], 2))+' m'}"
                             if collection == "buildings" else item["name"])
                    label_x, label_y = (x+x2)/2, (y+y2)/2
                elif collection == "risk_zones":
                    rx, ry = item["rx"]*scale, item["ry"]*scale
                    shape = canvas.create_oval(x-rx, y-ry, x+rx, y+ry, fill="#F0C3B7", stipple="gray25", **options)
                    x2, y2 = x+rx, y+ry
                    label, label_x, label_y = item["name"], x, y
                elif collection == "pads":
                    shape = canvas.create_oval(x-px(7), y-px(7), x+px(7), y+px(7), fill="white", **options)
                    label, label_x, label_y = item["id"], x+px(15), y
                else:
                    shape = canvas.create_polygon(x, y-px(7), x+px(7), y, x, y+px(7), x-px(7), y, fill="#FFDE9D", **options)
                    label, label_x, label_y = item["id"], x+px(15), y
                self.item_refs[shape] = reference
                full_label = collection not in ("buildings", "map_features") or selected or item["w"]*scale >= px(60) and item["h"]*scale >= px(38)
                if not full_label:
                    label = item["id"]
                if (self.show_labels.get() or selected or collection in ("pads", "deliveries")) and (full_label or item["w"]*scale >= px(20) and item["h"]*scale >= px(20)):
                    text = canvas.create_text(label_x, label_y, text=label, fill=INK, font=(FONT, 9), justify="center")
                    self.item_refs[text] = reference
                    if collection == "buildings":
                        bounds = canvas.bbox(text)
                        plate = canvas.create_rectangle(bounds[0]-px(2), bounds[1]-px(1), bounds[2]+px(2), bounds[3]+px(1), fill="#FFFFFF", outline="")
                        canvas.tag_lower(plate, text)
                        self.item_refs[plate] = reference
                if selected and collection in ("buildings", "risk_zones", "map_features") and self.tool.get() != "vertices":
                    canvas.create_rectangle(x2-px(5), y2-px(5), x2+px(5), y2+px(5), fill=BLUE, outline="white", width=px(1), tags="resize")
                if selected and self.tool.get() == "vertices" and item.get("polygon"):
                    for i, (a, b) in enumerate(item["polygon"]):
                        vx, vy = ox+a*scale, oy+b*scale
                        canvas.create_rectangle(vx-px(3), vy-px(3), vx+px(3), vy+px(3), fill="white", outline=BLUE, tags=(f"vertex:{i}",))
        if self.drag and self.drag["kind"] == "draw":
            a, b = self.drag["start"], self.drag["end"]
            canvas.create_rectangle(ox+a[0]*scale, oy+a[1]*scale, ox+b[0]*scale, oy+b[1]*scale, outline=BLUE, dash=(5, 3), width=px(2))
        for x, y in self.calibration_points:
            canvas.create_oval(ox+x*scale-px(5), oy+y*scale-px(5), ox+x*scale+px(5), oy+y*scale+px(5), fill="#E6694C", outline="white")
        unit = "相对单位，待定标" if scene.get("image_import", {}).get("scale_confirmed") is False else "米"
        canvas.create_text(px(12), px(12), anchor="nw", text=f"{scene['width']:.5g} × {scene['height']:.5g} {unit}  /  缩放 {self.zoom:.1f}×", fill=INK, font=(FONT, 10))

    def fit(self):
        self.zoom, self.pan, self.bg_cache = 1., (0., 0.), None
        self.draw()

    def wheel(self, event):
        if self.drag:
            return
        self.zoom = min(4., max(.5, self.zoom * (1.15 if event.delta > 0 else 1/1.15)))
        self.draw()
        return "break"

    def pan_start(self, event):
        self.pan_anchor = (event.x, event.y, *self.pan)

    def pan_motion(self, event):
        if hasattr(self, "pan_anchor"):
            x, y, px, py = self.pan_anchor
            self.pan = px+event.x-x, py+event.y-y
            self.draw()

    def history(self, redo=False):
        self.drag = None
        (self.document.redo if redo else self.document.undo)()
        self.refresh("已重做。" if redo else "已撤销。")
        return "break"

    def delete_key(self, event):
        if isinstance(self.window.focus_get(), (tk.Entry, ttk.Entry, tk.Text, ttk.Spinbox, ttk.Combobox)):
            return
        self.delete()
        return "break"

    def delete(self):
        if self.selected:
            self.document.delete(*self.selected)
            self.selected = None
            self.refresh("组件已删除，可撤销。")

    def duplicate(self):
        if not self.selected:
            return
        try:
            self.commit_form()
            collection, identity = self.selected
            self.selected = (collection, self.document.duplicate(collection, identity))
            self.refresh("组件已复制。")
        except ValueError as error:
            messagebox.showerror("无法复制", str(error), parent=self.window)

    def set_width(self):
        try:
            self.commit_form()
            self.document.set_width(self.width_var.get())
            self.fit()
            self.refresh("尺度已确认，所有平面组件等比调整，楼高不变。")
        except ValueError as error:
            messagebox.showerror("定标未完成", str(error), parent=self.window)

    def set_all_heights(self):
        try:
            self.commit_form()
            self.document.set_heights(self.batch_height.get())
            self.refresh("已按手动输入的数值设置全部楼高，可逐栋修改。")
        except ValueError as error:
            messagebox.showerror("楼高未修改", str(error), parent=self.window)

    def set_settings(self):
        try:
            self.commit_form()
            self.document.settings({key: var.get() for key, var in self.setting_vars.items()})
            self.refresh("地图参数已更新。")
        except ValueError as error:
            messagebox.showerror("参数未修改", str(error), parent=self.window)

    def convert_feature(self):
        if not self.selected:
            return
        try:
            self.commit_form()
            collection, identity = self.selected
            if collection == "map_features":
                identity = self.document.convert_feature_to_building(identity)
                self.selected = ("buildings", identity)
            elif collection == "buildings":
                kind = next(k for k, v in FEATURE_TYPES.items() if v == self.feature_kind.get())
                identity = self.document.convert_building_to_feature(identity, kind)
                self.selected = ("map_features", identity)
            self.refresh("类别已转换，轮廓保留；转为建筑后须填写楼高。")
        except ValueError as error:
            messagebox.showerror("类别未修改", str(error), parent=self.window)

    def recognize(self):
        if self.background is None:
            return
        try:
            self.commit_form()
            if (self.document.undo_stack or any(b.get("height_confirmed") for b in self.document.scene["buildings"])) and not messagebox.askyesno("重新识别", "将替换全部建筑和地物区域，楼高需重新填写。起降场、配送点和人群区保留；本操作可撤销。继续？", parent=self.window):
                return
            from image_map import MODES, recognize_map
            self.window.configure(cursor="watch")
            self.status.set("正在识别建筑、道路、水体、绿地和运动场……")
            self.window.update_idletasks()
            buildings, features, metadata = recognize_map(self.background, self.document.scene["width"], MODES[self.mode.get()], self.picked_color, self.tolerance.get(), self.min_area.get())
            self.document.replace_recognition(buildings, features, metadata)
            self.selected = None
            self.refresh(f"已生成{len(buildings)}个建筑候选、{len(features)}个地物区域；可分层查看、改类别或拖动顶点，楼高需核实。")
        except ValueError as error:
            messagebox.showerror("识别未完成", str(error), parent=self.window)
            self.update_status()
        finally:
            self.window.configure(cursor="")

    def save(self):
        try:
            self.commit_form()
            destination = filedialog.asksaveasfilename(parent=self.window, title="保存可编辑地图（可保留楼高未填的草稿）", initialfile=(self.saved_path.name if self.saved_path else "我的图片地图.json"), defaultextension=".json", filetypes=(("可编辑地图 JSON", "*.json"),))
            if destination:
                self.document.save(destination)
                self.saved_path = Path(destination)
                self.baseline = deepcopy(self.document.scene)
                self.refresh("已保存地图，包含原始底图与全部可编辑组件。")
        except (ValueError, OSError) as error:
            messagebox.showerror("地图未保存", str(error), parent=self.window)

    def apply(self):
        try:
            self.commit_form()
            scene = self.document.ready_scene(self.config)
        except ValueError as error:
            messagebox.showerror("地图尚未就绪", str(error), parent=self.window)
            self.refresh()
            return
        self.result = scene
        self.window.destroy()

    def close(self):
        changes = self.document.scene != self.baseline or any(var.get() != self.form_original.get(key) for key, var in self.form_vars.items())
        if changes and not messagebox.askyesno("关闭编辑器", "本次修改尚未保存或应用，确定放弃？", parent=self.window):
            return
        self.window.destroy()
