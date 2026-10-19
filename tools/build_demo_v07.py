"""Rebuild the V0.7 candidate video from real Tk UI captures and existing footage.

Requires Pillow, ffmpeg/ffprobe on PATH and Windows SAPI Chinese voice. No source
video or existing published result is overwritten. Runtime captures are automated
actions in the actual application; the recorded study is not modified.
"""
from pathlib import Path
from datetime import datetime
from hashlib import sha256
import argparse
import ctypes
import json
import shutil
import subprocess
import sys
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / '参赛材料/演示视频/V0.7候选版'
WORK = ROOT / '.verification/competition_20261018/video'
SOURCE = ROOT / '参赛材料/演示视频/04_成片输出/精简实操版/低空配送仿真_精简实操版_转场优化版.mp4'

def run(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, **kwargs)

def capture():
    sys.path.insert(0, str(ROOT))
    from PIL import ImageGrab
    import tkinter as tk
    from app import Application
    from engine import Config
    study = json.loads((ROOT / 'results/sites_v1/study.json').read_text(encoding='utf-8'))
    manifest = json.loads((ROOT / 'results/sites_v1/manifest.json').read_text(encoding='utf-8'))
    for name, digest in manifest['export_source_sha256'].items():
        if sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            raise ValueError(f'Stored study source has changed: {name}; reproduce before recording')
    root = tk.Tk()
    errors = []
    root.report_callback_exception = lambda kind, value, trace: errors.append(str(value))
    app = Application(root, Config(**study['base_config']), auto_calculate=False)
    app.scene_data = study['scene']
    def grab(window, path):
        root.update()
        hwnd = ctypes.windll.user32.GetAncestor(window.winfo_id(), 2)
        ImageGrab.grab(window=hwnd).convert('RGB').save(path)
    try:
        root.update()
        app.facility_button.invoke()
        w = app.facility_window
        w.study, w.dirty = study, False
        w._show_results()
        w.export_button.configure(state='normal')
        w.replay_button.configure(state='normal')
        w.progressbar.configure(value=100)
        w.tabs.select(w.settings_page)
        w.window.lift()
        root.update()
        time.sleep(.3)
        grab(w.window, WORK / 'settings.png')
        w.tabs.select(w.results_page)
        root.update()
        grab(w.window, WORK / 'results.png')
        w.replay()
        root.lift()
        root.update()
        assert app.result['config']['drone_count'] == 5
        assert app.plan_var.get() == '运行优选'
        for index in range(150):
            # The UI draws actual saved task interpolation for accelerated replay.
            app.seek_time(str(index * 1.5))
            grab(root, WORK / f'replay-{index:04d}.png')
        assert not errors, errors
        for name in ('settings.png', 'results.png', 'replay-0000.png'):
            shutil.copy2(WORK / name, OUT / name)
        return {'study_sha256': sha256((ROOT/'results/sites_v1/study.json').read_bytes()).hexdigest(),
                'manifest_sha256': sha256((ROOT/'results/sites_v1/manifest.json').read_bytes()).hexdigest(),
                'ui_errors': errors, 'capture': 'Actual Tk windows, automated actions; saved evaluation seed replay; simulation time 0 to 223.5 seconds'}
    finally:
        app.close()

