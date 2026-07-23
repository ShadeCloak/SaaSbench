# SaaSBench Test Prompt — task_jtbxfpny (Enterprise Data Analytics & Visualization Platform)

> **How to use:**
> 1. Start the docker stack first: `cd <repo-root>/tasks/task_jtbxfpny/docker && docker compose up -d`
> 2. Send the "Prompt" section below to the model under test.
> 3. After the model finishes writing code, run `./test_model_output.sh` to see the score.

---

## Prompt


> **<!-- _BENCH_ANTI_CHEAT_BANNER -->Mandatory anti-cheat policy.** You MUST implement
> the platform from scratch within this Docker environment. Cloning, copying,
> or otherwise importing any pre-existing open-source codebase (via
> `git clone`, `wget`, `curl`, container image extraction, package downloads
> of unrelated projects, etc.) is strictly forbidden and will be detected by
> the harness. Trajectories that fetch external source repositories receive a
> score of 0 regardless of the resulting test outcomes.

You are a senior full-stack engineer. Your task is to build a complete enterprise-grade data analytics and visualization platform from scratch inside an already-running Docker environment.

### Environment

The Docker environment is already up and running — you do not need to pull images or start containers.

You work inside the container `app_jtbxfpny`, with `/app` as the working directory (currently empty). The bash tool you have access to executes every command **inside** that container automatically — you do **not** need to (and must not) wrap your commands with `docker exec ...` yourself. Just type plain shell commands as if you were ssh-ed into that box; the harness routes them. <!-- _SAASBENCH_AGENT_IN_CONTAINER -->

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

**Database (PostgreSQL 17, already running):**
- Host: `postgres`
- Port: `5432`
- Database: `app_jtbxfpny`
- Username: `appjtbxfpny`
- Password: `app123jtbxfpny`

**Redis (already running):**
- Host: `redis`
- Port: `6379`

**The application MUST listen on port `8013`.**

### What you need to do

1. Create a complete project inside `/app` (application config, dependency manifest, models, views/controllers, migrations, etc.). Any modern stack is acceptable as long as it satisfies the API contract below.
2. Install the project's dependencies.
3. Run database migrations to create the schema.
4. Initialise the application's role and permission catalogue.
5. Create the following 3 evaluation users (roles may use names equivalent to the listed examples — see "Role naming" below):
   - **Admin**: `username=admin`, `email=admin@test.com`, `password=admin`,
     `firstname=Admin`, `lastname=User`. Full administrative privileges.
   - **Viewer**: `username=gamma_eval`, `email=gamma_eval@test.com`,
     `password=GammaPass123`. Viewer-equivalent role
     (e.g. `viewer` / `Gamma` / `regular_user` / `member`).
   - **Editor**: `username=alpha_eval`, `email=alpha_eval@test.com`,
     `password=AlphaPass123`. Editor-equivalent role
     (e.g. `editor` / `Alpha` / `contributor`).
6. Start the application server, listening on `0.0.0.0:8013` (a production WSGI/ASGI server such as gunicorn / uvicorn / pm2 is recommended).

> **Role naming.** The evaluator accepts a small set of aliases per role
> (case-insensitive). For example, the viewer role may be named any of
> `viewer`, `Gamma`, `regular_user`, `member`, `user`, `reader`, etc.; the
> editor role may be `editor`, `Alpha`, `contributor`, `power_user`. You may
> pick whichever name fits your framework's conventions.

### Key technical requirements

- **REST API base path**: `/api/v1/`
- **OpenAPI document**: served under `/api/v1/_openapi` (or an equivalent
  path such as `/openapi.json`, `/swagger.json`, or `/docs/openapi.json` —
  the evaluator probes a small set of common paths).
- **Authentication**: session cookie + CSRF token. Provide a CSRF token
  endpoint (typically `/api/v1/security/csrf_token/`, or one of
  `/api/csrf/`, `/csrf-token`, `/auth/csrf`) returning either
  `{"result": "<token>"}` or `{"csrf_token": "<token>"}`. Send the token via
  the `X-CSRFToken` header on state-modifying requests.
- **Login**: a login endpoint (typically `/api/v1/security/login`, or one
  of `/api/auth/login`, `/api/login`, `/login`) that accepts
  `{"username", "password"}` (also `provider: "db"` and `refresh: true` are
  accepted but optional) and returns either an `access_token` field or sets
  a session cookie.
- **Framework**: any modern web framework that can satisfy the API
  contract is acceptable.
- **ORM**: any modern ORM with relationship support.
- **Serialisation**: any schema/serialization library is fine; the
  evaluator inspects JSON shape, not your library choice.
- **Async tasks**: a background task queue with Redis as broker and
  result backend.
- **Database migrations**: a versioned migration tool (Alembic, Prisma,
  Django migrations, ...).
- **Configuration**: place the application's config at a path of your
  choosing. The path may be exposed via an env var if the framework
  expects one. Enable Swagger UI for the API if your framework supports
  it.
- **Health check**: the deployment probe issues `GET /` and accepts HTTP 200/301/302/401, so the application root must respond (not 404/5xx). A `GET /health` returning 200 is also recommended.
- **CORS**: enabled.

---

## Tester Workflow

### Before testing: start the environment

```bash
cd <repo-root>/tasks/task_jtbxfpny/docker
# `pull_policy: missing` in compose lets it fall back to a local build if
# the image isn't cached or pre-pulled.
docker compose up -d
docker compose ps   # verify all 3 containers are running (app, postgres, redis)
```

### During testing: send the prompt above + the contents of task.md to the model

The model will write code, install dependencies, and start the server inside the container via `docker exec`.

### After testing: run the evaluation

```bash
cd <repo-root>/check/task_jtbxfpny
./test_model_output.sh
```
