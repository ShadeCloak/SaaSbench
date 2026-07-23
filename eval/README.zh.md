# SaaSBench（中文说明）

SaaSBench 用于衡量编程 agent 从一份自然语言产品需求文档（PRD）出发、构建
完整可用 SaaS 后端的能力。基准包含 **30 道自包含题目**，每道题都源自一个真实
开源 SaaS 项目。对每道题，agent 需要实现 `task.md` 描述的功能、启动应用，随后
由 **DAG 驱动的评测器**通过 HTTP / SQL / LLM 裁判对运行中的系统进行验证。

> English version: [`README.md`](README.md).

---

## 目录结构

```
saas-kaiyuan/
├── task_<id>/                     # 一道自包含题目（共 30 道）
│   ├── tasks/task_<id>/
│   │   ├── task/task.md           # 产品需求文档（PRD）
│   │   ├── kb/knowledge_base.json # 对 PRD 模糊点的澄清知识库
│   │   └── docker/                # docker-compose 环境 + 空的 workspace/
│   └── check/
│       ├── task_<id>/
│       │   ├── prompt_for_model.md   # 交给 agent 的 prompt
│       │   ├── prepare_workspace.sh  # 拉起该题的 docker 环境
│       │   ├── test_source_code.sh   # 用源码跑评测器
│       │   └── test_model_output.sh  # 用 agent 产出的应用跑评测器
│       └── task_<id>_e/evaluate/     # DAG 评测器（dag.json, run_all.py, ...）
│
├── _harness/                      # agent 运行器（Claude Code / Codex）
│   └── run_all_source_tests.sh    # 源码冒烟测试驱动（校验评测体系）
└── _shared/                       # 公共脚本（_print_score.py、prepare 库）
```


| # | 流程 | 作用 | 入口脚本 | 默认并行 |
|---|------|------|----------|----------|
| 1 | **源码测试** | 用项目**原始源码**校验评测器 | `_harness/run_all_source_tests.sh` | `-j 8` |
| 2 | **Claude Code** | 评测 Claude Code agent（在应用**容器内**运行） | `_harness/run_all.sh` | `-j 4` |
| 3 | **Codex** | 评测 Codex agent（在应用**容器内**运行） | `_harness/run_codex_all.sh` | `-j 4` |

---

## 0. 先下载题目输入（第一步）

```bash
pip install huggingface_hub

# 全部 30 道题
python _harness/fetch_task_inputs.py

# 或只下载指定题目
python _harness/fetch_task_inputs.py task_jtbxfpny task_qmjfeopc

# 墙内可走镜像（只读，下载没问题）
HF_ENDPOINT=https://hf-mirror.com python _harness/fetch_task_inputs.py
```

```
task_<id>/tasks/task_<id>/task/task.md
task_<id>/tasks/task_<id>/kb/knowledge_base.json
```

---

## 前置依赖

```bash
# Docker（每道题启动自己的 compose 栈）
docker ps

# 评测器的 Python 依赖（每题的 evaluate 目录都自带 requirements.txt）
pip install pyyaml requests psycopg2-binary
python -m playwright install chromium        # 大多数评测器会驱动浏览器
# 以及你要跑的每道题：
pip install -r task_<id>/check/task_<id>_e/evaluate/requirements.txt
```


## 运行前配置


   ```bash
   export LLM_API_BASE="https://<你的中转>/v1"
   export LLM_API_KEY="<你的裁判 key>"
   export LLM_MODEL="claude-sonnet-4-5-20250929"
   Agent 运行器里的仓库路径
   ```

## 1. 源项目测试（校验评测体系）

```bash
cd _harness

# 全部 30 道题，默认并行 8
./run_all_source_tests.sh

# 指定并行度
./run_all_source_tests.sh -j 5

# 只跑指定题目
./run_all_source_tests.sh task_jtbxfpny task_qmjfeopc

# 运行后查看得分汇总
./run_all_source_tests.sh --summary
```

## 2. Claude Code

```bash
cd _harness

# 单题
./run_task.sh task_jtbxfpny

# 多题，并行 5
./run_all.sh -j 5 task_jtbxfpny task_qmjfeopc task_ygamciur
# 或从文件读取（每行一个 task id）
./run_all.sh -j 5 -f tasklist.txt
```

---

## 3. Codex


```bash
cd _harness

# 单题
./run_codex_task.sh task_jtbxfpny

# 多题，并行 5
./run_codex_all.sh -j 5 task_jtbxfpny task_qmjfeopc task_ygamciur
./run_codex_all.sh -j 5 -f tasklist.txt
```


## 结果与打分

```
prompt.md                 # 交给 agent 的完整 prompt
workspace_snapshot/       # agent 写出的代码
*_output.json             # 运行摘要（耗时、退出码）
codex_events.jsonl        #（Codex）完整事件日志
eval_reports/             # 拷贝出的评测器 JSON 报告
evaluation_output.json    # 评测器 stdout/stderr
result.json               # 最终状态 + 得分
```

---

## 关于并行度

所有并行驱动都接受 `-j N`。每道题都会拉起自己的 Docker 栈
（数据库 + 应用，有时还有 Redis/ES/Mongo），所以并行度受内存和 CPU 限制。工作站上 `-j 5` 是个不错的默认值；若在高负载下看到容器无法进入
healthy 状态，就把它调低。
