"""Visual layout for the desktop simulator, using standard Tk / ttk only."""
from __future__ import annotations

import math
import tkinter as tk
from tkinter import font as tkfont, ttk

from display import SCALE, px
from engine import PLAN_NAMES, risk_at
from reporting import COLORS, SCENARIOS

BG = "#F1F5FA"
INK = "#192B46"
MUTED = "#52657F"
BLUE = "#3568ED"
NAVY = "#142640"
LINE = "#E3EAF3"
FONT = "Microsoft YaHei UI"


def setup_styles(app):
    # Named fonts also cover entry fields, radio buttons and Tk dialogs.
    for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont",
                 "TkCaptionFont", "TkIconFont", "TkTooltipFont"):
        tkfont.nametofont(name, root=app.root).configure(family=FONT, size=10)
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
    style.configure("Muted.TLabel", background="white", foreground=MUTED, font=(FONT, 10))
    style.configure("Section.TLabel", background="white", foreground=INK, font=(FONT, 12, "bold"))
    style.configure("Number.TLabel", background="white", foreground=INK, font=("Segoe UI", 22, "bold"))
    style.configure("Header.TLabel", background=NAVY, foreground="white", font=(FONT, 17, "bold"))
    style.configure("HeaderSub.TLabel", background=NAVY, foreground="#A9BCD7", font=(FONT, 9))
    for name, color, fill in (("Ready", "#0B8F78", "#E8F7F0"), ("Pending", "#AD7620", "#FFF4DA"),
                             ("Busy", BLUE, "#EAF0FF")):
        style.configure(f"{name}.TLabel", foreground=color, background=fill, padding=px((12, 5)), font=(FONT, 9))

    # Flat controls eliminate the default grey, beveled Tk appearance.
    style.layout("TButton", [("Button.padding", {"sticky": "nswe", "children": [("Button.label", {"sticky": "nswe"})]})])
    for name, fill, text, active in (
        ("TButton", "#EFF3F9", "#425673", "#E3EAF6"),
        ("Primary.TButton", BLUE, "white", "#2557D3"),
        ("Header.TButton", "#283C58", "#E5EDFA", "#344C6E"),
        ("Quiet.TButton", "white", MUTED, "#F0F4FA"),
        ("Play.TButton", "#E9F0FF", BLUE, "#DAE6FF"),
    ):
        style.configure(name, background=fill, foreground=text, padding=px((13, 9)), borderwidth=px(0),
                        font=(FONT, 10), anchor="center")
        style.map(name, background=[("disabled", "#E9EDF4"), ("pressed", active), ("active", active)],
                  foreground=[("disabled", "#A2AFC2")])
    style.configure("TCombobox", fieldbackground="#F5F7FB", background="#F5F7FB", foreground=INK,
                    bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, arrowcolor=MUTED,
                    borderwidth=px(1), padding=px((9, 7)), arrowsize=px(12))
    style.map("TCombobox", fieldbackground=[("readonly", "#F5F7FB"), ("disabled", "#F0F2F6")],
              selectbackground=[("readonly", "#F5F7FB")], selectforeground=[("readonly", INK)],
              bordercolor=[("focus", "#A9C0FA")])
    style.configure("TSpinbox", fieldbackground="#F5F7FB", background="#F5F7FB", foreground=INK,
                    bordercolor=LINE, lightcolor=LINE, darkcolor=LINE, arrowcolor=MUTED,
                    padding=px((8, 7)), arrowsize=px(11))
    style.map("TSpinbox", bordercolor=[("focus", "#A9C0FA")],
              fieldbackground=[("disabled", "#F0F2F6")])
    style.configure("TCheckbutton", background="white", foreground=INK, font=(FONT, 10), padding=px(2))
    style.configure("TRadiobutton", background=BG, foreground=INK, font=(FONT, 10), indicatorsize=px(12))
    style.configure("TEntry", foreground=INK, fieldbackground="white", padding=px((6, 5)))
    style.map("TCheckbutton", background=[("active", "white")],
              foreground=[("disabled", "#A2AFC2")])
    app.check_images = []
    for selected in (False, True):
        picture = tk.PhotoImage(master=app.root, width=px(21), height=px(16))
        picture.put("white", to=px((0, 0, 21, 16)))
        for y in range(1, 15):
            for x in range(1, 15):
                border = x in (1, 14) or y in (1, 14)
                picture.put(BLUE if selected else ("#94A7BF" if border else "white"), to=px((x, y, x+1, y+1)))
        if selected:
            for ax, ay, bx, by in ((4, 8, 7, 11), (7, 11, 12, 5)):
                steps = max(abs(bx-ax), abs(by-ay))
                for i in range(steps+1):
                    x, y = round(ax+(bx-ax)*i/steps), round(ay+(by-ay)*i/steps)
                    picture.put("white", to=px((x, y, x+1, y+2)))
        app.check_images.append(picture)
    style.element_create("LayerCheck", "image", app.check_images[0], ("selected", app.check_images[1]))
    style.layout("TCheckbutton", [("Checkbutton.padding", {"sticky": "nswe", "children": [
        ("LayerCheck", {"side": "left", "sticky": "w"}),
        ("Checkbutton.label", {"side": "left", "sticky": "w"})]})])

    # A native image element gives the safety toggle a familiar switch shape.
    app.switch_images = []
    for selected in (False, True):
        picture = tk.PhotoImage(master=app.root, width=px(34), height=px(20))
        fill = BLUE if selected else "#CBD5E3"
        for py in range(px(20)):
            for pxx in range(px(34)):
                x, y = (pxx+.5)/SCALE, (py+.5)/SCALE
                near_x = min(24, max(9, x))
                if (x-near_x)**2+(y-9.5)**2 <= 9**2:
                    picture.put(fill, (pxx, py))
                center = 24 if selected else 9
                if (x-center)**2+(y-9.5)**2 <= 6.8**2:
                    picture.put("white", (pxx, py))
        app.switch_images.append(picture)
    style.element_create("SafetySwitch", "image", app.switch_images[0], ("selected", app.switch_images[1]))
    style.layout("Switch.TCheckbutton", [("Checkbutton.padding", {"sticky": "nswe", "children": [
        ("SafetySwitch", {"side": "left", "sticky": "w"}),
        ("Checkbutton.label", {"side": "left", "sticky": "w"})]})])
    style.configure("Switch.TCheckbutton", background="white", foreground=INK, padding=px(0), font=(FONT, 10))
    style.map("Switch.TCheckbutton", background=[("active", "white")])

    style.configure("TNotebook", background=BG, borderwidth=px(0), tabmargins=px((0, 0, 0, 4)),
                    lightcolor="white", darkcolor="white", bordercolor="white")
    style.configure("TNotebook.Tab", padding=px((20, 6)), background=BG, foreground=MUTED, borderwidth=px(0),
                    lightcolor=BG, darkcolor=BG, bordercolor=BG,
                    font=(FONT, 10))
    style.map("TNotebook.Tab", background=[("selected", "white"), ("active", "#E7EDF6")],
              foreground=[("selected", BLUE)])
    style.layout("TNotebook.Tab", [("Notebook.padding", {"sticky": "nswe", "children": [
        ("Notebook.label", {"sticky": "nswe"})]})])
    style.configure("Treeview", rowheight=px(36), font=(FONT, 10), background="white", fieldbackground="white",
                    borderwidth=px(0), foreground=INK, bordercolor=LINE, lightcolor=LINE, darkcolor=LINE)
    style.configure("Treeview.Heading", background="#F1F5FC", foreground=MUTED, padding=px((7, 11)),
                    font=(FONT, 10), borderwidth=px(0))
    style.map("Treeview", background=[("selected", "#EAF0FF")], foreground=[("selected", BLUE)])
    style.map("Treeview.Heading", background=[("active", "#EAF0FA")])
    style.configure("Horizontal.TScale", background="white", troughcolor="#E8EEF7", borderwidth=px(0),
                    bordercolor="#E8EEF7", darkcolor="#E8EEF7", lightcolor="#E8EEF7",
                    sliderlength=px(16), sliderthickness=px(12), gripcount=0)
    style.configure("Vertical.TScrollbar", background="#D6DFEC", troughcolor="white", borderwidth=px(0),
                    arrowsize=px(9), width=px(7))
    style.layout("Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [
        ("Vertical.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
    style.configure("Horizontal.TScrollbar", background="#D6DFEC", troughcolor="white", arrowsize=px(10),
                    borderwidth=px(0), lightcolor="#D6DFEC", darkcolor="#D6DFEC", bordercolor="white")
    style.layout("Horizontal.TScrollbar", [("Horizontal.Scrollbar.trough", {"sticky": "we", "children": [
        ("Horizontal.Scrollbar.thumb", {"expand": "1", "sticky": "nswe"})]})])
    style.configure("Busy.Horizontal.TProgressbar", background=BLUE, troughcolor="#EDF2FA", borderwidth=px(0),
                    bordercolor="#EDF2FA", lightcolor=BLUE, darkcolor=BLUE, thickness=px(3))


def _metric_icon(parent, index, color):
    icon = tk.Canvas(parent, width=px(34), height=px(34), bg="white", highlightthickness=px(0))
    icon.create_oval(0, 0, 33, 33, fill="#F1F5FC", outline="")
    if index == 0:
        icon.create_oval(9, 9, 25, 25, outline=color, width=px(1.6))
        icon.create_line(17, 12, 17, 17, 22, 19, fill=color, width=px(1.6), capstyle="round")
    elif index == 1:
        icon.create_polygon(17, 8, 25, 11, 24, 21, 17, 27, 10, 21, 9, 11, outline=color, fill="", width=px(1.6))
        icon.create_line(13, 17, 16, 20, 21, 14, fill=color, width=px(1.6))
    elif index == 2:
        icon.create_line(10, 24, 10, 12, 23, 12, 23, 22, fill=color, width=px(1.6), dash=(3, 2))
        for x, y in ((10, 24), (23, 22)):
            icon.create_oval(x-2, y-2, x+2, y+2, fill=color, outline="")
    else:
        icon.create_oval(9, 9, 25, 25, outline=color, width=px(1.6))
        icon.create_line(12, 17, 16, 21, 23, 13, fill=color, width=px(1.8))
    icon.scale("all", 0, 0, SCALE, SCALE)
    return icon


def build_interface(app):
    header = ttk.Frame(app.root, style="Header.TFrame", padding=px((22, 10)))
    header.pack(fill="x")
    brand = tk.Canvas(header, width=px(39), height=px(39), bg=NAVY, highlightthickness=px(0))
    brand.grid(row=0, column=0, rowspan=2, padx=px((0, 12)))
    brand.create_polygon(19, 3, 34, 12, 34, 28, 19, 37, 4, 28, 4, 12, fill="#2F63DF", outline="")
    brand.create_line(11, 26, 19, 12, 27, 26, fill="white", width=px(2), capstyle="round")
    brand.create_line(15, 22, 23, 22, fill="#AFC7FF", width=px(2))
    brand.scale("all", 0, 0, SCALE, SCALE)
    ttk.Label(header, text="低空配送仿真", style="Header.TLabel").grid(row=0, column=1, sticky="w")
    app.overview_text = tk.StringVar(value="空域风险评估与起降场选址")
    ttk.Label(header, textvariable=app.overview_text, style="HeaderSub.TLabel").grid(row=1, column=1, sticky="w", pady=px((3, 0)))
    header.columnconfigure(2, weight=1)
    app.state_badge = ttk.Label(header, text="待计算", style="Pending.TLabel")
    app.state_badge.grid(row=0, column=2, rowspan=2, sticky="e", padx=px((12, 8)))
    app.import_button = ttk.Button(header, text="＋ 导入地图", style="Primary.TButton", command=app.import_map)
    app.import_button.grid(row=0, column=3, rowspan=2, padx=px((12, 9)))
    app.export_button = ttk.Button(header, text="导出结果", style="Header.TButton", command=app.export, state="disabled")
    app.export_button.grid(row=0, column=4, rowspan=2)
    app.facility_button = ttk.Button(header, text="起飞点优选", style="Header.TButton", command=app.open_facility_planner)
    app.facility_button.grid(row=0, column=5, rowspan=2, padx=px((9, 0)))
    app.close_button = ttk.Button(header, text="× 关闭", style="Header.TButton", command=app.close, width=7)
    app.close_button.grid(row=0, column=6, rowspan=2, padx=px((9, 0)))

    outer = ttk.Frame(app.root, padding=px((20, 10, 20, 8)))
    outer.pack(fill="both", expand=True)
    outer.columnconfigure(0, weight=1)
    outer.rowconfigure(2, weight=1)
    cards = ttk.Frame(outer)
    cards.grid(row=1, column=0, sticky="ew", pady=px((0, 12)))
    app.metric_values = []
    app.metric_numbers = []
    for i, (label, note, color) in enumerate((
        ("平均配送时间", "分钟 / 完成订单", BLUE),
        ("每单人员暴露", "仿真代理指数", "#D49A33"),
        ("总飞行航程", "公里 / 包含返程", "#5A78B9"),
        ("订单准时率", "下单后 10 分钟内", "#0A9D88"),
    )):
        cards.columnconfigure(i, weight=1, uniform="metrics")
        card = ttk.Frame(cards, style="Card.TFrame", padding=px((15, 8)))
        card.grid(row=0, column=i, sticky="ew", padx=px((0 if i == 0 else 5, 0 if i == 3 else 5)))
        card.columnconfigure(0, weight=1)
        ttk.Label(card, text=label, style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        _metric_icon(card, i, color).place(relx=1, x=px(-8), y=px(0), anchor="ne")
        value = tk.StringVar(value="—")
        app.metric_values.append(value)
        number = ttk.Label(card, textvariable=value, style="Number.TLabel")
        number.grid(row=1, column=0, sticky="w", pady=px((1, 0)))
        app.metric_numbers.append(number)
        ttk.Label(card, text=note, style="Muted.TLabel").grid(row=1, column=1, sticky="se", padx=px((5, 0)), pady=px((0, 7)))

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
    footer.grid(row=3, column=0, sticky="ew", pady=px((8, 0)))
    ttk.Label(footer, textvariable=app.source_text, foreground=MUTED, font=(FONT, 9)).pack(side="left")
    ttk.Label(footer, text="固定高度轨迹模型   ·   暴露与间距均为仿真指标", foreground=MUTED, font=(FONT, 9)).pack(side="right")


def _build_controls(app, workspace):
    shell = ttk.Frame(workspace, style="Card.TFrame", width=px(254))
    shell.grid(row=0, column=0, sticky="ns", padx=px((0, 15)))
    shell.grid_propagate(False)
    shell.columnconfigure(0, weight=1)
    shell.rowconfigure(1, weight=1)
    title = ttk.Frame(shell, style="Card.TFrame", padding=px((16, 15, 16, 9)))
    title.grid(row=0, column=0, sticky="ew")
    ttk.Label(title, text="运行设置", style="Section.TLabel").pack(anchor="w")
    ttk.Label(title, text="调整参数后，重新计算生效", style="Muted.TLabel").pack(anchor="w", pady=px((4, 0)))
    area = ttk.Frame(shell, style="Card.TFrame")
    area.grid(row=1, column=0, sticky="nsew")
    area.columnconfigure(0, weight=1)
    area.rowconfigure(0, weight=1)
    app.control_canvas = tk.Canvas(area, width=px(246), bg="white", highlightthickness=px(0))
    app.control_canvas.grid(row=0, column=0, sticky="nsew")
    scroll = ttk.Scrollbar(area, orient="vertical", command=app.control_canvas.yview)
    scroll.grid(row=0, column=1, sticky="ns")
    app.control_canvas.configure(yscrollcommand=scroll.set)
    control = ttk.Frame(app.control_canvas, style="Card.TFrame", padding=px((16, 0, 13, 8)))
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

    ttk.Label(control, text="运行场景", style="Muted.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=px((6, 5)))
    scenario = ttk.Combobox(control, textvariable=app.scenario, values=list(SCENARIOS.values()), state="readonly", width=18)
    scenario.grid(row=1, column=0, columnspan=2, sticky="ew")
    app.controls.append((scenario, "readonly"))
    app.scenario.trace_add("write", app._mark_dirty)

    def field(parent, row, col, label, var, limits):
        block = ttk.Frame(parent, style="Card.TFrame")
        block.grid(row=row, column=col, sticky="ew", padx=px((0 if col == 0 else 5, 5 if col == 0 else 0)), pady=px((10, 0)))
        ttk.Label(block, text=label, style="Muted.TLabel").pack(anchor="w", pady=px((0, 5)))
        widget = ttk.Spinbox(block, textvariable=var, from_=limits[0], to=limits[1], increment=limits[2], width=6)
        widget.pack(fill="x")
        app.controls.append((widget, "normal"))
        var.trace_add("write", app._mark_dirty)

    field(control, 2, 0, "基础订单 / 单", app.order_count, (1, 200, 1))
    field(control, 2, 1, "无人机 / 架", app.drone_count, (1, 20, 1))
    field(control, 3, 0, "巡航高度 / 米", app.altitude, (15, 120, 5))
    field(control, 3, 1, "风险权重", app.risk_weight, (0, 20, .5))
    ttk.Frame(control, style="Line.TFrame", height=px(1)).grid(row=4, column=0, columnspan=2, sticky="ew", pady=px((15, 12)))
    toggle = ttk.Checkbutton(control, text="  多机错峰起飞", variable=app.deconflict, style="Switch.TCheckbutton")
    toggle.grid(row=5, column=0, columnspan=2, sticky="w")
    app.controls.append((toggle, "normal"))
    app.deconflict.trace_add("write", app._mark_dirty)
    ttk.Label(control, text="通过等待起飞时隙，减少空中接近", style="Muted.TLabel", wraplength=px(210)).grid(
        row=6, column=0, columnspan=2, sticky="w", pady=px((6, 8)))
    app.advanced_button = ttk.Button(control, text="高级参数  ＋", style="Quiet.TButton", command=app.toggle_advanced)
    app.advanced_button.grid(row=7, column=0, columnspan=2, sticky="ew")
    app.advanced_panel = ttk.Frame(control, style="Card.TFrame")
    app.advanced_panel.grid(row=8, column=0, columnspan=2, sticky="ew")
    app.advanced_panel.columnconfigure(0, weight=1)
    app.advanced_panel.columnconfigure(1, weight=1)
    field(app.advanced_panel, 0, 0, "间距阈值 / 米", app.separation, (1, 200, 5))
    field(app.advanced_panel, 1, 0, "评价订单种子", app.seed, (0, 2**32-1, 1))
    # The long seed gets the full panel width.
    app.advanced_panel.grid_slaves(row=1, column=0)[0].grid_configure(columnspan=2, padx=px(0))
    app.advanced_panel.grid_remove()
    app.advanced_open = False

    app.layout_text = tk.StringVar(value="从候选位置中选择 2 个场站")
    ttk.Frame(control, style="Line.TFrame", height=px(1)).grid(row=9, column=0, columnspan=2, sticky="ew", pady=px((12, 10)))
    ttk.Label(control, text="选址范围", style="Muted.TLabel").grid(row=10, column=0, columnspan=2, sticky="w")
    ttk.Label(control, textvariable=app.layout_text, style="Muted.TLabel", wraplength=px(210), justify="left").grid(
        row=11, column=0, columnspan=2, sticky="w", pady=px((5, 0)))

    dock = ttk.Frame(shell, style="Card.TFrame", padding=px((16, 10, 16, 10)))
    dock.grid(row=2, column=0, sticky="ew")
    app.calculate_button = ttk.Button(dock, text="计算航路与选址", style="Primary.TButton", command=app.calculate)
    app.calculate_button.pack(fill="x")
    app.progressbar = ttk.Progressbar(dock, mode="determinate", style="Busy.Horizontal.TProgressbar", length=px(180))
    app.progressbar.pack(fill="x", pady=px((9, 7)))
    app.status = tk.StringVar(value="准备就绪，等待计算")
    tk.Label(dock, textvariable=app.status, bg="white", fg=MUTED, font=(FONT, 9), anchor="nw",
             justify="left", wraplength=px(214), height=2).pack(fill="x")


def _build_map(app):
    panel = ttk.Frame(app.notebook, style="Card.TFrame", padding=px((14, 10)))
    app.notebook.add(panel, text="仿真地图")
    panel.columnconfigure(0, weight=1)
    panel.rowconfigure(2, weight=1)
    app.map_panel = panel
    head = ttk.Frame(panel, style="Card.TFrame")
    head.grid(row=0, column=0, sticky="ew", pady=px((0, 7)))
    head.columnconfigure(0, weight=1)
    app.map_title = tk.StringVar(value="园区地图")
    app.map_meta = tk.StringVar(value="导入图片、Excel或JSON地图，开始仿真")
    app.map_text = tk.StringVar(value="当前地图：待计算")
    app.source_text = tk.StringVar(value="")
    ttk.Label(head, textvariable=app.map_title, style="Section.TLabel").grid(row=0, column=0, sticky="w")
    ttk.Label(head, textvariable=app.map_meta, style="Muted.TLabel").grid(row=1, column=0, sticky="w", pady=px((2, 0)))
    app.template_button = ttk.Button(head, text="Excel模板", style="Quiet.TButton", command=app.save_map_template)
    app.template_button.grid(row=0, column=1, rowspan=2, padx=px((10, 3)))
    app.demo_button = ttk.Button(head, text="恢复演示", style="Quiet.TButton", command=lambda: app.load_map(None))
    app.demo_button.grid(row=0, column=3, rowspan=2)
    app.edit_button = ttk.Button(head, text="编辑地图", style="Quiet.TButton", command=app.edit_map)
    app.edit_button.grid(row=0, column=2, rowspan=2, padx=px(3))
    tools = ttk.Frame(panel, style="Card.TFrame")
    tools.grid(row=1, column=0, sticky="ew", pady=px((0, 9)))
    toolbar = ttk.Frame(tools, style="Card.TFrame")
    toolbar.pack(fill="x")
    app.plan_var = tk.StringVar(value=PLAN_NAMES[app.plan_key])
    ttk.Label(toolbar, text="布局方案", style="Muted.TLabel").pack(side="left", padx=px((0, 8)))
    app.plan_select = ttk.Combobox(toolbar, textvariable=app.plan_var, values=list(PLAN_NAMES.values()), state="readonly", width=10)
    app.plan_select.pack(side="left")
    app.plan_select.bind("<<ComboboxSelected>>", lambda e: app.select_plan())
    app.pad_text = tk.StringVar(value="选中场站：—")
    ttk.Label(toolbar, textvariable=app.pad_text, style="Muted.TLabel").pack(side="left", padx=px(14))
    app.risk_layer = tk.BooleanVar(value=False)
    app.route_layer = tk.BooleanVar(value=True)
    app.background_layer = tk.BooleanVar(value=False)
    app.feature_layer = tk.BooleanVar(value=True)
    for text, var in (("航路", app.route_layer), ("人员暴露", app.risk_layer), ("道路", app.feature_layer)):
        ttk.Checkbutton(toolbar, text=text, variable=var, command=app.draw_map).pack(side="right", padx=px((8, 0)))

    viewbar = ttk.Frame(tools, style="Card.TFrame")
    viewbar.pack(fill="x", pady=px((7, 0)))
    ttk.Label(viewbar, text="地图视图", style="Muted.TLabel").pack(side="left", padx=px((0, 8)))
    app.zoom_out_button = ttk.Button(viewbar, text="−", width=3, style="Quiet.TButton", command=lambda: app.zoom_map(1/1.25))
    app.zoom_out_button.pack(side="left")
    app.map_zoom_text = tk.StringVar(value="100%")
    ttk.Label(viewbar, textvariable=app.map_zoom_text, style="Muted.TLabel", width=6, anchor="center").pack(side="left")
    app.zoom_in_button = ttk.Button(viewbar, text="＋", width=3, style="Quiet.TButton", command=lambda: app.zoom_map(1.25))
    app.zoom_in_button.pack(side="left")
    app.fit_map_button = ttk.Button(viewbar, text="适应窗口", style="Quiet.TButton", command=app.fit_map)
    app.fit_map_button.pack(side="left", padx=px((6, 12)))
    ttk.Label(viewbar, text="滚轮缩放 · 拖动平移", style="Muted.TLabel").pack(side="left")
    app.show_building_names = tk.BooleanVar(value=False)
    app.building_names_button = ttk.Checkbutton(viewbar, text="建筑名称", variable=app.show_building_names, command=app.draw_map)
    app.building_names_button.pack(side="right")

    app.canvas = tk.Canvas(panel, bg="#F6F9FC", highlightthickness=px(1), highlightbackground=LINE, height=px(380), width=px(650))
    app.canvas.grid(row=2, column=0, sticky="nsew")
    app.resize_timer = None
    app.canvas.bind("<Configure>", app._resize)
    app.canvas.bind("<Motion>", app.map_hover)
    app.canvas.bind("<MouseWheel>", app.map_wheel)
    app.canvas.bind("<Button-4>", app.map_wheel)
    app.canvas.bind("<Button-5>", app.map_wheel)
    for button in (1, 3):
        app.canvas.bind(f"<ButtonPress-{button}>", app.map_drag_start)
        app.canvas.bind(f"<B{button}-Motion>", app.map_drag)
        app.canvas.bind(f"<ButtonRelease-{button}>", app.map_drag_end)
    app.canvas.bind("<Double-Button-1>", lambda e: app.fit_map())
    app.map_hint = tk.StringVar(value="滚轮缩放 · 拖动平移 · 悬停查看详情")
    app.canvas.bind("<Leave>", lambda e: app.map_hint.set("滚轮缩放 · 拖动平移 · 悬停查看详情"))
    legend = ttk.Frame(panel, style="Card.TFrame")
    legend.grid(row=3, column=0, sticky="ew", pady=px((6, 7)))
    ttk.Label(legend, text="● 选中场站    ○ 候选场站    ◆ 配送点", style="Muted.TLabel").pack(side="left")
    ttk.Label(legend, textvariable=app.map_hint, style="Muted.TLabel").pack(side="right")
    play = ttk.Frame(panel, style="Card.TFrame")
    play.grid(row=4, column=0, sticky="ew", pady=px((0, 6)))
    play.columnconfigure(2, weight=1)
    app.play_button = ttk.Button(play, text="▶ 播放", style="Play.TButton", command=app.toggle_play, state="disabled", width=7)
    app.play_button.grid(row=0, column=0)
    ttk.Button(play, text="重置", style="Quiet.TButton", command=app.reset_playback).grid(row=0, column=1, padx=px((3, 7)))
    app.seek = tk.DoubleVar(value=0)
    app.timeline = ttk.Scale(play, from_=0, to=1, variable=app.seek, command=app.seek_time)
    app.timeline.grid(row=0, column=2, sticky="ew", padx=px((0, 12)))
    ttk.Label(play, text="倍速", style="Muted.TLabel").grid(row=0, column=3, padx=px((0, 6)))
    app.speed = tk.StringVar(value="60")
    ttk.Combobox(play, textvariable=app.speed, values=("20", "60", "120"), width=4, state="readonly").grid(row=0, column=4)
    status = ttk.Frame(panel, style="Card.TFrame")
    status.grid(row=5, column=0, sticky="ew")
    app.progress = tk.StringVar(value="00:00  /  等待运行")
    ttk.Label(status, textvariable=app.progress, style="Muted.TLabel").pack(side="left")
    app.safety_text = tk.StringVar(value="计算后显示多机间距与错峰结果")
    app.safety_label = ttk.Label(panel, textvariable=app.safety_text, style="Muted.TLabel")
    app.safety_label.grid(row=6, column=0, sticky="w", pady=px((4, 0)))


def _build_comparison(app):
    panel = ttk.Frame(app.notebook, style="Card.TFrame", padding=px(16))
    app.notebook.add(panel, text="方案对比")
    panel.columnconfigure(0, weight=1)
    panel.rowconfigure(2, weight=1)
    ttk.Label(panel, text="三种布局，同一组评价订单", style="Section.TLabel").grid(row=0, column=0, sticky="w", pady=px((0, 12)))
    table_box = ttk.Frame(panel, style="Card.TFrame")
    table_box.grid(row=1, column=0, sticky="ew")
    table_box.columnconfigure(0, weight=1)
    fields = ("plan", "pads", "time", "risk", "distance", "conflicts", "air_wait", "on_time", "complete")
    app.table = ttk.Treeview(table_box, columns=fields, show="headings", height=3, selectmode="browse")
    for field, label, width in zip(fields,
        ("方案", "场站", "配送 / 分钟", "暴露指数", "航程 / km", "间距不足 / 次", "错峰 / 秒每单", "准时率", "完成 / 总单数"),
        (96, 82, 100, 90, 95, 110, 116, 86, 115)):
        app.table.heading(field, text=label)
        app.table.column(field, width=px(width), minwidth=px(width), anchor="center", stretch=True)
    app.table.grid(row=0, column=0, sticky="ew")
    scrollbar = ttk.Scrollbar(table_box, orient="horizontal", command=app.table.xview)
    scrollbar.grid(row=1, column=0, sticky="ew", pady=px((3, 0)))
    app.table.configure(xscrollcommand=scrollbar.set)
    app.table.bind("<<TreeviewSelect>>", app._table_selected)
    app.comparison_canvas = tk.Canvas(panel, height=px(160), bg="white", highlightthickness=px(0))
    app.comparison_canvas.grid(row=2, column=0, sticky="nsew", pady=px((14, 10)))
    app.comparison_canvas.bind("<Configure>", lambda e: app.draw_comparison())
    notes = ttk.Frame(panel, style="Card.TFrame")
    notes.grid(row=3, column=0, sticky="ew")
    for i, (title, text) in enumerate((
        ("选址依据", "距离优先：最小化设计订单航程。\n综合风险：暴露45%、时间30%、航程15%、起降等待10%。"),
        ("评价口径", "三种布局共用订单、机队与航路规划器。\n时间与暴露按完成订单统计，请同时查看完成率。"),
    )):
        notes.columnconfigure(i, weight=1, uniform="notes")
        block = ttk.Frame(notes, style="Inset.TFrame", padding=px(12))
        block.grid(row=0, column=i, sticky="nsew", padx=px((0 if i == 0 else 5, 5 if i == 0 else 0)))
        ttk.Label(block, text=title, background="#F6F8FC", font=(FONT, 10, "bold")).pack(anchor="w", pady=px((0, 5)))
        label = ttk.Label(block, text=text, background="#F6F8FC", foreground=MUTED, justify="left", font=(FONT, 9), wraplength=px(320))
        label.pack(anchor="w")
        block.bind("<Configure>", lambda e, lab=label: lab.configure(wraplength=max(px(150), e.width-px(24))))


def _rounded(canvas, x1, y1, x2, y2, radius=None, **options):
    radius = px(6) if radius is None else radius
    radius = max(0, min(radius, (x2-x1)/2, (y2-y1)/2))
    return canvas.create_polygon(x1+radius, y1, x2-radius, y1, x2, y1, x2, y1+radius,
                                 x2, y2-radius, x2, y2, x2-radius, y2, x1+radius, y2,
                                 x1, y2, x1, y2-radius, x1, y1+radius, x1, y1,
                                 smooth=True, splinesteps=12, **options)


def render_map(app):
    canvas = app.canvas
    canvas.delete("all")
    app.map_details = {}
    cw, ch = max(px(50), canvas.winfo_width()), max(px(50), canvas.winfo_height())
    if not app.result:
        canvas.create_oval(cw/2-px(30), ch/2-px(50), cw/2+px(30), ch/2+px(10), fill="#EAF0FB", outline="")
        canvas.create_line(cw/2-px(13), ch/2-px(13), cw/2, ch/2-px(33), cw/2+px(13), ch/2-px(13), fill=BLUE, width=px(2))
        canvas.create_text(cw/2, ch/2+px(36), text="准备你的第一张配送地图", font=(FONT, 14, "bold"), fill=INK)
        canvas.create_text(cw/2, ch/2+px(65), text="导入地图，或使用演示园区开始计算", font=(FONT, 10), fill=MUTED)
        return
    scene = app.result["scene"]
    scale = max(.001, min((cw-px(64))/scene["width"], (ch-px(58))/scene["height"])) * app.map_zoom
    map_w, map_h = scene["width"]*scale, scene["height"]*scale
    limit_x, limit_y = max(0., (cw+map_w)/2-px(60)), max(0., (ch+map_h)/2-px(60))
    pan_x = min(limit_x, max(-limit_x, app.map_pan[0]))
    pan_y = min(limit_y, max(-limit_y, app.map_pan[1]))
    app.map_pan = pan_x, pan_y
    ox, oy = (cw-map_w)/2+pan_x, (ch-map_h)/2+pan_y
    app.transform = scale, ox, oy
    app.map_zoom_text.set(f"{app.map_zoom:.0%}")
    app.zoom_out_button.configure(state="disabled" if app.map_zoom <= 1 else "normal")
    app.zoom_in_button.configure(state="disabled" if app.map_zoom >= 12 else "normal")
    right, bottom = ox+scene["width"]*scale, oy+scene["height"]*scale
    view_left, view_top = max(0., -ox/scale), max(0., -oy/scale)
    view_right = min(scene["width"], (cw-ox)/scale)
    view_bottom = min(scene["height"], (ch-oy)/scale)
    _rounded(canvas, ox-px(2), oy-px(2), right+px(2), bottom+px(2), radius=px(5), fill="#E2EAF4", outline="")
    canvas.create_rectangle(ox, oy, right, bottom, fill="#F2F6FA", outline="")
    has_background = False
    if scene.get("map_presentation") != "schematic" and scene.get("image_background") and app.background_layer.get():
        try:
            from image_map import decode_background
            from PIL import Image, ImageTk
            key = scene["image_background"].get("png_base64")
            if getattr(app,"background_key",None) != key:
                app.background_original = decode_background(scene)
                app.background_key = key
                app.background_size = None
            left, top = max(0, math.ceil(ox)), max(0, math.ceil(oy))
            bg_right, bg_bottom = min(cw, math.floor(right)), min(ch, math.floor(bottom))
            view = (left, top, bg_right, bg_bottom, ox, oy, map_w, map_h)
            if bg_right > left and bg_bottom > top:
                if app.background_size != view:
                    original = app.background_original
                    source_box = ((left-ox)/map_w*original.width, (top-oy)/map_h*original.height,
                                  (bg_right-ox)/map_w*original.width, (bg_bottom-oy)/map_h*original.height)
                    size = bg_right-left, bg_bottom-top
                    app.background_photo = ImageTk.PhotoImage(original.resize(size, Image.Resampling.LANCZOS, box=source_box), master=app.root)
                    app.background_size = view
                canvas.create_image(left,top,anchor="nw",image=app.background_photo)
            has_background = True
        except (ImportError,ValueError,OSError):
            pass

    def box(item, padding=0, **options):
        return canvas.create_rectangle(ox+(item["x"]-padding)*scale, oy+(item["y"]-padding)*scale,
                                       ox+(item["x"]+item["w"]+padding)*scale,
                                       oy+(item["y"]+item["h"]+padding)*scale, **options)

    def heat_color(value):
        cold, warm = (244, 248, 252), (240, 176, 129)
        return "#"+"".join(f"{round(a+(b-a)*value):02x}" for a, b in zip(cold, warm))

    def visible(item):
        return (item["x"] <= view_right and item["x"]+item["w"] >= view_left
                and item["y"] <= view_bottom and item["y"]+item["h"] >= view_top)

    if app.risk_layer.get():
        for y in range(int(view_top//24)*24, int(view_bottom)+1, 24):
            for x in range(int(view_left//24)*24, int(view_right)+1, 24):
                width, height = min(24, scene["width"]-x), min(24, scene["height"]-y)
                if min(width, height) <= 0:
                    continue
                risk = risk_at(scene, (x+width/2, y+height/2))
                box({"x": x, "y": y, "w": width, "h": height}, fill=heat_color(risk), outline="",stipple="gray50" if has_background else "")
    grid_step = max(80, round(scene["width"]/10/20)*20)
    for i in range(1, int(scene["width"]//grid_step)+1):
        x = ox+i*grid_step*scale
        canvas.create_line(x, oy, x, bottom, fill="#E6ECF3", width=px(1), dash=(2, 6))
    for i in range(1, int(scene["height"]//grid_step)+1):
        y = oy+i*grid_step*scale
        canvas.create_line(ox, y, right, y, fill="#E6ECF3", width=px(1), dash=(2, 6))

    from map_geometry import FEATURE_COLORS, FEATURE_TYPES, canvas_polygon
    if app.feature_layer.get():
        for feature in scene.get("map_features", []):
            if feature["kind"] != "road" or not visible(feature):
                continue
            color = FEATURE_COLORS[feature["kind"]]
            options = {"fill": "" if has_background else "#E6EBF1", "outline": "#ADBACA", "width": px(1)}
            if app.risk_layer.get() and not has_background:
                options["stipple"] = "gray50"
            parts = (canvas_polygon(canvas, feature, scale, ox, oy, **options)
                     if feature.get("polygon") else [box(feature, **options)])
            detail = f"{feature['name']} · {FEATURE_TYPES[feature['kind']]} · 地图分类候选"
            app.map_details.update({part: detail for part in parts})

    # The editor and simulation share every footprint. Height determines
    # obstacle status, not whether a building exists on the map.
    for building in scene["buildings"]:
        if not visible(building):
            continue
        blocked = building["height"]+scene["vertical_clearance"] >= scene["altitude"]
        options = {"fill": "" if has_background else "#D5E0EE" if blocked else "#EDF2F7",
                   "outline": "#597594" if blocked else "#A6B7C9", "width": px(1.3 if blocked else 1),
                   "tags": ("building", f"building:{building['id']}")}
        x1, y1 = ox+building["x"]*scale, oy+building["y"]*scale
        x2, y2 = x1+building["w"]*scale, y1+building["h"]*scale
        if building.get("polygon"):
            parts = canvas_polygon(canvas, building, scale, ox, oy, **options)
            body = parts[0]
        else:
            body = box(building, **options)
        detail = f"{building['name']} · {building['height']:g}米 · "+("需绕行" if blocked else "可从上方通过")
        app.map_details[body] = detail
        if app.show_building_names.get():
            label = (f"{building['name']}\n{building['height']:g} m" if x2-x1 >= px(60) and y2-y1 >= px(38) else building["id"])
            text = canvas.create_text((x1+x2)/2, (y1+y2)/2, text=label, fill="#324B69", font=(FONT, 9), justify="center", tags="building-label")
            app.map_details[text] = detail
        if building.get("polygon"):
            app.map_details.update({part: detail for part in parts})
    if scene["closure"]:
        box(scene["closure"], fill="#F9DDD8", outline="#D97A6D", dash=(5, 3), width=px(1.5))
        closure = scene["closure"]
        canvas.create_text(ox+(closure["x"]+closure["w"]/2)*scale,
                           oy+(closure["y"]+closure["h"]/2)*scale, text="关闭区", fill="#9C3D31", font=(FONT, 9))
    plan = app.result["plans"][app.plan_key]
    if app.route_layer.get():
        route_color = {"fixed": "#8B9EB8", "distance": "#6287DB", "combined": "#4CA697"}[app.plan_key]
        for pad in plan["pad_ids"]:
            for destination in scene["deliveries"]:
                route = app.result["routes"].get(f"{pad}:{destination['id']}")
                if route and len(route["points"]) > 1:
                    points = [c for x, y in route["points"] for c in (ox+x*scale, oy+y*scale)]
                    canvas.create_line(*points, fill=route_color, width=px(1.5), joinstyle="round")
    for destination in scene["deliveries"]:
        x, y = ox+destination["x"]*scale, oy+destination["y"]*scale
        marker = canvas.create_polygon(x, y-px(4), x+px(4), y, x, y+px(4), x-px(4), y, fill="#B07624", outline="white", width=px(1))
        label = canvas.create_text(x+px(7), y, text=destination["id"], anchor="w", fill="#364E6C", font=("Segoe UI", 9))
        detail = f"{destination['id']} {destination['name']} · 配送点 · ({destination['x']:g}, {destination['y']:g})米"
        app.map_details.update({marker: detail, label: detail})
    for pad in scene["pads"]:
        x, y = ox+pad["x"]*scale, oy+pad["y"]*scale
        selected = pad["id"] in plan["pad_ids"]
        radius = px(7 if selected else 4.5)
        if selected:
            canvas.create_oval(x-px(11), y-px(11), x+px(11), y+px(11), fill="#DBEBF4", outline="")
        marker = canvas.create_oval(x-radius, y-radius, x+radius, y+radius,
                                    fill=COLORS[app.plan_key] if selected else "white", outline="white" if selected else "#7C98C4", width=px(2))
        label_text = pad["id"]
        if selected and "facility_configuration" in plan:
            cfg = plan["facility_configuration"]
            names = {v["id"]: v["name"] for v in app.result["facility_design"]["levels"]}
            label_text = f"{pad['id']} {names[cfg['levels'][pad['id']]]} {cfg['fleet_allocation'][pad['id']]}架"
        if selected and "site_configuration" in plan:
            label_text = f"{pad['id']} {plan['site_configuration']['fleet_allocation'][pad['id']]}架"
        label = canvas.create_text(x+px(12), y, text=label_text, anchor="w", fill=INK, font=("Segoe UI", 10, "bold"))
        detail = f"{pad['id']} {pad['name']} · "+("已选场站" if selected else "候选场站")
        app.map_details.update({marker: detail, label: detail})
    # Keep orientation and a scale-correct ruler visible while the map is panned.
    canvas.create_rectangle(0, 0, cw, px(25), fill="#F6F9FC", outline="", tags="map-overlay")
    canvas.create_rectangle(0, ch-px(29), cw, ch, fill="#F6F9FC", outline="", tags="map-overlay")
    canvas.create_text(px(12), px(12), text="园区平面 / 米 · 深色建筑需绕行，浅色可飞越", anchor="w", fill=MUTED, font=(FONT, 9), tags="map-overlay")
    canvas.create_text(cw-px(12), px(12), text="X →   Y ↓", anchor="e", fill=MUTED, font=("Segoe UI", 9), tags="map-overlay")
    target = px(100)/scale
    magnitude = 10**math.floor(math.log10(target))
    ruler = min(scene["width"], min((n*magnitude for n in (1, 2, 5, 10)), key=lambda n: abs(n-target)))
    x, y = px(16), ch-px(14)
    canvas.create_line(x, y-px(3), x, y, x+ruler*scale, y, x+ruler*scale, y-px(3), fill=MUTED, width=px(1), tags=("map-overlay", "map-ruler"))
    canvas.create_text(x+ruler*scale+px(7), y, text=f"{ruler:g} m", anchor="w", fill=MUTED, font=("Segoe UI", 9), tags=("map-overlay", "map-ruler-label"))
    if app.risk_layer.get():
        for i in range(50):
            canvas.create_line(cw-px(90-i), y-px(3), cw-px(90-i), y+px(3), fill=heat_color(i/49), width=px(1), tags="map-overlay")
        canvas.create_text(cw-px(96), y, text="暴露  低", anchor="e", fill=MUTED, font=(FONT, 9), tags="map-overlay")
        canvas.create_text(cw-px(34), y, text="高", anchor="w", fill=MUTED, font=(FONT, 9), tags="map-overlay")
    app.draw_drones()


def render_comparison(app):
    canvas = app.comparison_canvas
    canvas.delete("all")
    if not app.result:
        return
    width, height = max(px(200), canvas.winfo_width()), max(1, canvas.winfo_height())
    specs = (("mean_delivery", "平均配送时间 / 分钟", 1/60, ""), ("mean_exposure", "每单人员暴露", 1, ""))
    for i, (field, title, factor, unit) in enumerate(specs):
        left, right = i*width/2+px(8), (i+1)*width/2-px(16)
        canvas.create_text(left, px(7), text=title, anchor="nw", fill=INK, font=(FONT, 10, "bold"))
        maximum = max((p["stats"][field] or 0)*factor for p in app.result["plans"].values()) or 1
        bar_left, bar_width = left+px(80), max(px(30), right-left-px(136))
        spacing = min(px(42), max(px(18), (height-px(48))/3))
        for j, (key, plan) in enumerate(app.result["plans"].items()):
            y = px(38)+j*spacing
            selected = key == app.plan_key
            canvas.create_text(left, y+px(5), text=plan["name"], anchor="w", fill=INK if selected else MUTED, font=(FONT, 10))
            _rounded(canvas, bar_left, y, bar_left+bar_width, y+px(10), radius=px(5), fill="#F0F4FA", outline="")
            value = plan["stats"][field]
            if value is not None:
                length = max(px(2), value*factor/maximum*bar_width)
                _rounded(canvas, bar_left, y, bar_left+length, y+px(10), radius=px(5), fill=COLORS[key], outline="")
            label = "—" if value is None else f"{value*factor:.2f}{unit}"
            canvas.create_text(right, y+px(5), text=label, anchor="e", fill=INK, font=("Segoe UI", 10))
