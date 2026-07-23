# SaaSBench Test Prompt — task_ghmkznee (Observability & Monitoring Dashboard Platform)

> **How to use:**
> 1. Start the Docker environment first: `cd /Users/bytedance/Downloads/qingnan/SaaSBench_tasks/tasks/task_ghmkznee/docker && docker compose up -d`
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

You are a senior full-stack engineer. Your task is to build a complete observability & monitoring dashboard platform from scratch inside an already-running Docker environment.

### Environment

The Docker environment is already up and running — you do not need to pull images or start containers.

You work inside the container `app_ghmkznee_app`, with `/app` as the working directory (currently empty). The bash tool you have access to executes every command **inside** that container automatically — you do **not** need to (and must not) wrap your commands with `docker exec ...` yourself. Just type plain shell commands as if you were ssh-ed into that box; the harness routes them. <!-- _SAASBENCH_AGENT_IN_CONTAINER -->

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
- Database: `app_ghmkznee`
- Username: `appghmkznee`
- Password: `app123ghmkznee`

**The application MUST listen on port `8025`.**

### What you need to do

1. Create a complete Go backend project inside `/app` (main.go, routes, models, database migrations, API handlers, etc.)
2. Install Go dependencies (`go mod init` + `go mod tidy`)
3. Create the frontend project (React + Redux + TypeScript, built with Webpack)
4. Run database migrations (create the necessary tables)
5. Create the following evaluation users:
   - Admin: login=`admin`, password=`admin` (server-admin / superuser-equivalent role; the platform's default administrator account)
   - Viewer: login=`testviewer`, email=`testviewer@test.com`, password=`testpass123` (read-only / viewer-equivalent role)
6. Build and start the application server, listening on `0.0.0.0:8025`

### Key technical requirements

- **API base path**: every API endpoint is prefixed with `/api` (e.g. `/api/health`, `/api/dashboards`, `/api/datasources`)
- **Authentication**: support both Basic Auth and API Key (Bearer token) authentication
- **Language (REQUIRED)**: Go 1.21+ (the docker environment ships Go 1.25.x). Go is mandatory: the harness verifies a `go.mod` module file exists in the workspace, and the evaluation rubric assumes a Go-based reference implementation, so other languages will fail the deployment/module checks.
- **Database access**: any SQL-based ORM (e.g. XORM, GORM, sqlx, sqlboiler) or direct SQL against PostgreSQL
- **Frontend**: a modern SPA framework (React 18 + Redux recommended) with TypeScript, built with a standard bundler (Webpack / Vite / esbuild / etc.)
- **Package manager**: any Node.js package manager (npm / yarn / pnpm); the docker image ships Yarn v4 as a default
- **Health check**: `GET /api/health` returns JSON `{"database": "ok", ...}`
- **Core features**: dashboard CRUD, data source management, folder hierarchy, user/org/team management, alert rules, annotations
- **Environment-variable configuration**: the application reads its configuration from environment variables. The exact prefix may be customized by the implementation; common conventions include `APP_*`, `SERVER_*`, `DATABASE_*`, or any consistent naming scheme. The evaluator only inspects API behavior and database state — it does not enforce a particular env-var prefix.

---

## Tester Workflow

### Before testing: start the environment

```bash
cd /Users/bytedance/Downloads/qingnan/SaaSBench_tasks/tasks/task_ghmkznee/docker
docker pull shadetocloak/task_ghmkznee-app:latest
docker compose up -d
docker compose ps   # verify both containers are running (app + db)
```

### During testing: send the prompt above + the contents of task.md to the model

The model will write code, install dependencies, and start the server inside the container via `docker exec`.

### After testing: run the evaluation

```bash
cd /Users/bytedance/Downloads/qingnan/SaaSBench_tasks/check/task_ghmkznee
./test_model_output.sh
```
