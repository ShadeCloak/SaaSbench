# SaaSBench Test Prompt — task_fpumriig (Open CRM Platform)

> **How to use:**
> 1. Start the Docker environment first: `cd <repo>/tasks/task_fpumriig/docker && docker compose up -d`
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
>
> Specifically forbidden npm packages (any usage = 0 score):
> - Any package whose name starts with the upstream CRM project namespace
>   (the harness scans `package.json` for known CRM platform package prefixes)
> - Commercial CRM SDKs as application core: `salesforce-platform-sdk`,
>   `hubspot-api-client`, `pipedrive-api-v2`
> - Embedding/template SDKs that wrap a complete CRM project:
>   `metabase-embedding-sdk-react`, `metabase-static-embed`, `vendure-cli`,
>   `medusa-cli`, `saleor` starter templates
>
> Forbidden Docker images (as application layer; use only as evaluation middleware):
> - Any pre-built complete-CRM container image (the harness inspects pulled images)
>
> Permitted as evaluation middleware (no penalty): `postgres:*`, `redis:*`,
> `clickhouse/*`, and your own NestJS/Express/etc. application code.

You are a senior full-stack engineer. Your task is to build a complete open-source CRM (Customer Relationship Management) platform from scratch inside an already-running Docker environment.

### Environment

The Docker environment is already up and running — you do not need to pull images or start containers.

You work inside the container `app_fpumriig`, with `/app` as the working directory (currently empty). The bash tool you have access to executes every command **inside** that container automatically — you do **not** need to (and must not) wrap your commands with `docker exec ...` yourself. Just type plain shell commands as if you were ssh-ed into that box; the harness routes them. <!-- _SAASBENCH_AGENT_IN_CONTAINER -->

**Tools pre-installed in the container** (Debian-based Linux):
- Node.js (recent LTS) + npm + pnpm + yarn + npx
- Python 3 + pip
- A wide range of additional language toolchains (use whatever you need)
- Globally installed npm: TypeScript 5, ts-node, vite, sass, webpack 5, nx, jest, prettier, eslint, nodemon, pm2
- PostgreSQL client 14 (psql, pg_isready); MariaDB / MySQL client; redis-cli; sqlite3
- Build essentials: gcc 11, g++, make, cmake, pkg-config
- Dev libraries: libssl-dev, libpq-dev, libsqlite3-dev, libxml2-dev, libffi-dev
- git, curl, wget, jq, openssl, unzip, ca-certificates
- `apt` is available for installing any additional packages or language toolchains you need

**Database (PostgreSQL 16, already running):**
- Host: `db`
- Port: `5432`
- Database: `app_fpumriig`
- Username: `appfpumriig`
- Password: `app123fpumriig`
- Connection URL: `postgres://appfpumriig:app123fpumriig@db:5432/app_fpumriig`
- Schemas already created: `core`, `metadata`
- Extensions installed: uuid-ossp, pg_trgm

**Redis (already running):**
- Host: `redis`
- Port: `6379`
- URL: `redis://redis:6379`

**ClickHouse (already running):**
- Host: `clickhouse`
- Port: `8123` (HTTP)
- Database: `app_fpumriig`
- Username: `appfpumriig`
- Password: `app123fpumriig`
- URL: `http://appfpumriig:app123fpumriig@clickhouse:8123/app_fpumriig`

**The application MUST listen on port `8034`.**

### What you need to do

1. Create a complete TypeScript/NestJS project inside `/app` (we recommend an Nx
   monorepo with separate `server` and `front-end` workspaces; the specific
   package names and structure are at your discretion).
2. Run `yarn install` (or `npm install` / `pnpm install`) to install dependencies.
3. Build the backend (e.g. `npx nx build <your-server-package-name>`).
4. Run database migrations (TypeORM or any equivalent migration tool; the schemas
   `core`, `metadata`, and the per-workspace schemas must be created).
