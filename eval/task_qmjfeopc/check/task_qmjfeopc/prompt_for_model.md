# SaaSBench Test Prompt — task_qmjfeopc (Gamified Habit-Tracking RPG)

> **How to use:**
> 1. Start the Docker environment first: `cd <SAASBENCH_ROOT>/tasks/task_qmjfeopc/docker && docker compose up -d`
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

You are a senior full-stack engineer. Your task is to build a complete gamified habit-tracking RPG application from scratch inside an already-running Docker environment.

### Environment

The Docker environment is already up and running — you do not need to pull images or start containers.

You work inside the container `app_qmjfeopc`, with `/app` as the working directory (currently empty). The bash tool you have access to executes every command **inside** that container automatically — you do **not** need to (and must not) wrap your commands with `docker exec ...` yourself. Just type plain shell commands as if you were ssh-ed into that box; the harness routes them. <!-- _SAASBENCH_AGENT_IN_CONTAINER -->

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

**Database (MongoDB 7, already running in Replica Set mode):**
- Host: `mongo`
- Port: `27017` (in-container port)
- Database: `app_qmjfeopc`
- Username: `appqmjfeopc`
- Password: `app123qmjfeopc`
- Connection URI: `mongodb://appqmjfeopc:app123qmjfeopc@mongo:27017/app_qmjfeopc?authSource=admin`
- Note: MongoDB runs in Replica Set mode (`--replSet rs0`), so the RS must be initialised before transactions can be used

**Redis (already running):**
- Host: `redis`
- Port: `6379`

**The application MUST listen on port `8002`.**

### What you need to do

1. Create a complete Node.js/Express project inside `/app` (package.json, routes, models, controllers, etc.)
2. Run `npm install` to install dependencies
3. Initialise the MongoDB Replica Set (if not yet initialised)
4. Set up database collections and indexes
5. Create the following 3 evaluation users:
   - User1: username=`eval_user1`, email=`eval1@test.com`, password=`EvalPass123!@#`
   - User2: username=`eval_user2`, email=`eval2@test.com`, password=`EvalPass123!@#`
   - Admin: username=`eval_superuser1`, email=`superuser1@eval.test`, password=`AdminPass123!@#` (admin permissions, contributor level)
6. Start the application server, listening on `0.0.0.0:8002`

### Key technical requirements

- **REST API** with versioned endpoints (the recommended layout is `/api/v3/` as the primary version and `/api/v4/` for newer features; the exact version numbers may be adjusted as long as the routing contract is honoured)
- **Authentication**: header-based API authentication using a paired user-identifier + API-token header (the recommended naming is `x-api-user` for the user UUID and `x-api-key` for the API token; alternatives such as `Authorization: Bearer <token>` are also acceptable) and session cookies for browser-based access
- **API response format**: `{"success": true, "data": {...}}` on success, `{"success": false, "error": "ErrorType", "message": "..."}` on failure (this envelope is part of the task contract — please honour it)
- **Backend framework**: any Node.js framework (Express 4.x is recommended; alternatives such as Fastify, Koa, Hono, or NestJS are also acceptable)
- **MongoDB client / ODM**: any MongoDB ODM or driver (Mongoose 8.x is recommended; alternatives such as the native MongoDB driver, Prisma, or TypeGoose are also acceptable)
- **Cache**: Redis
- **Password hashing**: bcrypt (or another strong, salted password hashing algorithm such as argon2 / scrypt)
- **Note**: the evaluation script will run tests via the HTTP API and `docker exec app_qmjfeopc` to execute commands inside the container

---

## Tester Workflow

### Before testing: start the environment

```bash
cd <SAASBENCH_ROOT>/tasks/task_qmjfeopc/docker
docker pull shadetocloak/task_qmjfeopc-app:latest
docker compose up -d
docker compose ps   # verify all 3 containers are running (app, mongo, redis)
```

### During testing: send the prompt above + the contents of task.md to the model

The model will write code, install dependencies, and start the server inside the container via `docker exec`.

### After testing: run the evaluation

```bash
cd <SAASBENCH_ROOT>/check/task_qmjfeopc
./test_model_output.sh
```
