# SaaSBench Test Prompt — task_iyjruvfz (Scheduling / Booking Platform)

> **How to use:**
> 1. Start the Docker environment first: `cd <REPO_ROOT>/tasks/task_iyjruvfz/docker && docker compose up -d`
> 2. Send the "Prompt" section below + the contents of `task.md` to the model under test
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

You are a senior full-stack engineer. Your task is to build a complete open-source scheduling and booking platform from scratch inside an already-running Docker environment.

### Environment

The Docker environment is already up and running — you do not need to pull images or start containers.

You work inside the container `task_iyjruvfz-app`, with `/app` as the working directory (currently empty). The bash tool you have access to executes every command **inside** that container automatically — you do **not** need to (and must not) wrap your commands with `docker exec ...` yourself. Just type plain shell commands as if you were ssh-ed into that box; the harness routes them. <!-- _SAASBENCH_AGENT_IN_CONTAINER -->

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

- Host: `postgres` (alias `db` also works)
- Port: `5432`
- Database: `app_iyjruvfz`
- Username: `appiyjruvfz`
- Password: `app123iyjruvfz`
- Connection URL: `postgresql://appiyjruvfz:app123iyjruvfz@postgres:5432/app_iyjruvfz`

**Redis (already running):**

- Host: `redis`
- Port: `6379`
- URL: `redis://redis:6379`

**Mock webhook receiver (already running):**

- URL inside the container: `http://host.docker.internal:9012`
- Endpoints: `POST /hook` (200) / `POST /always-500` (500) / `GET /history` (history) / `DELETE /history` (reset)
- The evaluation harness uses this receiver to verify webhook delivery for booking-lifecycle events. Do NOT modify it.

**The application must listen on host port `8016` (container port `3000` is the recommended internal mapping).** This is enforced by `task.md §8.1`. The REST `v1` (port 3003) and REST `v2` (port 5555) endpoints should be reachable through the front webapp on host port 8016 — the harness only ever calls `http://localhost:8016/api/v1/*`, `http://localhost:8016/api/v2/*`, `http://localhost:8016/api/trpc/*`. The implementation may use a single multi-router server, multiple dedicated servers behind a reverse-proxy / URL-rewrite, or any framework — the critical constraint is that all documented endpoints respond on the specified ports.

### What you need to do

1. Build the application inside `/app`. The recommended layout is a TypeScript/Node monorepo (e.g. Yarn 4 + Turborepo or pnpm workspaces) with workspaces such as:
   - a webapp serving the booking flow + RBAC dashboard (any framework that provides server-rendered routes, e.g. Next.js)
   - a REST API v1 (any HTTP framework, e.g. Express / Next.js Pages Router / Fastify)
   - a REST API v2 (any modern HTTP framework, e.g. NestJS / Fastify / Express)
   - a `prisma` (or equivalent ORM) package — schema + migrations + seed (the schema is large; see `task.md §3` for required models)
   - a `trpc` package (or equivalent RPC layer) for internal webapp calls
   - shared utility / UI / platform packages
2. Run `yarn install --immutable` (uses the cache above; <1 min)
3. Run the prisma workspace's `db-deploy` and `db-seed` scripts to create schema and seed users (e.g. `yarn workspace <ns>/prisma db-deploy`).
4. Create the following 3 evaluation users (already created automatically if `db-seed` provisions the admin/owner/member triplet):

   | Role   | Username | Email                | Password (env-var or seeded) |
   |--------|----------|----------------------|------------------------------|
   | admin  | admin    | admin@example.com    | `ChangeMe!2026` (default)    |
   | owner  | owner    | owner@example.com    | `ChangeMe!2026`              |
   | member | member   | member@example.com   | `ChangeMe!2026`              |

   Passwords are environment-overridable via `EVAL_USER_<ROLE>_PASSWORD`.
5. Start three dev servers in the container background (one terminal each):
   ```bash
   cd /app && nohup <web-dev-cmd>    > /tmp/web.log    2>&1 &
   cd /app && nohup <api-v1-dev-cmd> > /tmp/api-v1.log 2>&1 &
   cd /app && nohup <api-v2-dev-cmd> > /tmp/api-v2.log 2>&1 &
   ```
   The exact commands depend on your package manager and monorepo layout (e.g.
   `yarn workspace <ns>/web dev`, `pnpm --filter web dev`, `npm run dev:web`). The agent
   MUST ensure all three dev processes are running and serving from `localhost:8016`.
