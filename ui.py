"""Visual layout for the desktop simulator, using standard Tk / ttk only."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from engine import PLAN_NAMES, risk_at
from reporting import COLORS, SCENARIOS

BG = "#F1F5FA"
INK = "#192B46"
MUTED = "#71829A"
BLUE = "#3568ED"
NAVY = "#142640"
LINE = "#E3EAF3"
FONT = "Microsoft YaHei UI"


def setup_styles(app):
    style = ttk.Style(app.root)
    style.theme_use("clam")
    app.style = style
    app.root.option_add("*TCombobox*Listbox.font", (FONT, 10))
    app.root.option_add("*TCombobox*Listbox.background", "white")
    app.root.option_add("*TCombobox*Listbox.selectBackground", "#E7EEFF")
    app.root.option_add("*TCombobox*Listbox.selectForeground", INK)
    style.configure(".", font=(FONT, 10), background=BG, foreground=INK)
    for name, color in (("TFrame", BG), ("Card.TFrame", "white"), ("Header.TFrame", NAVY),
                        ("Line.TFrame", LINE), ("Inset.TFrame", "#F6F8FC")):
        style.configure(name, background=color)
    style.configure("TLabel", background=BG, foreground=INK)
    style.configure("Card.TLabel", background="white", foreground=INK)
    style.configure("Muted.TLabel", background="white", foreground=MUTED, font=(FONT, 9))
    style.configure("Section.TLabel", background="white", foreground=INK, font=(FONT, 12, "bold"))
    style.configure("Number.TLabel", background="white", foreground=INK, font=("Segoe UI", 22, "bold"))
    style.configure("Header.TLabel", background=NAVY, foreground="white", font=(FONT, 17, "bold"))
    style.configure("HeaderSub.TLabel", background=NAVY, foreground="#A9BCD7", font=(FONT, 9))
    for name, color, fill in (("Ready", "#0B8F78", "#E8F7F0"), ("Pending", "#AD7620", "#FFF4DA"),
                             ("Busy", BLUE, "#EAF0FF")):
        style.configure(f"{name}.TLabel", foreground=color, background=fill, padding=(12, 5), font=(FONT, 9))

    # Flat controls eliminate the default grey, beveled Tk appearance.
    style.layout("TButton", [("Button.padding", {"sticky": "nswe", "children": [("Button.label", {"sticky": "nswe"})]})])
    for name, fill, text, active in (
        ("TButton", "#EFF3F9", "#425673", "#E3EAF6"),
        ("Primary.TButton", BLUE, "white", "#2557D3"),
        ("Header.TButton", "#283C58", "#E5EDFA", "#344C6E"),
        ("Quiet.TButton", "white", MUTED, "#F0F4FA"),
        ("Play.TButton", "#E9F0FF", BLUE, "#DAE6FF"),
    ):
        style.configure(name, background=fill, foreground=text, padding=(13, 9), borderwidth=0,
                        font=(FONT, 10), anchor="center")
        style.map(name, background=[("disabled", "#E9EDF4"), ("pressed", active), ("active", active)],
                  foreground=[("disabled", "#A2AFC2")])
    style.configure("TCombobox", fieldbackground="#F5F7FB", background="#F5F7FB", foreground=INK,
                    bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, arrowcolor=MUTED,
                    borderwidth=1, padding=(9, 7), arrowsize=12)
    style.map("TCombobox", fieldbackground=[("readonly", "#F5F7FB"), ("disabled", "#F0F2F6")],
              selectbackground=[("readonly", "#F5F7FB")], selectforeground=[("readonly", INK)],
              bordercolor=[("focus", "#A9C0FA")])
    style.configure("TSpinbox", fieldbackground="#F5F7FB", background="#F5F7FB", foreground=INK,
                    bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, arrowcolor=MUTED,
                    padding=(8, 7), arrowsize=11)
    style.map("TSpinbox", bordercolor=[("focus", "#A9C0FA")],
              fieldbackground=[("disabled", "#F0F2F6")])
    style.configure("TCheckbutton", background="white", foreground=INK, font=(FONT, 9), padding=2)
    style.map("TCheckbutton", background=[("active", "white")],
              foreground=[("disabled", "#A2AFC2")])
    app.check_images = []
    for selected in (False, True):
        picture = tk.PhotoImage(master=app.root, width=21, height=16)
        picture.put("white", to=(0, 0, 21, 16))
        for y in range(1, 15):
            for x in range(1, 15):
                border = x in (1, 14) or y in (1, 14)
                picture.put(BLUE if selected else ("#BCCBE0" if border else "white"), (x, y))
        if selected:
            for ax, ay, bx, by in ((4, 8, 7, 11), (7, 11, 12, 5)):
                steps = max(abs(bx-ax), abs(by-ay))
                for i in range(steps+1):
                    x, y = round(ax+(bx-ax)*i/steps), round(ay+(by-ay)*i/steps)
                    picture.put("white", to=(x, y, x+1, y+2))
        app.check_images.append(picture)
    style.element_create("LayerCheck", "image", app.check_images[0], ("selected", app.check_images[1]))
    style.layout("TCheckbutton", [("Checkbutton.padding", {"sticky": "nswe", "children": [
        ("LayerCheck", {"side": "left", "sticky": "w"}),
        ("Checkbutton.label", {"side": "left", "sticky": "w"})]})])

    # A native image element gives the safety toggle a familiar switch shape.
    app.switch_images = []
    for selected in (False, True):
        picture = tk.PhotoImage(master=app.root, width=34, height=20)
        fill = BLUE if selected else "#CBD5E3"
        for y in range(20):
            for x in range(34):
                near_x = min(24, max(9, x))
                if (x-near_x)**2+(y-9.5)**2 <= 9**2:
                    picture.put(fill, (x, y))
                center = 24 if selected else 9
                if (x-center)**2+(y-9.5)**2 <= 6.8**2:
                    picture.put("white", (x, y))
        app.switch_images.append(picture)
    style.element_create("SafetySwitch", "image", app.switch_images[0], ("selected", app.switch_images[1]))
    style.layout("Switch.TCheckbutton", [("Checkbutton.padding", {"sticky": "nswe", "children": [
        ("SafetySwitch", {"side": "left", "sticky": "w"}),
        ("Checkbutton.label", {"side": "left", "sticky": "w"})]})])
    style.configure("Switch.TCheckbutton", background="white", foreground=INK, padding=0, font=(FONT, 10))
    style.map("Switch.TCheckbutton", background=[("active", "white")])

    style.configure("TNotebook", background=BG, borderwidth=0, tabmargins=(0, 0, 0, 4),
                    lightcolor="white", darkcolor="white", bordercolor="white")
    style.configure("TNotebook.Tab", padding=(20, 6), background=BG, foreground=MUTED, borderwidth=0,
                    lightcolor=BG, darkcolor=BG, bordercolor=BG,
                    font=(FONT, 10))
    style.map("TNotebook.Tab", background=[("selected", "white"), ("active", "#E7EDF6")],
              foreground=[("selected", BLUE)])
    style.layout("TNotebook.Tab", [("Notebook.padding", {"sticky": "nswe", "children": [
        ("Notebook.label", {"sticky": "nswe"})]})])
    style.configure("Treeview", rowheight=36, font=(FONT, 9), background="white", fieldbackground="white",
                    borderwidth=0, foreground=INK, bordercolor=LINE, lightcolor=LINE, darkcolor=LINE)
    style.configure("Treeview.Heading", background="#F1F5FC", foreground="#61758F", padding=(7, 11),
                    font=(FONT, 9), borderwidth=0)
    style.map("Treeview", background=[("selected", "#EAF0FF")], foreground=[("selected", BLUE)])
    style.map("Treeview.Heading", background=[("active", "#EAF0FA")])
    style.configure("Horizontal.TScale", background="white", troughcolor="#E8EEF7", borderwidth=0,
                    bordercolor="#E8EEF7", darkcolor="#E8EEF7", lightcolor="#E8EEF7",
                    sliderlength=16, sliderthickness=12, gripcount=0)
    style.configure("Vertical.TScrollbar", background="#D6DFEC", troughcolor="white", borderwidth=0,
                    arrowsize=9, width=7)
    style.layout("Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
        ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
    style.configure("Horizontal.TScrollbar", background="#D6DFEC", troughcolor="white", arrowsize=10,
                    borderwidth=0, lightcolor="#D6DFEC", darkcolor="#D6DFEC", bordercolor="white")
    style.layout("Horizontal.TScrollbar", [("Horizontal.Scrollbar.trough", {"sticky": "we", "children": [
        ("Horizontal.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
    style.configure("Busy.Horizontal.TProgressbar", background=BLUE, troughcolor="#EDF2FA", borderwidth=0,
                    bordercolor="#EDF2FA", lightcolor=BLUE, darkcolor=BLUE, thickness=3)


def _metric_icon(parent, index, color):
    icon = tk.Canvas(parent, width=34, height=34, bg="white", highlightthickness=0)
    icon.create_oval(0, 0, 33, 33, fill="#F1F5FC", outline="")
    if index == 0:
        icon.create_oval(9, 9, 25, 25, outline=color, width=1.6)
        icon.create_line(17, 12, 17, 17, 22, 19, fill=color, width=1.6, capstyle="round")
    elif index == 1:
        icon.create_polygon(17, 8, 25, 11, 24, 21, 17, 27, 10, 21, 9, 11, outline=color, fill="", width=1.6)
        icon.create_line(13, 17, 16, 20, 21, 14, fill=color, width=1.6)
    elif index == 2:
        icon.create_line(10, 24, 10, 12, 23, 12, 23, 22, fill=color, width=1.6, dash=(3, 2))
        for x, y in ((10, 24), (23, 22)):
            icon.create_oval(x-2, y-2, x+2, y+2, fill=color, outline="")
    else:
        icon.create_oval(9, 9, 25, 25, outline=color, width=1.6)
        icon.create_line(12, 17, 16, 21, 23, 13, fill=color, width=1.8)
    return icon


def build_interface(app):
    header = ttk.Frame(app.root, style="Header.TFrame", padding=(22, 10))
    header.pack(fill="x")
    brand = tk.Canvas(header, width=39, height=39, bg=NAVY, highlightthickness=0)
    brand.grid(row=0, column=0, rowspan=2, padx=(0, 12))
    brand.create_polygon(19, 3, 34, 12, 34, 28, 19, 37, 4, 28, 4, 12, fill="#2F63DF", outline="")
    brand.create_line(11, 26, 19, 12, 27, 26, fill="white", width=2, capstyle="round")
    brand.create_line(15, 22, 23, 22, fill="#AFC7FF", width=2)
    ttk.Label(header, text="低空配送仿真", style="Header.TLabel").grid(row=0, column=1, sticky="w")
    app.overview_text = tk.StringVar(value="空域风险评估与起降场选址")
    ttk.Label(header, textvariable=app.overview_text, style="HeaderSub.TLabel").grid(row=1, column=1, sticky="w", pady=(3, 0))
    header.columnconfigure(2, weight=1)
    app.state_badge = ttk.Label(header, text="待计算", style="Pending.TLabel")
    app.state_badge.grid(row=0, column=2, rowspan=2, sticky="e", padx=(12, 8))
    app.import_button = ttk.Button(header, text="＋ 导入地图", style="Primary.TButton", command=app.import_map)
    app.import_button.grid(row=0, column=3, rowspan=2, padx=(12, 9))
    app.export_button = ttk.Button(header, text="导出结果", style="Header.TButton", command=app.export, state="disabled")
    app.export_button.grid(row=0, column=4, rowspan=2)

    outer = ttk.Frame(app.root, padding=(20, 10, 20, 8))
    outer.pack(fill="both", expand=True)
    outer.columnconfigure(0, weight=1)
    outer.rowconfigure(2, weight=1)
    cards = ttk.Frame(outer)
    cards.grid(row=1, column=0, sticky="ew", pady=(0, 12))
    app.metric_values = []
    app.metric_numbers = []
    for i, (label, note, color) in enumerate((
        ("平均配送时间", "分钟 / 完成订单", BLUE),
        ("每单人员暴露", "仿真代理指数", "#D49A33"),
        ("总飞行航程", "公里 / 包含返程", "#5A78B9"),
        ("订单准时率", "下单后 10 分钟内", "#0A9D88"),
    )):
        cards.columnconfigure(i, weight=1, uniform="metrics")
        card = ttk.Frame(cards, style="Card.TFrame", padding=(15, 8))
        card.grid(row=0, column=i, sticky="ew", padx=(0 if i == 0 else 5, 0 if i == 3 else 5))
        card.columnconfigure(0, weight=1)
        ttk.Label(card, text=label, style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        _metric_icon(card, i, color).place(relx=1, x=-8, y=0, anchor="ne")
        value = tk.StringVar(value="—")
        app.metric_values.append(value)
        number = ttk.Label(card, textvariable=value, style="Number.TLabel")
        number.grid(row=1, column=0, sticky="w", pady=(1, 0))
        app.metric_numbers.append(number)
        ttk.Label(card, text=note, style="Muted.TLabel").grid(row=1, column=1, sticky="se", padx=(5, 0), pady=(0, 7))

    workspace = ttk.Frame(outer)
    workspace.grid(row=2, column=0, sticky="nsew")
    workspace.columnconfigure(1, weight=1)
    workspace.rowconfigure(0, weight=1)
    _build_controls(app, workspace)
    app.notebook = ttk.Notebook(workspace)
    app.notebook.grid(row=0, column=1, sticky="nsew")
    _build_map(app)
    _build_comparison(app)
    footer = ttk.Frame(outer)
    footer.grid(row=3, column=0, sticky="ew", pady=(8, 0))
    ttk.Label(footer, textvariable=app.source_text, foreground=MUTED, font=(FONT, 8)).pack(side="left")
    ttk.Label(footer, text="固定高度轨迹模型   ·   暴露与间距均为仿真指标", foreground=MUTED, font=(FONT, 8)).pack(side="right")


def _build_controls(app, workspace):
    shell = ttk.Frame(workspace, style="Card.TFrame", width=254)
    shell.grid(row=0, column=0, sticky="ns", padx=(0, 15))
    shell.grid_propagate(False)
    shell.columnconfigure(0, weight=1)
    shell.rowconfigure(1, weight=1)
    title = ttk.Frame(shell, style="Card.TFrame", padding=(16, 15, 16, 9))
    title.grid(row=0, column=0, sticky="ew")
    ttk.Label(title, text="运行设置", style="Section.TLabel").pack(anchor="w")
    ttk.Label(title, text="调整参数后，重新计算生效", style="Muted.TLabel").pack(anchor="w", pady=(4, 0))
    area = ttk.Frame(shell, style="Card.TFrame")
    area.grid(row=1, column=0, sticky="nsew")
    area.columnconfigure(0, weight=1)
    area.rowconfigure(0, weight=1)
    app.control_canvas = tk.Canvas(area, width=246, bg="white", highlightthickness=0)
    app.control_canvas.grid(row=0, column=0, sticky="nsew")
    scroll = ttk.Scrollbar(area, orient="vertical", command=app.control_canvas.yview)
    scroll.grid(row=0, column=1, sticky="ns")
    app.control_canvas.configure(yscrollcommand=scroll.set)
    control = ttk.Frame(app.control_canvas, style="Card.TFrame", padding=(16, 0, 13, 8))
    window = app.control_canvas.create_window((0, 0), window=control, anchor="nw")
    control.columnconfigure(0, weight=1)
    control.columnconfigure(1, weight=1)
    control.bind("<Configure>", lambda e: app.control_canvas.configure(scrollregion=app.control_canvas.bbox("all")))
    app.control_canvas.bind("<Configure>", lambda e: app.control_canvas.itemconfigure(window, width=e.width))
    app.control_shell = shell
    # Binding at the toplevel also catches wheel events over entries and labels.
    app.root.bind("<MouseWheel>", app.scroll_parameters, add="+")
    app.scenario = tk.StringVar(value=SCENARIOS[app.base_config.scenario])
    app.order_count = tk.StringVar(value=str(app.base_config.order_count))
    app.altitude = tk.StringVar(value=str(app.base_config.altitude))
    app.risk_weight = tk.StringVar(value=str(app.base_config.risk_weight))
    app.drone_count = tk.StringVar(value=str(app.base_config.drone_count))
    app.seed = tk.StringVar(value=str(app.base_config.seed))
    app.separation = tk.StringVar(value=str(app.base_config.separation))
    app.deconflict = tk.BooleanVar(value=app.base_config.deconflict)

    ttk.Label(control, text="运行场景", style="Muted.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(6, 5))
    scenario = ttk.Combobox(control, textvariable=app.scenario, values=list(SCENARIOS.values()), state="readonly", width=18)
    scenario.grid(row=1, column=0, columnspan=2, sticky="ew")
    app.controls.append((scenario, "readonly"))
    app.scenario.trace_add("write", app._mark_dirty)

    def field(parent, row, col, label, var, limits):
        block = ttk.Frame(parent, style="Card.TFrame")
        block.grid(row=row, column=col, sticky="ew", padx=(0 if col == 0 else 5, 5 if col == 0 else 0), pady=(10, 0))
        ttk.Label(block, text=label, style="Muted.TLabel").pack(anchor="w", pady=(0, 5))
        widget = ttk.Spinbox(block, textvariable=var, from_=limits[0], to=limits[1], increment=limits[2], width=6)
        widget.pack(fill="x")
        app.controls.append((widget, "normal"))
        var.trace_add("write", app._mark_dirty)

    field(control, 2, 0, "基础订单 / 单", app.order_count, (1, 200, 1))
    field(control, 2, 1, "无人机 / 架", app.drone_count, (1, 20, 1))
    field(control, 3, 0, "巡航高度 / 米", app.altitude, (15, 120, 5))
    field(control, 3, 1, "风险权重", app.risk_weight, (0, 20, .5))
    ttk.Frame(control, style="Line.TFrame", height=1).grid(row=4, column=0, columnspan=2, sticky="ew", pady=(15, 12))
    toggle = ttk.Checkbutton(control, text="  多机错峰起飞", variable=app.deconflict, style="Switch.TCheckbutton")
    toggle.grid(row=5, column=0, columnspan=2, sticky="w")
    app.controls.append((toggle, "normal"))
    app.deconflict.trace_add("write", app._mark_dirty)
    ttk.Label(control, text="通过等待起飞时隙，减少空中接近", style="Muted.TLabel", wraplength=210).grid(
        row=6, column=0, columnspan=2, sticky="w", pady=(6, 8))
    app.advanced_button = ttk.Button(control, text="高级参数  ＋", style="Quiet.TButton", command=app.toggle_advanced)
    app.advanced_button.grid(row=7, column=0, columnspan=2, sticky="ew")
    app.advanced_panel = ttk.Frame(control, style="Card.TFrame")
    app.advanced_panel.grid(row=8, column=0, columnspan=2, sticky="ew")
    app.advanced_panel.columnconfigure(0, weight=1)
    app.advanced_panel.columnconfigure(1, weight=1)
    field(app.advanced_panel, 0, 0, "间距阈值 / 米", app.separation, (1, 200, 5))
    field(app.advanced_panel, 1, 0, "评价订单种子", app.seed, (0, 2**32-1, 1))
    # The long seed gets the full panel width.
    app.advanced_panel.grid_slaves(row=1, column=0)[0].grid_configure(columnspan=2, padx=0)
    app.advanced_panel.grid_remove()
    app.advanced_open = False

    app.layout_text = tk.StringVar(value="从候选位置中选择 2 个场站")
    ttk.Frame(control, style="Line.TFrame", height=1).grid(row=9, column=0, columnspan=2, sticky="ew", pady=(12, 10))
    ttk.Label(control, text="选址范围", style="Muted.TLabel").grid(row=10, column=0, columnspan=2, sticky="w")
    ttk.Label(control, textvariable=app.layout_text, style="Muted.TLabel", wraplength=210, justify="left").grid(
        row=11, column=0, columnspan=2, sticky="w", pady=(5, 0))

    dock = ttk.Frame(shell, style="Card.TFrame", padding=(16, 10, 16, 10))
    dock.grid(row=2, column=0, sticky="ew")
    app.calculate_button = ttk.Button(dock, text="计算航路与选址", style="Primary.TButton", command=app.calculate)
    app.calculate_button.pack(fill="x")
    app.progressbar = ttk.Progressbar(dock, mode="determinate", style="Busy.Horizontal.TProgressbar", length=180)
    app.progressbar.pack(fill="x", pady=(9, 7))
    app.status = tk.StringVar(value="准备就绪，等待计算")
    tk.Label(dock, textvariable=app.status, bg="white", fg=MUTED, font=(FONT, 8), anchor="nw",
             justify="left", wraplength=214, height=2).pack(fill="x")


def _build_map(app):
    panel = ttk.Frame(app.notebook, style="Card.TFrame", padding=(14, 10))
    app.notebook.add(panel, text="仿真地图")
    panel.columnconfigure(0, weight=1)
    panel.rowconfigure(2, weight=1)
    app.map_panel = panel
    head = ttk.Frame(panel, style="Card.TFrame")
    head.grid(row=0, column=0, sticky="ew", pady=(0, 7))
    head.columnconfigure(0, weight=1)
    app.map_title = tk.StringVar(value="园区地图")
    app.map_meta = tk.StringVar(value="导入Excel或JSON地图，开始仿真")
    app.map_text = tk.StringVar(value="当前地图：待计算")
    app.source_text = tk.StringVar(value="")
    ttk.Label(head, textvariable=app.map_title, style="Section.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(head, textvariable=app.map_meta, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=(2, 0))
    app.template_button = ttk.Button(head, text="Excel模板", style="Quiet.TButton", command=app.save_map_template)
    app.template_button.grid(row=0, column=1, rowspan=2, padx=(10, 3))
    app.demo_button = ttk.Button(head, text="恢复演示", style="Quiet.TButton", command=lambda: app.load_map(None))
    app.demo_button.grid(row=0, column=2, rowspan=2)
    toolbar = ttk.Frame(panel, style="Card.TFrame")
    toolbar.grid(row=1, column=0, sticky="ew", pady=(0, 9))
    app.plan_var = tk.StringVar(value=PLAN_NAMES[app.plan_key])
    ttk.Label(toolbar, text="布局方案", style="Muted.TLabel").pack(side="left", padx=(0, 8))
    app.plan_select = ttk.Combobox(toolbar, textvariable=app.plan_var, values=list(PLAN_NAMES.values()), state="readonly", width=10)
    app.plan_select.pack(side="left")
    app.plan_select.bind("<<ComboboxSelected>>", lambda e: app.select_plan())
    app.pad_text = tk.StringVar(value="选中场站：—")
    ttk.Label(toolbar, textvariable=app.pad_text, style="Muted.TLabel").pack(side="left", padx=14)
    app.risk_layer = tk.BooleanVar(value=True)
    app.route_layer = tk.BooleanVar(value=True)
    for text, var in (("航路", app.route_layer), ("人员暴露", app.risk_layer)):
        ttk.Checkbutton(toolbar, text=text, variable=var, command=app.draw_map).pack(side="right", padx=(8, 0))

    app.canvas = tk.Canvas(panel, bg="#F6F9FC", highlightthickness=1, highlightbackground=LINE, height=380, width=650)
    app.canvas.grid(row=2, column=0, sticky="nsew")
    app.resize_timer = None
    app.canvas.bind("<Configure>", app._resize)
    app.canvas.bind("<Motion>", app.map_hover)
    app.map_hint = tk.StringVar(value="本地米制坐标 · 建筑标注为高度")
    app.canvas.bind("<Leave>", lambda e: app.map_hint.set("本地米制坐标 · 建筑标注为高度"))
    legend = ttk.Frame(panel, style="Card.TFrame")
    legend.grid(row=3, column=0, sticky="ew", pady=(6, 7))
    ttk.Label(legend, text="● 选中场站    ○ 候选场站    ◆ 配送点", style="Muted.TLabel").pack(side="left")
    ttk.Label(legend, textvariable=app.map_hint, style="Muted.TLabel").pack(side="right")
    play = ttk.Frame(panel, style="Card.TFrame")
    play.grid(row=4, column=0, sticky="ew", pady=(0, 6))
    play.columnconfigure(2, weight=1)
    app.play_button = ttk.Button(play, text="▶ 播放", style="Play.TButton", command=app.toggle_play, state="disabled", width=7)
    app.play_button.grid(row=0, column=0)
    ttk.Button(play, text="重置", style="Quiet.TButton", command=app.reset_playback).grid(row=0, column=1, padx=(3, 7))
    app.seek = tk.DoubleVar(value=0)
    app.timeline = ttk.Scale(play, from_=0, to=1, variable=app.seek, command=app.seek_time)
    app.timeline.grid(row=0, column=2, sticky="ew", padx=(0, 12))
    ttk.Label(play, text="倍速", style="Muted.TLabel").grid(row=0, column=3, padx=(0, 6))
    app.speed = tk.StringVar(value="60")
    ttk.Combobox(play, textvariable=app.speed, values=("20", "60", "120"), width=4, state="readonly").grid(row=0, column=4)
    status = ttk.Frame(panel, style="Card.TFrame")
    status.grid(row=5, column=0, sticky="ew")
    app.progress = tk.StringVar(value="00:00  /  等待运行")
    ttk.Label(status, textvariable=app.progress, style="Muted.TLabel").pack(side="left")
    app.safety_text = tk.StringVar(value="计算后显示多机间距与错峰结果")
    app.safety_label = ttk.Label(panel, textvariable=app.safety_text, style="Muted.TLabel")
    app.safety_label.grid(row=6, column=0, sticky="w", pady=(4, 0))


def _build_comparison(app):
    panel = ttk.Frame(app.notebook, style="Card.TFrame", padding=16)
    app.notebook.add(panel, text="方案对比")
    panel.columnconfigure(0, weight=1)
    panel.rowconfigure(2, weight=1)
    ttk.Label(panel, text="三种布局，同一组评价订单", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 12))
    table_box = ttk.Frame(panel, style="Card.TFrame")
    table_box.grid(row=1, column=0, sticky="ew")
    table_box.columnconfigure(0, weight=1)
    fields = ("plan", "pads", "time", "risk", "distance", "conflicts", "air_wait", "on_time", "complete")
    app.table = ttk.Treeview(table_box, columns=fields, show="headings", height=3, selectmode="browse")
    for field, label, width in zip(fields,
        ("方案", "场站", "配送 / 分钟", "暴露指数", "航程 / km", "间距不足 / 次", "错峰 / 秒每单", "准时率", "完成 / 总单数"),
        (96, 82, 100, 90, 95, 110, 116, 86, 115)):
        app.table.heading(field, text=label)
        app.table.column(field, width=width, minwidth=width, anchor="center", stretch=True)
    app.table.grid(row=0, column=0, sticky="ew")
    scrollbar = ttk.Scrollbar(table_box, orient="horizontal", command=app.table.xview)
    scrollbar.grid(row=1, column=0, sticky="ew", pady=(3, 0))
    app.table.configure(xscrollcommand=scrollbar.set)
    app.table.bind("<<TreeviewSelect>>", app._table_selected)
    app.comparison_canvas = tk.Canvas(panel, height=160, bg="white", highlightthickness=0)
    app.comparison_canvas.grid(row=2, column=0, sticky="nsew", pady=(14, 10))
    app.comparison_canvas.bind("<Configure>", lambda e: app.draw_comparison())
    notes = ttk.Frame(panel, style="Card.TFrame")
    notes.grid(row=3, column=0, sticky="ew")
    for i, (title, text) in enumerate((
        ("选址依据", "距离优先：最小化设计订单航程。\n综合风险：暴露45%、时间30%、航程15%、起降等待10%。"),
        ("评价口径", "三种布局共用订单、机队与航路规划器。\n时间与暴露按完成订单统计，请同时查看完成率。"),
    )):
        notes.columnconfigure(i, weight=1, uniform="notes")
        block = ttk.Frame(notes, style="Inset.TFrame", padding=12)
        block.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 5, 5 if i == 0 else 0))
        ttk.Label(block, text=title, background="#F6F8FC", font=(FONT, 10, "bold")).pack(anchor="w", pady=(0, 5))
        label = ttk.Label(block, text=text, background="#F6F8FC", foreground=MUTED, justify="left", font=(FONT, 9), wraplength=320)
        label.pack(anchor="w")
        block.bind("<Configure>", lambda e, lab=label: lab.configure(wraplength=max(150, e.width-24)))


def _rounded(canvas, x1, y1, x2, y2, radius=6, **options):
    radius = max(0, min(radius, (x2-x1)/2, (y2-y1)/2))
    return canvas.create_polygon(x1+radius, y1, x2-radius, y1, x2, y1, x2, y1+radius,
                                 x2, y2-radius, x2, y2, x2-radius, y2, x1+radius, y2,
                                 x1, y2, x1, y2-radius, x1, y1+radius, x1, y1,
                                 smooth=True, splinesteps=12, **options)


def render_map(app):
    canvas = app.canvas
    canvas.delete("all")
    app.map_details = {}
    cw, ch = max(50, canvas.winfo_width()), max(50, canvas.winfo_height())
    if not app.result:
        canvas.create_oval(cw/2-30, ch/2-50, cw/2+30, ch/2+10, fill="#EAF0FB", outline="")
        canvas.create_line(cw/2-13, ch/2-13, cw/2, ch/2-33, cw/2+13, ch/2-13, fill=BLUE, width=2)
        canvas.create_text(cw/2, ch/2+36, text="准备你的第一张配送地图", font=(FONT, 14, "bold"), fill=INK)
        canvas.create_text(cw/2, ch/2+65, text="导入地图，或使用演示园区开始计算", font=(FONT, 10), fill=MUTED)
        return
    scene = app.result["scene"]
    scale = max(.001, min((cw-64)/scene["width"], (ch-58)/scene["height"]))
    ox, oy = (cw-scene["width"]*scale)/2, (ch-scene["height"]*scale)/2
    app.transform = scale, ox, oy
    right, bottom = ox+scene["width"]*scale, oy+scene["height"]*scale
    _rounded(canvas, ox-2, oy-2, right+2, bottom+2, radius=5, fill="#E2EAF4", outline="")
    canvas.create_rectangle(ox, oy, right, bottom, fill="#F2F6FA", outline="")

    def box(item, padding=0, **options):
        return canvas.create_rectangle(ox+(item["x"]-padding)*scale, oy+(item["y"]-padding)*scale,
                                       ox+(item["x"]+item["w"]+padding)*scale,
                                       oy+(item["y"]+item["h"]+padding)*scale, **options)

    def heat_color(value):
        cold, warm = (244, 248, 252), (240, 176, 129)
        return "#"+"".join(f"{round(a+(b-a)*value):02x}" for a, b in zip(cold, warm))

    if app.risk_layer.get():
        for y in range(0, int(scene["height"])+1, 24):
            for x in range(0, int(scene["width"])+1, 24):
                width, height = min(24, scene["width"]-x), min(24, scene["height"]-y)
                if min(width, height) <= 0:
                    continue
                risk = risk_at(scene, (x+width/2, y+height/2))
                box({"x": x, "y": y, "w": width, "h": height}, fill=heat_color(risk), outline="")
    grid_step = max(80, round(scene["width"]/10/20)*20)
    for i in range(1, int(scene["width"]//grid_step)+1):
        x = ox+i*grid_step*scale
        canvas.create_line(x, oy, x, bottom, fill="#E6ECF3", width=1, dash=(2, 6))
    for i in range(1, int(scene["height"]//grid_step)+1):
        y = oy+i*grid_step*scale
        canvas.create_line(ox, y, right, y, fill="#E6ECF3", width=1, dash=(2, 6))

    for building in scene["buildings"]:
        blocked = building["height"]+scene["vertical_clearance"] >= scene["altitude"]
        if blocked:
            box(building, scene["clearance"], outline="#BCCBDD", dash=(3, 3))
        x1, y1 = ox+building["x"]*scale, oy+building["y"]*scale
        x2, y2 = x1+building["w"]*scale, y1+building["h"]*scale
        _rounded(canvas, x1+2, y1+2, x2+2, y2+2, fill="#DEE6EF", outline="")
        body = _rounded(canvas, x1, y1, x2, y2, fill="#D5E0EE" if blocked else "#EBF0F6",
                        outline="#9FB3CB" if blocked else "#C5D0DF", width=1)
        label = (f"{building['name']}\n{building['height']:g} m" if x2-x1 >= 46 and y2-y1 >= 29 else building["id"])
        text = canvas.create_text((x1+x2)/2, (y1+y2)/2, text=label, fill="#48617F", font=(FONT, 8), justify="center")
        detail = f"{building['name']} · {building['height']:g}米 · "+("需绕行" if blocked else "可从上方通过")
        app.map_details.update({body: detail, text: detail})
    if scene["closure"]:
        box(scene["closure"], fill="#F9DDD8", outline="#D97A6D", dash=(5, 3), width=1.5)
        closure = scene["closure"]
        canvas.create_text(ox+(closure["x"]+closure["w"]/2)*scale,
                           oy+(closure["y"]+closure["h"]/2)*scale, text="关闭区", fill="#B95D51", font=(FONT, 8))
    plan = app.result["plans"][app.plan_key]
    if app.route_layer.get():
        route_color = {"fixed": "#8B9EB8", "distance": "#6287DB", "combined": "#4CA697"}[app.plan_key]
        for pad in plan["pad_ids"]:
            for destination in scene["deliveries"]:
                route = app.result["routes"].get(f"{pad}:{destination['id']}")
                if route and len(route["points"]) > 1:
                    points = [c for x, y in route["points"] for c in (ox+x*scale, oy+y*scale)]
                    canvas.create_line(*points, fill=route_color, width=1.5, joinstyle="round")
    for destination in scene["deliveries"]:
        x, y = ox+destination["x"]*scale, oy+destination["y"]*scale
        marker = canvas.create_polygon(x, y-4, x+4, y, x, y+4, x-4, y, fill="#C48A38", outline="white", width=1)
        label = canvas.create_text(x+7, y, text=destination["id"], anchor="w", fill="#576C87", font=("Segoe UI", 8))
        detail = f"{destination['id']} {destination['name']} · 配送点 · ({destination['x']:g}, {destination['y']:g})米"
        app.map_details.update({marker: detail, label: detail})
    for pad in scene["pads"]:
        x, y = ox+pad["x"]*scale, oy+pad["y"]*scale
        selected = pad["id"] in plan["pad_ids"]
        radius = 7 if selected else 4.5
        if selected:
            canvas.create_oval(x-11, y-11, x+11, y+11, fill="#DBEBF4", outline="")
        marker = canvas.create_oval(x-radius, y-radius, x+radius, y+radius,
                                    fill=COLORS[app.plan_key] if selected else "white", outline="white" if selected else "#7C98C4", width=2)
        label = canvas.create_text(x+12, y, text=pad["id"], anchor="w", fill=INK, font=("Segoe UI", 9, "bold"))
        detail = f"{pad['id']} {pad['name']} · "+("已选场站" if selected else "候选场站")
        app.map_details.update({marker: detail, label: detail})
    canvas.create_text(ox, oy-12, text="园区平面 / 米", anchor="w", fill=MUTED, font=(FONT, 8))
    canvas.create_text(right, oy-12, text="X →   Y ↓", anchor="e", fill=MUTED, font=("Segoe UI", 8))
    ruler = min(scene["width"]/4, max(20, round(scene["width"]/8/20)*20))
    y = bottom+15
    canvas.create_line(ox, y-3, ox, y, ox+ruler*scale, y, ox+ruler*scale, y-3, fill="#8397AE", width=1)
    canvas.create_text(ox+ruler*scale+7, y, text=f"{ruler:g} m", anchor="w", fill=MUTED, font=("Segoe UI", 8))
    if app.risk_layer.get():
        for i in range(50):
            canvas.create_line(right-90+i, y-3, right-90+i, y+3, fill=heat_color(i/49))
        canvas.create_text(right-96, y, text="暴露  低", anchor="e", fill=MUTED, font=(FONT, 8))
        canvas.create_text(right-34, y, text="高", anchor="w", fill=MUTED, font=(FONT, 8))
    app.draw_drones()


def render_comparison(app):
    canvas = app.comparison_canvas
    canvas.delete("all")
    if not app.result:
        return
    width, height = max(200, canvas.winfo_width()), max(1, canvas.winfo_height())
    specs = (("mean_delivery", "平均配送时间 / 分钟", 1/60, ""), ("mean_exposure", "每单人员暴露", 1, ""))
    for i, (field, title, factor, unit) in enumerate(specs):
        left, right = i*width/2+8, (i+1)*width/2-16
        canvas.create_text(left, 7, text=title, anchor="nw", fill=INK, font=(FONT, 10, "bold"))
        maximum = max((p["stats"][field] or 0)*factor for p in app.result["plans"].values()) or 1
        bar_left, bar_width = left+72, max(30, right-left-128)
        spacing = min(42, max(14, (height-35)/3))
        for j, (key, plan) in enumerate(app.result["plans"].items()):
            y = 34+j*spacing
            selected = key == app.plan_key
            canvas.create_text(left, y+5, text=plan["name"], anchor="w", fill=INK if selected else MUTED, font=(FONT, 9))
            _rounded(canvas, bar_left, y, bar_left+bar_width, y+10, radius=5, fill="#F0F4FA", outline="")
            value = plan["stats"][field]
            if value is not None:
                length = max(2, value*factor/maximum*bar_width)
                _rounded(canvas, bar_left, y, bar_left+length, y+10, radius=5, fill=COLORS[key], outline="")
            label = "—" if value is None else f"{value*factor:.2f}{unit}"
            canvas.create_text(right, y+5, text=label, anchor="e", fill=INK, font=("Segoe UI", 9))
