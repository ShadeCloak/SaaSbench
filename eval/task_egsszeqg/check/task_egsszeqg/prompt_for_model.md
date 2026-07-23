# SaaSBench Test Prompt — task_egsszeqg (Workflow Automation Platform)

> **How to use:**
> 1. Prepare the environment: `cd <repo_root>/check/task_egsszeqg && ./prepare_workspace.sh`
> 2. Send the "Prompt" section below + the full contents of task.md to the model under test
> 3. After the model finishes writing code, run `cd <repo_root>/check/task_egsszeqg && ./test_model_output.sh` to see the score

---

## Prompt


> **<!-- _BENCH_ANTI_CHEAT_BANNER -->Mandatory anti-cheat policy.** You MUST implement
> the platform from scratch within this Docker environment. Cloning, copying,
> or otherwise importing any pre-existing open-source codebase (via
> `git clone`, `wget`, `curl`, container image extraction, package downloads
> of unrelated projects, etc.) is strictly forbidden and will be detected by
> the harness. Trajectories that fetch external source repositories receive a
> score of 0 regardless of the resulting test outcomes.

You are a senior full-stack engineer. Your task is to build a complete workflow-automation platform from scratch inside an already-running Docker environment.

### Environment

The Docker environment is already up and running — you do not need to pull images or start containers.

You work inside the container `task_egsszeqg_app`, with `/app` as the working directory. The bash tool you have access to executes every command **inside** that container automatically — you do **not** need to (and must not) wrap your commands with `docker exec ...` yourself. Just type plain shell commands as if you were ssh-ed into that box; the harness routes them. <!-- _SAASBENCH_AGENT_IN_CONTAINER -->

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
- Host: `postgres`
- Port: `5451`
- Database: `app_egsszeqg`
- Username: `appegsszeqg`
- Password: `app123egsszeqg`

**Redis (already running):**
- Host: `redis`
- Port: `6384`

**The application MUST listen on container port `8029`** (mapped 1:1 to host port `8029`). If you want to run a reverse proxy in front of an upstream worker, install one yourself (`apt install nginx` etc.); the variable `APP_UPSTREAM_PORT=18029` is exported in case your design uses a separate upstream.

### What you need to do

1. Create a complete workflow-automation platform inside `/app`, organised as a monorepo with backend, frontend and shared packages
2. Install dependencies
3. Configure an ORM/data layer to connect to PostgreSQL and run database migrations
4. Create the following evaluation users:
   - Owner: email=`owner@example.com`, password=`App123egsszeqG!`, firstName=`Eval`, lastName=`Owner`
   - Member: email=`member@example.com`, password=`Testpassword1!`
5. Start the server and make sure the application is reachable on port 8029 (a reverse proxy in front of an upstream worker is allowed but not required)

### Key technical requirements

- **Backend**: TypeScript (Node.js ≥ 22) with an HTTP framework of your choice (e.g., Express, Fastify, NestJS)
- **Frontend**: any modern SPA framework (e.g., Vue 3 + Element Plus, React + Ant Design, Svelte + UI library) with a build tool (e.g., Vite, Webpack, esbuild)
- **Database**: PostgreSQL, accessed via an ORM/query builder of your choice (e.g., TypeORM, Prisma, Drizzle, Knex)
- **Cache / queue**: Redis 7; background jobs use a Redis-backed queue worker (e.g., BullMQ, Bull, RQ, or any Redis-compatible queue library)
- **Monorepo**: organised with any monorepo build tool (e.g., Turborepo, Nx, Lerna, pnpm workspaces)
- **Authentication**:
  - Session-based internal REST API (cookie-based session; the cookie name is configurable, default `app-auth` — the implementation may use any name as long as it is consistent and documented)
  - Public API (authenticated via the `X-PLATFORM-API-KEY` request header)
  - Support for OAuth1/OAuth2 credential handshake, MFA/TOTP, LDAP, OIDC, SAML
- **REST API path prefixes** (organized by route family; the implementation may add additional prefixes for advanced features):
  - Internal API: `/rest/**` (session auth) — the prefix may be customized (e.g., `/api/internal/**`)
  - Public API: `/api/v1/**` (API Key auth)
  - Well-known endpoints: `/.well-known/**` (OAuth discovery and similar)
  - Health check: `/healthz*`
  - External webhook entry points: `/webhook*`, `/form*`
  - Optional advanced features (e.g., distributed task runners, agent integrations) may use additional prefixes as needed.
- **First-time setup**: POST a setup endpoint (e.g., `/rest/owner/setup`, `/setup/initial`, or any documented path) creates the owner/admin user
- **Login**: POST a documented login endpoint (e.g., `/rest/login`) returns a session cookie (cookie name configurable, see above)
- **Workflow execution model**: support visual workflow creation/editing with composable steps (commonly called nodes, actions, or tasks)
- **Execution engine**: support workflow execution with execution history tracking
- **Encrypted credential storage**: encrypt credential data using an encryption key (the algorithm and key derivation are at the implementation's discretion)
- **Response format**: route families may use different envelope formats (e.g., internal API returns `{data: ...}`, public API returns a paginated format with `{data: [...], nextCursor: ...}`); document the chosen envelope clearly

---

## Tester Workflow

### Before testing: prepare the environment

```bash
cd /Users/bytedance/Downloads/qingnan/SaaSBench_tasks/check/task_egsszeqg
./prepare_workspace.sh
```

### During testing: send the prompt

Send the "Prompt" section above + the full contents of task.md to the model under test.

The model will use `docker exec task_egsszeqg_app bash -c "..."` to write code, install dependencies, run migrations, and start the server inside the container.

### After testing: run the evaluation

```bash
cd /Users/bytedance/Downloads/qingnan/SaaSBench_tasks/check/task_egsszeqg
./test_model_output.sh
```
