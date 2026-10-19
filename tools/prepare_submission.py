"""Create a reviewable candidate submission and a portable support attachment.

Standard library only; never registers, uploads, signs, or invents identity.
Use an empty --output directory for each reviewed snapshot. Files in the working
project are copied, not moved, and previous candidate archives are preserved.
"""
import argparse
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from zipfile import ZipFile, ZIP_DEFLATED, ZIP_STORED

ROOT = Path(__file__).resolve().parents[1]
LIMIT_PACKAGE = 400_000_000
LIMIT_VIDEO = 200_000_000
LIMIT_DEFENSE = 100_000_000
TITLE = '面向园区末端配送的低空风险仿真与起降场选址系统'
REQUIRED_SUPPORT = (
    'run.py', 'engine.py', 'site_selection.py', 'site_ui.py', 'airspace.py',
    'reporting.py', 'app.py', 'ui.py', 'display.py', 'map_import.py',
    'data/demo_scene.json', 'data/地图填写模板.xlsx',
    'tests/test_engine.py', 'tests/test_site_selection.py', 'tests/test_continuous_audit.py',
    'cases/verify_sites_gui.py', 'cases/verify_continuous_model.py',
    'cases/run_competition_holdout.py', 'cases/audit_sites_reproduction.py',
    'cases/audit_air_ground_boundary.py', 'cases/user_map_300m/scene.json',
    'docs/参赛验收/技术验证.md', 'docs/参赛验收/技术证据/full_tests_round2.txt',
    'docs/参赛验收/技术证据/sites_audit_round1.json',
    'docs/参赛验收/技术证据/boundary_audit_round1.json',
    'results/sites_v1/study.json', 'results/sites_v1/manifest.json',
    'results/sites_v1/scene.json', 'results/sites_v1/raw_metrics.csv', 'results/sites_v1/summary.csv',
    'results/user_map_300m/studies/h30_d5.json.gz',
    'results/competition_v07/manifest.json', 'results/competition_v07/raw_metrics.csv',
    'results/competition_v07/paired_differences.csv', 'results/competition_v07/difference_summary.csv',
    'results/competition_v07/frozen_designs.json', 'results/competition_v07/independent_audit.json',
    'results/competition_v07/studies/demo_5.json.gz',
    'results/competition_v07/studies/user_map_h30_d5.json.gz',
)
DECISION_REQUIRED_SUPPORT = (
    'decision_support.py', 'tests/test_decision_support.py',
    'cases/verify_decision_gui.py', 'cases/run_decision_validation.py',
    'tools/diagnose_study.py', 'tools/capture_decision_ui.py', 'tools/capture_decision_export.py', 'tools/build_demo_round2.py',
    'docs/参赛验收/第二轮独立评审.md', 'docs/参赛验收/第二轮独立复审.md',
    'docs/参赛验收/第二轮实验协议.json', 'docs/参赛验收/第二轮技术验证.md',
    'docs/参赛验收/第二轮材料验证.md', 'docs/参赛验收/第二轮交付与验收.md',
    'docs/参赛验收/官网复核20261019.md',
    'docs/参赛验收/材料证据/第二轮/final-artifacts.json',
    'docs/参赛验收/技术证据/第二轮独立诊断核验.json',
    'docs/参赛验收/技术证据/第二轮独立研究核验.json',
    'docs/参赛验收/技术证据/第二轮独立R13命令核验.json',
    'docs/参赛验收/技术证据/第二轮独立视频核验.json',
    'docs/参赛验收/第二轮证据/full_tests_decision_round2.txt',
    'results/decision_v07_round2/manifest.json',
    'results/decision_v07_round2/raw_metrics.csv',
    'results/decision_v07_round2/paired_differences.csv',
    'results/decision_v07_round2/difference_summary.csv',
    'results/decision_v07_round2/design_stability.json',
    'results/decision_v07_round2/design_seed_stats.csv',
    'results/decision_v07_round2/design_subset_candidate_scores.csv',
    'results/decision_v07_round2/independent_diagnostic_audit.json',
    'results/decision_v07_round2/independent_trajectory_audit.json',
    'results/decision_v07_round2/studies/demo_5.json.gz',
    'results/decision_v07_round2/studies/user_map_h30_d5.json.gz',
    'results/decision_v07_round2/demo_5/decision_diagnostics.json',
    'results/decision_v07_round2/user_map_h30_d5/decision_diagnostics.json',
)

def digest(path):
    h = sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()