5. Create the following 3 evaluation users (via the GraphQL `signUp` mutation
   or any equivalent registration endpoint your platform exposes):
   - Admin: email=`eval_admin@test.com`, password=`EvalAdmin123!`
   - Member: email=`eval_member@test.com`, password=`EvalMember123!` (joins the workspace via invitation)
   - Restricted: email=`eval_restricted@test.com`, password=`EvalRestricted123!` (joins the workspace via invitation)

   These three accounts and roles are required by the evaluation harness; you
   may also accept overrides via the env vars `ADMIN_EMAIL`, `MEMBER_EMAIL`,
   `MEMBER_RESTRICTED_EMAIL` (and matching `_PASSWORD` vars).
6. Start the application server, listening on `0.0.0.0:8034`
7. The health-check endpoint `GET /healthz` MUST return HTTP 200

### Key technical requirements

- **Framework**: NestJS (TypeScript, Node.js) — recommended; equivalent
  TypeScript/Node frameworks accepted as long as the API contract is preserved
- **ORM**: TypeORM + PostgreSQL recommended; alternatives accepted
- **API**: GraphQL at `/graphql`; REST API at `/rest`; Metadata API at `/metadata`
  (server-side GraphQL framework choice is implementation-defined: Apollo Server,
  GraphQL Yoga, or equivalent)
- **Authentication**: JWT signed with the `APP_SECRET` environment variable
- **Multi-tenant architecture**: each workspace gets its own PostgreSQL schema
  (recommended naming: `workspace_<uuid>`)
- **Database schemas**: `core` (users / workspaces / auth), `metadata`
  (object / field definitions), `workspace_<uuid>` (CRM business data)
- **Build tool**: Nx monorepo recommended
- **Job queue**: BullMQ (Redis-backed) recommended
- **Analytics database**: ClickHouse (used for analytics-style data storage)
- **GraphQL auth**: Bearer token (`Authorization: Bearer <token>`)
- **signUp mutation**: `signUp(email, password)` returns auth tokens. The exact
  shape may be `{ loginToken { token } }` (verify-flow) or
  `{ tokens { accessToken { token } } }` (direct token); the evaluation
  harness extracts the token via multiple shape fallbacks.
- **signIn mutation**: `signIn(email, password)` returns auth tokens. Use any
  field name (e.g. `accessToken`, `accessOrWorkspaceAgnosticToken`, or your own
  convention); the evaluation harness extracts via multiple shape fallbacks.
- **REST API error format**: `{"statusCode": 400, "error": "BadRequestException", "messages": ["..."]}`
- **GraphQL error format**: standard GraphQL errors, with the error code in `extensions.code`

### Token Lifetime Recommendations

The evaluation harness expects reasonable production-grade defaults:
- Access tokens: short-lived (≤30 minutes recommended)
- Refresh tokens: long-lived but revocable (≤90 days recommended)
- Specific values are configurable; do not hardcode values that disagree with
  these recommendations.

### Evaluation user information

| Role | Email | Password |
|------|-------|------|
| Admin | eval_admin@test.com | EvalAdmin123! |
| Member | eval_member@test.com | EvalMember123! |
| Restricted | eval_restricted@test.com | EvalRestricted123! |

The Admin user is created via `signUp` (which also creates the workspace). The Member and Restricted users join the workspace by being invited via `sendInvitations` and then completing `signUp`.

### Important environment variables

The following environment variables are injected into the container via Docker `env_file`:

- `PG_DATABASE_URL=postgres://appfpumriig:app123fpumriig@db:5432/app_fpumriig`
- `REDIS_URL=redis://redis:6379`
- `CLICKHOUSE_URL=http://appfpumriig:app123fpumriig@clickhouse:8123/app_fpumriig`
- `PORT=8034`
- `APP_SECRET=fpumriig_secret_key_change_in_production_abc123xyz`
- `SERVER_URL=http://localhost:8034`
- `FRONTEND_URL=http://localhost:8034`

---

## Tester Workflow

### Before testing: start the environment

```bash
cd <repo>/tasks/task_fpumriig/docker
docker pull shadetocloak/task_fpumriig-app:latest
docker compose up -d
docker compose ps   # verify all 4 containers are running (app, db, redis, clickhouse)
```

### During testing: send the prompt above + the contents of task.md to the model

The model will write code, install dependencies, build the project, and start the server inside the container via `docker exec`.

### After testing: run the evaluation

```bash
cd <repo>/check/task_fpumriig
./test_model_output.sh
```
