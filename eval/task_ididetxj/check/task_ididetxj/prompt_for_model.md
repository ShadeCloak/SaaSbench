# SaaSBench Test Prompt — task_ididetxj (Collaborative Knowledge Base & Wiki Platform)

> **How to use:**
> 1. Start the Docker environment first: `cd <REPO_ROOT>/tasks/task_ididetxj/docker && docker compose up -d`
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
>
> Examples of explicitly forbidden installs (non-exhaustive): `npm install outline-server`, `git clone https://github.com/outline/*`, `docker pull outlinewiki/outline:*`, `docker pull outlinewiki/*` — these are detected and trigger 0 score.
>
> Examples of explicitly allowed installs (these libraries are required by task.md §2.1 — using them is NOT cheating): `@hocuspocus/server`, `@hocuspocus/provider`, `@hocuspocus/extension-redis`, `@hocuspocus/extension-throttle`, `yjs`, `y-prosemirror`, `prosemirror-state`/`-view`/`-model`/`-schema-basic`/`-schema-list`, `sequelize`, `sequelize-typescript`, `umzug`, `koa`, `koa-router`, `koa-helmet`, `bull`, `@bull-board/api`, `@bull-board/koa`, `socket.io`, `socket.io-redis`, `passport`, `passport-google-oauth2`, `passport-slack-oauth2`, `passport-azure-ad`, `@simplewebauthn/server`, `@simplewebauthn/browser`, `@aws-sdk/client-s3`, `@node-oauth/oauth2-server`, plus the React/MobX/Vite frontend stack.

You are a senior full-stack engineer. Your task is to build a complete open-source collaborative knowledge base / wiki platform from scratch inside an already-running Docker environment.

### Environment

The Docker environment is already up and running — you do not need to pull images or start containers.

You work inside the container `task_ididetxj-app`, with `/app` as the working directory (currently empty). The bash tool you have access to executes every command **inside** that container automatically — you do **not** need to (and must not) wrap your commands with `docker exec ...` yourself. Just type plain shell commands as if you were ssh-ed into that box; the harness routes them. <!-- _SAASBENCH_AGENT_IN_CONTAINER -->

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
- Database: `app_ididetxj`
- Username: `appididetxj`
- Password: `app123ididetxj`
- Connection URL: `postgres://appididetxj:app123ididetxj@db:5432/app_ididetxj`
- Extensions pre-installed: `uuid-ossp`, `pg_trgm`, `citext`

**Redis (already running):**

- Host: `redis`
- Port: `6379`
- URL: `redis://redis:6379`

**File storage volume (persistent):**

