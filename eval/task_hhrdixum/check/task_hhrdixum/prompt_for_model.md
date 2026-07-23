# SaaSBench Test Prompt — task_hhrdixum (Inventory Management & Light-MRP)

> **How to use:**
> 1. Bring up the Docker stack first by running `./prepare_workspace.sh` from this directory. It wipes the workspace, ensures the `:model` image variant is used, and verifies the container is idle and port-free.
> 2. Send the **Prompt** section below to the model under test. The model must read `task.md` (provided in full at the bottom of this file) and implement the application from scratch inside the running container.
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

You are a senior full-stack engineer. Your task is to build a complete production-grade inventory-management & light-MRP web application from scratch inside an already-running Docker environment.

### Environment

The Docker environment is already up and running — you do **not** need to pull images or start containers.

You work inside the container `task_hhrdixum-app`, with `/app` as the working directory (currently empty). The bash tool you have access to executes every command **inside** that container automatically — you do **not** need to (and must not) wrap your commands with `docker exec ...` yourself. Just type plain shell commands as if you were ssh-ed into that box; the harness routes them. <!-- _SAASBENCH_AGENT_IN_CONTAINER -->

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

**PostgreSQL 16** (already running, healthy):
- Host: `db`
- Port: `5432` (inside the network) / `5439` (on the host)
- Database: `app_hhrdixum`
- Username: `apphhrdixum`
- Password: `app123hhrdixum`
- Connection URL: `postgresql://apphhrdixum:app123hhrdixum@db:5432/app_hhrdixum`

**Redis 7** (already running, healthy):
- Host: `cache`
- Port: `6379` (inside the network) / `6380` (on the host)
- Used as the Django cache backend AND the django-q2 broker.

**The application MUST listen on container port `8000`** (mapped to host port `8014`).

### What you need to do

1. **Create a complete Django + DRF project under `/app`** following the spec in `task.md` below. The project name must be `app` so that `DJANGO_SETTINGS_MODULE=app.settings` resolves (the docker-compose env var is set to this).
2. **Install Python deps via `pip install`** (Django, DRF, drf-spectacular, django-mptt, django-money, django-q2, etc.; plus native deps via `apt install` for WeasyPrint / lxml / Pillow if you use them). Read `task.md` § 2.1 for the full stack.
3. **Run database migrations** (`python manage.py migrate --noinput`).
4. **Seed the deterministic exchange-rate snapshot** (USD = base; AUD = 1.5; CAD = 1.7; GBP = 0.9). See `task.md` § 8.10 for the exact 4-row table and the resulting pricing acceptance values.
5. **Create the 2 evaluation users** that the harness expects:
   - **Admin**: `username=admin`, `email=admin@test.com`, `password=Admin123!@#`, `is_superuser=True`, `is_staff=True`.
   - **Reader**: `username=reader`, `email=reader@test.com`, `password=Reader123!`, `is_superuser=False`, `is_staff=False`, `groups=['Read Only']`. The `Read Only` Group / `RuleSet` must grant `view`-only on every model the spec mentions.
6. **Start the application server** listening on `0.0.0.0:8000` inside the container (the docker-compose health-check probes `/api/system/health/` first, then `/api/`).
7. **(Recommended)** drop a `bin/start.sh` into the workspace that does steps 3-6 in one shot. The container's default `command:` looks for `/app/bin/start.sh`; if present, it executes it on `docker compose restart`.

### Key technical requirements (excerpt — see `task.md` for the full spec)

- **Backend framework**: Django 5.2 LTS + Django REST Framework
- **API schema**: drf-spectacular (`GET /api/schema/` returns OpenAPI 3.0)
- **ORM**: Django ORM + django-mptt for tree models (PartCategory, StockLocation, Part variants, BuildOrder, etc.)
- **Authentication suite**: 5 mechanisms must coexist — Token (`Authorization: Token <token>`), Basic, Session, OAuth2 (`django-oauth-toolkit`), Browser-headless (`django-allauth headless`). When the credential is an **API token** issued via `/api/user/tokens/`, `Authorization: Bearer <api_token>` MUST be REJECTED (the test verifies this). OAuth2 access tokens (issued by `django-oauth-toolkit`) legitimately use the `Bearer` prefix per RFC 6750 and are handled by a separate authentication class — see `task.md` § 7.1 / § 2.3.
- **Token format**: 50+ char string starting with the prefix `app-`. Token table is `users_apitoken`, columns include `key`, `name`, `revoked`, `expiry`, `user_id`, `created`. `POST /api/user/tokens/` issues; `DELETE /api/user/tokens/<pk>/` revokes (sets `revoked=True`).
- **Background tasks**: `django-q2` with one scheduler + N workers (default 4; forced to 1 when cache is disabled). Cron jobs from `task.md` § 4.14.1 must be registered at startup.
- **Money / multi-currency**: `django-money` + `djmoney.contrib.exchange`. All prices stored as `MoneyField` with explicit currency. Exchange rates seeded as in § 8.10.
- **Permissions**: 9 independent rule sets × 4 CRUD permissions = 36 cells. `RuleSet`, `Owner`, `UserProfile` models per `task.md` § 7.
- **API surface**: ~170 REST endpoints; reference paths in `task.md` § 5. Notable quirks:
  - `/api/version/` returns an *object* (not array), with `version.server` and `version.api` keys.
  - `/api/version-text` (no trailing slash) returns the changelog *array*.
  - Part parameters live under `/api/part/parameter/` and parameter templates under `/api/part/parameter/template/` (the harness checks these exact paths).
  - `/api/order/so-allocation/` (short-dash, NOT `/api/order/so/allocation/`).
  - `/api/order/{po,so,ro}/` order types use reference patterns `PO-{ref:04d}` / `SO-{ref:04d}` / `RMA-{ref:04d}` enforced by the global settings table.
  - `/api/stock/` POST returns a *single-element list* `[{...}]` (the spec allows bulk creation; you can return `[obj]` for a single create).
