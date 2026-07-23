# SaaSBench Test Prompt — task_ygamciur (Low-Code Application Builder Platform)

> **How to use:**
> 1. Start the Docker environment first: `cd <repo_root>/tasks/task_ygamciur/docker && docker compose up -d`
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

You are a senior full-stack engineer. Your task is to build a complete low-code application builder platform from scratch inside an already-running Docker environment.

### Environment

The Docker environment is already up and running — you do not need to pull images or start containers.

You work inside the container `lowcode-platform`, with `/app` as the working directory (currently empty). The bash tool you have access to executes every command **inside** that container automatically — you do **not** need to (and must not) wrap your commands with `docker exec ...` yourself. Just type plain shell commands as if you were ssh-ed into that box; the harness routes them. <!-- _SAASBENCH_AGENT_IN_CONTAINER -->

**Tools pre-installed in the container** (Ubuntu 22.04):
- OpenJDK 17 (`JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64`) + Maven + Gradle (Maven Aliyun mirror configured)
- Node.js 20 + npm + pnpm + yarn + npx
- Python 3.10 + pip, Go
- PostgreSQL client 14 (psql, pg_isready); MariaDB / MySQL client; redis-cli; sqlite3
- Build essentials: gcc 11, g++, make, cmake, pkg-config
- Dev libraries: libssl-dev, libpq-dev, libsqlite3-dev, libxml2-dev, libffi-dev
- git, curl, wget, jq, openssl, unzip, ca-certificates
- `apt` is available for installing any additional packages or language toolchains you need

**MongoDB and Redis (you must install and start them yourself inside the container):**

The container ships **no** MongoDB or Redis server pre-installed. You are responsible for installing both, configuring credentials, and starting them so the application can use them with the connection details below. Recommended approach:

```bash
set -e
# MongoDB 7 — install via the official Ubuntu 22.04 repo
apt install -y gnupg curl
curl -fsSL https://www.mongodb.org/static/pgp/server-7.0.asc | gpg -o /usr/share/keyrings/mongodb-server-7.0.gpg --dearmor
echo "deb [signed-by=/usr/share/keyrings/mongodb-server-7.0.gpg] https://repo.mongodb.org/apt/ubuntu jammy/mongodb-org/7.0 multiverse" > /etc/apt/sources.list.d/mongodb-org-7.0.list
apt update && apt install -y mongodb-org
# Redis
apt install -y redis-server
```

Configure credentials (Mongo target):
- Host: `localhost`, Port: `27017`
- Database: `app_ygamciur`
- Username: `appygamciur`, Password: `app123ygamciur`, Auth Source: `admin`
- Connection String: `mongodb://appygamciur:app123ygamciur@localhost:27017/app_ygamciur?authSource=admin`
- **Important**: The application uses multi-document transactions, so MongoDB SHOULD run in a topology that supports them. The recommended setup is replica-set mode: generate a `keyFile` and start `mongod` with `--replSet rs0 --keyFile <path>`, then run `rs.initiate()` from `mongosh`. Alternative MongoDB topologies that satisfy the transactional requirement (e.g., a sharded cluster) are also acceptable.

Configure credentials (Redis target):
- Host: `localhost`, Port: `6379`

**The application MUST listen on port `8007`.**

### What you need to do

1. Install MongoDB 7 + Redis inside the container (see commands above) and start both servers (MongoDB in a transaction-capable topology — e.g., replica-set mode `rs0` — with the configured user/password)
2. Create a complete JVM backend (e.g., Java + Spring Boot) + React/TypeScript frontend project inside `/app`
3. Build the backend with a multi-module JVM build tool (e.g., Maven multi-module: server + plugins)
4. Copy the plugin JARs into the plugin-loading framework's scan directory (e.g., the PF4J scan directory)
5. Install frontend dependencies and build
6. Run database migrations (executed automatically when the application server starts)
7. Create the following 3 evaluation users:
   - Admin: email=`admin@eval.com`, password=`EvalAdmin123!`, name=`Eval Admin`
   - Developer: email=`dev@eval.com`, password=`EvalDev123!`, name=`Eval Developer`
   - Viewer: email=`viewer@eval.com`, password=`EvalViewer123!`, name=`Eval Viewer`
8. Start the application server, listening on `0.0.0.0:8007`

### Key technical requirements

- **Backend**: Java 17 + any modern JVM web framework with reactive support (e.g., Spring Boot 3.3.x WebFlux/Reactive stack — recommended for full feature parity; alternatives: Quarkus, Micronaut, Spring Boot MVC for non-reactive implementations)
- **Database**: Any MongoDB driver (a reactive driver such as Spring Data MongoDB Reactive is recommended; sync drivers are also acceptable)
- **Cache / sessions**: Redis
- **Plugin framework**: Any plugin-loading framework that loads datasource connectors (MongoDB, PostgreSQL, MySQL, REST API, etc.) — recommended: PF4J; alternatives: Java SPI, OSGi, custom class-loader-based loader
- **Build tool**: Any JVM build tool with multi-module support (e.g., Maven multi-module — recommended; alternative: Gradle multi-project)
- **Frontend**: React 18 + TypeScript + Redux + a modern JavaScript package manager and bundler (e.g., Yarn 3.x + Webpack — recommended; alternatives: npm/pnpm + Vite/esbuild)
- **Authentication**: Form-based login + OAuth2 (e.g., Google, GitHub) + OIDC
- **API format**: every REST API response MUST be wrapped in a uniform response envelope (the project uses a class commonly named `StandardResponse<T>`) containing a meta object (`responseMeta` with at least `status` and `success` fields) plus a `data` field. The class name and field names are project conventions and the evaluator asserts them as such.
- **API prefix**: `/api/v1/`
- **Application port**: `8007`
- **Encryption configuration**:
  - `app.encryption.password=enc_ygamciur_a7b3c9d2e5f1`
  - `app.encryption.salt=salt_ygamciur_x4k8m2n6p9q1`
- **Git storage**: A configurable directory for storing per-application Git repositories (e.g., `APP_GIT_ROOT=/app/git-storage`); the env var name is at the implementation's discretion.

---

## Tester Workflow

### Before testing: start the environment

```bash
cd <repo_root>/tasks/task_ygamciur/docker
docker compose up -d
docker compose ps   # verify the containers are running
```

### During testing: send the prompt above + the contents of task.md to the model

The model will use `docker exec` to install MongoDB and Redis, configure MongoDB for transactional workloads (e.g., enable a replica set), write code, build the JVM project, install frontend dependencies and start the server inside the container.

### After testing: run the evaluation

```bash
cd <repo_root>/check/task_ygamciur
./test_model_output.sh
```
