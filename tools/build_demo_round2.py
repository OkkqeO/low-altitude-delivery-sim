"""Build a new candidate MP4 from real diagnostic UI and labeled prior footage.

No original candidate MP4 is overwritten. The screenshots are captured by
capture_decision_ui.py; Windows SAPI provides disclosed synthetic narration.
"""
from datetime import datetime
from hashlib import sha256
import json
from pathlib import Path
import shutil
import subprocess
import sys
import wave

ROOT = Path(__file__).resolve().parents[1]
WORK = ROOT/'.verification/competition_20261019/video'
OUT = ROOT/'参赛材料/演示视频/V0.7第二轮'
SOURCE = ROOT/'参赛材料/演示视频/V0.7候选版/低空配送仿真_V0.7候选演示.mp4'


def run(args, **kwargs):
    return subprocess.run([str(x) for x in args], check=True, **kwargs)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    WORK.mkdir(parents=True, exist_ok=True)
    final = OUT/'低空配送仿真_V0.7第二轮演示.mp4'
    if final.exists():
        raise ValueError('Preserve the existing video; use a new output name before rebuilding')
    capture = json.loads((WORK/'capture.json').read_text(encoding='utf-8'))
    ffmpeg, ffprobe = shutil.which('ffmpeg'), shutil.which('ffprobe')
    if not ffmpeg or not ffprobe:
        raise RuntimeError('ffmpeg and ffprobe are required')
    sections = [
        '这是本轮真实工作台。系统可以离线运行，支持图片、Excel和JSON地图，一到二十架无人机。三个位置方案没有默认选中。设计优选只是设计样本中的选择，原始数据中仍称运行优选。',
        '默认园区正常场景，设计优选平均一百四十三点三五秒，距离优先一百二十三点七一秒。设计优选更慢，但路径暴露更低。四指标诊断显示取舍，不把非劣候选当作普遍最优。这些是原五个种子的评价均值。',
        '再看截图地图原五种子高峰。设计优选准时率百分之四十六，固定位置百分之五十二点三三，设计优选还更慢、暴露更高，因此被基线支配。三方案均没有达到百分之九十研究目标，系统明确不推荐采用任何方案。',
        '这里把研究目标从百分之九十改为四十，仅演示目标敏感性。仿真订单、布局和指标全部不变，设计优选仍然被支配。门槛改变不是性能提升，四十也不是运营承诺。用户需要主动选行才可以回放，导出会保留三个方案及诊断。',
        '即使方案被支配，也允许查看原任务回放，追查具体订单。新增证据解释设计目标首先在哪一级决胜，检验设计种子敏感性，并冻结原布局追加新的二十个种子。它不重新选址，也不证明新优化收益。后面是明确标识的历史基础模块实操。',
        '最后回到当前工作台，实际点击导出完整研究结果。无需选中某一方案，全部候选与原任务都会保留，并写出JSON、CSV和Markdown诊断，便于复核。这是固定高度的研究仿真，真实尺度、楼高和需求仍需核实，尚无真实飞行验证。'
    ]
    captions = [
        'V0.7 第二轮｜实际Tk工作台，主动选行，无默认推荐\n地图导入、1—20架；设计优选 = 原始数据“运行优选”',
        '原5种子｜默认园区正常场景，比较时效与暴露取舍\n143.35秒 vs 123.71秒；暴露更低不代表全面最优',
        '原5种子｜截图地图高峰：设计优选被基线支配\n三方案均未达90%研究目标；不是赛事标准或实测SLA',
        '目标敏感性演示｜90%改40%仅重算诊断\n订单、布局和原始指标不变；不代表性能或安全改善',
        '人工选中后回放已存任务，允许追查被支配方案\n设计留一与新20种子用于验证证据，不宣称新优化收益',
        '实际导出完成｜原研究 + JSON / CSV / Markdown诊断\n保留全部候选与任务；固定高度研究仿真，尚无真实飞行验证'
    ]
    for i, text in enumerate(sections):
        (WORK/f'round2-speech-{i}.txt').write_text(text, encoding='utf-8-sig')
    script = r'''param([string]$TaskDirectory)
$ErrorActionPreference = 'Stop'
$voice = New-Object -ComObject SAPI.SpVoice
$token = $voice.GetVoices() | Where-Object { $_.GetDescription() -like '*Huihui*' } | Select-Object -First 1
if (-not $token) { throw 'Chinese Huihui voice is required' }
$voice.Voice = $token
$voice.Rate = 0
0..5 | ForEach-Object {
    $n = $_
    $stream = New-Object -ComObject SAPI.SpFileStream
    $stream.Open((Join-Path $TaskDirectory "round2-speech-$n.wav"), 3, $false)
    $voice.AudioOutputStream = $stream
    [void]$voice.Speak((Get-Content -Raw -Encoding UTF8 -LiteralPath (Join-Path $TaskDirectory "round2-speech-$n.txt")))
    $stream.Close()
}
'''
    (WORK/'round2-speech.ps1').write_text(script, encoding='utf-8-sig')
    run(['powershell', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', WORK/'round2-speech.ps1', '-TaskDirectory', WORK])
    durations = []
    for i in range(len(sections)):
        with wave.open(str(WORK/f'round2-speech-{i}.wav')) as speech:
            durations.append(speech.getnframes()/speech.getframerate()+1)
    parts = []
    for i, duration in enumerate(durations):
        for line, text in enumerate(captions[i].splitlines()):
            (WORK/f'round2-caption-{i}-{line}.txt').write_text(text, encoding='utf-8')
        source_args = (['-framerate', str(80/duration), '-i', str(WORK/'replay-%04d.png')] if i == 4 else
                       ['-loop', '1', '-i', str(WORK/('normal.png' if i < 2 else 'adverse.png' if i == 2 else 'target.png' if i == 3 else 'export.png'))])
        filter_text = ('scale=1920:880:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:170:color=0x101b2b,'
                       f"drawtext=fontfile='C\\:/Windows/Fonts/msyh.ttc':textfile=round2-caption-{i}-0.txt:expansion=none:fontsize=32:fontcolor=white:x=42:y=20,"
                       f"drawtext=fontfile='C\\:/Windows/Fonts/msyh.ttc':textfile=round2-caption-{i}-1.txt:expansion=none:fontsize=28:fontcolor=white:x=42:y=85")
        path = WORK/f'round2-part-{i}.mp4'
        run([ffmpeg, '-y', '-hide_banner', '-loglevel', 'error', *source_args, '-i', WORK/f'round2-speech-{i}.wav',
             '-t', str(duration), '-vf', filter_text, '-af', 'apad', '-r', '30', '-c:v', 'libx264',
             '-preset', 'veryfast', '-crf', '20', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '48000', '-ac', '2', path], cwd=WORK)
        parts.append(path)
    # Reuse a continuous segment from the prior candidate. Its existing legacy
    # label remains on every frame; it is not presented as the new decision UI.
    previous = json.loads((SOURCE.parent/'技术验收.json').read_text(encoding='utf-8'))
    legacy_start = sum(previous['current_segment_durations'])+1
    legacy_seconds = max(45, 200-sum(durations))
    if legacy_start+legacy_seconds > previous['duration']:
        raise ValueError('Not enough continuous labeled legacy source footage')
    legacy = WORK/'round2-legacy.mp4'
    run([ffmpeg, '-y', '-hide_banner', '-loglevel', 'error', '-ss', str(legacy_start), '-i', SOURCE,
         '-t', str(legacy_seconds), '-r', '30', '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '20',
         '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-ar', '48000', '-ac', '2', legacy])
    # Close on actual current export evidence, after the labeled legacy clip.
    parts.insert(-1, legacy)
    concat = WORK/'round2-concat.txt'
    concat.write_text('\n'.join("file '"+p.as_posix().replace("'", "'\\''")+"'" for p in parts), encoding='utf-8')
    run([ffmpeg, '-y', '-hide_banner', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', concat,
         '-c', 'copy', '-movflags', '+faststart', final])
    probe = json.loads(subprocess.check_output([ffprobe, '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(final)], encoding='utf-8'))
    duration = float(probe['format']['duration'])
    if not 180 <= duration <= 300 or final.stat().st_size > 200_000_000:
        raise ValueError(f'Video limits exceeded: {duration}, {final.stat().st_size}')
    run([ffmpeg, '-v', 'error', '-i', final, '-f', 'null', '-'])
    record = {'created_at': datetime.now().astimezone().isoformat(), 'bytes': final.stat().st_size,
              'duration': duration, 'sha256': sha256(final.read_bytes()).hexdigest(), 'full_decode': 'passed',
              'current_segment_durations': durations, 'narration': sections, 'captions': captions,
              'segment_order': [0, 1, 2, 3, 4, 'labeled_legacy', 5],
              'export_capture': json.loads((WORK/'export_capture.json').read_text(encoding='utf-8')),
              'voice': 'Windows SAPI Microsoft Huihui, synthetic voice', 'capture_record': capture,
              'legacy_source': str(SOURCE.relative_to(ROOT)), 'legacy_source_sha256': sha256(SOURCE.read_bytes()).hexdigest(),
              'legacy_source_start': legacy_start, 'legacy_seconds': legacy_seconds,
              'limits': 'Real software screenshots and accelerated saved task replay; simulated data, no real flights. '
                        '40% target is diagnosis-only sensitivity, not an optimization gain or operating SLA.'}
    (OUT/'技术验收.json').write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    (OUT/'媒体参数.json').write_text(json.dumps(probe, ensure_ascii=False, indent=2), encoding='utf-8')
    shutil.copy2(WORK/'export.png', OUT/'导出完成.png')
    shutil.copy2(WORK/'export_capture.json', OUT/'导出操作核验.json')
    (OUT/'阅读说明.md').write_text('# V0.7第二轮演示视频\n\n当前唯一候选视频为低空配送仿真_V0.7第二轮演示.mp4。'
        '前段为真实Tk诊断工作台与已保存任务回放，默认和截图案例均注明原5评价种子。'
        '90%是可调研究目标，40%只是敏感性演示，改目标不改变订单、布局或指标。'
        '中后段从上轮视频连续截取且全程保留旧入口标识，展示基础模块，不当作当前选址收益。结尾回到实际Tk导出完成界面；目录选择由脚本自动提供，产品实际写出原研究与三种诊断，保存研究逐项相等且源文件未变。\n\n'
        'AI辅助包括代码、录制与剪辑脚本、说明材料；旁白为Windows Huihui合成语音。'
        '界面截图来自实际Tk程序，回放使用保存的模拟任务，不是新计算或真实飞行。'
        '视频时长、段落、原片来源及哈希见技术验收.json。\n', encoding='utf-8')
    print(json.dumps(record, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
