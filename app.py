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
        self.root.title("低空配送仿真 · 风险评估与场站选址")
        screen_w, screen_h = root.winfo_screenwidth(), root.winfo_screenheight()
        root.geometry(f"{min(1520,screen_w-60)}x{min(1000,screen_h-70)}+25+25")
        root.minsize(1120, 720)
        root.configure(bg=BG)
        root.protocol("WM_DELETE_WINDOW", self.close)
        self._style()
        self._build()
        self.poll_id = root.after(80, self._poll)
        if auto_calculate:
            root.after(120, self.calculate)

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
        for item in reversed(self.canvas.find_overlapping(event.x-2,event.y-2,event.x+2,event.y+2)):
            if item in getattr(self,"map_details",{}):
                detail=self.map_details[item]
                self.map_hint.set(detail if len(detail)<=42 else detail[:40]+"…")
                return
        self.map_hint.set("本地米制坐标 · 建筑标注为高度")

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
        path=filedialog.askopenfilename(parent=self.root,title="选择地图：填好的Excel模板或JSON",
                initialdir=str(Path(self.scene_path).parent if self.scene_path else ROOT/"data"),
                filetypes=(("地图文件（Excel / JSON）","*.xlsx *.json"),("Excel地图模板","*.xlsx"),("JSON地图","*.json")))
        if path:
            self.load_map(Path(path))

    def load_map(self,path):
        if self.busy:
            return
        try:
            config=self.get_config()
            if config.seed==self.design_seed:
                raise ValueError("评价种子不能与设计种子相同")
            scene=create_scene(config,path)
        except (OSError,ValueError,StopIteration) as error:
            messagebox.showerror("地图未导入",str(error),parent=self.root)
            return
        self._calculate(config,scene,Path(path) if path else None,importing=True)

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
        self.demo_button.configure(state="disabled")
        for widget,_ in self.controls:
            widget.configure(state="disabled")
        self.status.set("正在导入并计算新地图……" if importing else "正在计算航路与候选布局……")
        self.progressbar.configure(mode="indeterminate")
        self.progressbar.start(12)
        self.refresh_state()

        def work():
            try:
                result=evaluate_plans(config,scene_input,self.design_seed)
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
            self.demo_button.configure(state="normal")
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
        self.dirty=False
        self.current_time=0.
        scene=result["scene"]
        name=Path(self.scene_path).name if self.scene_path else "演示园区"
        self.map_title.set(name if len(name)<=28 else name[:25]+"…")
        self.map_meta.set(f"{scene['width']:g} × {scene['height']:g} 米   /   {len(scene['buildings'])} 栋建筑   /   "
                          f"{len(scene['pads'])} 个候选场站   /   {len(scene['deliveries'])} 个配送点")
        self.source_text.set("数据来源："+scene['source'][:54])
        self.map_text.set(f"当前地图：{name}　{scene['width']:g}×{scene['height']:g}米　"
                          f"{len(scene['buildings'])}栋建筑 / {len(scene['pads'])}个候选场站 / {len(scene['deliveries'])}个配送点\n"
                          f"来源：{scene['source'][:100]}")
        self.layout_text.set(f"{len(scene['pads'])} 选 2 · 可用布局 {result['candidate_count']} 种\n每场站配置 1 个起降服务位")
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
            self.plan_var.set(PLAN_NAMES[selected[0]])
            self.select_plan()

    def select_plan(self):
        self.pause()
        self.plan_key=next(k for k,v in PLAN_NAMES.items() if v==self.plan_var.get())
        if not self.result:
            return
        plan=self.result["plans"][self.plan_key]
        stats=plan["stats"]
        for var,value in zip(self.metric_values,(self._number(stats["mean_delivery"],1/60),self._number(stats["mean_exposure"]),self._number(stats["total_distance"],.001),f"{stats['on_time_rate']:.1%}")):
            var.set(value)
        self.pad_text.set("选中场站："+" + ".join(plan["pad_ids"]))
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
        self.safety_label.configure(wraplength=max(300,event.width-8))
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
            points=[coordinate for a,r in ((angle,9),(angle+2.5,6),(angle-2.5,6)) for coordinate in (x+math.cos(a)*r,y+math.sin(a)*r)]
            self.canvas.create_polygon(*points,fill="#21334d",outline="white",width=1,tags="drone")
            self.canvas.create_text(x+9,y-10,text=drone["id"],fill=INK,font=("Segoe UI",8,"bold"),tags="drone")
        active=[e for e in plan.get("conflicts",[]) if e["start"]<=self.current_time<e["end"]]
        for event in active:
            a,b=positions[event["drone_a"]],positions[event["drone_b"]]
            ax,ay,bx,by=ox+a["x"]*scale,oy+a["y"]*scale,ox+b["x"]*scale,oy+b["y"]*scale
            self.canvas.create_line(ax,ay,bx,by,fill="#d64c4c",width=3,tags="drone")
            for x,y in ((ax,ay),(bx,by)):
                self.canvas.create_oval(x-13,y-13,x+13,y+13,outline="#d64c4c",width=2,tags="drone")
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
        self.closed=True
        self.pause()
        self.root.after_cancel(self.poll_id)
        if self.resize_timer:
            self.root.after_cancel(self.resize_timer)
        self.root.destroy()


def launch(config=None,scene_path=None,design_seed=DEFAULT_DESIGN_SEED):
    root=tk.Tk()
    Application(root,config,scene_path,design_seed)
    root.mainloop()


if __name__=="__main__":
    launch()
