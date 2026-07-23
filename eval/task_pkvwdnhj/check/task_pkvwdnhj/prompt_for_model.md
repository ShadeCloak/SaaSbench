# SaaSBench Test Prompt — task_pkvwdnhj (Self-Hosted Mailing List & Newsletter System)

> **How to use:**
> 1. Prepare the environment first: `cd <SaaSBench_repo>/check/task_pkvwdnhj && ./prepare_workspace.sh`
> 2. Send the "Prompt" section below to the model under test
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

You are a senior full-stack engineer. Your task is to build a complete, high-performance self-hosted mailing list and newsletter management system from scratch inside an already-running Docker environment.

### Environment

The Docker environment is already up and running — you do not need to pull images or start containers.

You work inside the container `pkvwdnhj-app-1`, with `/app` as the working directory (it is empty — you'll write all source code from scratch and run `yarn install` / `pnpm install` / `pip install` yourself; expect the dependency installs to take a few minutes since there is no pre-warmed cache). The bash tool you have access to executes every command **inside** that container automatically — you do **not** need to (and must not) wrap your commands with `docker exec ...` yourself. Just type plain shell commands as if you were ssh-ed into that box; the harness routes them. <!-- _SAASBENCH_AGENT_IN_CONTAINER -->

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

**Database (PostgreSQL 16, already running):**
- Host: `db`
- Port: `5432`
- Database: `app_pkvwdnhj`
- Username: `apppkvwdnhj`
- Password: `app123pkvwdnhj`
- SSL Mode: `disable`
- Extensions installed: pgcrypto

**The application MUST listen on port `8010`.**

### What you need to do

1. Create a complete Go project inside `/app` (go.mod, main.go, SQL files, frontend code, etc.)
2. Create a `config.toml` configuration file with the database connection and application address settings
3. Run `go mod download` to download dependencies
4. Build the frontend: `cd frontend && yarn install && yarn build`
5. Build the backend: `make build` (or `go build`)
6. Initialise the database (one-time schema setup; e.g. via a `--install --idempotent --yes --config config.toml` CLI flag on the built binary)
7. Start the application server (built Go binary) and listen on `0.0.0.0:8010`

**Note:** The evaluation script will create the admin user (username=evaladmin, email=admin@test.com, password=EvalPass123) by sending a POST request to `/admin/login` on the first visit, so your first-time setup flow must support this operation.

### Key technical requirements

- **Backend language**: Go (any version supporting the required features; e.g., Go 1.21+)
- **Web framework**: Any Go HTTP framework (the recommended pattern is Echo v4; alternatives such as chi, Gin, Fiber, or net/http with gorilla/mux are also acceptable)
- **Database driver**: Any Go PostgreSQL driver (the recommended pattern is lib/pq + sqlx; alternatives such as pgx, GORM, or sqlc are also acceptable)
- **Configuration**: TOML or YAML config file + environment variables
- **API format**: REST + JSON; every successful response is wrapped in a `{"data": ...}` structure
- **Error response**: `{"message": "error description"}`
- **Authentication**: session-based login (form POST to a configurable login endpoint, e.g. `/admin/login`) and Basic Auth for API tokens (Bearer tokens may also be supported)
- **First-time setup**: a setup mechanism for the first admin user (the recommended path is a POST to `/admin/login` on first visit; alternative setup endpoints such as `/admin/setup`, `/install`, or a CLI command are acceptable as long as the evaluation flow can create the documented admin user)
- **Frontend**: Vue.js SPA with a UI library (the recommended pattern is Buefy on top of Bulma; alternatives such as Vuetify, Element Plus, or Naive UI are also acceptable)
- **Build artefact**: a single static Go binary (the binary name is at the implementation's discretion; common names include `mailing-list`, `newsletter`, `app`, or simply `server`)
- **Health check**: `GET /health` returns 200
- **RBAC**: fine-grained role-based access control, supporting both human users and API / service users (the exact type names are at the implementation's discretion: `user` + `api`, `human` + `service`, etc.)

---

## Tester Workflow

### Before testing: prepare the environment

```bash
cd <SaaSBench_repo>/check/task_pkvwdnhj
./prepare_workspace.sh
```

### During testing: send the prompt above + the contents of task.md to the model

The model will write code, install dependencies, and start the server inside the container via `docker exec`.

### After testing: run the evaluation

```bash
cd <SaaSBench_repo>/check/task_pkvwdnhj
./test_model_output.sh
```
