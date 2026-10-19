"""Check real Tk main/editor geometry, edits, height changes and SVG export."""
from copy import deepcopy
import argparse
import json
from pathlib import Path
import sys
import time
from unittest.mock import patch
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import tkinter as tk
from app import Application
from engine import Config, create_scene, is_blocked
from flight_map import flight_obstacles
from map_editor import MapEditor
from reporting import map_svg


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.output:
        args.output.mkdir(parents=True, exist_ok=True)
    root = tk.Tk()
    errors, checks = [], []
    root.report_callback_exception = lambda kind, value, trace: errors.append(str(value))
    app = Application(root)

    def wait():
        until = time.monotonic()+90
        while app.busy or app.result is None:
            root.update()
            assert time.monotonic() < until, 'Simulation timeout'
            time.sleep(.01)
        root.update()
        assert not errors, errors

    def capture(widget, name):
        if args.output:
            import ctypes
            from PIL import ImageGrab
            widget.lift()
            root.update()
            widget.update_idletasks()
            # Capture this window rather than whatever happens to cover its
            # desktop coordinates while the user works in another app.
            time.sleep(.12)
            handle = ctypes.windll.user32.GetAncestor(widget.winfo_id(), 2)
            ImageGrab.grab(window=handle).save(args.output/name)

    def check_main():
        app.fit_map()
        root.update()
        scene = app.result['scene']
        scale, ox, oy = app.transform
        assert len(app.canvas.find_withtag('building')) == len(scene['buildings'])
        for b in scene['buildings']:
            shapes = app.canvas.find_withtag(f"building:{b['id']}")
            assert len(shapes) == 1
            coords = app.canvas.coords(shapes[0])
            actual = [(coords[0]-ox)/scale, (coords[1]-oy)/scale,
                      (coords[2]-ox)/scale, (coords[3]-oy)/scale]
            expected = [b['x'], b['y'], b['x']+b['w'], b['y']+b['h']]
            assert all(abs(a-e) < 1e-7 for a, e in zip(actual, expected))
            blocked = b['height']+scene['vertical_clearance'] >= scene['altitude']
            assert app.canvas.itemcget(shapes[0], 'fill') == ('#D5E0EE' if blocked else '#EDF2F7')
            assert ('需绕行' if blocked else '可从上方通过') in app.map_details[shapes[0]]
        svg = ET.fromstring(map_svg(app.result))
        groups = [g for g in svg.iter() if g.get('class') == 'building']
        assert {g.get('data-building-id') for g in groups} == {b['id'] for b in scene['buildings']}
        return scene

    def open_editor(action, screenshot=None):
        before = deepcopy(app.result)
        failures = []

        class AutomatedEditor(MapEditor):
            def show(self):
                def inspect():
                    try:
                        root.update_idletasks()
                        scene = before['scene']
                        for key in ('buildings', 'pads', 'deliveries', 'map_features'):
                            assert self.document.scene[key] == scene[key], key
                        ids = {identity for kind, identity in self.item_refs.values() if kind == 'buildings'}
                        assert ids == {b['id'] for b in scene['buildings']}
                        scale, ox, oy = self.transform
                        for b in scene['buildings']:
                            shape = next(item for item, ref in self.item_refs.items()
                                         if ref == ('buildings', b['id']) and self.canvas.type(item) == 'rectangle')
                            coords = self.canvas.coords(shape)
                            actual = [(coords[0]-ox)/scale, (coords[1]-oy)/scale,
                                      (coords[2]-ox)/scale, (coords[3]-oy)/scale]
                            expected = [b['x'], b['y'], b['x']+b['w'], b['y']+b['h']]
                            assert all(abs(a-e) < 1e-7 for a, e in zip(actual, expected))
                        if scene.get('map_presentation') == 'schematic':
                            assert not self.show_background.get()
                        assert self.show_labels.get() == app.show_building_names.get()
                        assert self.layers['risk_zones'].get() == app.risk_layer.get()
                        assert self.layers['road'].get() == app.feature_layer.get()
                        if screenshot:
                            capture(self.window, screenshot)
                        action(self)
                    except Exception as error:
                        failures.append(repr(error))
                        self.window.destroy()
                self.window.after(120, inspect)
                return super().show()

        with patch('map_editor.MapEditor', AutomatedEditor):
            app.edit_button.invoke()
        assert not failures, failures
        root.update()
        return before

    try:
        with patch('tkinter.messagebox.showerror', side_effect=lambda *a, **kw: errors.append(str(a))):
            wait()  # Includes the real startup calculation.
            scene = check_main()
            assert len(scene['buildings']) == 10 and len(flight_obstacles(scene)) == 4
            capture(root, 'main-all-buildings.png')
            before = open_editor(lambda e: e.close(), 'editor-same-buildings.png')
            assert app.result == before
            checks.append('Startup: main/editor/SVG show the same 10 footprints; 4 obstacles; cancel preserves result')

            open_editor(lambda e: e.apply())
            wait()
            assert app.result['scene']['buildings'] == before['scene']['buildings']
            assert app.result['routes'] == before['routes']
            assert app.result['plans'] == before['plans']
            check_main()
            before = deepcopy(app.result)
            checks.append('Apply without edits preserves footprints, routes, plans and simulation statistics')

            app.show_building_names.set(True)
            app.risk_layer.set(True)
            app.feature_layer.set(False)
            open_editor(lambda e: e.close())
            app.show_building_names.set(False)
            app.risk_layer.set(False)
            app.feature_layer.set(True)
            app.draw_map()
            checks.append('Editor inherits main-view names, crowd-region and road layer switches')

            def reveal_risk(editor):
                assert not editor.layers['risk_zones'].get()
                editor.set_tool('risk_zones')
                assert editor.layers['risk_zones'].get()
                editor.layers['risk_zones'].set(False)
                editor.select(('risk_zones', editor.document.scene['risk_zones'][0]['id']))
                assert editor.layers['risk_zones'].get()
                editor.close()
            open_editor(reveal_risk)
            checks.append('Selecting/drawing a hidden crowd region reveals its layer without modifying scene data')

            def change(editor, apply):
                editor.document.update('buildings', 'B1', {'x': scene['buildings'][0]['x']+5, 'height': 60})
                if apply:
                    editor.apply()
                else:
                    with patch('tkinter.messagebox.askyesno', return_value=True):
                        editor.close()
            open_editor(lambda e: change(e, False))
            assert app.result == before
            open_editor(lambda e: change(e, True))
            wait()
            changed = check_main()
            assert changed['buildings'][0]['x'] == scene['buildings'][0]['x']+5
            assert changed['buildings'][0]['height'] == 60
            assert len(flight_obstacles(changed)) == 5
            open_editor(lambda e: e.close())
            checks.append('Edit/cancel leaves scene unchanged; edit/apply updates position and height in both views')

            for height in (25, 120):
                app.altitude.set(height)
                app.calculate()
                wait()
                scene = check_main()
                assert len(scene['buildings']) == 10
                b = scene['buildings'][0]
                center = b['x']+b['w']/2, b['y']+b['h']/2
                assert is_blocked(scene, center) == (height == 25)
                open_editor(lambda e: e.close())
            checks.append('25m/120m: all 10 footprints remain visible while height-based routing obstacles change')

            # Import the real Excel template, then verify the editor uses the
            # loaded snapshot even if its path is subsequently unavailable.
            app.load_map(ROOT/'data/地图填写模板.xlsx')
            wait()
            check_main()
            app.scene_path = ROOT/'nonexistent-map-for-snapshot-check.xlsx'
            open_editor(lambda e: e.close())
            checks.append('Excel import: editor uses the loaded in-memory snapshot')

            study = json.loads((ROOT/'results/sites_v1/study.json').read_text(encoding='utf-8'))
            app.show_facility_result(study['results'][0])
            root.update()
            check_main()
            open_editor(lambda e: e.close())
            checks.append('Site result replay: main/editor share the replay scene')

            # A source image remains accessible, with a consistent initial
            # schematic view. Unprocessed drafts still show their background.
            image_scene = create_scene(Config(), ROOT/'cases/user_map_300m/scene.json')
            image_scene['map_presentation'] = 'schematic'
            editor = MapEditor(root, image_scene, Config())
            try:
                root.update()
                assert editor.background is not None and not editor.show_background.get()
                editor.show_background.set(True)
                editor.draw()
                assert editor.photo is not None
            finally:
                editor.window.destroy()
            # Real image-import drafts are also marked schematic. Their
            # unconfirmed scale/height must still keep the original visible.
            image_scene['image_import'] = {'scale_confirmed': False}
            editor = MapEditor(root, image_scene, Config())
            try:
                root.update()
                assert editor.show_background.get()
            finally:
                editor.window.destroy()
            checks.append('Image: schematic editor initially hides source background; toggle and original draft retain it')
            assert not errors, errors
        report = {'passed': True, 'checks': checks, 'tk_callback_errors': errors}
        if args.output:
            (args.output/'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(json.dumps(report, ensure_ascii=True, indent=2))
    finally:
        app.close()


if __name__ == '__main__':
    main()