def safe_piece(text):
    if not text or any(c in text for c in '<>:"/\\|?*') or text.endswith((' ', '.')):
        raise ValueError(f'Invalid directory component: {text!r}')
    return text

def source_files():
    result = set()
    for p in ROOT.iterdir():
        if p.is_file() and (p.suffix.lower() in {'.py', '.cmd', '.ps1'} or p.name.startswith('requirements') or p.name in {'README.md', '低空配送仿真项目参赛实施方案.md'}):
            result.add(p)
    for directory in ('data', 'docs', 'tests', 'cases', 'matlab', 'tools'):
        for current, subdirectories, filenames in os.walk(ROOT/directory, followlinks=False):
            # Material builders may use a local junction to a bundled runtime.
            # Carry source/dependency declarations, not caches or installed npm
            # packages (which can point outside this project).
            subdirectories[:] = [name for name in subdirectories
                                  if name not in {'node_modules', '__pycache__', '.venv', '.git'}]
            for filename in filenames:
                p = Path(current)/filename
                if p.is_file() and p.suffix not in {'.pyc', '.pyo'}:
                    result.add(p)
    for directory in ('batch', 'safety', 'sites_v1', 'facility_v1', 'competition_v07', 'decision_v07_round2'):
        for p in (ROOT/'results'/directory).rglob('*'):
            if p.is_file():
                result.add(p)
    for p in (ROOT/'results/user_map_300m').rglob('*'):
        relative = p.relative_to(ROOT/'results/user_map_300m')
        if p.is_file() and (len(relative.parts) == 1 or relative.parts[0] == 'studies'):
            result.add(p)
    # Editable materials, charts and their exact data; omit historical alternative
    # decks to give reviewers a single current defense choice.
    for directory in ('参赛材料/主报告', '参赛材料/独立表单', '参赛材料/演示视频/V0.7候选版'):
        result.update(p for p in (ROOT/directory).rglob('*') if p.is_file() and p.suffix.lower() != '.mp4')
    for directory in ('参赛材料/答辩PPT/增强版验证数据',):
        result.update(p for p in (ROOT/directory).rglob('*') if p.is_file() and p.suffix != '.pyc')
    result.update((ROOT/'参赛材料').glob('*.md'))
    result.update(p for p in (ROOT/'参赛材料/答辩PPT').glob('*.md') if p.name not in {'阅读说明.md', '增强版阅读说明.md'})
    for evidence in (ROOT/'.verification/competition_20261018', ROOT/'.verification/competition_20261019'):
        if not evidence.exists():
            continue
        for p in evidence.iterdir():
            # Archive-specific receipts belong beside that exact snapshot. They
            # cannot sign a future archive or be embedded in the archive they hash.
            if p.is_file() and not p.name.startswith('package_verification') and p.suffix.lower() in {'.txt', '.json', '.csv', '.py', '.png'}:
                result.add(p)
        for p in (evidence/'official').glob('*.txt'):
            result.add(p)
        if (evidence/'official/fetch_log.json').exists():
            result.add(evidence/'official/fetch_log.json')
    return sorted(result, key=lambda p: p.relative_to(ROOT).as_posix())

def unfinished(profile):
    items = []
    for key, label in [('group', '学历组别未核实'), ('contact_name', '联系人姓名未填'), ('contact_phone', '联系电话未填'), ('contact_email', '联系邮箱未填')]:
        if not profile.get(key):
            items.append(label)
    if not 1 <= len(profile.get('members', [])) <= 5:
        items.append('真实成员资料及排序未补齐')
    if not 1 <= len(profile.get('teachers', [])) <= 2:
        items.append('学生参赛须1—2名在校指导教师，真实资料未补齐')
    if not profile.get('signed_commitment_pdf'):
        items.append('全体成员手写签字扫描PDF未提供；报告内目前仅为待签页')
    if not profile.get('human_review_and_rights_confirmation'):
        items.append('本人尚需完成模型/AI辅助内容审核、图源与使用权限核实')
    if not profile.get('baidu_permanent_share_url'):
        items.append('永久百度网盘链接后置，未视为已完成')
    if not profile.get('registration_receipt'):
        items.append('报名与系统上传后置，无正式提交回执')
    return items

