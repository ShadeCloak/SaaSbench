# SaaSBench

A benchmark that measures a coding agent's ability to build a complete,
production-grade SaaS backend from a natural-language product requirements
document (PRD). It contains **30 self-contained tasks**, each derived from a
real open-source SaaS project. For every task the agent must implement the
feature set described in `task.md`, start the application, and then a
**DAG-driven evaluator** verifies the running system over HTTP / SQL / an
LLM judge.

> 中文版见 [`README.zh.md`](README.zh.md).

---

## Repository layout

```
saas-kaiyuan/
├── task_<id>/                     # one self-contained task (30 total)
│   ├── tasks/task_<id>/
│   │   ├── task/task.md           # the product requirements document (PRD)
│   │   ├── kb/knowledge_base.json # clarifications for ambiguous PRD points
│   │   └── docker/                # docker-compose stack + empty workspace/
│   └── check/
│       ├── task_<id>/
│       │   ├── prompt_for_model.md   # the prompt handed to the agent
│       │   ├── prepare_workspace.sh  # brings up the task's docker stack
│       │   ├── test_source_code.sh   # runs the evaluator against source code
│       │   └── test_model_output.sh  # runs the evaluator against the agent's app
│       └── task_<id>_e/evaluate/     # the DAG evaluator (dag.json, run_all.py, ...)
│
├── _harness/                      # agent runners (Claude Code / Codex)
│   └── run_all_source_tests.sh    # source-code smoke test driver (harness validation)
└── _shared/                       # shared helpers (_print_score.py, prepare libs)
```

| # | Workflow | What it does | Entry point | Default parallelism |
|---|----------|--------------|-------------|---------------------|
| 1 | **Source tests** | Validate the evaluator against the *original* project source | `_harness/run_all_source_tests.sh` | `-j 8` |
| 2 | **Claude Code** | Score the Claude Code agent (runs *inside* the app container) | `_harness/run_all.sh` | `-j 4` |
| 3 | **Codex** | Score the Codex agent (runs *inside* the app container) | `_harness/run_codex_all.sh` | `-j 4` |

---

## 0. Download the task inputs (do this first)

```bash
pip install huggingface_hub

# all 30 tasks
python _harness/fetch_task_inputs.py

# or only specific tasks
python _harness/fetch_task_inputs.py task_jtbxfpny task_qmjfeopc

# behind a firewall, use the mirror (download works, read-only)
HF_ENDPOINT=https://hf-mirror.com python _harness/fetch_task_inputs.py
```


```
task_<id>/tasks/task_<id>/task/task.md
task_<id>/tasks/task_<id>/kb/knowledge_base.json
```

---

## Prerequisites

```bash
# Docker (each task runs its own compose stack)
docker ps

# Python evaluator deps (per-task; each evaluator ships a requirements.txt)
pip install pyyaml requests psycopg2-binary
python -m playwright install chromium        # most evaluators drive a browser
# and, per task you intend to run:
pip install -r task_<id>/check/task_<id>_e/evaluate/requirements.txt
```

## Configuration before running

```bash
export LLM_API_BASE="https://<your-relay>/v1"
export LLM_API_KEY="<your-judge-key>"
export LLM_MODEL="claude-sonnet-4-5-20250929"
# repo path in the agent runners (auto-derived, no edit needed)
```

## 1. Source-project tests (evaluator validation)

```bash
cd _harness

# all 30 tasks, 8 in parallel (default)
./run_all_source_tests.sh

# choose parallelism
./run_all_source_tests.sh -j 5

# only specific tasks
./run_all_source_tests.sh task_jtbxfpny task_qmjfeopc

# view the score summary after a run
./run_all_source_tests.sh --summary
```

## 2. Claude Code

```bash
cd _harness

# single task
./run_task.sh task_jtbxfpny

# many tasks, parallelism 5
./run_all.sh -j 5 task_jtbxfpny task_qmjfeopc task_ygamciur
# or from a file (one task id per line)
./run_all.sh -j 5 -f tasklist.txt
```

---

## 3. Codex

```bash
cd _harness

# single task
./run_codex_task.sh task_jtbxfpny

# many tasks, parallelism 5
./run_codex_all.sh -j 5 task_jtbxfpny task_qmjfeopc task_ygamciur
./run_codex_all.sh -j 5 -f tasklist.txt
```

## Results & scoring

```
prompt.md                 # the exact prompt given to the agent
workspace_snapshot/       # the code the agent wrote
*_output.json             # run summary (elapsed, exit code)
codex_events.jsonl        # (Codex) full event log
eval_reports/             # copied evaluator JSON reports
evaluation_output.json    # evaluator stdout/stderr
result.json               # final status + score
```

---

## Choosing parallelism

Every parallel driver takes `-j N`. Each task spins up its own Docker stack
(database + app, sometimes Redis/ES/Mongo), so parallelism is bounded by RAM and
CPU. `-j 5` is a good default on a workstation; lower it if you see containers
failing to become healthy under load.
