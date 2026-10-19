"""Location selection workbench; shares background/replay lifecycle with the UI."""
from copy import deepcopy
from pathlib import Path
import math
import shutil
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

from display import px
from engine import ROOT
from facility_ui import FacilityWindow
from site_selection import location_scene, run_site_study, export_site_study
from decision_support import diagnose_site_study, decision_diagnostics_text, export_decision_diagnostics


class SiteWindow(FacilityWindow):
    WINDOW_TITLE = '起飞点优选'
    HEADING = '起飞点优选 · 正常与高峰配送比较'
    INTRO = '同条件比较1—20架无人机的位置方案，检查准时率目标与指标取舍，再由使用者选择；设计优选不保证独立评价更优。'
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
        ttk.Label(self.results_page, text='独立评价均值；“设计优选”对应原始数据的“运行优选”。不默认推荐，请查看诊断后主动选行回放。', wraplength=px(1100)).pack(anchor='w')
        goal_line = ttk.Frame(self.results_page)
        goal_line.pack(fill='x', pady=px((6, 0)))
        ttk.Label(goal_line, text='研究准时率目标 / %：').pack(side='left')
        self.minimum_on_time = tk.StringVar(self.window, '90')
        self.goal_entry = ttk.Entry(goal_line, textvariable=self.minimum_on_time, width=7)
        self.goal_entry.pack(side='left', padx=px(5))
        self.goal_button = ttk.Button(goal_line, text='应用诊断目标', command=self._apply_goal)
        self.goal_button.pack(side='left')
        self.controls.extend(((self.goal_entry, 'normal'), (self.goal_button, 'normal')))
        ttk.Label(goal_line, text='可调研究目标，不是赛事标准或实测SLA；修改仅重算诊断。').pack(side='left', padx=px(8))
        ttk.Label(self.results_page, text='四指标：失败率↓、准时率↑、平均配送时间↓、路径暴露↓（容差1e-8）；仅比较当前三方案，P95与间距事件另列。', wraplength=px(1100)).pack(anchor='w', pady=px(3))
        self.diagnostic_status = tk.StringVar(self.window, '尚无评价结果。')
        ttk.Label(self.results_page, textvariable=self.diagnostic_status, wraplength=px(1100)).pack(anchor='w', pady=px(4))
        self.diagnostics = None
        self.diagnostics_ready = False
        self.minimum_on_time.trace_add('write', self._goal_changed)
        frame = ttk.Frame(self.results_page)
        frame.pack(fill='x', pady=px(8))
        frame.columnconfigure(0, weight=1)
        columns = ('scenario', 'name', 'configuration', 'on_time', 'delivery', 'p95', 'exposure', 'failed', 'conflicts', 'service', 'pareto')
        self.result_table = ttk.Treeview(frame, columns=columns, show='headings', height=6)
        for key, label, width in zip(columns, ('场景', '方案', '起飞点 / 无人机', '准时率', '配送/分', 'P95/分', '暴露', '失败', '间距事件', '研究目标', '四指标比较'), (55, 100, 195, 75, 70, 70, 65, 55, 70, 80, 105)):
            self.result_table.heading(key, text=label)
            self.result_table.column(key, width=px(width), minwidth=px(55), stretch=key=='configuration')
        self.result_table.grid(row=0, column=0, sticky='ew')
        scroll = ttk.Scrollbar(frame, orient='horizontal', command=self.result_table.xview)
        scroll.grid(row=1, column=0, sticky='ew')
        self.result_table.configure(xscrollcommand=scroll.set)
        self.result_table.bind('<<TreeviewSelect>>', self._selection_changed)
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
                '正常' if row['scenario']=='normal' else '高峰', '设计优选' if row['plan']=='combined' else row['plan_name'], row['configuration'],
                fmt(row['on_time_rate'], 100)+'%', fmt(row['mean_delivery'], 1/60), fmt(row['p95_delivery'], 1/60),
                fmt(row['mean_exposure']), fmt(row['failed_orders']), fmt(row['air_conflict_count']), '', ''))
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
        self.study_details = '\n'.join(lines)
        self._apply_goal()
        self.replay_button.configure(state='disabled')
        self.tabs.select(self.results_page)

    def _goal_changed(self, *_):
        self.diagnostics_ready = False
        if self.study:
            self.diagnostic_status.set('研究目标待应用；请点击“应用诊断目标”，原仿真结果不变。')
            self.replay_button.configure(state='disabled')
            self.export_button.configure(state='disabled')

    def _target(self):
        value = float(self.minimum_on_time.get())
        if not math.isfinite(value) or not 0 <= value <= 100:
            raise ValueError('研究准时率目标须为0—100的有限数字')
        return value / 100

    def _apply_goal(self):
        if not self.study or self.busy or self.dirty:
            return
        try:
            self.diagnostics = diagnose_site_study(self.study, self._target())
        except ValueError as error:
            self.diagnostics_ready = False
            self.diagnostic_status.set('研究目标无效；诊断、回放与导出尚未启用。')
            self._selection_changed()
            messagebox.showerror('诊断目标无效', str(error), parent=self.window)
            return
        service_names = {'meets': '达到', 'below': '未达到', 'pending': '待验证'}
        pareto_names = {'non_dominated': '未被支配', 'dominated': '被支配', 'pending': '待验证'}
        for scenario in self.diagnostics['scenarios']:
            for plan in scenario['plans']:
                iid = f"{scenario['scenario']}:{plan['plan']}"
                self.result_table.set(iid, 'service', service_names[plan['service_status']])
                self.result_table.set(iid, 'pareto', pareto_names[plan['pareto_status']])
        self.diagnostics_ready = True
        self.diagnostic_status.set('；'.join(f"{s['scenario_name']}：{s['message']}" for s in self.diagnostics['scenarios']))
        text = decision_diagnostics_text(self.diagnostics) + '\n\n' + self.study_details
        self.report_text.configure(state='normal')
        self.report_text.delete('1.0', 'end')
        self.report_text.insert('1.0', text)
        self.report_text.configure(state='disabled')
        self.export_button.configure(state='normal')
        self._selection_changed()

    def _selection_changed(self, *_):
        enabled = bool(self.study and not self.dirty and not self.busy and self.diagnostics_ready and self.result_table.selection())
        self.replay_button.configure(state='normal' if enabled else 'disabled')
        if not self.diagnostics_ready:
            self.export_button.configure(state='disabled')

    def _poll(self):
        super()._poll()
        if not self.closed:
            # The inherited completion handler enables replay unconditionally.
            # Restore the requirement for a deliberate, current row selection.
            self._selection_changed()

    def replay(self):
        if self.diagnostics_ready:
            super().replay()

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
                target = self._target()
                if not self.diagnostics_ready:
                    raise ValueError('请先应用当前研究诊断目标')
                export_site_study(self.study, folder)
                export_decision_diagnostics(self.study, folder, target)
                self.status.set(f'已导出原始研究、基线差、四指标诊断和研究目标：{folder}')
            except (OSError, ValueError) as error:
                messagebox.showerror('结果未导出', str(error), parent=self.window)
