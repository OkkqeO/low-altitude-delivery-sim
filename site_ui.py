"""Location selection workbench; shares background/replay lifecycle with the UI."""
from copy import deepcopy
from pathlib import Path
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from display import px
from engine import ROOT
from facility_ui import FacilityWindow
from site_selection import location_scene, run_site_study, export_site_study


class SiteWindow(FacilityWindow):
    WINDOW_TITLE = '起飞点优选'
    HEADING = '起飞点优选 · 正常与高峰配送比较'
    INTRO = '无人机总数可设置1—20架；同一次比较使用相同总数和服务参数，选择运行表现更好的起飞位置。'
    SETTINGS_TITLE = '地图与无人机数量'
    COMPUTE_TEXT = '比较起飞位置'

    def _build_settings(self):
        top = ttk.Frame(self.settings_page)
        top.pack(fill='x', pady=px((0, 8)))
        self._button(top, '加载Excel / JSON', self.import_scene).pack(side='right', padx=px(4))
        self._button(top, '保存场景JSON', self.save_scene).pack(side='right', padx=px(4))
        self._button(top, '获取地图Excel模板', self.save_template).pack(side='right', padx=px(4))
        ttk.Label(self.settings_page, textvariable=self.scene_name).pack(anchor='w')
        params = ttk.LabelFrame(self.settings_page, text='运行参数', padding=px(6))
        params.pack(fill='x', pady=px(8))
        c = self.config
        fields = [('无人机总数（1—20架）', 'drone_count', c.drone_count),
                  ('基础订单量（高峰翻倍）', 'order_count', c.order_count),
                  ('巡航高度 / 米', 'altitude', c.altitude), ('航路风险权重', 'risk_weight', c.risk_weight),
                  ('间距阈值 / 米', 'separation', c.separation), ('设计种子', 'design_seed', self.app.design_seed),
                  ('设计种子数（1—5）', 'design_seed_count', 3),
                  ('评价种子（逗号分隔）', 'seeds', ','.join(str((c.seed+i) % 2**32) for i in range(5)))]
        for i, (label, key, value) in enumerate(fields):
            self._entry(params, label, key, value, i//2, i%2)
        params.columnconfigure(1, weight=1)
        params.columnconfigure(3, weight=1)
        ttk.Label(self.settings_page, text='1架时选择1个起飞点；2—20架时选择2个点并均衡分配，奇数时按候选点顺序前站多一架。改变数量后重新计算。', wraplength=px(1100)).pack(anchor='w', pady=px(5))
        ttk.Label(self.sites_page, text='候选位置来自地图。可在主窗口“编辑地图”中增删或移动，保存后重新加载。', wraplength=px(1100)).pack(anchor='w', pady=px((0, 8)))
        self.pad_table = ttk.Treeview(self.sites_page, columns=('id', 'name', 'x', 'y'), show='headings')
        for key, label, width in (('id', '编号', 90), ('name', '位置名称', 340), ('x', 'X / 米', 140), ('y', 'Y / 米', 140)):
            self.pad_table.heading(key, text=label)
            self.pad_table.column(key, width=px(width), minwidth=px(60))
        scroll = ttk.Scrollbar(self.sites_page, orient='vertical', command=self.pad_table.yview)
        scroll.pack(side='right', fill='y')
        self.pad_table.configure(yscrollcommand=scroll.set)
        self.pad_table.pack(fill='both', expand=True)

    def _load_scene(self, scene):
        self.scene = location_scene(self.config, scene)
        self.scene_name.set(f"{len(self.scene['pads'])}个候选起飞点 / {len(self.scene['deliveries'])}个配送点 / {self.scene['width']:g}×{self.scene['height']:g}米")
        self.pad_table.delete(*self.pad_table.get_children())
        for p in self.scene['pads']:
            self.pad_table.insert('', 'end', iid=p['id'], values=(p['id'], p['name'], f"{p['x']:g}", f"{p['y']:g}"))
        self._dirty()
        self.status.set('设置无人机数量与订单参数，点击“比较起飞位置”。')

    def _scene_from_form(self):
        return deepcopy(self.scene)

    def apply_pad(self):
        return True

    def _run_study(self, c, scene, seeds, design_seed, progress, cancel, design_seed_count):
        return run_site_study(c, scene, seeds, design_seed, progress, cancel, design_seed_count)

    def _build_results(self):
        ttk.Label(self.results_page, text='各方案使用相同的无人机总数；以下为独立评价种子的均值。选中一行可回放。', wraplength=px(1100)).pack(anchor='w')
        frame = ttk.Frame(self.results_page)
        frame.pack(fill='x', pady=px(8))
        frame.columnconfigure(0, weight=1)
        columns = ('scenario', 'name', 'configuration', 'on_time', 'delivery', 'p95', 'exposure', 'failed', 'conflicts')
        self.result_table = ttk.Treeview(frame, columns=columns, show='headings', height=6)
        for key, label, width in zip(columns, ('场景', '方案', '起飞点 / 无人机', '准时率', '配送/分', 'P95/分', '暴露', '失败', '间距事件'), (60, 110, 270, 90, 85, 85, 70, 60, 80)):
            self.result_table.heading(key, text=label)
            self.result_table.column(key, width=px(width), minwidth=px(55), stretch=key=='configuration')
        self.result_table.grid(row=0, column=0, sticky='ew')
        scroll = ttk.Scrollbar(frame, orient='horizontal', command=self.result_table.xview)
        scroll.grid(row=1, column=0, sticky='ew')
        self.result_table.configure(xscrollcommand=scroll.set)
        actions = ttk.Frame(self.results_page)
        actions.pack(fill='x')
        ttk.Label(actions, text='回放种子：').pack(side='left')
        self.replay_seed = tk.StringVar(self.window)
        self.seed_combo = ttk.Combobox(actions, textvariable=self.replay_seed, state='readonly', width=16)
        self.seed_combo.pack(side='left', padx=px(6))
        self.replay_button = ttk.Button(actions, text='回放选中方案', command=self.replay, state='disabled')
        self.replay_button.pack(side='left')
        details = ttk.Frame(self.results_page)
        details.pack(fill='both', expand=True, pady=px((10, 0)))
        self.report_text = tk.Text(details, wrap='word', font=('Microsoft YaHei UI', 10), height=8, relief='flat', padx=px(8), pady=px(8))
        self.report_text.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(details, orient='vertical', command=self.report_text.yview)
        scroll.pack(side='right', fill='y')
        self.report_text.configure(yscrollcommand=scroll.set, state='disabled')

    def _show_results(self):
        def fmt(v, scale=1):
            return '—' if v is None else f'{v*scale:.2f}'
        self.result_table.delete(*self.result_table.get_children())
        for row in self.study['summary']:
            self.result_table.insert('', 'end', iid=f"{row['scenario']}:{row['plan']}", values=(
                '正常' if row['scenario']=='normal' else '高峰', row['plan_name'], row['configuration'],
                fmt(row['on_time_rate'], 100)+'%', fmt(row['mean_delivery'], 1/60), fmt(row['p95_delivery'], 1/60),
                fmt(row['mean_exposure']), fmt(row['failed_orders']), fmt(row['air_conflict_count'])))
        self.result_table.selection_set('peak:combined')
        self.seed_combo.configure(values=[str(v) for v in self.study['evaluation_seeds']])
        self.replay_seed.set(str(self.study['evaluation_seeds'][0]))
        lines = [f"无人机总数：{self.study['base_config']['drone_count']}架；启用起飞点：{self.study['station_count']}个。",
                 f"已比较{self.study['candidate_count']}种布局，设计耗时{self.study['design_seconds']:.2f}秒。",
                 f"设计种子：{self.study['design_seeds']}；评价种子：{self.study['evaluation_seeds']}。", '',
                 '同一次比较中各布局使用相同总数，按候选点顺序均衡分配。正常与高峰评价冻结同一位置及配比。',
                 '改变无人机数量后重新选址，可以检查不同数量下更合适的起飞位置。', '', '等待分解（秒 / 成功订单）：']
        for r in self.study['summary']:
            lines.append(f"{'正常' if r['scenario']=='normal' else '高峰'} · {r['plan_name']}：等待无人机 {fmt(r['mean_drone_wait'])}；起飞位排队 {fmt(r['mean_takeoff_wait'])}；额外错峰 {fmt(r['mean_airspace_delay'])}；返场排队 {fmt(r['mean_landing_wait'])}。")
        lines += ['', '运行优选依次减少失败率、非准时率与超时，再比较配送时间＋30×路径暴露，正常与高峰等权。',
                  '配送时间、暴露和P95按成功订单计算；P95为每次运行P95的均值，请同时查看失败数。',
                  '结果来自固定高度和理想运动模型，独立评价表现可能优于或差于固定位置。']
        self.report_text.configure(state='normal')
        self.report_text.delete('1.0', 'end')
        self.report_text.insert('1.0', '\n'.join(lines))
        self.report_text.configure(state='disabled')
        self.tabs.select(self.results_page)

    def import_scene(self):
        path = filedialog.askopenfilename(parent=self.window, title='加载已定标地图', filetypes=(('地图', '*.xlsx *.json'),))
        if path:
            try:
                self._load_scene(location_scene(self.config, Path(path)))
            except (ValueError, OSError) as error:
                messagebox.showerror('地图未加载', str(error), parent=self.window)

    def save_scene(self):
        path = filedialog.asksaveasfilename(parent=self.window, title='保存选址地图', initialfile='起飞点地图.json', defaultextension='.json')
        if path:
            try:
                from reporting import write_json
                write_json(path, self.scene)
                self.status.set('地图已保存，可再次加载。无人机数量等运行参数随研究结果导出。')
            except OSError as error:
                messagebox.showerror('地图未保存', str(error), parent=self.window)

    def save_template(self):
        path = filedialog.asksaveasfilename(parent=self.window, title='保存地图Excel模板', initialfile='地图填写模板.xlsx', defaultextension='.xlsx')
        if path:
            try:
                source = ROOT/'data/地图填写模板.xlsx'
                if Path(path).resolve() != source.resolve():
                    shutil.copyfile(source, path)
                self.status.set('地图模板已保存，填写候选起飞点和配送点后重新加载。')
            except OSError as error:
                messagebox.showerror('模板未保存', str(error), parent=self.window)

    def export(self):
        if not self.study or self.dirty or self.busy:
            return
        folder = filedialog.askdirectory(parent=self.window, title='导出起飞点比较', initialdir=str(ROOT/'results'))
        if folder:
            try:
                export_site_study(self.study, folder)
                self.status.set(f'已导出布局、无人机数量、设计评分、正常/高峰指标与回放数据：{folder}')
            except (OSError, ValueError) as error:
                messagebox.showerror('结果未导出', str(error), parent=self.window)
