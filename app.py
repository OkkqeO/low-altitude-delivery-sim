"""A desktop demonstration written entirely in Python / Tkinter."""
from __future__ import annotations

from dataclasses import replace
import math
from pathlib import Path
import queue
import shutil
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox

from display import px, window_geometry
from engine import Config, DEFAULT_DESIGN_SEED, PLAN_NAMES, ROOT, create_scene, drone_at_time, evaluate_plans
from reporting import SCENARIOS, export_result
from ui import BG, INK, build_interface, setup_styles, render_map, render_comparison


class Application:
    def __init__(self, root: tk.Tk, config: Config | None = None,
                 scene_path: Path | None = None, design_seed: int = DEFAULT_DESIGN_SEED,
                 auto_calculate: bool = True):
        self.root, self.base_config = root, config or Config()
        self.scene_path, self.design_seed = scene_path, design_seed
        self.scene_data = None
        self.pending_import = False
        self.result = None
        self.facility_window = None
        self.plan_key = "combined"
        self.current_time = 0.
        self.playing = False
        self.busy = False
        self.dirty = True
        self.closed = False
        self.timer = None
        self.seek_updating = False
        self.messages = queue.Queue()
        self.controls = []
        self.transform = (1., 0., 0.)
        self.map_zoom = 1.
        self.map_pan = (0., 0.)
        self.map_pan_anchor = None
        self.map_scene_key = None
        self.root.title("低空配送仿真 · 风险评估与场站选址")
        root.geometry(window_geometry(root, 1520, 1000))
        root.minsize(px(1120), px(720))
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._style()
        self._build()
        self.poll_id = root.after(80, self._poll)
        if auto_calculate:
            root.after(120, lambda: self.load_map(self.scene_path) if self.scene_path else self.calculate())

    def _style(self):
        setup_styles(self)

    def _build(self):
        build_interface(self)

    def toggle_advanced(self):
        self.advanced_open = not self.advanced_open
        if self.advanced_open:
            self.advanced_panel.grid()
        else:
            self.advanced_panel.grid_remove()
        self.advanced_button.configure(text="高级参数  －" if self.advanced_open else "高级参数  ＋")

    def scroll_parameters(self, event):
        shell = self.control_shell
        if (shell.winfo_rootx() <= event.x_root < shell.winfo_rootx()+shell.winfo_width()
                and shell.winfo_rooty() <= event.y_root < shell.winfo_rooty()+shell.winfo_height()):
            bounds = self.control_canvas.bbox("all")
            if bounds and bounds[3] > self.control_canvas.winfo_height():
                self.control_canvas.yview_scroll(-int(event.delta/120), "units")
            return "break"

    def map_hover(self, event):
        for item in reversed(self.canvas.find_overlapping(event.x-px(2),event.y-px(2),event.x+px(2),event.y+px(2))):
            if item in getattr(self,"map_details",{}):
                detail=self.map_details[item]
                self.map_hint.set(detail if len(detail)<=42 else detail[:40]+"…")
                return
        if self.result:
            from map_geometry import contains
            scale, ox, oy = self.transform
            point = (event.x-ox)/scale, (event.y-oy)/scale
            scene = self.result["scene"]
            from flight_map import flight_obstacles
            building = next((b for b in reversed(flight_obstacles(scene)) if contains(b, point)), None)
            if building:
                blocked = building["height"]+scene["vertical_clearance"] >= scene["altitude"]
                detail = f"{building['name']} · {building['height']:g}米 · "+("需绕行" if blocked else "可从上方通过")
                self.map_hint.set(detail if len(detail)<=42 else detail[:40]+"…")
                return
        self.map_hint.set("滚轮缩放 · 拖动平移 · 悬停查看详情")

    def zoom_map(self, factor, anchor=None):
        if not self.result:
            return
        zoom = min(12., max(1., self.map_zoom*factor))
        if zoom == self.map_zoom:
            return
        cw, ch = self.canvas.winfo_width(), self.canvas.winfo_height()
        x, y = anchor if anchor is not None else (cw/2, ch/2)
        scale, ox, oy = self.transform
        world_x, world_y = (x-ox)/scale, (y-oy)/scale
        new_scale = scale*zoom/self.map_zoom
        scene = self.result["scene"]
        self.map_zoom = zoom
        self.map_pan = (x-world_x*new_scale-(cw-scene["width"]*new_scale)/2,
                        y-world_y*new_scale-(ch-scene["height"]*new_scale)/2)
        self.draw_map()

    def map_wheel(self, event):
        delta = getattr(event, "delta", 0)
        direction = (1 if getattr(event, "num", None) == 4 else -1
                     if getattr(event, "num", None) == 5 else 1 if delta > 0 else -1 if delta < 0 else 0)
        if direction:
            self.zoom_map(1.25 if direction > 0 else 1/1.25, (event.x, event.y))
        return "break"

    def fit_map(self):
        self.map_zoom, self.map_pan, self.map_pan_anchor = 1., (0., 0.), None
        self.draw_map()

    def map_drag_start(self, event):
        if self.result:
            self.map_pan_anchor = (event.x, event.y, *self.map_pan)
            self.canvas.configure(cursor="fleur")
        return "break"

    def map_drag(self, event):
        if self.map_pan_anchor is not None:
            x, y, pan_x, pan_y = self.map_pan_anchor
            self.map_pan = pan_x+event.x-x, pan_y+event.y-y
            self.draw_map()
        return "break"

    def map_drag_end(self, event):
        if self.map_pan_anchor is not None:
            self.map_drag(event)
        self.map_pan_anchor = None
        self.canvas.configure(cursor="")
        return "break"

    def draw_comparison(self):
        render_comparison(self)

    def refresh_state(self):
        if self.busy:
            text,style="正在计算", "Busy.TLabel"
        elif self.dirty:
            text,style=("参数待应用" if self.result else "待计算"), "Pending.TLabel"
        else:
            text,style="计算完成", "Ready.TLabel"
        self.state_badge.configure(text=text,style=style)

    def get_config(self):
        return replace(self.base_config, scenario=next(k for k,v in SCENARIOS.items() if v==self.scenario.get()),
                       order_count=int(self.order_count.get()), altitude=float(self.altitude.get()),
                       risk_weight=float(self.risk_weight.get()),drone_count=int(self.drone_count.get()),seed=int(self.seed.get()),
                       deconflict=self.deconflict.get(),separation=float(self.separation.get())).validated()

    def _mark_dirty(self,*_):
        self.dirty=True
        self.pause()
        self.export_button.configure(state="disabled")
        self.play_button.configure(state="disabled")
        self.status.set("参数已修改，请重新计算。" if self.result else "待计算")
        self.refresh_state()

    def calculate(self):
        if self.busy:
            return
        try:
            config=self.get_config()
            if config.seed==self.design_seed:
                raise ValueError("评价种子不能与设计种子相同")
        except (ValueError,StopIteration) as error:
            messagebox.showerror("参数无效",str(error),parent=self.root)
            return
        self._calculate(config,self.scene_data if self.scene_data is not None else self.scene_path,self.scene_path)

    def import_map(self):
        if self.busy:
            return
        path=filedialog.askopenfilename(parent=self.root,title="选择地图：图片、Excel模板或JSON",
                initialdir=str(Path(self.scene_path).parent if self.scene_path else ROOT/"data"),
                filetypes=(("地图（图片 / Excel / JSON）","*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff *.xlsx *.json"),
                           ("地图图片","*.png *.jpg *.jpeg *.webp *.bmp *.tif *.tiff"),
                           ("Excel地图模板","*.xlsx"),("JSON地图","*.json")))
        if path:
            self.load_map(Path(path))

    def load_map(self,path):
        if self.busy:
            return
        try:
            config=self.get_config()
            if config.seed==self.design_seed:
                raise ValueError("评价种子不能与设计种子相同")
            from image_map import IMAGE_SUFFIXES
            if path and Path(path).suffix.lower() in IMAGE_SUFFIXES:
                from image_map import scene_from_image
                self.pause()
                self.status.set("正在生成建筑矩形和道路简图……")
                self.root.update_idletasks()
                draft=scene_from_image(path)
                self.edit_map(draft,path)
                return
            if path:
                from map_import import load_scene_file
                raw=load_scene_file(path)
                if not isinstance(raw.get("image_import",{}),dict):
                    raise ValueError("图片导入信息格式无效")
                if (raw.get("image_import",{}).get("scale_confirmed") is False
                        or any(item.get("height_confirmed") is False for item in raw.get("buildings",[]) if isinstance(item,dict))):
                    self.edit_map(raw,path)
                    return
                scene=create_scene(config,raw)
            else:
                scene=create_scene(config)
        except (OSError,ValueError,StopIteration) as error:
            self.status.set("地图未导入，当前仿真结果保留。" if self.result else "地图未导入，请检查所选文件。")
            messagebox.showerror("地图未导入",str(error),parent=self.root)
            return
        self._calculate(config,scene,Path(path) if path else None,importing=True)

    def edit_map(self,scene=None,path=None):
        if self.busy:
            return
        self.pause()
        try:
            config=self.get_config()
            if config.seed==self.design_seed:
                raise ValueError("评价种子不能与设计种子相同")
            from map_editor import MapEditor
            source=scene if scene is not None else self.scene_data if self.scene_data is not None else create_scene(config,self.scene_path)
            editor=MapEditor(self.root,source,config,path if path else self.scene_path)
            result=editor.show()
            if result is not None:
                self._calculate(config,result,editor.saved_path or (Path(path) if path else self.scene_path),importing=True)
            else:
                self.status.set("已关闭编辑器，当前仿真结果保留。")
        except (OSError,ValueError,ImportError,StopIteration) as error:
            messagebox.showerror("地图编辑器未打开",str(error),parent=self.root)

    def save_map_template(self):
        source=ROOT/"data"/"地图填写模板.xlsx"
        destination=filedialog.asksaveasfilename(parent=self.root,title="保存Excel地图模板（用Excel或WPS填写）",
                initialfile="我的地图.xlsx",defaultextension=".xlsx",filetypes=(("Excel工作簿","*.xlsx"),))
        if not destination:
            return
        try:
            if source.resolve()!=Path(destination).resolve():
                shutil.copyfile(source,destination)
            self.status.set("模板已保存。用Excel或WPS修改，\n保存后点击“导入地图”。")
        except OSError as error:
            messagebox.showerror("模板保存失败",str(error),parent=self.root)

    def open_facility_planner(self):
        if self.busy:
            return
        if self.facility_window is not None and not self.facility_window.closed:
            self.facility_window.window.lift()
            return
        try:
            from site_ui import SiteWindow
            self.pause()
            self.facility_window = SiteWindow(self)
        except (ValueError, OSError) as error:
            messagebox.showerror("起飞点优选未打开", str(error), parent=self.root)

    def show_facility_result(self, result, key="combined"):
        self.pause()
        config = Config(**result["config"])
        self.base_config = config
        self.design_seed = result["design_seed"]
        for var, value in ((self.scenario, SCENARIOS[config.scenario]), (self.order_count, config.order_count),
                           (self.altitude, config.altitude), (self.risk_weight, config.risk_weight),
                           (self.drone_count, config.drone_count), (self.seed, config.seed),
                           (self.separation, config.separation), (self.deconflict, config.deconflict)):
            var.set(value)
        self.scene_path = None
        self.scene_data = result["scene"]
        self.plan_key = key
        self.apply_result(result)
        if "site_design" in result:
            self.status.set(f"已载入{config.drone_count}架无人机的起飞点独立评价，可回放和导出。\n调整数量后，请在“起飞点优选”重新比较。")
        else:
            self.status.set("已载入设施独立评价，可回放和导出。")

    def _calculate(self,config,scene_input,target_path,importing=False):
        self.previous_dirty=self.dirty
        self.pending_import=importing
        self.pause()
        self.busy=True
        self.dirty=True
        self.calculate_button.configure(state="disabled")
        self.export_button.configure(state="disabled")
        self.play_button.configure(state="disabled")
        self.import_button.configure(state="disabled")
        self.edit_button.configure(state="disabled")
        self.demo_button.configure(state="disabled")
        self.facility_button.configure(state="disabled")
        for widget,_ in self.controls:
            widget.configure(state="disabled")
        self.status.set("正在导入并计算新地图……" if importing else "正在计算航路与候选布局……")
        self.progressbar.configure(mode="indeterminate")
        self.progressbar.start(12)
        self.refresh_state()

        def work():
            try:
                from flight_map import schematic_scene
                simplified = schematic_scene(create_scene(config, scene_input))
                result=evaluate_plans(config,simplified,self.design_seed)
                self.messages.put(("success",(result,target_path)))
            except Exception as error:
                self.messages.put(("error",str(error)))
        threading.Thread(target=work,daemon=True,name="simulation-worker").start()

    def _poll(self):
        if self.closed:
            return
        try:
            kind,payload=self.messages.get_nowait()
        except queue.Empty:
            pass
        else:
            self.busy=False
            self.progressbar.stop()
            self.progressbar.configure(mode="determinate",value=0)
            self.calculate_button.configure(state="normal")
            self.import_button.configure(state="normal")
            self.edit_button.configure(state="normal")
            self.demo_button.configure(state="normal")
            self.facility_button.configure(state="normal")
            for widget,state in self.controls:
                widget.configure(state=state)
            if kind=="error":
                if self.pending_import:
                    self.dirty=self.previous_dirty
                    if self.result and not self.dirty:
                        self.export_button.configure(state="normal")
                        self.play_button.configure(state="normal")
                self.status.set("地图未切换，保留原结果。" if self.pending_import else "计算失败，请检查参数。")
                messagebox.showerror("地图未导入" if self.pending_import else "计算失败",payload,parent=self.root)
            else:
                result,self.scene_path=payload
                self.scene_data=result["scene"]
                self.apply_result(result)
            self.pending_import=False
            self.refresh_state()
        self.poll_id=self.root.after(80,self._poll)

    def apply_result(self,result):
        self.result=result
        names = {key: plan["name"] for key, plan in result["plans"].items()}
        self.plan_select.configure(values=list(names.values()))
        self.plan_key = self.plan_key if self.plan_key in names else "combined"
        self.plan_var.set(names[self.plan_key])
        self.dirty=False
        self.current_time=0.
        scene=result["scene"]
        scene_key = (scene["width"], scene["height"], scene.get("source"), scene.get("name"))
        if scene_key != self.map_scene_key:
            self.map_scene_key = scene_key
            self.map_zoom, self.map_pan, self.map_pan_anchor = 1., (0., 0.), None
        name=Path(self.scene_path).name if self.scene_path else scene.get("name","演示园区")
        self.map_title.set(name if len(name)<=28 else name[:25]+"…")
        from flight_map import flight_obstacles
        self.map_meta.set(f"{scene['width']:g} × {scene['height']:g} 米   /   {len(flight_obstacles(scene))} 处飞行障碍   /   "
                          f"{len(scene['pads'])} 个候选场站   /   {len(scene['deliveries'])} 个配送点")
        self.source_text.set("数据来源："+scene['source'][:54])
        self.map_text.set(f"当前地图：{name}　{scene['width']:g}×{scene['height']:g}米　"
                          f"{len(scene['buildings'])}栋建筑 / {len(scene['pads'])}个候选场站 / {len(scene['deliveries'])}个配送点\n"
                          f"来源：{scene['source'][:100]}")
        self.layout_text.set(f"{len(scene['pads'])} 选 2 · 可用布局 {result['candidate_count']} 种\n每场站配置 1 个起降服务位")
        if "facility_design" in result:
            self.layout_text.set(f"预算 {result['facility_design']['budget']:g} 相对单位 · {result['candidate_count']} 种设施配置\n同一配置冻结评价正常 / 高峰")
        if "site_design" in result:
            self.layout_text.set(f"{len(scene['pads'])}选{result['site_design']['station_count']} · 比较{result['candidate_count']}种布局\n{result['config']['drone_count']}架无人机 · 正常/高峰复用同一位置")
        self.status.set(f"已计算 {result['candidate_count']} 种布局。\n设计与评价订单独立。")
        self.export_button.configure(state="normal")
        self.play_button.configure(state="normal")
        for item in self.table.get_children():
            self.table.delete(item)
        for key,plan in result["plans"].items():
            s=plan["stats"]
            self.table.insert("","end",iid=key,values=(plan["name"],"+".join(plan["pad_ids"]),self._number(s["mean_delivery"],1/60),self._number(s["mean_exposure"]),
                                  self._number(s["total_distance"],.001),s.get("air_conflict_count",0),self._number(s.get("mean_airspace_delay")),f"{s['on_time_rate']:.1%}",f"{s['delivered_orders']}/{s['total_orders']}"))
        self.select_plan()
        self.refresh_state()

    @staticmethod
    def _number(value,factor=1):
        return "—" if value is None else f"{value*factor:.2f}"

    def _table_selected(self,event):
        selected=self.table.selection()
        if selected and selected[0]!=self.plan_key:
            self.plan_var.set(self.result["plans"][selected[0]]["name"])
            self.select_plan()

    def select_plan(self):
        self.pause()
        names = {k: p["name"] for k, p in self.result["plans"].items()} if self.result else PLAN_NAMES
        self.plan_key=next(k for k,v in names.items() if v==self.plan_var.get())
        if not self.result:
            return
        plan=self.result["plans"][self.plan_key]
        stats=plan["stats"]
        for var,value in zip(self.metric_values,(self._number(stats["mean_delivery"],1/60),self._number(stats["mean_exposure"]),self._number(stats["total_distance"],.001),f"{stats['on_time_rate']:.1%}")):
            var.set(value)
        self.pad_text.set("选中场站："+" + ".join(plan["pad_ids"]))
        if "facility_configuration" in plan:
            cfg = plan["facility_configuration"]
            self.pad_text.set(f"{plan['configuration_label']} · 成本 {cfg['cost']:g}/{self.result['facility_design']['budget']:g}")
        if "site_configuration" in plan:
            self.pad_text.set(f"{plan['configuration_label']} · 总数{self.result['config']['drone_count']}架")
        self.overview_text.set(f"{plan['name']}  /  全程计划指标")
        mode="错峰开启" if self.result["config"].get("deconflict",False) else "基线调度"
        self.safety_text.set(f"{mode} · 间距阈值 {self.result['config'].get('separation',20):g}m · 全程间距不足 {stats.get('air_conflict_count',0)} 次 · 平均错峰 {self._number(stats.get('mean_airspace_delay'))} 秒/单")
        self.table.selection_set(self.plan_key)
        self.current_time=0.
        self.timeline.configure(to=stats["duration"])
        self._update_seek()
        self.draw_map()
        self.draw_comparison()

    def _resize(self,event):
        self.safety_label.configure(wraplength=max(px(300),event.width-px(8)))
        if self.resize_timer:
            self.root.after_cancel(self.resize_timer)
        self.resize_timer=self.root.after(120,self.draw_map)

    def draw_map(self):
        self.resize_timer=None
        render_map(self)

    def draw_drones(self):
        self.canvas.delete("drone")
        if not self.result:
            return
        scale,ox,oy=self.transform
        plan=self.result["plans"][self.plan_key]
        positions={}
        for drone in plan["drones"]:
            p=drone_at_time(self.result,self.plan_key,drone["id"],self.current_time)
            positions[drone["id"]]=p
            if p["state"]=="idle":
                continue
            x,y=ox+p["x"]*scale,oy+p["y"]*scale
            angle=p["angle"]
            points=[coordinate for a,r in ((angle,px(9)),(angle+2.5,px(6)),(angle-2.5,px(6))) for coordinate in (x+math.cos(a)*r,y+math.sin(a)*r)]
            self.canvas.create_polygon(*points,fill="#21334d",outline="white",width=px(1),tags="drone")
            self.canvas.create_text(x+px(9),y-px(10),text=drone["id"],fill=INK,font=("Segoe UI",9,"bold"),tags="drone")
        active=[e for e in plan.get("conflicts",[]) if e["start"]<=self.current_time<e["end"]]
        for event in active:
            a,b=positions[event["drone_a"]],positions[event["drone_b"]]
            ax,ay,bx,by=ox+a["x"]*scale,oy+a["y"]*scale,ox+b["x"]*scale,oy+b["y"]*scale
            self.canvas.create_line(ax,ay,bx,by,fill="#d64c4c",width=px(3),tags="drone")
            for x,y in ((ax,ay),(bx,by)):
                self.canvas.create_oval(x-px(13),y-px(13),x+px(13),y+px(13),outline="#d64c4c",width=px(2),tags="drone")
        self.canvas.tag_raise("map-overlay")
        delivered=sum(j["delivered_at"]<=self.current_time for j in plan["jobs"])
        failed=sum(o["created_at"]<=self.current_time for o in plan["failed"])
        minutes,seconds=divmod(int(self.current_time),60)
        self.progress.set(f"{minutes:02d}:{seconds:02d}  /  已送达 {delivered} / {plan['stats']['total_orders']} 单  /  失败 {failed} 单  /  当前接近 {len(active)} 对")

    def _update_seek(self):
        self.seek_updating=True
        self.seek.set(self.current_time)
        self.seek_updating=False

    def seek_time(self,value):
        if self.seek_updating or not self.result:
            return
        target=float(value)
        self.pause()
        self.current_time=target
        self.draw_drones()

    def toggle_play(self):
        if not self.result or self.dirty or self.busy:
            return
        if self.playing:
            self.pause()
            return
        duration=self.result["plans"][self.plan_key]["stats"]["duration"]
        if self.current_time>=duration:
            self.current_time=0.
        self.playing=True
        self.play_button.configure(text="Ⅱ 暂停")
        self.last_tick=time.perf_counter()
        self.timer=self.root.after(40,self._tick)

    def _tick(self):
        self.timer=None
        if not self.playing or self.closed:
            return
        now=time.perf_counter()
        duration=self.result["plans"][self.plan_key]["stats"]["duration"]
        self.current_time=min(duration,self.current_time+(now-self.last_tick)*float(self.speed.get()))
        self.last_tick=now
        self._update_seek()
        self.draw_drones()
        if self.current_time>=duration:
            self.pause()
        else:
            self.timer=self.root.after(40,self._tick)

    def pause(self):
        self.playing=False
        if self.timer is not None:
            self.root.after_cancel(self.timer)
            self.timer=None
        if hasattr(self,"play_button"):
            self.play_button.configure(text="▶ 播放")

    def reset_playback(self):
        self.pause()
        self.current_time=0.
        self._update_seek()
        self.draw_drones()

    def export(self):
        if not self.result or self.dirty or self.busy:
            return
        folder=filedialog.askdirectory(title="选择结果保存目录",initialdir=str(ROOT/"results"),parent=self.root)
        if folder:
            try:
                export_result(self.result,folder)
            except Exception as error:
                messagebox.showerror("导出失败",str(error),parent=self.root)
            else:
                self.status.set(f"已导出结果、表格与图表。\n保存至：{Path(folder).name}")

    def close(self):
        if self.closed:
            return
        self.closed=True
        if self.facility_window is not None and not self.facility_window.closed:
            self.facility_window.close()
        self.pause()
        self.progressbar.stop()
        for callback in self.root.tk.call("after", "info"):
            self.root.after_cancel(callback)
        self.root.destroy()


def launch(config=None,scene_path=None,design_seed=DEFAULT_DESIGN_SEED):
    root=tk.Tk()
    Application(root,config,scene_path,design_seed)
    root.mainloop()


if __name__=="__main__":
    launch()
