"""Read-only, standard-library verification of the frozen round-two artifacts."""
from datetime import datetime, timezone, timedelta
from pathlib import Path
import csv
import gzip
import hashlib
import json
import math
import statistics
import sys

ROOT = Path(__file__).resolve().parents[3]
RESULTS = ROOT / "results/decision_v07_round2"


def read(path):
    return json.loads(path.read_text(encoding="utf-8-sig"))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def rows(path):
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def main():
    manifest = read(RESULTS / "manifest.json")
    protocol_path = ROOT / manifest["protocol_path"]
    protocol = read(protocol_path)
    assert sha(protocol_path) == manifest["protocol_sha256"]
    assert datetime.fromisoformat(protocol["frozen_at_beijing"]) < datetime.fromisoformat(manifest["evaluation_started_at_beijing"])
    hashes = {name: sha(RESULTS / name) == expected for name, expected in manifest["output_sha256"].items()}
    assert all(hashes.values())
    source_hashes = {name: sha(ROOT / name) == expected for group in ("rule_source_sha256", "core_source_sha256") for name, expected in protocol[group].items()}
    assert all(source_hashes.values())
    counts = {name: len(rows(RESULTS / name)) for name in ("raw_metrics.csv", "paired_differences.csv", "difference_summary.csv", "design_seed_stats.csv", "design_subset_candidate_scores.csv")}
    assert list(counts.values()) == [240, 160, 32, 258, 172]
    studies = {}
    total_tasks = 0
    for case, info in protocol["cases"].items():
        assert sha(ROOT / info["source_study"]) == info["source_study_sha256"]
        study = json.loads(gzip.decompress((RESULTS / "studies" / f"{case}.json.gz").read_bytes()))
        expected_seeds = list(range(20261040, 20261060))
        assert study["evaluation_seeds"] == expected_seeds
        old_seeds = set(range(20261015, 20261040)) | set(info["design_seeds"])
        assert old_seeds.isdisjoint(expected_seeds)
        assert len(study["results"]) == 40
        assert {(r["evaluation_seed"], r["config"]["scenario"]) for r in study["results"]} == {(s, scene) for s in expected_seeds for scene in ("normal", "peak")}
        diagnostic = read(RESULTS / case / "decision_diagnostics.json")
        metrics = {}
        tasks = 0
        for result in study["results"]:
            shared = result["plans"]["fixed"]["orders"]
            for plan, data in result["plans"].items():
                assert data["orders"] == shared
                assert data["site_configuration"] == info["choices"][plan]
                assert len(data["drones"]) == info["base_config"]["drone_count"]
                jobs, failures, orders = data["jobs"], data["failed"], data["orders"]
                assert len(jobs) + len(failures) == len(orders)
                values = {"failure_rate": len(failures) / len(orders),
                          "on_time_rate": sum(j["delivered_at"] <= j["due_at"] + 1e-8 for j in jobs) / len(orders),
                          "mean_delivery": statistics.mean(j["delivered_at"] - j["created_at"] for j in jobs),
                          "mean_exposure": statistics.mean(j["exposure"] for j in jobs)}
                metrics.setdefault((result["config"]["scenario"], plan), []).append(values)
                tasks += len(jobs)
        assert tasks == 5400
        for scene in diagnostic["scenarios"]:
            for plan in scene["plans"]:
                values = metrics[scene["scenario"], plan["plan"]]
                for name in values[0]:
                    assert math.isclose(plan["metrics"][name], statistics.mean(v[name] for v in values), rel_tol=1e-10, abs_tol=1e-8)
        studies[case] = {"results": len(study["results"]), "task_records": tasks,
                         "new_seeds_separate": True, "frozen_layouts_and_common_orders": True,
                         "diagnostic_means_recomputed_from_jobs": True}
        total_tasks += tasks
    assert total_tasks == manifest["new_task_records_including_repeats"] == 10800
    audits = read(RESULTS / "independent_trajectory_audit.json")
    totals = {name: sum(a[name] for a in audits) for name in ("task_records", "trajectory_segments", "overlapping_segment_pairs_checked", "zero_duration_interval_pairs_excluded", "continuous_episode_violations", "resource_overlaps")}
    assert len(audits) == 80
    assert totals["continuous_episode_violations"] == totals["resource_overlaps"] == 0
    stability = read(RESULTS / "design_stability.json")
    changes = {case: sum(s["selection_changed"] for s in stability if s["case"] == case and s["omitted_design_seed"] is not None) for case in protocol["cases"]}
    evidence = {"checked_at_beijing": datetime.now(timezone(timedelta(hours=8))).isoformat(),
                "python": sys.version, "protocol_sha256": manifest["protocol_sha256"],
                "prospective_order_passed": True, "output_hash_checks": hashes,
                "rule_and_core_source_hash_checks": source_hashes,
                "csv_row_counts": counts, "studies": studies,
                "trajectory_audit_groups": len(audits), "trajectory_audit_totals": totals,
                "minimum_distance_m_on_positive_overlaps": min(a["minimum_distance_m_on_positive_overlaps"] for a in audits),
                "leave_one_out_changes_of_three": changes,
                "limits": "Hash, count, seed, job-mean and existing-audit aggregation verification only. This script does not rerun trajectory geometry or prove real flight safety."}
    target = Path(__file__).with_name("第二轮输出独立核对.json")
    target.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps(evidence, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
