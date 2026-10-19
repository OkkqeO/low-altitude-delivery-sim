"""Diagnose a saved study without changing its simulation, choices or source file."""
import argparse
import gzip
from hashlib import sha256
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from decision_support import diagnose_site_study, export_decision_diagnostics


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--study', type=Path, required=True, help='Existing V0.7 study.json or study.json.gz')
    parser.add_argument('--output', type=Path, required=True, help='A new empty output directory')
    parser.add_argument('--minimum-on-time-rate', type=float, default=.90,
                        help='Research service target as a fraction from 0 to 1, default .90; not an official threshold')
    args = parser.parse_args()
    if args.output.exists() and any(args.output.iterdir()):
        parser.error('Output must be empty so earlier evidence is preserved')
    original = args.study.read_bytes()
    study = json.loads((gzip.decompress(original) if args.study.suffix == '.gz' else original).decode('utf-8-sig'))
    diagnostics = diagnose_site_study(study, args.minimum_on_time_rate)
    export_decision_diagnostics(study, args.output, args.minimum_on_time_rate)
    source_hash = sha256(original).hexdigest()
    if sha256(args.study.read_bytes()).hexdigest() != source_hash:
        raise RuntimeError('Source study changed during diagnosis')
    (args.output/'source_provenance.json').write_text(json.dumps({
        'source': str(args.study.resolve()), 'sha256': source_hash,
        'source_unchanged': True, 'simulation_recomputed': False,
        'selected_layouts_changed': False,
        'minimum_on_time_rate': args.minimum_on_time_rate,
        'scope': 'Evaluation-set diagnosis only; no new algorithm or independent future gain claim'
    }, ensure_ascii=False, indent=2), encoding='utf-8')
    for scenario in diagnostics['scenarios']:
        print(f"{scenario['scenario_name']}：{scenario['message']}")
    print(f'诊断已保存：{args.output.resolve()}；原研究未改变')


if __name__ == '__main__':
    main()