- **Health check endpoint**: `GET /api/system/health/` returns `200 OK`; `GET /api/` returns the InfoView JSON with `apiVersion` field.
- **Plugin system**: 10 mandatory built-in plugins per `task.md` § 4.8 — see the spec for the exact slug list (e.g. `builtin-barcode`, `bom-exporter`, `data-exporter`, `ui-notification`, `machines`, `email-notification`, `currency-exchange`, `label`, `label-machine`, `parameter-exporter`). The 23 plugin **mixin types** (`BarcodeMixin`, `LocateMixin`, `ActionMixin`, `LabelPrintingMixin`, `ReportMixin`, `UserInterfaceMixin`, `ValidationMixin`, `ScheduleMixin`, `EventMixin`, ...) are a separate concept — see `task.md` § 4.8 for the mixin catalogue.
- **Pagination**: `LimitOffsetPagination`; default 50, max 1000.
- **Testing-friendly defaults**: `APP_PLUGINS_INSTALL_DISABLED=True` and `APP_DEBUG=True` in dev.

### Useful environment variables already exported in the container

| Variable | Value |
|---|---|
| `APP_DB_*` | postgresql @ db:5432, db `app_hhrdixum`, user/pwd `apphhrdixum`/`app123hhrdixum` |
| `APP_CACHE_HOST` / `APP_CACHE_PORT` | `cache` / `6379` |
| `REDIS_URL` | `redis://cache:6379/0` |
| `APP_BASE_URL` | `http://localhost:8014` |
| `DJANGO_SETTINGS_MODULE` | `app.settings` (override if you use a different module) |

### Verification (what the harness will check)

The evaluation runs ~298 graph-of-API-calls against the live application. The categories are: `ApiCRUD` (79 nodes), `ApiQuirks` (18), `Authentication` (8), `BusinessLogic{BOM,Build,Orders,Pricing,Stock}` (44), `DataModel` (36), `RBAC` (42), `Reports` (6), `Settings` (24), `Frontend` (5), `Importer` (5), `Plugins` (4), `EdgeCases` (8), `Deployment` (5), `AsyncTasks` (11), `ArchitectureQuality` (3 LLM-judge nodes). Read `task.md` from top to bottom — every section maps to one or more evaluator nodes.

---

## Tester Workflow

### Before testing — start the environment

```bash
cd <REPO_ROOT>/check/task_hhrdixum
./prepare_workspace.sh          # uses the `:model` image variant, empties ./workspace
docker compose -f ../../tasks/task_hhrdixum/docker/docker-compose.yml ps   # all 3 containers running and healthy (db, cache, app)
```

The model image (`:model` tag) is the one you should target — it is a clean dev base
without the application preinstalled. The PID-1 process is `sleep infinity`, so the
container stays idle until the model starts its own server. The baseline image
(`:baseline`) used by source-fidelity tests is intentionally different and is not
visible to the model under test.

### During testing — send the Prompt + the contents of task.md to the model

The model writes code + installs deps + starts the server inside the container via `docker exec task_hhrdixum-app bash -c "..."`.

### After testing — run the evaluation

```bash
cd <REPO_ROOT>/check/task_hhrdixum
./test_model_output.sh
```

---

## Full task.md (verbatim, ~3700 lines)

Read this carefully — every section is a contract that the evaluator may probe.

> **Note:** The full `task.md` is shipped at `<REPO_ROOT>/tasks/task_hhrdixum/task/task.md`. Either paste the full file content into the model conversation alongside this prompt, or instruct the model to `cat` / read the file directly if your runner mounts the SaaSBench_tasks repository inside the conversation.
