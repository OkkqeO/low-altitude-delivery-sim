"""Verify a prepared candidate archive, extract safely, run core without packages.

No uploads or permanent filesystem changes outside the requested result log.
"""
from datetime import datetime, timezone, timedelta
from hashlib import sha256
import argparse
import csv
import json
from pathlib import Path, PurePosixPath
import subprocess
import sys
import tempfile
from zipfile import ZipFile

def hashed(path):
    h = sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            h.update(block)
    return h.hexdigest()

def extract_checked(archive_path, destination):
    with ZipFile(archive_path) as archive:
        if archive.testzip() is not None:
            raise ValueError('ZIP CRC check failed')
        names = set()
        for info in archive.infolist():
            name = info.filename
            if PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts or ':' in name or '\\' in name:
                raise ValueError(f'Unsafe archive path: {name}')
            normalized = PurePosixPath(name).as_posix().rstrip('/').casefold()
            if normalized in names:
                raise ValueError(f'Duplicate archive path: {name}')
            names.add(normalized)
            target = (destination/name).resolve()
            if destination.resolve() not in target.parents and target != destination.resolve():
                raise ValueError(f'Escaping archive path: {name}')
        archive.extractall(destination)

def assert_manifest(base, records):
    if not isinstance(records, list) or not records:
        raise ValueError('Manifest must enumerate a nonempty list of files')
    seen = set()
    for row in records:
        name = row['path']
        if not isinstance(name, str) or PurePosixPath(name).is_absolute() or '..' in PurePosixPath(name).parts or ':' in name or '\\' in name:
            raise ValueError(f'Unsafe manifest path: {name}')
        normalized = PurePosixPath(name).as_posix()
        if normalized.casefold() in seen:
            raise ValueError(f'Duplicate manifest path: {name}')
        seen.add(normalized.casefold())
        path = (base/row['path']).resolve()
        if base.resolve() not in path.parents:
            raise ValueError('Manifest path escaped extraction root')
        if not path.is_file() or path.stat().st_size != row['bytes'] or hashed(path) != row['sha256']:
            raise ValueError(f'Manifest mismatch: {row["path"]}')
    return seen

def assert_inventory(base, expected, excluded=()):
    actual = {p.relative_to(base).as_posix().casefold() for p in base.rglob('*') if p.is_file()}
    actual -= {name.casefold() for name in excluded}
    if actual != expected:
        raise ValueError(f'Archive and manifest inventories differ: unlisted={sorted(actual-expected)}, missing={sorted(expected-actual)}')

def assert_hash_map(base, entries):
    if not isinstance(entries, dict) or not entries:
        raise ValueError('Research hash map must not be empty')
    for relative, digest in entries.items():
        path = (base/relative).resolve()
        if base.resolve() not in path.parents or not path.is_file() or hashed(path) != digest:
            raise ValueError(f'Research evidence hash mismatch: {relative}')

