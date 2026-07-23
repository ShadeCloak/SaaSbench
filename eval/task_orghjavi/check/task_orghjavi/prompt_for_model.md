# SaaSBench Test Prompt — task_orghjavi (Privacy-friendly Web Analytics)

> **How to use:**
> 1. Prepare the environment: `cd ${REPO_ROOT}/check/task_orghjavi && ./prepare_workspace.sh`
> 2. Send the "Prompt" section below + the full content of `tasks/task_orghjavi/task/task.md` to the model under test
> 3. After the model finishes writing code, run `./test_model_output.sh` to see the score

---

## Prompt


> **<!-- _BENCH_ANTI_CHEAT_BANNER -->Mandatory anti-cheat policy.** You MUST implement
> the platform from scratch within this Docker environment. Cloning, copying,
> or otherwise importing any pre-existing open-source codebase (via
> `git clone`, `wget`, `curl`, container image extraction, package downloads
> of unrelated projects, etc.) is strictly forbidden and will be detected by
> the harness. Trajectories that fetch external source repositories receive a
> score of 0 regardless of the resulting test outcomes.

You are a senior backend engineer. Your task is to build a privacy-friendly **WebAnalytics platform** from scratch inside an already-running Docker environment. The platform must support cookieless web analytics (event ingest, dashboards, public Stats / Query / Plugins APIs, RBAC, etc.) per the requirements in `task.md`.

### Environment

The Docker environment is already up and running — you do not need to pull images or start containers.

You work inside the container `webanalytics_orghjavi_app`, with `/app` as the working directory (currently empty). The bash tool you have access to executes every command **inside** that container automatically — you do **not** need to (and must not) wrap your commands with `docker exec ...` yourself. Just type plain shell commands as if you were ssh-ed into that box; the harness routes them. <!-- _SAASBENCH_AGENT_IN_CONTAINER -->

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

**PostgreSQL 16 (already running, container `webanalytics_orghjavi_postgres`):**
- Host (intra-container): `postgres`, port `5432`
- Database: `app_orghjavi`
- Username: `apporghjavi`
- Password: `app123orghjavi`
- DATABASE_URL: `postgres://apporghjavi:app123orghjavi@postgres:5432/app_orghjavi`
- `citext` extension is pre-loaded by `init-db.sql`

**ClickHouse 24.12 (already running, container `webanalytics_orghjavi_clickhouse`):**
- Host (intra-container): `clickhouse`, port `8123` (HTTP) / `9000` (native)
- Database: `analytics_events_db`
- Username: `default`, password empty
- CLICKHOUSE_DATABASE_URL: `http://clickhouse:8123/analytics_events_db`

**Required runtime env vars (already exported via `docker-compose env_file: .env`):**
- `BASE_URL=http://localhost:8015`
- `SECRET_KEY_BASE` (64-byte base64 random)
- `TOTP_VAULT_KEY` (32-byte base64 random)
- `DISABLE_REGISTRATION=invite_only`
- `MAILER_ADAPTER=Bamboo.LocalAdapter`

**The application MUST listen on container port `8000` (mapped to host `8015`).**

### What you need to do