def support_sources(files, config, decision_diagnostics=False):
    # Configured editable inputs may be anywhere inside the project, rather than
    # only under the default material directories. Keep every selected source.
    selected = set(source_files()) | {p for key, p in files.items() if key != 'video'} | {config}
    selected.update(p for p in files['video'].parent.rglob('*') if p.is_file() and p.suffix.lower() in {'.md', '.json', '.png'})
    if decision_diagnostics:
        video_record = json.loads((files['video'].parent/'技术验收.json').read_text(encoding='utf-8'))
        if digest(files['video']) != video_record['sha256']:
            raise ValueError('Selected video differs from its technical review record')
        legacy_source = (ROOT/video_record['legacy_source']).resolve()
        if ROOT not in legacy_source.parents or not legacy_source.is_file() or digest(legacy_source) != video_record['legacy_source_sha256']:
            raise ValueError('Historical video source required to reproduce the current edit is missing or changed')
        # A labeled production input inside support, not another current video at
        # the top level. Capture/rebuild scripts can reproduce the complete edit.
        selected.add(legacy_source)
    required = REQUIRED_SUPPORT + (DECISION_REQUIRED_SUPPORT if decision_diagnostics else ())
    for relative in required:
        expected = ROOT/relative
        if not expected.is_file() or expected not in selected:
            raise ValueError(f'Missing required technical support source: {relative}')
    for source in selected:
        if ROOT not in source.resolve().parents or not source.is_file():
            raise ValueError(f'Missing or unsafe support source: {source}')
    return selected

