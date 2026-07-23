# SaaSBench Test Prompt — task_xayqujrv (Feature Flag & Remote Config SaaS)

> **How to use:**
> 1. Bring up the Docker stack first: `cd <REPO_ROOT>/tasks/task_xayqujrv/docker && docker pull shadetocloak/task_xayqujrv-app:latest && docker compose up -d`
> 2. Send the **Prompt** section below to the model under test. The model must read `task.md` (placed in the workspace at `/app/task.md` by the harness) and implement the application from scratch inside the running container.
> 3. After the model has finished writing code + starting the server, run `./test_model_output.sh` from this directory to score the implementation.

---

## Prompt


> **<!-- _BENCH_ANTI_CHEAT_BANNER -->Mandatory anti-cheat policy.** You MUST implement
> the platform from scratch within this Docker environment. Cloning, copying,
> or otherwise importing any pre-existing open-source codebase (via
> `git clone`, `wget`, `curl`, container image extraction, package downloads
> of unrelated projects, etc.) is strictly forbidden and will be detected by
> the harness. Trajectories that fetch external source repositories receive a
> score of 0 regardless of the resulting test outcomes.

You are a senior full-stack engineer. Your task is to build a complete production-grade Feature Flag & Remote Configuration SaaS platform from scratch inside an already-running Docker environment.

### Environment

The Docker environment is already up and running — you do **not** need to pull images or start containers.

You work inside two containers:
- **`task_xayqujrv-app`** — main Django application (workspace at `/app`)
- **`task_xayqujrv-worker`** — task processor (shares the same `/app` workspace)

The bash tool you have access to executes every command **inside** that container automatically — you do **not** need to (and must not) wrap your commands with `docker exec ...` yourself. Just type plain shell commands as if you were ssh-ed into that box; the harness routes them. <!-- _SAASBENCH_AGENT_IN_CONTAINER -->

**Tools pre-installed in the container** (Ubuntu 22.04):
- Node.js 20 + npm + pnpm + yarn + npx
- Python 3.10 + pip
- Go (toolchain in `/usr/local/go`)
- Globally installed npm: TypeScript 5, ts-node, vite, sass, webpack 5, nx, jest, prettier, eslint, nodemon, pm2
- PostgreSQL client 14 (psql, pg_isready); MariaDB / MySQL client; redis-cli; sqlite3
- Build essentials: gcc 11, g++, make, cmake, pkg-config
- Dev libraries: libssl-dev, libpq-dev, libsqlite3-dev, libxml2-dev, libffi-dev
- git, curl, wget, jq, openssl, unzip, ca-certificates
- `apt` is available for installing any additional packages or language toolchains you need

**PostgreSQL 15** (already running, healthy):
- Host: `postgres` (alias: `db`)
- Port: `5432` (inside the network) / `5446` (on the host)
- Database: `app_xayqujrv`
- Username: `appxayqujrv`
- Password: `app123xayqujrv`
- Connection URL: `postgres://appxayqujrv:app123xayqujrv@postgres:5432/app_xayqujrv`

**Redis 7** (already running, healthy):
- Host: `redis`
- Port: `6379` (inside the network) / `6396` (on the host)

**Mock webhook receiver** (for testing webhook delivery):
- Inside containers: `http://mock-receiver:9001`
- On the host: `http://localhost:9011`
- Endpoints: `POST /hook` (200), `POST /always-500` (500), `GET /history`, `DELETE /history`, `GET /health`

**The application MUST listen on container port `8000`** (mapped to host port `8023`).

`DJANGO_SECRET_KEY` is injected into the container via the docker-compose `.env` file; you do not need to generate one. If your project's settings expects a different env var name, read it from `os.environ["DJANGO_SECRET_KEY"]`.

### Evaluation Users

The harness creates 4 evaluation users. Your implementation must support them:

| Role | Username | Email | Password | Superuser |
|------|----------|-------|----------|-----------|
| admin | eval_admin | eval_admin@eval.test | EvalPass12345! | Yes |
| user | eval_user | eval_user@eval.test | EvalPass12345! | No |
| approver | eval_approver | eval_approver@eval.test | EvalPass12345! | No |
| anonymous | — | — | — | — (no credentials) |

Authentication header: `Authorization: Token <value>` (DRF Token auth).
SDK endpoints use `X-Environment-Key: <env-api-key>`.

### Default Resources

The harness expects these default resources to exist after admin login:
- **Organisation**: "Eval Org"
- **Project**: "Eval Project"
- **Environment**: "Development"

### Task Processing

The `app` container runs with `TASK_RUN_METHOD=SEPARATE_THREAD`, so the Django
application processes background tasks **in-process** — you do not need to start
a separate task processor yourself. A dedicated `task_xayqujrv-worker` container
(same image, sharing the same `/app` code) also exists for `TASK_PROCESSOR`
mode; it is managed by the harness, not by you, and you cannot reach it from
inside the `app` container. Just make sure your `python manage.py runtaskprocessor`
management command is implemented and runnable, since the evaluation may exercise it.

### Key Technical Requirements Summary

1. **Approximately 87 data models** with four-level data isolation: Organisation → Project → Environment → Identity
2. **Three-tier RBAC** with 19 permission codes + tag-level scoping + user-group inheritance
3. **14 segment condition operators**: EQUAL, GREATER_THAN, LESS_THAN, CONTAINS, NOT_CONTAINS, REGEX, PERCENTAGE_SPLIT, MODULO, IS_SET, IS_NOT_SET, IN, NOT_IN, GREATER_THAN_INCLUSIVE, LESS_THAN_INCLUSIVE
4. **Multivariate features** with stable-hash variant assignment (identity → 0..99 bucket)
5. **Change request workflow**: N-approval before commit, rejection of self-approval
6. **Environment feature versioning**: immutable snapshots on each commit
7. **5 authentication mechanisms**: token-based dashboard auth (e.g. DRF Token), JWT cookie sliding session, hashed master API key, `X-Environment-Key` header for SDKs, OAuth 2.1 (PKCE + S256)
8. **16 third-party integrations** (analytics, observability, chat, error-tracking, source-control, etc.; see `task.md` for the full enumeration)
9. **Audit log**: every model change emits AuditLog rows
10. **Webhook subsystem**: org-level + env-level, exponential backoff retry
11. **Custom task processor**: 3 run modes (TASK_PROCESSOR / SEPARATE_THREAD / SYNCHRONOUSLY)
12. **Environment document cache**: pre-serialised JSON for SDK offline bundle

> You **MUST** use **Django 5.x + DRF**. This is required, not just recommended: the evaluation harness runs Django management commands inside the container (e.g. `python manage.py showmigrations`, used as a deployment gate) and most evaluator probes target Django ORM table/column conventions. A non-Django stack (FastAPI, Flask, …) has no `manage.py` and will fail the deployment-migration gate and the ORM-convention probes.

---

## Tester Workflow

### Before testing: prepare the environment

```bash
cd <REPO_ROOT>/check/task_xayqujrv
./prepare_workspace.sh
```

This will: pull the image → start the Docker stack → place `task.md` and `knowledge_base.json` into the workspace at `/app/`.

### During testing: send the prompt above to the model

The model will read `/app/task.md` and `/app/knowledge_base.json`, write code, install dependencies, and start the Django server inside the container via `docker exec`.

### After testing: run the evaluation

```bash
cd <REPO_ROOT>/check/task_xayqujrv
./test_model_output.sh
```