6. Health checks: the application MUST expose `GET http://localhost:8016/api/healthz` returning `{"status":"ok"}` (this exact endpoint is asserted by the harness), and `GET http://localhost:8016/` MUST return any non-5xx response (a 200/307 redirect to /login is fine).

### Key technical requirements

- **Framework**: a TypeScript-based fullstack stack (recommended: Next.js for the webapp + a modern HTTP framework such as NestJS for REST v2; alternatives such as Fastify / Express / Remix / SvelteKit are acceptable as long as the documented routes respond)
- **ORM**: a relational ORM with PostgreSQL 15 (the recommended approach is Prisma; the task requires a large data model — see `task.md §3` for required entities)
- **Auth**: a session-based credentials provider (recommended: NextAuth or equivalent) + API key (prefix configurable via `API_KEY_PREFIX` env; defaults to `app_`)
- **API versioning**: `Api-Version: 2024-08-13` header on all v2 calls (the harness sends this header verbatim)
- **Pre-installed APIs**:
  - REST v1 at `http://localhost:8016/api/v1` — uses `?apiKey=app_xxx` query param (not `Authorization: Bearer`)
  - REST v2 at `http://localhost:8016/api/v2` — uses `Authorization: Bearer app_xxx`
  - RPC layer at `http://localhost:8016/api/trpc` — webapp internal only (any compatible RPC implementation is acceptable)
- **Webhook signing**: HMAC-SHA256 of payload with `webhook.secret`, header `X-App-Signature-256` (see `task.md §6.1` / KB for full algorithm)
- **Background jobs**: an in-process job queue with Redis-backed locking (recommended pattern; see `task.md §4`)
- **i18n**: dozens of locale catalogues via any standard i18n library (recommended file layout: `apps/web/public/static/locales/<lang>/common.json`)
- **Multi-tenant**: `Profile` model maps `userId × organizationId × username` (slug uniqueness scoped per org)
- **Note**: The evaluation script executes via `docker exec task_iyjruvfz-app bash -c "..."` and direct DB queries on `localhost:5441`, so the `psql` CLI MUST be on PATH (it already is in the `:model` image — `postgresql-client-14`).

### Evaluation user information

| Role   | Email                | Password         | UserPermissionRole | MembershipRole |
|--------|----------------------|------------------|--------------------|----------------|
| admin  | admin@example.com    | `ChangeMe!2026`  | ADMIN              | ADMIN          |
| owner  | owner@example.com    | `ChangeMe!2026`  | USER               | OWNER          |
| member | member@example.com   | `ChangeMe!2026`  | USER               | MEMBER         |

(All 3 are members of one team named `eval-team-<RANDOM_SUFFIX>` for the RBAC tests; framework auto-creates the team if missing.)

The complete requirements document with all 268 evaluation nodes (categories: Setup / Auth / API_v1 / API_v2 / tRPC / DataModel / RBAC / BusinessLogic_Booking / BusinessLogic_Scheduling / BusinessLogic_Webhook / BusinessLogic_Workflow / Cron / Integration / EdgeCases / Frontend / Internationalization / Security_Crypto / Deployment / ArchitectureQuality) is at `tasks/task_iyjruvfz/task/task.md` (≈6000 lines). Knowledge-base clarifications are at `tasks/task_iyjruvfz/kb/knowledge_base.json` (90 KB-### items).

---

## Tester Workflow

### Before testing: start the environment

```bash
cd <REPO_ROOT>/tasks/task_iyjruvfz/docker
# generate docker/.env if missing (NEXTAUTH_SECRET / APP_ENCRYPTION_KEY / CRON_API_KEY / JWT_SECRET)
[ -f .env ] || cp .env.example .env && \
    sed -i "s|please_replace_via_openssl_rand_base64_32|$(openssl rand -base64 32 | tr -d '\n')|g" .env && \
    sed -i "s|please_replace_via_openssl_rand_base64_24|$(openssl rand -base64 24 | tr -d '\n')|g" .env && \
    sed -i "s|please_replace_via_openssl_rand_hex_16|$(openssl rand -hex 16 | tr -d '\n')|g" .env
docker pull shadetocloak/task_iyjruvfz-app:latest
docker compose up -d
docker compose ps   # verify 4 containers: app/postgres/redis/mock-receiver
```

### During testing: send the prompt above + the contents of task.md to the model

The model will write code from scratch, run `pnpm install` (no pre-warmed cache, expect a few minutes on first run), run `prisma migrate`/`prisma db seed`, and start the dev servers inside the container via `docker exec`.

### After testing: run the evaluation

```bash
cd <REPO_ROOT>/check/task_iyjruvfz
./test_model_output.sh
```