def speech():
    sections = [
        '当前版本支持一到二十架无人机。三个设计种子比较正常和高峰，五个独立种子检验冻结后的布局。',
        '这里是同条件三方案结果。高峰距离优先为七百三十一秒，运行优选为七百七十八秒。运行优选并非总是更好。',
        '选中高峰方案，回放已保存的任务。后续展示地图与间距模块，其中综合风险属于旧入口，与当前位置优选分别验证。',
    ]
    for i, txt in enumerate(sections):
        (WORK / f'speech-{i}.txt').write_text(txt, encoding='utf-8-sig')
    ps = r'''param([string]$TaskDirectory)
$ErrorActionPreference = 'Stop'
$voice = New-Object -ComObject SAPI.SpVoice
$token = $voice.GetVoices() | Where-Object { $_.GetDescription() -like '*Huihui*' } | Select-Object -First 1
if (-not $token) { throw 'Chinese Huihui voice is required' }
$voice.Voice = $token
$voice.Rate = 1
0..2 | ForEach-Object {
    $n = $_
    $stream = New-Object -ComObject SAPI.SpFileStream
    $stream.Open((Join-Path $TaskDirectory "speech-$n.wav"), 3, $false)
    $voice.AudioOutputStream = $stream
    [void]$voice.Speak((Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $TaskDirectory "speech-$n.txt")))
    $stream.Close()
}
'''
    (WORK/'speech.ps1').write_text(ps, encoding='utf-8-sig')
    run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', WORK/'speech.ps1', '-TaskDirectory', WORK])
    durations = []
    for i in range(3):
        with wave.open(str(WORK/f'speech-{i}.wav')) as wav:
            durations.append(wav.getnframes()/wav.getframerate() + .8)
    return sections, durations

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--reuse-captures', action='store_true')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:
        raise RuntimeError('ffmpeg and ffprobe are required on PATH')
    capture_record = json.loads((WORK/'capture.json').read_text(encoding='utf-8')) if args.reuse_captures else capture()
    capture_record['capture'] = 'Actual Tk windows, automated actions; saved evaluation seed replay; simulation time 0 to 223.5 seconds'
    (WORK/'capture.json').write_text(json.dumps(capture_record, ensure_ascii=False, indent=2), encoding='utf-8')
    sections, durations = speech()
    captions = [
        '当前 V0.7  起飞点优选｜1—20架，修改后重新计算\n3个设计种子 × 正常/高峰；5个独立评价种子',
        'V0.7 独立评价｜正常/高峰冻结位置与配比\n高峰：距离优先731.00秒；运行优选778.18秒（并非总是更优）',
        'V0.7 已保存高峰任务回放（加速播放）\n后续旧入口用于地图与间距模块验证，与当前位置优选分开报告',
    ]
    segments = []
    for i, (caption, duration) in enumerate(zip(captions, durations)):
        for line, value in enumerate(caption.splitlines()):
            (WORK/f'caption-{i}-{line}.txt').write_text(value, encoding='utf-8')
        video_input = ['-loop', '1', '-i', str(WORK/('settings.png' if i == 0 else 'results.png'))] if i < 2 else ['-framerate', str(150/duration), '-i', str(WORK/'replay-%04d.png')]
        filters = ('scale=1920:880:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:170:color=0x101b2b,'
                   f"drawtext=fontfile='C\\:/Windows/Fonts/msyh.ttc':textfile=caption-{i}-0.txt:fontsize=34:fontcolor=white:x=48:y=20,"
                   f"drawtext=fontfile='C\\:/Windows/Fonts/msyh.ttc':textfile=caption-{i}-1.txt:fontsize=30:fontcolor=white:x=48:y=85")
        path = WORK/f'part-{i}.mp4'
        run([ffmpeg, '-y', '-hide_banner', '-loglevel', 'error', *video_input, '-i', WORK/f'speech-{i}.wav', '-t', str(duration),
             '-vf', filters, '-af', 'apad', '-r', '30', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '48000', '-ac', '2', path], cwd=WORK)
        segments.append(path)
    (WORK/'legacy-caption.txt').write_text('基础模块验证｜旧入口“综合风险”，非当前V0.7运行优选', encoding='utf-8')
    legacy = WORK/'legacy.mp4'
    legacy_filter = ("drawbox=x=0:y=0:w=iw:h=55:color=0x101b2b@0.96:t=fill,"
                     "drawtext=fontfile='C\\:/Windows/Fonts/msyh.ttc':textfile=legacy-caption.txt:fontsize=28:fontcolor=white:x=30:y=10")
    run([ffmpeg, '-y', '-hide_banner', '-loglevel', 'error', '-i', SOURCE, '-vf', legacy_filter, '-r', '30', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '48000', '-ac', '2', legacy], cwd=WORK)
    segments.append(legacy)
    (WORK/'concat.txt').write_text('\n'.join("file '"+x.as_posix().replace("'", "'\\''")+"'" for x in segments), encoding='utf-8')
    final = OUT/'低空配送仿真_V0.7候选演示.mp4'
    run([ffmpeg, '-y', '-hide_banner', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', WORK/'concat.txt', '-c', 'copy', '-movflags', '+faststart', final])
    probe = json.loads(subprocess.check_output([ffprobe, '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(final)], encoding='utf-8'))
    duration = float(probe['format']['duration'])
    assert 180 <= duration <= 300, duration
    assert final.stat().st_size <= 200_000_000
    run([ffmpeg, '-v', 'error', '-i', final, '-f', 'null', '-'])
    record = {'created_at': datetime.now().astimezone().isoformat(), 'file': final.name, 'bytes': final.stat().st_size,
              'duration': duration, 'sha256': sha256(final.read_bytes()).hexdigest(), 'full_decode': 'passed',
              'current_segment_durations': durations, 'narration': sections, 'voice': 'Windows SAPI Microsoft Huihui; synthetic voice',
              'source': str(SOURCE.relative_to(ROOT)), 'source_sha256': sha256(SOURCE.read_bytes()).hexdigest(),
              'source_footage_seconds': 216.233333, 'capture_record': capture_record,
              'note': 'UI captures and source footage are real application output. Historical selection label overlaid throughout legacy segment. No real flight.'}
    (OUT/'技术验收.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT/'媒体参数.json').write_text(json.dumps(probe, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(record, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
