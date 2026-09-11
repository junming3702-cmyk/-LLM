"""Read-only source capture and metadata-only protection for expert material."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import shutil
import subprocess
from experiment_integrity import file_digest, utc_now, write_new_json


def capture(model_root, corpus, expert_workbook, study_root, output):
    model_root, corpus, expert_workbook, study_root, output = map(
        Path, (model_root, corpus, expert_workbook, study_root, output))
    if output.exists():
        raise FileExistsError("freeze output must be new")
    # Explicit allowlist: never copy .env, tokens, source project documents or scores.
    source_files = [p for p in (model_root / "phase2_public").rglob("*")
                    if p.is_file() and p.suffix in {".py", ".md", ".json", ".jsonl", ".csv", ".txt"}
                    and not any(part in {".local_runs", ".local_cache", "__pycache__"} for part in p.parts)]
    rows = []
    for path in source_files:
        relative = path.relative_to(model_root)
        destination = output / "model_snapshot" / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
        rows.append({"path": str(path.resolve()), "sha256": file_digest(path),
                     "role": "protected_model_source", "snapshot": str(destination.relative_to(output))})
    destination = output / "corpus_snapshot" / corpus.name
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(corpus, destination)
    rows.append({"path": str(corpus.resolve()), "sha256": file_digest(corpus),
                 "role": "fixed_corpus", "snapshot": str(destination.relative_to(output))})
    # Hash bytes only. No spreadsheet cells, labels, comments or participant data read.
    for path in sorted(p for p in study_root.rglob("*") if p.is_file()):
        rows.append({"path": str(path.resolve()), "sha256": file_digest(path),
                     "role": "expert_material_metadata_only"})
    if not expert_workbook.is_file():
        raise FileNotFoundError("user-identified expert workbook missing")
    if not any(r["path"] == str(expert_workbook.resolve()) for r in rows):
        rows.append({"path": str(expert_workbook.resolve()), "sha256": file_digest(expert_workbook),
                     "role": "expert_material_metadata_only"})
    commit = subprocess.check_output(["git", "-C", str(model_root), "rev-parse", "HEAD"], text=True).strip()
    manifest = {"freeze_id": output.name, "captured_at": utc_now(), "observed_model_commit": commit,
                "expert_workbook_identified_by_user": str(expert_workbook.resolve()),
                "expert_progress": "partial_returns_user_reported_2026-09-12",
                "expert_scores_inspected": False, "expert_model_version_binding": "pending_output_provenance_confirmation",
                "warning": "Current code snapshot is not proof of which model generated the expert-rated outputs.",
                "files": rows}
    write_new_json(output / "manifest.json", manifest)
    return {"files": len(rows), "manifest": str(output / "manifest.json")}


def verify(manifest_path):
    manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
    changes = []
    for row in manifest["files"]:
        path = Path(row["path"])
        if not path.is_file() or file_digest(path) != row["sha256"]:
            changes.append({"path": row["path"], "role": row["role"]})
    return {"checked": len(manifest["files"]), "unchanged": not changes, "changed_files": changes}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--verify", type=Path)
    parser.add_argument("--model-root", type=Path)
    parser.add_argument("--corpus", type=Path)
    parser.add_argument("--expert-workbook", type=Path)
    parser.add_argument("--study-root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.verify:
        result = verify(args.verify)
    else:
        if not all([args.model_root, args.corpus, args.expert_workbook, args.study_root, args.output]):
            parser.error("capture requires all five explicit paths")
        result = capture(args.model_root, args.corpus, args.expert_workbook, args.study_root, args.output)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if result.get("unchanged") is False else 0


if __name__ == "__main__":
    raise SystemExit(main())
