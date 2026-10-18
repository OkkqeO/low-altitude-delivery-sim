"""Graded-facility workbench, hosted by the existing desktop application."""
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
import queue
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from display import px, window_geometry
from engine import Config, ROOT, create_scene
from facility import (FACILITY_NAMES, PlanningCancelled, configuration_label,
                      export_facility_study, run_facility_study)
from facility_schema import facility_inputs
from map_document import MapDocument


class FacilityWindow:
    WINDOW_TITLE = "分级起降场 · 选址与容量配置"
    HEADING = "分级起降场选址与容量配置"
    INTRO = "固定两个场站、总机队和预算上限；同一设施配置同时检验正常与高峰。单站1个起降服务位。"
    SETTINGS_TITLE = "地图、预算与等级"
    COMPUTE_TEXT = "计算分级选址与容量"
    def __init__(self, app):
        self.app = app
        self.window = tk.Toplevel(app.root)
        self.window.title(self.WINDOW_TITLE)
        self.window.geometry(window_geometry(self.window, 1230, 850))
        self.window.minsize(px(1000), px(680))
        self.window.protocol("WM_DELETE_WINDOW", self.close)
        self.config = replace(app.get_config(), deconflict=True)
        from flight_map import schematic_scene
        self.scene = schematic_scene(create_scene(self.config, app.scene_data if app.scene_data is not None else app.scene_path))
        self.closed, self.busy, self.dirty = False, False, True
        self.study = None
        self.messages = queue.Queue()
        self.cancel_event = threading.Event()
        self.controls = []
        self.vars, self.level_vars = {}, []
        self.status = tk.StringVar(self.window, "设置预算和等级，计算同一设施在正常与高峰下的运行结果。")
        self.scene_name = tk.StringVar(self.window)
        self.source = tk.StringVar(self.window)
        self.selected_pad = None
        self.filling_pad = False
        self.building = True
        self._build()
        self._load_scene(self.scene)
        self.building = False
        self.poll_id = self.window.after(100, self._poll)

    def _entry(self, parent, label, key, value, row, column=0):
        ttk.Label(parent, text=label).grid(row=row, column=column*2, sticky="w", padx=px(7), pady=px(5))
        var = tk.StringVar(self.window, str(value))
        self.vars[key] = var
        widget = ttk.Entry(parent, textvariable=var, width=17)
        widget.grid(row=row, column=column*2+1, sticky="ew", padx=px(7), pady=px(5))
        self.controls.append((widget, "normal"))
        var.trace_add("write", self._dirty)
        return widget

    def _button(self, parent, text, command):
        button = ttk.Button(parent, text=text, command=command)
        self.controls.append((button, "normal"))
        return button

    def _build(self):
        outer = ttk.Frame(self.window, padding=px(14))
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text=self.HEADING, font=("Microsoft YaHei UI", 17, "bold")).pack(anchor="w")
        ttk.Label(outer, text=self.INTRO, wraplength=px(1100)).pack(anchor="w", pady=px((4, 10)))
        bottom = ttk.Frame(outer)
        bottom.pack(side="bottom", fill="x", pady=px((10, 0)))
        self.compute_button = ttk.Button(bottom, text=self.COMPUTE_TEXT, style="Primary.TButton", command=self.calculate)
        self.compute_button.pack(side="left")
        self.cancel_button = ttk.Button(bottom, text="取消计算", command=self.cancel, state="disabled")
        self.cancel_button.pack(side="left", padx=px(8))
        self.export_button = ttk.Button(bottom, text="导出完整研究结果", command=self.export, state="disabled")
        self.export_button.pack(side="right")
        self.progressbar = ttk.Progressbar(outer, maximum=100)
        self.progressbar.pack(side="bottom", fill="x", pady=px((8, 0)))
        ttk.Label(outer, textvariable=self.status, wraplength=px(1100)).pack(side="bottom", fill="x", pady=px((8, 0)))
        self.tabs = ttk.Notebook(outer)
        self.tabs.pack(fill="both", expand=True)
        self.settings_page = ttk.Frame(self.tabs, padding=px(10))
        self.sites_page = ttk.Frame(self.tabs, padding=px(10))
        self.results_page = ttk.Frame(self.tabs, padding=px(10))
        self.tabs.add(self.settings_page, text=self.SETTINGS_TITLE)
        self.tabs.add(self.sites_page, text="候选场地")
        self.tabs.add(self.results_page, text="正常 / 高峰对照")
        self._build_settings()
        self._build_results()

    def _build_settings(self):
        settings_canvas = tk.Canvas(self.settings_page, highlightthickness=0, borderwidth=0)
        settings_scroll = ttk.Scrollbar(self.settings_page, orient="vertical", command=settings_canvas.yview)
        settings_scroll.pack(side="right", fill="y")
        settings_canvas.pack(side="left", fill="both", expand=True)
        settings_canvas.configure(yscrollcommand=settings_scroll.set)
        settings_body = ttk.Frame(settings_canvas)
        settings_item = settings_canvas.create_window((0, 0), window=settings_body, anchor="nw")
        settings_body.bind("<Configure>", lambda _: settings_canvas.configure(scrollregion=settings_canvas.bbox("all")))
        settings_canvas.bind("<Configure>", lambda event: settings_canvas.itemconfigure(settings_item, width=event.width))
        self.settings_canvas = settings_canvas
        top = ttk.Frame(settings_body)
        top.pack(fill="x")
        ttk.Label(top, textvariable=self.scene_name).pack(side="left", fill="x", expand=True)
        self._button(top, "加载Excel / JSON", self.import_scene).pack(side="right", padx=px(4))
        self._button(top, "保存场景JSON", self.save_scene).pack(side="right", padx=px(4))
        self._button(top, "获取分级Excel模板", self.save_template).pack(side="right", padx=px(4))
        params = ttk.LabelFrame(settings_body, text="预算与运行参数", padding=px(6))
        params.pack(fill="x", pady=px(8))
        c = self.config
        fields = [("预算（相对单位）", "budget", 260), ("无人机总数", "drone_count", c.drone_count),
                  ("基础订单量（高峰翻倍）", "order_count", c.order_count), ("巡航高度 / 米", "altitude", c.altitude),
                  ("航路风险权重", "risk_weight", c.risk_weight), ("间距阈值 / 米", "separation", c.separation),
                  ("设计种子", "design_seed", self.app.design_seed), ("评价种子（逗号分隔）", "seeds", ",".join(str((c.seed+i) % 2**32) for i in range(5))),
                  ("设计种子数（1—5）", "design_seed_count", 3)]
        for i, (label, key, value) in enumerate(fields):
            self._entry(params, label, key, value, i//2, i%2)
        params.columnconfigure(1, weight=1)
        params.columnconfigure(3, weight=1)
        self.level_frame = ttk.LabelFrame(settings_body, text="等级参数（相对成本；时间为秒）", padding=px(6))
        self.level_frame.pack(fill="x")
        self.source.trace_add("write", self._dirty)
        source_line = ttk.Frame(settings_body)
        source_line.pack(fill="x", pady=px(7))
        ttk.Label(source_line, text="参数来源 / 假设：").pack(side="left")
        source_entry = ttk.Entry(source_line, textvariable=self.source)
        source_entry.pack(fill="x", expand=True)
        self.source_entry = source_entry
        self.controls.append((source_entry, "normal"))
        ttk.Label(self.sites_page, textvariable=self.scene_name).pack(anchor="w", pady=px((0, 8)))
        ttk.Label(self.sites_page, text="允许等级使用编号，如standard,enhanced；留空禁用该候选点。场地附加成本会计入所选设施总成本。", wraplength=px(1050)).pack(anchor="w", pady=px((0, 8)))
        pad_frame = ttk.LabelFrame(self.sites_page, text="候选场地（选中一行编辑，修改后点击应用）", padding=px(6))
        pad_frame.pack(fill="both", expand=True)
        pad_frame.columnconfigure(0, weight=1)
        pad_frame.rowconfigure(0, weight=1)
        self.pad_table = ttk.Treeview(pad_frame, columns=("id", "name", "allowed", "cost"), show="headings", height=4)
        for key, label, width in (("id", "编号", 65), ("name", "场地名称", 180), ("allowed", "允许等级编号", 300), ("cost", "场地附加成本", 110)):
            self.pad_table.heading(key, text=label)
            self.pad_table.column(key, width=px(width), minwidth=px(60))
        self.pad_table.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(pad_frame, orient="vertical", command=self.pad_table.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.pad_table.configure(yscrollcommand=scroll.set)
        self.pad_table.bind("<<TreeviewSelect>>", self._select_pad)
        form = ttk.Frame(pad_frame)
        form.grid(row=1, column=0, columnspan=2, sticky="ew", pady=px((5, 0)))
        self.pad_allowed = tk.StringVar(self.window)
        self.pad_cost = tk.StringVar(self.window, "0")
        self.pad_allowed.trace_add("write", self._dirty)
        self.pad_cost.trace_add("write", self._dirty)
        for label, var, width in (("允许等级：", self.pad_allowed, 30), ("附加成本：", self.pad_cost, 10)):
            ttk.Label(form, text=label).pack(side="left")
            entry = ttk.Entry(form, textvariable=var, width=width)
            entry.pack(side="left", padx=px((0, 7)))
            self.controls.append((entry, "normal"))
        self._button(form, "应用场地设置", self.apply_pad).pack(side="left")

    def _load_scene(self, scene):
        inputs = facility_inputs(scene)
        self.scene = deepcopy(scene)
        self.scene["facility_planning"] = inputs
        self.vars["budget"].set(str(inputs["budget"]))
        self.source.set(inputs["parameter_source"])
        self.scene_name.set(f"{len(scene['pads'])}个候选场站 / {len(scene['deliveries'])}个配送点 / {scene['width']:g}×{scene['height']:g}米")
        for child in self.level_frame.winfo_children():
            self.controls = [(w, s) for w, s in self.controls if w != child]
            child.destroy()
        self.level_vars = []
        headers = ("id", "name", "cost", "max_drones", "takeoff_service", "landing_service")
        for col, label in enumerate(("等级编号", "等级名称", "建设成本", "驻机上限", "起飞服务秒数", "降落服务秒数")):
            ttk.Label(self.level_frame, text=label).grid(row=0, column=col, sticky="w", padx=px(4))
            self.level_frame.columnconfigure(col, weight=1)
        for row, level in enumerate(inputs["levels"], 1):
            values = {}
            for col, key in enumerate(headers):
                var = tk.StringVar(self.window, str(level[key]))
                values[key] = var
                state = "readonly" if key == "id" else "normal"
                entry = ttk.Entry(self.level_frame, textvariable=var, width=14, state=state)
                entry.grid(row=row, column=col, sticky="ew", padx=px(4), pady=px(3))
                self.controls.append((entry, state))
                var.trace_add("write", self._dirty)
            self.level_vars.append(values)
        self.selected_pad = None
        self._refresh_pads()
        self._dirty()

    def _refresh_pads(self):
        self.pad_table.delete(*self.pad_table.get_children())
        default_ids = [v["id"] for v in self.scene["facility_planning"]["levels"]]
        for p in self.scene["pads"]:
            self.pad_table.insert("", "end", iid=p["id"], values=(p["id"], p["name"], ",".join(p.get("allowed_levels", default_ids)), p.get("site_cost", 0)))
        if self.selected_pad and self.pad_table.exists(self.selected_pad):
            self.pad_table.selection_set(self.selected_pad)

    def _select_pad(self, event=None):
        if self.busy:
            return
        selected = self.pad_table.selection()
        if not selected:
            return
        self.selected_pad = selected[0]
        p = next(p for p in self.scene["pads"] if p["id"] == self.selected_pad)
        self.filling_pad = True
        self.pad_allowed.set(",".join(p.get("allowed_levels", [v["id"] for v in self.scene["facility_planning"]["levels"]])))
        self.pad_cost.set(str(p.get("site_cost", 0)))
        self.filling_pad = False

    def apply_pad(self):
        if not self.selected_pad:
            return True
        try:
            candidate = self._scene_from_form()
            document = MapDocument(candidate)
            document.update("pads", self.selected_pad, {"allowed_levels": self.pad_allowed.get(), "site_cost": self.pad_cost.get()})
            changed = document.scene != self.scene
            self.scene = document.scene
            self._refresh_pads()
            if changed:
                self._dirty()
            return True
        except ValueError as error:
            messagebox.showerror("场地设置无效", str(error), parent=self.window)
            return False

    def _scene_from_form(self):
        scene = deepcopy(self.scene)
        levels = []
        for values in self.level_vars:
            level = {k: v.get().strip() for k, v in values.items()}
            for field in ("cost", "takeoff_service", "landing_service"):
                level[field] = float(level[field])
            level["max_drones"] = int(level["max_drones"])
            levels.append(level)
        scene["facility_planning"] = {"budget": float(self.vars["budget"].get()), "levels": levels,
                                      "parameter_source": self.source.get().strip()}
        facility_inputs(scene)
        return scene

    def _dirty(self, *_):
        if self.building or self.busy or self.filling_pad:
            return
        self.dirty = True
        self.export_button.configure(state="disabled")
        self.replay_button.configure(state="disabled")
        self.status.set("参数已修改，请重新计算；导出的场景JSON可再次加载。")

    def calculate(self):
        if self.busy or not self.apply_pad():
            return
        try:
            scene = self._scene_from_form()
            c = replace(self.config, drone_count=int(self.vars["drone_count"].get()),
                        order_count=int(self.vars["order_count"].get()), altitude=float(self.vars["altitude"].get()),
                        risk_weight=float(self.vars["risk_weight"].get()), separation=float(self.vars["separation"].get())).validated()
            design_seed = int(self.vars["design_seed"].get())
            design_seed_count = int(self.vars["design_seed_count"].get())
            seeds = [int(v.strip()) for v in self.vars["seeds"].get().replace("，", ",").split(",") if v.strip()]
            if not seeds:
                raise ValueError("请至少填写一个评价种子")
            create_scene(c, scene)
        except ValueError as error:
            messagebox.showerror("参数无效", str(error), parent=self.window)
            return
        self.scene, self.config = scene, c
        self.busy, self.dirty = True, True
        self.cancel_event.clear()
        self.compute_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.export_button.configure(state="disabled")
        self.replay_button.configure(state="disabled")
        for widget, _ in self.controls:
            if widget.winfo_exists():
                widget.configure(state="disabled")
        self.status.set("正在建立航路并计算配置；可取消。")
        def work():
            try:
                def progress(done, total, message):
                    self.messages.put(("progress", (done, total, message)))
                result = self._run_study(c, scene, seeds, design_seed, progress, self.cancel_event.is_set, design_seed_count)
                self.messages.put(("success", result))
            except PlanningCancelled:
                self.messages.put(("cancelled", None))
            except Exception as error:
                self.messages.put(("error", str(error)))
        threading.Thread(target=work, daemon=True, name="facility-planner").start()

    def _run_study(self, c, scene, seeds, design_seed, progress, cancel, design_seed_count):
        return run_facility_study(c, scene, scene["facility_planning"]["budget"], seeds,
                                  design_seed, progress, cancel, design_seed_count)

    def _poll(self):
        if self.closed:
            return
        while True:
            try:
                kind, value = self.messages.get_nowait()
            except queue.Empty:
                break
            if kind == "progress":
                done, total, message = value
                self.progressbar.configure(value=100*done/max(total, 1))
                self.status.set(message)
                continue
            self.busy = False
            self.compute_button.configure(state="normal")
            self.cancel_button.configure(state="disabled")
            for widget, state in self.controls:
                if widget.winfo_exists():
                    widget.configure(state=state)
            if kind == "success":
                self.study, self.dirty = value, False
                self._show_results()
                self.export_button.configure(state="normal")
                self.replay_button.configure(state="normal")
                self.progressbar.configure(value=100)
                self.status.set(f"已完成{value['candidate_count']}种可行配置、{len(value['evaluation_seeds'])}个独立种子的正常 / 高峰评价。")
            elif kind == "cancelled":
                self.status.set("计算已取消。调整参数后可重新计算。")
                self.progressbar.configure(value=0)
            else:
                self.status.set("计算未完成，请检查参数。")
                self.progressbar.configure(value=0)
                messagebox.showerror(self.HEADING+"未完成", value, parent=self.window)
        self.poll_id = self.window.after(100, self._poll)

    def cancel(self):
        self.cancel_event.set()
        self.status.set("正在结束当前仿真，随后取消……")

    def _build_results(self):
        ttk.Label(self.results_page, text="以下为独立评价种子的运行均值；P95为每次运行P95的均值。选中一行可在主界面回放。", wraplength=px(1100)).pack(anchor="w")
        frame = ttk.Frame(self.results_page)
        frame.pack(fill="x", pady=px(8))
        frame.columnconfigure(0, weight=1)
        keys = ("scenario", "name", "configuration", "cost", "on_time", "delivery", "p95", "exposure", "failed", "conflicts")
        self.result_table = ttk.Treeview(frame, columns=keys, show="headings", height=6)
        for key, label, width in zip(keys, ("场景", "方案", "场站 / 等级 / 机队", "成本", "准时率", "配送/分", "P95/分", "暴露", "失败", "间距事件"), (55, 100, 270, 55, 75, 75, 75, 65, 50, 75)):
            self.result_table.heading(key, text=label)
            self.result_table.column(key, width=px(width), minwidth=px(55), stretch=key == "configuration")
        self.result_table.grid(row=0, column=0, sticky="ew")
        xscroll = ttk.Scrollbar(frame, orient="horizontal", command=self.result_table.xview)
        xscroll.grid(row=1, column=0, sticky="ew")
        self.result_table.configure(xscrollcommand=xscroll.set)
        actions = ttk.Frame(self.results_page)
        actions.pack(fill="x")
        ttk.Label(actions, text="回放种子：").pack(side="left")
        self.replay_seed = tk.StringVar(self.window)
        self.seed_combo = ttk.Combobox(actions, textvariable=self.replay_seed, state="readonly", width=16)
        self.seed_combo.pack(side="left", padx=px(6))
        self.replay_button = ttk.Button(actions, text="回放选中方案", command=self.replay, state="disabled")
        self.replay_button.pack(side="left")
        ttk.Label(actions, text="基线与配比优化成本相同；联合优化实际投入请对照成本列。", wraplength=px(580)).pack(side="left", padx=px(12))
        details = ttk.Frame(self.results_page)
        details.pack(fill="both", expand=True, pady=px((10, 0)))
        self.report_text = tk.Text(details, wrap="word", font=("Microsoft YaHei UI", 10), height=8, relief="flat", padx=px(8), pady=px(8))
        self.report_text.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(details, orient="vertical", command=self.report_text.yview)
        scroll.pack(side="right", fill="y")
        self.report_text.configure(yscrollcommand=scroll.set, state="disabled")

    def _show_results(self):
        self.result_table.delete(*self.result_table.get_children())
        for row in self.study["summary"]:
            def fmt(value, scale=1):
                return "—" if value is None else f"{value*scale:.2f}"
            self.result_table.insert("", "end", iid=f"{row['scenario']}:{row['plan']}", values=(
                "正常" if row["scenario"] == "normal" else "高峰", row["plan_name"], row["configuration"], f"{row['cost']:g}",
                fmt(row["on_time_rate"], 100)+"%", fmt(row["mean_delivery"], 1/60), fmt(row["p95_delivery"], 1/60),
                fmt(row["mean_exposure"]), fmt(row["failed_orders"]), fmt(row["air_conflict_count"])))
        self.result_table.selection_set("peak:combined")
        self.seed_combo.configure(values=[str(v) for v in self.study["evaluation_seeds"]])
        self.replay_seed.set(str(self.study["evaluation_seeds"][0]))
        self.report_text.configure(state="normal")
        self.report_text.delete("1.0", "end")
        lines = [f"预算上限：{self.study['budget']:g}相对单位；总机队：{self.study['base_config']['drone_count']}架。",
                 f"设计种子：{self.study['design_seeds']}；独立评价种子：{self.study['evaluation_seeds']}。",
                 f"设计耗时：{self.study['design_seconds']:.2f}秒；正常与高峰复用同一套站点、等级和机队配比。", "",
                 "等待分解（秒 / 成功订单）："]
        for row in self.study["summary"]:
            def fmt(value):
                return "—" if value is None else f"{value:.1f}"
            lines.append(f"{'正常' if row['scenario']=='normal' else '高峰'} · {row['plan_name']}：等待无人机 {fmt(row['mean_drone_wait'])}；起飞位排队 {fmt(row['mean_takeoff_wait'])}；额外错峰 {fmt(row['mean_airspace_delay'])}；返场排队 {fmt(row['mean_landing_wait'])}。")
        lines += ["", "等待无人机含前序任务排队和错峰的传导影响；返场排队影响后续任务。配送时间、暴露与P95按成功订单计算，须同时检查完成率和失败数。", "",
                  "选择规则：依次减少失败率、非准时率和超时秒数，再比较配送时间＋30×路径暴露；正常和高峰等权。",
                  "配比优化固定基线的站点、等级与成本；联合优化遵守同一预算上限，实际投入见成本列。独立评价结果可能优于或差于基线。", "",
                  "参数来源 / 假设："+self.study["scene"]["facility_planning"]["parameter_source"]]
        self.report_text.insert("1.0", "\n".join(lines))
        self.report_text.configure(state="disabled")
        self.tabs.select(self.results_page)

    def replay(self):
        if not self.study or self.dirty or self.busy:
            return
        if self.app.busy:
            messagebox.showinfo("主界面正在计算", "请等待主界面当前计算完成后回放。", parent=self.window)
            return
        selected = self.result_table.selection()
        if not selected:
            return
        scenario, key = selected[0].split(":")
        seed = int(self.replay_seed.get())
        result = next(v for v in self.study["results"] if v["config"]["scenario"] == scenario and v["evaluation_seed"] == seed)
        self.app.show_facility_result(result, key)
        self.app.root.lift()

    def import_scene(self):
        path = filedialog.askopenfilename(parent=self.window, title="加载已定标地图（图片请先在主界面导入编辑）", filetypes=(("地图", "*.xlsx *.json"),))
        if not path:
            return
        try:
            from flight_map import schematic_scene
            scene = schematic_scene(create_scene(self.config, Path(path)))
            facility_inputs(scene)
            self._load_scene(scene)
        except (ValueError, OSError) as error:
            messagebox.showerror("地图未加载", str(error), parent=self.window)

    def save_scene(self):
        if not self.apply_pad():
            return
        try:
            scene = self._scene_from_form()
            path = filedialog.asksaveasfilename(parent=self.window, title="保存分级设施场景", initialfile="分级场站场景.json", defaultextension=".json")
            if path:
                from reporting import write_json
                write_json(path, scene)
                self.status.set("场景已保存，包含等级、预算、允许等级和地图组件。")
        except (OSError, ValueError) as error:
            messagebox.showerror("场景未保存", str(error), parent=self.window)

    def save_template(self):
        path = filedialog.asksaveasfilename(parent=self.window, title="保存分级Excel模板", initialfile="分级起降场填写模板.xlsx", defaultextension=".xlsx")
        if path:
            try:
                from facility_template import write_facility_template
                write_facility_template(path)
                self.status.set("模板已保存：新增场站等级表和允许等级、场地附加成本列。")
            except (ValueError, OSError) as error:
                messagebox.showerror("模板未保存", str(error), parent=self.window)

    def export(self):
        if not self.study or self.dirty or self.busy:
            return
        folder = filedialog.askdirectory(parent=self.window, title="选择完整研究结果目录", initialdir=str(ROOT/"results"))
        if folder:
            try:
                export_facility_study(self.study, folder)
                self.status.set(f"已导出配置、设计评分、独立运行、指标、地图及分析：{folder}")
            except (OSError, ValueError) as error:
                messagebox.showerror("结果未导出", str(error), parent=self.window)

    def close(self):
        if self.closed:
            return
        self.closed = True
        self.cancel_event.set()
        self.window.after_cancel(self.poll_id)
        self.window.destroy()
