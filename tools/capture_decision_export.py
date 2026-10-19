"""Capture actual Tk export completion; the directory chooser is automated."""
import ctypes
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    import tkinter as tk
    from PIL import ImageGrab
    from app import Application
    from engine import Config

    work = ROOT/'.verification/competition_20261019/video'
    destination = work/'exported_study'
    if destination.exists() and any(destination.iterdir()):
        raise ValueError('Preserve existing export evidence; use an empty destination')
    destination.mkdir(parents=True, exist_ok=True)
    source = ROOT/'results/user_map_300m/studies/h30_d5.json.gz'
    payload = source.read_bytes()
    study = json.loads(gzip.decompress(payload).decode('utf-8'))
    root = tk.Tk()
    errors = []
    root.report_callback_exception = lambda kind, value, trace: errors.append(str(value))
    app = Application(root, Config(**study['base_config']), auto_calculate=False)
    try:
        root.update()
        app.facility_button.invoke()
        window = app.facility_window
        window.study, window.dirty = study, False
        window._show_results()
        root.update()
        assert not window.result_table.selection()
        assert str(window.export_button['state']) == 'normal'
        with patch('tkinter.filedialog.askdirectory', return_value=str(destination)):
            window.export_button.invoke()
        root.update()
        assert json.loads((destination/'study.json').read_text(encoding='utf-8')) == study
        assert source.read_bytes() == payload and not errors
        assert '已导出' in window.status.get()
        window.window.lift()
        root.update()
        time.sleep(.15)
        handle = ctypes.windll.user32.GetAncestor(window.window.winfo_id(), 2)
        ImageGrab.grab(window=handle).convert('RGB').save(work/'export.png')
        proof = {
            'capture': 'Actual Tk export button invoked; saved V0.7 evaluation, no selected row',
            'automation': 'Directory chooser return value supplied programmatically; actual product export ran',
            'source': source.relative_to(ROOT).as_posix(), 'source_sha256': sha256(payload).hexdigest(),
            'source_unchanged': True, 'saved_study_equal': True, 'minimum_on_time_rate': .90,
            'status': window.status.get(), 'ui_errors': errors,
            'diagnostics': {name: sha256((destination/name).read_bytes()).hexdigest() for name in
                            ('decision_diagnostics.json', 'decision_comparisons.csv', 'decision_diagnostics.md')},
            'exported_files': len([p for p in destination.rglob('*') if p.is_file()])
        }
        (work/'export_capture.json').write_text(json.dumps(proof, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(proof, ensure_ascii=False, indent=2))
    finally:
        app.close()


if __name__ == '__main__':
    main()