- In-container path: `/var/lib/app/data`
- Used for attachment uploads (the application's local file storage)

**The webapp MUST listen on container port `8031` (host port `8031`).** This is enforced by `task.md §8`. The harness only ever calls `http://localhost:8031/api/...`, `http://localhost:8031/auth/...`, `http://localhost:8031/oauth/...`, `http://localhost:8031/_health`.

### What you need to do

1. Build a TypeScript Yarn 4 project inside `/app` matching the structure in `task.md §3` (40 entities organized into 7 domains).
2. Run `yarn install --immutable` (first install fetches deps from npm; expect 2-5 min on first run depending on network).
3. Run `yarn build` to produce the frontend bundle (Vite) + server transpile.
4. Run `yarn db:migrate` to apply ~281 sequelize migrations creating 42+ application tables.
5. Bootstrap the first team + admin via `POST /api/installation.create { teamName, userName, userEmail }`.
6. Create the following 5 evaluation users (admin via installation.create above; the rest via `users.invite` or direct SQL INSERT into `users` + `apiKeys` rows):

   | Role             | Email                          |
   |------------------|--------------------------------|
   | admin            | eval_admin@example.com         |
   | member           | eval_member@example.com        |
   | viewer           | eval_viewer@example.com        |
   | guest            | eval_guest@example.com         |
   | other_team_admin | eval_other_team@example.com (in a separate team) |

   Each user needs an entry in the `apiKeys` table with `name='eval_<role>'` and a `secret`/`hash` token consumable as `Authorization: Bearer ol_api_<38 chars>` per task.md §2.4 #6 (API token format `<7-char prefix><38 random word chars>`). The default prefix `ol_api_` is the evaluator's `EVAL_API_TOKEN_PREFIX` value (overridable via env at evaluation time); your implementation only needs to accept the supplied token verbatim as a Bearer header — the literal prefix string is not business-critical and is provided by the evaluator harness.

7. Start the application in the background: `cd /app && nohup yarn start > /tmp/app.log 2>&1 &` — this brings up `web + worker + websockets + collaboration + cron + admin` services per `task.md §8.1`.
8. The health-check endpoint `GET http://localhost:8031/_health` MUST return `200 OK` with body `OK`.

### Key technical requirements (full spec in task.md)

- **Stack**: TypeScript 5.9 + Node 20+ + Yarn 4 + Koa 3 + Sequelize 6 (`sequelize-typescript` decorators) + Umzug 3 (migrations) + PostgreSQL 16 + Redis 7
- **Frontend**: React + styled-components + MobX 4 + Vite + ProseMirror editor + Yjs CRDT
- **Real-time collaboration**: HocusPocus server + `@hocuspocus/extension-redis` for multi-process awareness
- **Real-time messaging**: Socket.io 4.x (with redis adapter)
- **Background queue**: Bull 4.x (Redis-backed) with `@bull-board/koa` admin UI
- **Auth (9 mechanisms)**: email magic link, Google/Slack/Azure/OIDC OAuth2, API token, session JWT (HS256, per-user `jwtSecret` rotated on password/email change), WebAuthn passkey, plugin-supplied OAuth
- **Acts as OAuth2 IdP**: `/oauth/authorize`, `/oauth/token`, `/oauth/revoke`, `/oauth/register`, `.well-known/oauth-authorization-server`
- **API style**: JSON-over-POST RPC (`/api/<resource>.<action>`)
- **RBAC**: 4-role matrix (admin / member / viewer / guest) × 3-level resource permissions (`read` / `read_write` / `admin`) × user/group memberships, with 403→404 leakage protection
- **Plugin system**: `PluginManager` loader with 10 hook types (Hook.API / Hook.AuthProvider / Hook.EmailTemplate / etc.)
- **40 entities + 6 ORM anomalies** (see task.md §3.99 — must be respected literally)

### Evaluation user information

| Role             | Email                       | API token name (in apiKeys table) | Bearer format          |
|------------------|-----------------------------|-----------------------------------|------------------------|
| admin            | eval_admin@example.com      | `eval_admin`                      | `ol_api_<38 chars>`    |
| member           | eval_member@example.com     | `eval_member`                     | `ol_api_<38 chars>`    |
| viewer           | eval_viewer@example.com     | `eval_viewer`                     | `ol_api_<38 chars>`    |
| guest            | eval_guest@example.com      | `eval_guest`                      | `ol_api_<38 chars>`    |
| other_team_admin | eval_other_team@example.com | `eval_other_team_admin`           | `ol_api_<38 chars>`    |

The 5 tokens must be persistable so the harness can read them from `/tmp/saasbench_eval_<role>_token.txt` (the `preseed_fixtures.py` step in `test_source_code.sh` creates these for the source-code test; for model-output test, the harness's P13 primitive will INSERT them itself into the `apiKeys` table given each role's user already exists).

The complete requirements document with all 222 evaluation nodes (categories: Deployment / DataModel / Authentication / API / BusinessLogic / RBAC / Realtime / AsyncQueue / OAuthProvider / Search / Webhook / Email / EdgeCases / Frontend / ArchitectureQuality / CLI) is at `tasks/task_ididetxj/task/task.md` (~2811 lines). Knowledge-base clarifications are at `tasks/task_ididetxj/kb/knowledge_base.json` (~84 KB-### items).

---

## Tester Workflow

### Before testing: start the environment

```bash
cd <REPO_ROOT>/tasks/task_ididetxj/docker
# generate docker/.env if missing (SECRET_KEY / UTILS_SECRET)
[ -f .env ] || cp .env.example .env && \
    sed -i "s|please_replace_via_openssl_rand_hex_32|$(openssl rand -hex 32 | tr -d '\n')|" .env && \
    sed -i "s|please_replace_via_openssl_rand_hex_32|$(openssl rand -hex 32 | tr -d '\n')|" .env
# Image is already loaded locally; `docker pull` may be skipped if you don't have network access.
docker pull shadetocloak/task_ididetxj-app:latest 2>/dev/null || echo "(skipping pull — using local image)"
docker compose up -d
docker compose ps   # verify 3 containers: app/db/redis
```

### During testing: send the prompt above + the contents of task.md to the model

The model will write code from scratch in `/app`, run `yarn install` (no pre-warmed cache, expect a few minutes on first run), `yarn build`, `yarn db:migrate`, create the 5 evaluation users + their API tokens, then start `yarn start` inside the container via `docker exec`.

### After testing: run the evaluation

```bash
cd <REPO_ROOT>/check/task_ididetxj
./test_model_output.sh
```
