# SaaSBench Test Prompt — task_yobgvieg (ProjectFlow — Enterprise Project Management)

> **How to use:**
> 1. Start the Docker environment first: `cd <repo_root>/tasks/task_yobgvieg/docker && docker compose up -d`
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

You are a senior full-stack engineer. Your task is to build a complete enterprise-grade project-management and team-collaboration platform (ProjectFlow) from scratch inside an already-running Docker environment.

### Environment

The Docker environment is already up and running — you do not need to pull images or start containers.

You work inside the container `app_yobgvieg`, with `/app` as the working directory (currently empty). The bash tool you have access to executes every command **inside** that container automatically — you do **not** need to (and must not) wrap your commands with `docker exec ...` yourself. Just type plain shell commands as if you were ssh-ed into that box; the harness routes them. <!-- _SAASBENCH_AGENT_IN_CONTAINER -->

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

**Database (PostgreSQL 15, already running):**
- Host: `db`
- Port: `5432`
- Database: `app_yobgvieg`
- Username: `appyobgvieg`
- Password: `app123yobgvieg`
- Extensions installed: uuid-ossp, pg_trgm

**Redis (already running):**
- Host: `redis`
- Port: `6379`

**RabbitMQ (already running):**
- Host: `rabbitmq`
- Port: `5672`
- User: `guest`
- Password: `guest`

**MinIO / S3 object storage (already running):**
- Host: `minio`
- API port: `9000`
- Console port: `9090`
- Access Key: `minioadmin`
- Secret Key: `minioadmin`
- Bucket: `uploads`

**The application MUST listen on port `8032`.**

### What you need to do

1. Create a complete Python/Django project inside `/app` (backend API) + a React frontend (optional — the evaluation focuses on the backend API)
2. Run `pip install` to install Python dependencies
3. Run database migrations
4. Create the following 3 evaluation users:
   - Admin: username=`eval_admin`, email=`eval_admin@test.com`, password=`EvalAdmin123!` (super administrator, role=20)
   - Member: username=`eval_member`, email=`eval_member@test.com`, password=`EvalMember123!` (regular member, role=15)
   - Guest: username=`eval_guest`, email=`eval_guest@test.com`, password=`EvalGuest123!` (guest, role=5)
5. Initialise the application instance (Instance registration + InstanceConfiguration setup)
6. Start the application server, listening on `0.0.0.0:8032`

### Key technical requirements

> **Note:** the items below describe the recommended reference stack. Any modern Python web stack with equivalent capabilities is acceptable as long as it satisfies the explicit interface contracts (endpoint paths, cookie name, header name, response shape).

- **Backend framework**: any modern Python web framework (Django 4.2 + DRF recommended for full feature parity; alternatives: FastAPI, Flask)
- **ASGI server**: Gunicorn + ASGI workers for production (Uvicorn recommended; alternatives: Daphne, Hypercorn)
- **Authentication**: session-based + API Key (sent in the `X-Api-Key` header)
- **Login endpoint**: `POST /auth/sign-in/` accepts form-encoded data (`application/x-www-form-urlencoded`); JSON body is NOT accepted by this endpoint
- **Session cookie name**: `session-id` (the implementation should use `session-id` literally; this is an intentional design choice and the implementation must NOT silently fall back to any framework default cookie name)
- **API prefix**: `/api/` for internal APIs, `/api/v1/` for external APIs
- **Task queue**: Celery with any broker (RabbitMQ AMQP recommended; alternatives: Redis, Amazon SQS)
- **Cache**: Redis (any Python Redis client, e.g., django-redis, redis-py)
- **Object storage**: any S3-compatible object store (MinIO recommended for self-hosted; alternatives: AWS S3, Backblaze B2; integration via boto3 + any storage backend)
- **ORM**: any Python ORM (Django ORM recommended for Django stacks; alternatives: SQLAlchemy)
- **CORS**: any CORS middleware
- **Static files**: any static-file serving (WhiteNoise recommended; alternatives: nginx, CDN)
- **Health check**: `GET /` should return `{"status": "OK"}`
- **Note**: the evaluation script interacts with the application via the HTTP API — make sure all API endpoints work correctly

---

## Tester Workflow

### Before testing: start the environment

```bash
cd <repo_root>/tasks/task_yobgvieg/docker
docker pull <registry>/task_yobgvieg-app:latest
docker compose up -d
docker compose ps   # verify all 5 containers are running (app, db, redis, rabbitmq, minio)
```

### During testing: send the prompt above + the contents of task.md to the model

The model will write code, install dependencies, and start the server inside the container via `docker exec`.

### After testing: run the evaluation

```bash
cd <repo_root>/check/task_yobgvieg
./test_model_output.sh
```
