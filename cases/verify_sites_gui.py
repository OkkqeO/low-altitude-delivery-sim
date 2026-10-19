from pathlib import Path
import sys
import tempfile
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'tests'))
import tkinter as tk
from app import Application
from display import px
from engine import Config
from test_facility import small_scene

root = tk.Tk()
errors, dialogs = [], []
root.report_callback_exception = lambda kind, value, trace: errors.append(str(value))
app = Application(root, Config(order_count=6, drone_count=3, seed=101), auto_calculate=False)
app.scene_data = small_scene()

def wait(w):
    until = time.monotonic()+30
    while w.busy:
        root.update()
        assert time.monotonic() < until, 'UI timeout'
        time.sleep(.01)
    root.update()
    assert not dialogs and not errors, (dialogs, errors)

with tempfile.TemporaryDirectory() as tmp, patch('tkinter.messagebox.showerror', side_effect=lambda *a, **k: dialogs.append(a)):
    try:
        root.update()
        assert app.facility_button['text'] == '起飞点优选'
        app.facility_button.invoke()
        w = app.facility_window
        root.update()
        assert w.vars['drone_count'].get() == '3'
        assert 'budget' not in w.vars and not w.level_vars
        assert 'cost' not in w.result_table['columns']
        w.vars['design_seed'].set('900')
        w.vars['design_seed_count'].set('1')
        w.vars['seeds'].set('101,102')
        for n in (3, 8, 1, 20):
            w.vars['drone_count'].set(str(n))
            assert w.dirty and str(w.replay_button['state']) == 'disabled'
            w.compute_button.invoke()
            wait(w)
            assert len(w.result_table.get_children()) == 6
            assert w.study['base_config']['drone_count'] == n
            assert w.study['station_count'] == min(2, n)
            assert not w.result_table.selection(), 'A plan must not be implicitly recommended'
            assert str(w.replay_button['state']) == 'disabled'
            w.result_table.selection_set('peak:combined')
            root.update()
            assert str(w.replay_button['state']) == 'normal'
            w.replay()
            root.update()
            assert int(app.drone_count.get()) == n
            assert app.result['config']['drone_count'] == n
            assert app.plan_var.get() == '运行优选'
            assert len(app.result['plans']['combined']['drones']) == n
            assert f'{n}架' in app.pad_text.get()
            app.seek_time('100')
            app.toggle_play()
            root.update()
            assert app.playing
            app.pause()
            assert app.canvas.find_all()
        folder = Path(tmp)
        with patch('tkinter.filedialog.askdirectory', return_value=str(folder/'study')):
            w.export()
        assert (folder/'study/runs/peak_101/site_configurations.csv').exists()
        assert (folder/'study/decision_diagnostics.json').exists()
        assert (folder/'study/decision_comparisons.csv').exists()
        with patch('tkinter.filedialog.askdirectory', return_value=str(folder/'single')):
            app.export()
        assert (folder/'single/site_configurations.csv').exists()
        with patch('tkinter.filedialog.asksaveasfilename', return_value=str(folder/'scene.json')):
            w.save_scene()
        with patch('tkinter.filedialog.askopenfilename', return_value=str(folder/'scene.json')):
            w.import_scene()
        assert w.dirty
        with patch('tkinter.filedialog.asksaveasfilename', return_value=str(folder/'map.xlsx')):
            w.save_template()
        from map_import import load_scene_file
        assert 'facility_planning' not in load_scene_file(folder/'map.xlsx')
        w.window.geometry(f'{px(1000)}x{px(680)}')
        w.tabs.select(w.settings_page)
        root.update()
        for control in (w.compute_button, w.export_button):
            assert control.winfo_ismapped()
            assert control.winfo_rooty()+control.winfo_height() <= w.window.winfo_rooty()+w.window.winfo_height()
        w.calculate()
        w.cancel()
        wait(w)
        assert w.dirty and str(w.export_button['state']) == 'disabled'
        app.calculate()
        until = time.monotonic()+30
        while app.busy:
            root.update()
            assert time.monotonic() < until
            time.sleep(.01)
        assert app.plan_var.get() in ('固定布局', '距离优先', '综合风险')
        assert 'site_design' not in app.result
        assert not errors and not dialogs, (errors, dialogs)
        print('Sites GUI passed: fleet inherited from main, 1/3/8/20 actual drones, recalculation and dirty state, no cost/grade inputs, six results, deliberate selection before replay, playback, both exports including diagnostics, JSON reload, ordinary Excel template, small window, cancel, legacy recalculation.')
    finally:
        app.close()