def verify_zip(path):
    with ZipFile(path) as archive:
        bad = archive.testzip()
        if bad:
            raise ValueError(f'Corrupt ZIP member: {bad}')
        for name in archive.namelist():
            if name.startswith(('/', '\\')) or '..' in Path(name).parts or ':' in name:
                raise ValueError(f'Unsafe ZIP path: {name}')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=ROOT/'参赛材料/提交配置.json')
    parser.add_argument('--output', type=Path, default=ROOT/'dist/候选提交包_20261019_第二轮')
    parser.add_argument('--check-only', action='store_true', help='Validate selected source paths and video without creating a package')
    args = parser.parse_args()
    config = args.config.resolve()
    if ROOT not in config.parents or not config.is_file():
        parser.error('Config must be an existing file inside this project so it can be carried in the attachment.')
    profile = json.loads(config.read_text(encoding='utf-8-sig'))
    output = args.output.resolve()
    if output.exists() and any(output.iterdir()):
        parser.error('Output must be empty: use a new directory to preserve reviewed snapshots.')
    if ROOT == output or ROOT in output.parents and output.relative_to(ROOT).parts[0] not in {'dist', 'build'}:
        parser.error('Output inside this project must be in dist/ or build/.')
    keys = ['main_report', 'editable_report', 'information_form', 'editable_information_form', 'commitment_template', 'defense_pdf', 'defense_pptx', 'video']
    files = {}
    for key in keys:
        path = (ROOT/profile[key]).resolve()
        if ROOT not in path.parents or not path.is_file():
            parser.error(f'Missing or unsafe source {key}: {path}')
        files[key] = path
    if files['video'].suffix.lower() != '.mp4':
        parser.error('Selected demonstration must have the official .mp4 extension')
    if files['defense_pdf'].stat().st_size > LIMIT_DEFENSE or files['video'].stat().st_size > LIMIT_VIDEO:
        parser.error('Official defense/video size limit exceeded')
    probe_tool = shutil.which('ffprobe')
    if not probe_tool:
        parser.error('ffprobe is required to independently check actual video duration before packaging')
    probe = json.loads(subprocess.check_output([probe_tool, '-v', 'error', '-show_format', '-show_streams', '-of', 'json', str(files['video'])], encoding='utf-8'))
    if 'mp4' not in probe['format'].get('format_name', '').split(',') or not any(
            stream.get('codec_type') == 'video' and stream.get('width', 0) > 0 and stream.get('height', 0) > 0
            for stream in probe.get('streams', [])):
        parser.error('Selected MP4 must contain an actual video stream')
    duration = float(probe['format']['duration'])
    if not 180 <= duration <= 300:
        parser.error(f'Video duration outside 3–5 minutes: {duration}')
    missing = unfinished(profile)
    try:
        planned_sources = support_sources(files, config, profile.get('decision_diagnostics', False))
    except ValueError as error:
        parser.error(str(error))
    if args.check_only:
        print(json.dumps({'status': 'source preflight only; no archive created', 'selected': {k: str(p.relative_to(ROOT)) for k, p in files.items()},
                          'support_source_files': len(planned_sources), 'support_uncompressed_bytes': sum(p.stat().st_size for p in planned_sources),
                          'video_seconds': duration, 'pending': missing}, ensure_ascii=False, indent=2))
        return
    output.mkdir(parents=True, exist_ok=True)
    contact = safe_piece(profile.get('contact_name') or '联系人待填')
    folder = output / (safe_piece(profile['institution']) + '+' + safe_piece(TITLE) + '+' + contact + '_候选未签')
    folder.mkdir()
    report_name = f'{TITLE}+{contact}.pdf'
    top_files = {
        report_name: files['main_report'], '作品信息表.pdf': files['information_form'],
        '诚信承诺书_待全员手写签字.pdf': files['commitment_template'],
        '答辩材料_V0.7候选版.pdf': files['defense_pdf'], '答辩材料_V0.7可编辑.pptx': files['defense_pptx'],
        '演示视频_V0.7候选版.mp4': files['video'],
    }
    for name, source in top_files.items():
        shutil.copy2(source, folder/name)
    support = folder/'附件支撑材料.zip'
    source_manifest = []
    with ZipFile(support, 'w', compression=ZIP_DEFLATED, compresslevel=6) as archive:
        for source in sorted(planned_sources):
            name = source.relative_to(ROOT).as_posix()
            target = 'Python项目/' + name
            archive.write(source, target, compress_type=ZIP_STORED if source.suffix in {'.gz', '.mp4'} else ZIP_DEFLATED)
            source_manifest.append({'path': target, 'bytes': source.stat().st_size, 'sha256': digest(source)})
        archive.writestr('文件清单.json', json.dumps(source_manifest, ensure_ascii=False, indent=2))
        archive.writestr('先读我.txt', '本附件包含Python项目、原始实验、测试与验证证据。先读Python项目/README.md、docs/参赛验收/技术验证.md及第二轮技术验证.md。第二轮决策诊断不改变原模拟/选址算法。核心和Excel仅需Python3.10+含Tkinter；图片功能选装requirements-image.txt。历史facility仅作档案；当前主线sites。表单/签字与外部报名仍待本人完成。完整解压后在Python项目目录启动。')
    verify_zip(support)
    created = datetime.now(timezone(timedelta(hours=8))).isoformat()
    notes = '# 候选包说明\n\n本目录为项目与材料复核快照，尚非完成报名或正式提交。\n\n唯一当前答辩和视频均由提交配置指定；主报告内包含待填写信息表及待签承诺书，独立表单另存。第二轮新增评价后决策诊断：可调研究准时率目标、四指标比较与基线差；原模拟/选址算法不变，不代表获得新优化收益。\n\n未完成事项：\n\n' + '\n'.join('- '+x for x in missing) + '\n\n正式提交前须由本人补齐资料、真实手写签字并重新合并报告、核对命名，执行最新清单与官方通知核查。国奖没有公开量化通过线，本轮评审不保证获奖。\n'
    (folder/'候选包说明.md').write_text(notes, encoding='utf-8')
    manifest = {'created_at_beijing': created, 'status': '候选未签，外部报名与上传暂缓', 'version': profile['project_version'],
                'institution': profile['institution'], 'official_deadline_beijing': '2026-10-22T20:00:00+08:00',
                'edition': profile.get('edition', '20261018'), 'decision_diagnostics': profile.get('decision_diagnostics', False),
                'video_seconds': duration, 'pending': missing, 'files': []}
    for path in sorted(folder.iterdir()):
        if path.is_file():
            manifest['files'].append({'path': path.name, 'bytes': path.stat().st_size, 'sha256': digest(path)})
    (folder/'候选文件清单.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    final = output/(folder.name+'.zip')
    with ZipFile(final, 'w', compression=ZIP_DEFLATED, compresslevel=6) as archive:
        for path in sorted(folder.iterdir()):
            archive.write(path, folder.name+'/'+path.name, compress_type=ZIP_STORED if path.suffix in {'.zip', '.mp4'} else ZIP_DEFLATED)
    verify_zip(final)
    if final.stat().st_size > LIMIT_PACKAGE:
        raise ValueError(f'Package exceeds conservative 400MB limit: {final.stat().st_size}')
    receipt = {'archive': str(final), 'bytes': final.stat().st_size, 'sha256': digest(final), 'zip_integrity': 'passed',
               'support_files': len(source_manifest), 'support_bytes': support.stat().st_size, 'video_seconds': duration, 'pending': missing}
    (output/'合包验证.json').write_text(json.dumps(receipt, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(receipt, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