def assert_decision_evidence(project, previous_manifest):
    evidence = project/'results/decision_v07_round2'
    manifest = json.loads((evidence/'manifest.json').read_text(encoding='utf-8'))
    protocol_path = project/manifest['protocol_path']
    if protocol_path.resolve() != (project/'docs/参赛验收/第二轮实验协议.json').resolve():
        raise ValueError('Unexpected decision protocol path')
    if hashed(protocol_path) != manifest['protocol_sha256']:
        raise ValueError('Frozen decision protocol hash mismatch')
    protocol = json.loads(protocol_path.read_text(encoding='utf-8'))
    frozen = datetime.fromisoformat(protocol['frozen_at_beijing'])
    started = datetime.fromisoformat(manifest['evaluation_started_at_beijing'])
    finished = datetime.fromisoformat(manifest['evaluation_finished_at_beijing'])
    if not frozen < started <= finished:
        raise ValueError('Decision protocol was not frozen before evaluation')
    for field in ('core_source_sha256', 'rule_source_sha256'):
        if protocol[field] != manifest[field]:
            raise ValueError(f'Decision source provenance differs from protocol: {field}')
        assert_hash_map(project, manifest[field])
    seeds = manifest['new_evaluation_seeds']
    if len(seeds) != len(set(seeds)) or set(seeds) & set(previous_manifest['new_evaluation_seeds']):
        raise ValueError('New decision seeds duplicate or overlap previous evaluation')
    for case in protocol['cases'].values():
        assert_hash_map(project, {case['source_study']: case['source_study_sha256']})
        if case['new_evaluation_seeds'] != seeds or set(seeds) & set(case['design_seeds']):
            raise ValueError('Decision seed split differs from protocol')
    for field in ('old_source_studies_unchanged', 'diagnostic_did_not_mutate_studies'):
        if manifest[field] is not True:
            raise ValueError(f'Decision provenance check did not pass: {field}')
    assert_hash_map(evidence, manifest['output_sha256'])
    assert_inventory(evidence, {name.casefold() for name in manifest['output_sha256']}, ('manifest.json',))
    with (evidence/'raw_metrics.csv').open(encoding='utf-8-sig', newline='') as stream:
        count = sum(1 for _ in csv.DictReader(stream))
    if count != protocol['expected_new_plan_runs'] or count != manifest['new_plan_runs']:
        raise ValueError('Decision raw run count differs from frozen protocol')
    if manifest['new_task_records_including_repeats'] != protocol['expected_new_task_records_including_repeats']:
        raise ValueError('Decision task count differs from protocol')
    with (evidence/'design_seed_stats.csv').open(encoding='utf-8-sig', newline='') as stream:
        design_runs = sum(1 for _ in csv.DictReader(stream))
    if design_runs != protocol['design_stability']['expected_layout_runs']:
        raise ValueError('Design sensitivity replay count differs from protocol')
    return {'check': 'round2 frozen protocol, source studies, rule/core and all output hashes, separate seeds and run counts',
            'status': 'passed', 'new_plan_runs': count, 'design_layout_runs': design_runs,
            'protocol_sha256': manifest['protocol_sha256']}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('archive', type=Path)
    parser.add_argument('--log', type=Path, required=True)
    args = parser.parse_args()
    if args.archive.stat().st_size > 400_000_000:
        parser.error('Candidate archive exceeds conservative 400MB limit')
    checks = []
    with tempfile.TemporaryDirectory(prefix='uav_candidate_') as temporary:
        work = Path(temporary)
        extract_checked(args.archive, work/'outer')
        entries = list((work/'outer').iterdir())
        if len(entries) != 1 or not entries[0].is_dir():
            raise ValueError('Expected one submission folder')
        folder = entries[0]
        manifest = json.loads((folder/'候选文件清单.json').read_text(encoding='utf-8'))
        outer_inventory = assert_manifest(folder, manifest['files'])
        assert_inventory(folder, outer_inventory, ('候选文件清单.json',))
        checks.append({'check': 'outer archive hashes', 'files': len(manifest['files']), 'status': 'passed'})
        extract_checked(folder/'附件支撑材料.zip', work/'support')
        source_manifest = json.loads((work/'support/文件清单.json').read_text(encoding='utf-8'))
        source_inventory = assert_manifest(work/'support', source_manifest)
        assert_inventory(work/'support', source_inventory, ('文件清单.json', '先读我.txt'))
        checks.append({'check': 'support archive hashes', 'files': len(source_manifest), 'status': 'passed'})
        project = work/'support/Python项目'
        from prepare_submission import REQUIRED_SUPPORT, DECISION_REQUIRED_SUPPORT, TITLE
        decision = manifest.get('decision_diagnostics', False)
        for relative in REQUIRED_SUPPORT + (DECISION_REQUIRED_SUPPORT if decision else ()):
            if ('Python项目/'+relative).casefold() not in source_inventory:
                raise ValueError(f'Required packaged technical source missing: {relative}')
        sites = project/'results/sites_v1'
        sites_manifest = json.loads((sites/'manifest.json').read_text(encoding='utf-8'))
        assert_hash_map(project, sites_manifest['export_source_sha256'])
        if hashed(sites/'scene.json') != sites_manifest['scene_sha256']:
            raise ValueError('Packaged V0.7 default scene hash mismatch')
        holdout = project/'results/competition_v07'
        holdout_manifest = json.loads((holdout/'manifest.json').read_text(encoding='utf-8'))
        for field in ('source_sha256', 'source_study_sha256'):
            assert_hash_map(project, holdout_manifest[field])
        assert_hash_map(holdout, holdout_manifest['output_sha256'])
        assert_inventory(holdout, {name.casefold() for name in holdout_manifest['output_sha256']}, ('manifest.json',))
        checks.append({'check': 'packaged V0.7 source, scene, frozen-study and output research hashes', 'status': 'passed'})
        if decision:
            checks.append(assert_decision_evidence(project, holdout_manifest))
            profile = json.loads((project/'参赛材料/提交配置.json').read_text(encoding='utf-8-sig'))
            if profile.get('decision_diagnostics') is not True or profile['edition'] != manifest['edition']:
                raise ValueError('Candidate edition differs from packaged submission profile')
            artifacts = json.loads((project/'docs/参赛验收/材料证据/第二轮/final-artifacts.json').read_text(encoding='utf-8'))
            assert_manifest(project, artifacts['deliverables']+artifacts['sources'])
            report_name = TITLE+'+'+(profile.get('contact_name') or '联系人待填')+'.pdf'
            for key, outer_name in [('main_report', report_name), ('information_form', '作品信息表.pdf'),
                                    ('commitment_template', '诚信承诺书_待全员手写签字.pdf'),
                                    ('defense_pdf', '答辩材料_V0.7候选版.pdf'),
                                    ('defense_pptx', '答辩材料_V0.7可编辑.pptx')]:
                source = (project/profile[key]).resolve()
                if project.resolve() not in source.parents or hashed(source) != hashed(folder/outer_name):
                    raise ValueError(f'Top-level material differs from packaged source: {key}')
            video_record_path = (project/Path(profile['video']).parent/'技术验收.json').resolve()
            if project.resolve() not in video_record_path.parents:
                raise ValueError('Video record escaped extracted project')
            video_record = json.loads(video_record_path.read_text(encoding='utf-8'))
            if hashed(folder/'演示视频_V0.7候选版.mp4') != video_record['sha256']:
                raise ValueError('Current video differs from its reviewed technical record')
            if artifacts['video_index']['sha256'] != video_record['sha256']:
                raise ValueError('Current video differs from final material index')
            assert_hash_map(project, {video_record['legacy_source']: video_record['legacy_source_sha256']})
            checks.append({'check': 'current profile/material copies and video review identity, retained historical production source', 'status': 'passed'})
        runs = []
        for scene, label in [('data/demo_scene.json', 'json'), ('data/地图填写模板.xlsx', 'excel')]:
            output = work/f'run_{label}'
            command = [sys.executable, '-X', 'utf8', '-S', 'run.py', '--mode', 'single', '--orders', '6', '--scene', scene, '--output', str(output)]
            proc = subprocess.run(command, cwd=project, capture_output=True, encoding='utf-8', timeout=180)
            if proc.returncode:
                raise RuntimeError(proc.stdout+'\n'+proc.stderr)
            result = json.loads((output/'result.json').read_text(encoding='utf-8'))
            runs.append(result)
            checks.append({'check': f'extracted project standard-library {label} single run', 'status': 'passed', 'stdout': proc.stdout})
        for key in runs[0]['plans']:
            if runs[0]['plans'][key]['jobs'] != runs[1]['plans'][key]['jobs'] or runs[0]['plans'][key]['stats'] != runs[1]['plans'][key]['stats']:
                raise ValueError('JSON and Excel default scenes produced different task/metric results')
        checks.append({'check': 'extracted JSON/Excel task and metric equivalence', 'status': 'passed'})
        command = [sys.executable, '-X', 'utf8', '-S', 'run.py', '--mode', 'sites', '--orders', '6',
                   '--design-seed-count', '1', '--seeds', '20261015', '--output', str(work/'sites_smoke')]
        proc = subprocess.run(command, cwd=project, capture_output=True, encoding='utf-8', timeout=180)
        if proc.returncode:
            raise RuntimeError(proc.stdout+'\n'+proc.stderr)
        smoke = json.loads((work/'sites_smoke/study.json').read_text(encoding='utf-8'))
        if smoke['version'] != '0.7.0-sites' or len(smoke['raw_metrics']) != 6 or set(smoke['choices']) != {'fixed', 'distance', 'combined'}:
            raise ValueError('Minimal extracted V0.7 CLI smoke did not produce both scenarios and three plans')
        checks.append({'check': 'extracted standard-library V0.7 CLI smoke (6 orders, one design/evaluation seed; not the research reproduction)',
                       'status': 'passed', 'stdout': proc.stdout})
        proc = subprocess.run([sys.executable, '-X', 'utf8', '-S', 'cases/verify_sites_gui.py'], cwd=project, capture_output=True, encoding='utf-8', timeout=180)
        if proc.returncode:
            raise RuntimeError(proc.stdout+'\n'+proc.stderr)
        checks.append({'check': 'extracted actual Tk GUI standard-library smoke', 'status': 'passed', 'stdout': proc.stdout})
        if decision:
            for case in ('demo_5', 'user_map_h30_d5'):
                output = work/f'decision_{case}'
                source = project/f'results/decision_v07_round2/studies/{case}.json.gz'
                source_hash = hashed(source)
                command = [sys.executable, '-X', 'utf8', '-S', 'tools/diagnose_study.py',
                           '--study', str(source), '--output', str(output), '--minimum-on-time-rate', '.90']
                proc = subprocess.run(command, cwd=project, capture_output=True, encoding='utf-8', timeout=180)
                if proc.returncode:
                    raise RuntimeError(proc.stdout+'\n'+proc.stderr)
                expected = project/f'results/decision_v07_round2/{case}'
                for name in ('decision_diagnostics.json', 'decision_comparisons.csv', 'decision_diagnostics.md'):
                    if (output/name).read_bytes() != (expected/name).read_bytes():
                        raise ValueError(f'Extracted decision CLI differs from stored result: {case}/{name}')
                provenance = json.loads((output/'source_provenance.json').read_text(encoding='utf-8'))
                if hashed(source) != source_hash or provenance['sha256'] != source_hash or provenance['source_unchanged'] is not True:
                    raise ValueError('Decision CLI changed frozen source study')
            checks.append({'check': 'extracted standard-library decision CLI, both new cohorts byte-identical diagnostics and unchanged sources', 'status': 'passed'})
            proc = subprocess.run([sys.executable, '-X', 'utf8', '-S', 'cases/verify_decision_gui.py'],
                                  cwd=project, capture_output=True, encoding='utf-8', timeout=180)
            if proc.returncode:
                raise RuntimeError(proc.stdout+'\n'+proc.stderr)
            checks.append({'check': 'extracted actual Tk decision GUI: manual choice, target changes, invalid input, dominated replay and export',
                           'status': 'passed', 'stdout': proc.stdout})
    record = {'checked_at_beijing': datetime.now(timezone(timedelta(hours=8))).isoformat(),
              'archive': str(args.archive.resolve()), 'archive_bytes': args.archive.stat().st_size,
              'archive_sha256': hashed(args.archive), 'checks': checks,
              'limitations': 'Same Windows/Python host, temporary extracted checkout; not a second computer or Python 3.10 certification; administration/signature/upload still pending.'}
    args.log.parent.mkdir(parents=True, exist_ok=True)
    args.log.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(record, ensure_ascii=False, indent=2))

if __name__ == '__main__':
    main()
