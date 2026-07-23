#!/usr/bin/env python3
"""Download SaaSBench task inputs from Hugging Face and place them into the repo.

The GitHub repo ships every task's evaluator but NOT the task inputs
(`task.md` + `knowledge_base.json`); those live on the Hugging Face dataset
`SaaSBench/SaaSBench`. This script fetches them and drops each file into the
location the harness expects:

    task_<id>/tasks/task_<id>/task/task.md
    task_<id>/tasks/task_<id>/kb/knowledge_base.json

Usage:
    python _harness/fetch_task_inputs.py                # all tasks
    python _harness/fetch_task_inputs.py task_jtbxfpny  # only some tasks

Behind a firewall you can point at the mirror (download works, read-only):
    HF_ENDPOINT=https://hf-mirror.com python _harness/fetch_task_inputs.py
"""
import argparse
import os
import shutil
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATASET_REPO = "SaaSBench/SaaSBench"


def main() -> int:
    ap = argparse.ArgumentParser(description="Fetch SaaSBench task inputs from Hugging Face.")
    ap.add_argument("tasks", nargs="*", help="task ids to fetch (default: all)")
    ap.add_argument("--repo", default=DATASET_REPO, help="HF dataset repo id")
    args = ap.parse_args()

    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        sys.exit("huggingface_hub is required: pip install huggingface_hub")

    print(f"Downloading {args.repo} (endpoint={os.environ.get('HF_ENDPOINT', 'https://huggingface.co')}) ...")
    snap = snapshot_download(repo_id=args.repo, repo_type="dataset")
    src_root = os.path.join(snap, "tasks")
    if not os.path.isdir(src_root):
        sys.exit(f"unexpected dataset layout: {src_root} not found")

    wanted = set(args.tasks) if args.tasks else None
    placed = 0
    missing_local = []
    for task_id in sorted(os.listdir(src_root)):
        if wanted and task_id not in wanted:
            continue
        src_md = os.path.join(src_root, task_id, "task.md")
        src_kb = os.path.join(src_root, task_id, "knowledge_base.json")
        if not (os.path.isfile(src_md) and os.path.isfile(src_kb)):
            print(f"  ! {task_id}: missing inputs in dataset, skipping")
            continue

        dst_md = os.path.join(REPO_ROOT, task_id, "tasks", task_id, "task", "task.md")
        dst_kb = os.path.join(REPO_ROOT, task_id, "tasks", task_id, "kb", "knowledge_base.json")
        if not os.path.isdir(os.path.join(REPO_ROOT, task_id)):
            missing_local.append(task_id)
            continue
        os.makedirs(os.path.dirname(dst_md), exist_ok=True)
        os.makedirs(os.path.dirname(dst_kb), exist_ok=True)
        shutil.copy2(src_md, dst_md)
        shutil.copy2(src_kb, dst_kb)
        placed += 1
        print(f"  + {task_id}")

    print(f"\nPlaced inputs for {placed} task(s).")
    if missing_local:
        print(f"Note: {len(missing_local)} task id(s) from the dataset have no local "
              f"directory in this repo and were skipped: {', '.join(missing_local)}")
    if wanted:
        for t in wanted:
            if not os.path.isdir(os.path.join(src_root, t)):
                print(f"Warning: requested task '{t}' not found in the dataset.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
