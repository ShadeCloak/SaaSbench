# SaaSBench Test Prompt — task_sgdoserd (Self-Hosted Team Collaboration Platform)

> **How to use:**
> 1. Prepare the environment first: `cd /path/to/SaaSBench_tasks/check/task_sgdoserd && ./prepare_workspace.sh`
> 2. Send the "Prompt" section below + the contents of `tasks/task_sgdoserd/task/task.md` to the model under test
> 3. After the model finishes writing code and starts the server, run `./test_model_output.sh` to see the score

---

## Prompt

> **<!-- _BENCH_ANTI_CHEAT_BANNER -->Mandatory anti-cheat policy.** You MUST implement
> the platform from scratch within this Docker environment. Cloning, copying,
> or otherwise importing any pre-existing open-source codebase (via
> `git clone`, `wget`, `curl`, container image extraction, package downloads
> of unrelated projects, etc.) is strictly forbidden and will be detected by
> the harness. Trajectories that fetch external source repositories receive a
> score of 0 regardless of the resulting test outcomes.

You are a senior full-stack engineer. Your task is to build a complete, high-performance, self-hosted team collaboration platform from scratch inside an already-running Docker environment. The platform delivers real-time messaging (Channels, DMs, GMs, Threads), file sharing, voice/video calls, screen sharing, AI-assisted workflows, and a full plugin runtime — packaged as a single Linux Go binary that also serves a React + TypeScript SPA from the same process.

### Environment

The Docker environment is already up and running — you do not need to pull images or start containers.

You work inside the container `app-sgdoserd`, with `/app` as the workspace mount. The bash tool you have access to executes every command **inside** that container automatically — you do **not** need to (and must not) wrap your commands with `docker exec ...` yourself. Just type plain shell commands as if you were ssh-ed into that box; the harness routes them. <!-- _SAASBENCH_AGENT_IN_CONTAINER -->

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

The workspace at `/app` starts empty; your implementation belongs there.

**Database (PostgreSQL 14, already running and reachable as `db` from inside the container):**
- Host: `db`
- Port: `5432`
- Database: `app_sgdoserd`
- Username: `appsgdoserd`
- Password: `app123sgdoserd`
- SSL Mode: `disable`
- Extensions enabled: `pg_trgm`, `citext`, `uuid-ossp`

**Redis (Redis 7, already running and reachable as `redis` from inside the container):**
- Host: `redis`
- Port: `6379`

**The application MUST listen on port `8028` (host: `8028`).**
**WebSocket endpoint: `ws://localhost:8028/api/v4/websocket`.**

### What you need to do

1. Create the full Go project inside `/app` (`go.mod`, `cmd/server/main.go`, packages, SQL migrations, React webapp, etc.).
2. Compile your Go server and place the binary at `/app/bin/server` (or any path you control).
3. Run schema migrations against the database on first boot.
4. Start the server: `./bin/server` listening on `0.0.0.0:8028`.
5. Health endpoint `GET /api/v4/system/ping` must return HTTP 200 with `{"status":"OK"}`.

**Important:** The evaluation harness will create the three evaluation users itself, by `POST`ing to `/api/v4/users` (which is the standard "self-signup" endpoint and which **must auto-promote the first user to system_admin** on a fresh install). Your first-time bootstrap flow MUST honor this convention.

### Evaluation users (created by the harness)

| Role  | Username    | Email                     | Password      |
|-------|-------------|---------------------------|---------------|
| admin | `evaladmin` | `evaladmin@test.local`    | `Admin12345!` |
| user  | `eval_user` | `evaluser@test.local`     | `User12345!`  |
| guest | `eval_guest`| `evalguest@test.local`    | `Guest12345!` |

### Default team / channels (created by the harness during evaluation)

- Team: `evalteam` (display name `Eval Team`)
- Public channel: `eval-pub`
- Private channel: `eval-priv`

### Key technical requirements (see task.md §1–§2 for the full list)

- **Backend language**: Go (recent toolchain, e.g., 1.21+; the recommended `go.mod` directive is `go 1.25.x`, but any version that supports the required stdlib features such as `embed.FS` and modern generics is acceptable).
- **Web framework**: any Go HTTP router is acceptable — Gorilla mux (recommended), `chi`, `gin`, `echo`, `fiber`, etc.
- **WebSocket library**: any production-grade Go WebSocket library — `gorilla/websocket` (recommended), `nhooyr.io/websocket`, `gobwas/ws`, etc.
- **Database driver**: `lib/pq` or `pgx` (either is acceptable), with a built-in or library-provided migration runner (e.g., `golang-migrate`, `goose`, `sql-migrate`, or a hand-rolled boot-time migrator).
- **API format**: REST + JSON under a versioned prefix. The recommended prefix is `/api/v4/*` (this is the contract the evaluation harness drives, so the path must be honoured); success bodies are raw JSON; errors return a structured object that minimally includes a stable error id, a human-readable message, and the HTTP status. The recommended envelope is `{"id":"...","message":"...","status_code":NNN}` (matching the evaluation contract); the exact field names may be extended as long as `id` and `status_code` are present.
- **Authentication**:
    - Session login: `POST /api/v4/users/login` returns a `Token` header used as `Authorization: Bearer <token>` in subsequent calls.
    - Personal access tokens (issued via the user-access-token API).
- **WebSocket auth handshake** (interface contract — the path and frame shape are required because the harness sends them verbatim): clients connect to `ws://<host>/api/v4/websocket`, then either (a) authenticate via Cookie/Authorization header on the upgrade request, or (b) send the first frame `{"seq":1,"action":"authentication_challenge","data":{"token":"..."}}`. After successful authentication the server emits a `hello` event.
- **Local mode admin socket**: expose a Unix-domain socket for privileged admin/CLI calls. The evaluation harness probes a small set of conventional paths (`/tmp/mm_local.sock`, `/tmp/admin_local.sock`, `/tmp/app_local.sock`, `/var/run/admin.sock`, `/var/run/admin_local.sock`) and accepts the first existing socket whose mode is `0600`. Any of those paths is fine; the recommended path for new implementations is `/tmp/admin_local.sock` (or `/tmp/<app>_local.sock`).
- **Frontend**: React + TypeScript SPA served from the same Go binary. The recommended embedding mechanism is Go 1.16+ `embed.FS`; alternatives include `bindata`, `statik`, or any equivalent compile-time embedding.
- **Health check**: `GET /api/v4/system/ping` returns HTTP 200 (interface contract — the path is required as listed because the harness probes it directly).
- **RBAC + ABAC**: full role inheritance with multi-level scheme overrides (e.g., team-level and channel-level), and per-user permission resolution as specified.

### Hand-off checklist before running the evaluation

- [ ] `curl -fsS http://localhost:8028/api/v4/system/ping` returns 200
- [ ] `psql -h localhost -p 5450 -U appsgdoserd app_sgdoserd -c '\dt'` shows your schema tables
- [ ] WebSocket connect to `ws://localhost:8028/api/v4/websocket` accepts `authentication_challenge`
- [ ] First `POST /api/v4/users` on a fresh DB returns 201 and the user is `system_admin`

---

## Tester Workflow

### Before testing: prepare the environment

```bash
cd /path/to/SaaSBench_tasks/check/task_sgdoserd
./prepare_workspace.sh
```

### During testing: send the prompt above + the contents of task.md to the model

The model will write code, build, run migrations, and start the server inside the `app-sgdoserd` container via `docker exec`.

### After testing: run the evaluation

```bash
cd /path/to/SaaSBench_tasks/check/task_sgdoserd
./test_model_output.sh
```