1. Install the Elixir / Erlang OTP toolchain yourself (Elixir is **not** in the base image — `apt install -y elixir erlang-dev` works on Ubuntu 22.04, or use [`asdf`](https://asdf-vm.com/)). Then build a complete Elixir / Phoenix project inside `/app` implementing the WebAnalytics platform per `task.md` (mix.exs, lib/, priv/, assets/, config/, test/, etc.).
2. Run database migrations:
   - PostgreSQL: `mix ecto.create && mix ecto.migrate` (uses `App.Repo`)
   - ClickHouse: `mix ecto.migrate -r App.IngestRepo`
3. The harness will create the 5 evaluation users itself via direct DB INSERT (the application's `/register` is a Phoenix LiveView and not amenable to scripted POST). You only need to ensure the `users` / `teams` / `team_memberships` schema matches `task.md` §3.1–§3.2. The 5 users are:
   - admin: `bench-v2@example.com` / `BenchPass2026!@`
   - viewer: `bench-v2-viewer@example.com` / `ViewerPass2026!@`
   - editor: `bench-v2-editor@example.com` / `EditorPass2026!@`
   - billing: `bench-v2-billing@example.com` / `BillPass2026!@`
   - guest: `bench-v2-guest@example.com` / `GuestPass2026!@`
4. Start the application server, listening on `0.0.0.0:8000` inside the container. Recommended:
   ```bash
   cd /app && MIX_ENV=ce nohup elixir --sname app --cookie app_cookie -S mix phx.server > /tmp/phx.log 2>&1 &
   ```
   The `--sname app --cookie app_cookie` is required so the harness's RPC nodes (which call `/app/bin/app rpc 'code'`) can reach the running BEAM node.
5. Verify health: `curl http://localhost:8015/api/system/health/live` returns `{"ok":true}` and `/api/system/health/ready` returns all subsystems `ok`.

### Key technical requirements (see `task.md` for the full spec)

> **Naming convention note (REQUIRED)**: You **MUST** use the `App.` module namespace exactly as written below and in `task.md` (e.g. `App.Repo`, `App.IngestRepo`, `App.Site.Cache`, `App.Event.WriteBuffer`, `App.Auth.TOTP`, `App.Billing.Feature.*`). The evaluation harness invokes these modules by their literal names via release RPC (`/app/bin/app rpc "... App.Repo ..."`), so a different namespace prefix (`MyApp.`, `WebAnalytics.`, etc.) will cause those checks to fail. The OTP release/node name must be `app` (start with `--sname app --cookie app_cookie`). The drop-response header `x-app-dropped` and the token prefix `app-plugin-` are also literal parts of the wire contract — see `task.md`.

- **Multi-Repo architecture**: 1 PostgreSQL Repo (`App.Repo`) + 4 ClickHouse Repos (Ingest / Async / ImportDeletion / regular Clickhouse). PG holds metadata (users, sites, goals, funnels, segments, subscriptions); CH holds analytics events (`events_v2`, `sessions_v2`, `ingest_counters`, dictionary tables).
- **Two-buffer ingest**: `App.Event.WriteBuffer` + `App.Session.WriteBuffer`, both flushing every 5s. `flush/0` exposed for tests.
- **VersionedCollapsingMergeTree** sessions table with `sign` column ±1 collapse semantics; queries use FINAL or `sumIf(sign)` aggregation.
- **GateKeeper drop chain** (`App.Site.GateKeeper`): when a request hits `/api/event`, the response is always 202 + `x-app-dropped: 1` header (anti-enumeration; this header name is part of the wire contract); actual drops are recorded into `analytics_events_db.ingest_counters` with `metric` like `dropped_payment_required`, `dropped_throttle`, `dropped_not_found`, etc.
- **Acquisition channel attribution**: `events_v2.acquisition_channel` is a ClickHouse `MATERIALIZED` column (Ecto `writable: :never`) computed by a UDF at INSERT time using GA4-style 18-channel mapping driven by `priv/custom_sources.json` + `priv/ga4-source-categories.csv` dictionaries.
- **Authentication mechanisms** (5 distinct): Phoenix session cookie (UI/dashboard), Bearer API key (`/api/v1/stats/*`, `/api/v2/query`), HTTP Basic auth with `app-plugin-<env>-<rand>` token (`/api/plugins/*`), shared link token (read-only public), SAML SSO (EE-only). The literal token-prefix string `app-plugin-` is part of the wire contract.
- **RBAC** (5 roles): admin / editor / viewer / billing / guest. Cross-team access returns 404 (anti-enumeration), NOT 403. API-key insufficient-scope returns 401/403/404.
- **Plugins API token format**: `app-plugin-#{env_str}-#{rand_url64_30}`; stored as raw `:crypto.hash(:sha256, token)` (binary), NOT hex. Authenticated via HTTP Basic with `id:token`.
- **EE-gated features**: Funnels, Revenue Goals, SiteSegments, SAML SSO, ConsolidatedView. CE returns `{:error, :upgrade_required}` from `App.Billing.Feature.<X>.check_availability/1`.
- **Anti-cheat behaviours**: Stats v1 `/api/v1/stats/realtime/visitors` returns a **bare integer body** (NOT JSON object); timeseries date format `YYYY-MM-DD HH:MM:SS` with **space** (NOT ISO-8601 `T`); breakdown response keys use **short property names** (e.g. `page` not `event:page`).
- **TOTP**: 6-digit numeric, ±0/-30s grace window (NOT ±30s), 10 single-use recovery codes per setup. Module: `App.Auth.TOTP` with `initiate/1` returning `{:ok, user, %{secret, totp_uri}}` (3-tuple).
- **Phoenix CSRF token** in HTML forms: `<input name="_csrf_token" type="hidden" hidden value="...">` — note the extra attributes between `name=` and `value=`.

---

## Tester Workflow

### Before testing: prepare the environment

```bash
cd ${REPO_ROOT}/check/task_orghjavi
./prepare_workspace.sh
```

This will back up the previous workspace (leaving `/app` empty), start the Docker stack (`:model` app image + Postgres + ClickHouse), wait for healthchecks, and verify the app container is idle (`PID 1 = sleep infinity`, port `8015` free). The container then sits idle waiting for the model to write code from scratch.

### During testing: send the prompt + the contents of task.md to the model

The model writes code into `/app` (mounted from `tasks/task_orghjavi/docker/workspace/`), runs migrations inside the container, and launches `mix phx.server` (with `--sname app --cookie app_cookie` for RPC).

### After testing: run the evaluation

```bash
cd ${REPO_ROOT}/check/task_orghjavi
./test_model_output.sh
```

The harness will run the full DAG and print the LLM-judge-included total score.
