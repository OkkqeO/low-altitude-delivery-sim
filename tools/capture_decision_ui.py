"""Capture the real Tk decision workbench using unmodified saved study data."""
from hashlib import sha256
import ctypes
import gzip
import json
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
WORK = ROOT/'.verification/competition_20261019/video'
IMAGES = ROOT/'docs/images'


def main():
    from PIL import ImageGrab
    import tkinter as tk
    from app import Application
    from engine import Config
    WORK.mkdir(parents=True, exist_ok=True)
    paths = {'default': ROOT/'results/sites_v1/study.json',
             'adverse': ROOT/'results/user_map_300m/studies/h30_d5.json.gz'}
    payloads = {key: path.read_bytes() for key, path in paths.items()}
    studies = {key: json.loads((gzip.decompress(value) if paths[key].suffix == '.gz' else value).decode('utf-8'))
               for key, value in payloads.items()}
    root = tk.Tk()
    errors = []
    root.report_callback_exception = lambda kind, value, trace: errors.append(str(value))
    app = Application(root, Config(**studies['default']['base_config']), auto_calculate=False)

    def grab(window, name):
        window.lift()
        root.update()
        time.sleep(.12)
        handle = ctypes.windll.user32.GetAncestor(window.winfo_id(), 2)
        ImageGrab.grab(window=handle).convert('RGB').save(WORK/name)

    try:
        root.update()
        app.facility_button.invoke()
        w = app.facility_window
        for key, filename, heading in [('default', 'normal.png', '【正常】'), ('adverse', 'adverse.png', '【高峰】')]:
            w.study, w.dirty = studies[key], False
            w._show_results()
            root.update()
            assert not w.result_table.selection()
            assert str(w.replay_button['state']) == 'disabled'
            index = w.report_text.search(heading, '1.0')
            w.report_text.yview(index)
            grab(w.window, filename)
            target = 'site-diagnosis.png' if key == 'default' else 'site-diagnosis-adverse.png'
            (IMAGES/target).write_bytes((WORK/filename).read_bytes())
        w.minimum_on_time.set('40')
        w.goal_button.invoke()
        root.update()
        w.result_table.selection_set('peak:combined')
        root.update()
        index = w.report_text.search('【高峰】', '1.0')
        w.report_text.yview(index)
        grab(w.window, 'target.png')
        (IMAGES/'site-diagnosis-target.png').write_bytes((WORK/'target.png').read_bytes())
        w.replay_button.invoke()
        root.update()
        for i in range(80):
            app.seek_time(str(i*1.5))
            grab(root, f'replay-{i:04d}.png')
        assert not errors, errors
        assert all(paths[key].read_bytes() == value for key, value in payloads.items())
        proof = {'capture': 'Actual Tk workbench; automated actions using saved, unmodified V0.7 evaluations',
                 'sources': {str(paths[key].relative_to(ROOT)): sha256(value).hexdigest() for key, value in payloads.items()},
                 'source_unchanged': True, 'ui_errors': errors, 'default_selection': None,
                 'screenshots': ['normal.png', 'adverse.png', 'target.png'],
                 'replay_frames': 80, 'replay_simulation_seconds': [0, 118.5],
                 'goal_change': '90% to 40% changes diagnosis only, not simulation or layout',
                 'warning': '40% is an illustrative sensitivity target, not a validated operating SLA or a performance gain'}
        (WORK/'capture.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(proof, ensure_ascii=False, indent=2))
    finally:
        app.close()


if __name__ == '__main__':
    main()
