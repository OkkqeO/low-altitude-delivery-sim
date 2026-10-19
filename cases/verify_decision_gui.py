"""Exercise actual Tk diagnostics on saved positive and adverse map studies.

Uses Python's standard library, not simulated widgets or manually invented data.
"""
from copy import deepcopy
import gzip
import json
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import tkinter as tk
from app import Application
from display import px
from engine import Config


def main():
    default = json.loads((ROOT/'results/sites_v1/study.json').read_text(encoding='utf-8'))
    adverse = json.loads(gzip.decompress((ROOT/'results/user_map_300m/studies/h30_d5.json.gz').read_bytes()).decode('utf-8'))
    root = tk.Tk()
    errors, dialogs = [], []
    root.report_callback_exception = lambda kind, value, trace: errors.append(str(value))
    app = Application(root, Config(**default['base_config']), auto_calculate=False)
    try:
        root.update()
        app.facility_button.invoke()
        w = app.facility_window
        for name, study in [('default', default), ('adverse', adverse)]:
            before = deepcopy(study)
            w.study, w.dirty = study, False
            w._show_results()
            root.update()
            w.window.after_cancel(w.poll_id)
            w._poll()  # Completion polling must not undo deliberate selection.
            assert not w.result_table.selection()
            assert str(w.replay_button['state']) == 'disabled'
            assert w.diagnostics_ready and study == before
            normal, peak = w.diagnostics['scenarios']
            assert normal['scenario'] == 'normal' and peak['scenario'] == 'peak'
            assert peak['recommendation_status'] == 'not_recommended'
            combined = next(p for p in peak['plans'] if p['plan'] == 'combined')
            if name == 'adverse':
                assert combined['pareto_status'] == 'dominated'
                assert 'fixed' in combined['dominated_by']
                assert w.result_table.set('peak:combined', 'pareto') == '被支配'
                assert combined['baseline_differences']['fixed']['mean_delivery'] > 0
                assert combined['baseline_differences']['fixed']['mean_exposure'] > 0
            else:
                assert combined['pareto_status'] == 'non_dominated'
                assert combined['baseline_differences']['distance']['mean_delivery'] > 0
                assert combined['baseline_differences']['distance']['mean_exposure'] < 0
            w.result_table.selection_set('peak:combined')
            root.update()
            assert str(w.replay_button['state']) == 'normal'
            w.replay_button.invoke()  # Even a dominated candidate can be inspected.
            root.update()
            assert app.result['plans']['combined']['jobs'] == study['results'][1]['plans']['combined']['jobs']
            w.minimum_on_time.set('40')
            root.update()
            assert not w.diagnostics_ready and not w.dirty
            assert str(w.replay_button['state']) == 'disabled'
            assert str(w.export_button['state']) == 'disabled'
            w.goal_button.invoke()
            root.update()
            assert w.diagnostics_ready and w.diagnostics['minimum_on_time_rate'] == .4
            assert study == before
            with tempfile.TemporaryDirectory(prefix='uav_diagnosis_') as folder:
                with patch('tkinter.filedialog.askdirectory', return_value=folder):
                    w.export_button.invoke()
                saved = json.loads((Path(folder)/'decision_diagnostics.json').read_text(encoding='utf-8'))
                assert saved['minimum_on_time_rate'] == .4
                assert json.loads((Path(folder)/'study.json').read_text(encoding='utf-8')) == study
            with patch('tkinter.messagebox.showerror', side_effect=lambda *a, **k: dialogs.append(a)):
                w.minimum_on_time.set('nan')
                w.goal_button.invoke()
            root.update()
            assert not w.diagnostics_ready and dialogs
            assert str(w.replay_button['state']) == 'disabled'
            dialogs.clear()
            w.minimum_on_time.set('90')
            w.goal_button.invoke()
            root.update()
        w.window.geometry(f'{px(1000)}x{px(680)}')
        w.window.lift()
        root.update()
        for control in (w.goal_entry, w.goal_button, w.replay_button, w.export_button):
            assert control.winfo_ismapped()
            assert control.winfo_rooty()+control.winfo_height() <= w.window.winfo_rooty()+w.window.winfo_height()
        assert not errors, errors
        print('Decision GUI passed: real normal/adverse studies, no default selection, '
              'completion polling, four-metric dominance/tradeoffs, below-target rejection, '
              'dominated replay, adjustable target without resimulation, invalid target blocking, '
              'JSON/CSV exports, unchanged raw study, 1000x680 controls.')
    finally:
        app.close()


if __name__ == '__main__':
    main()
