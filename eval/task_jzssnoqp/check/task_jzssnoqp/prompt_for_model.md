# SaaSBench Test Prompt — task_jzssnoqp (Omnichannel Customer Communication Platform)

> **How to use:**
> 1. Start the Docker environment first: `cd <repo-root>/tasks/task_jzssnoqp/docker && docker compose up -d`
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

You are a senior full-stack engineer. Your task is to build a complete omnichannel customer communication platform (an open-source alternative to Intercom / Zendesk) from scratch inside an already-running Docker environment.

### Environment

The Docker environment is already up and running — you do not need to pull images or start containers.

You work inside the container `jzssnoqp-app`, with `/app` as the working directory (currently empty). The bash tool you have access to executes every command **inside** that container automatically — you do **not** need to (and must not) wrap your commands with `docker exec ...` yourself. Just type plain shell commands as if you were ssh-ed into that box; the harness routes them. <!-- _SAASBENCH_AGENT_IN_CONTAINER -->

**Tools pre-installed in the container** (Ubuntu 22.04):
- Ruby (`ruby-full` + `ruby-dev`) + Bundler (RubyChina mirror configured for `gem` and `bundle`)
- Node.js 20 + npm + pnpm + yarn + npx
- Python 3.10 + pip, Go
- PostgreSQL client 14 (psql, pg_isready); MariaDB / MySQL client; redis-cli; sqlite3
- Build essentials: gcc 11, g++, make, cmake, pkg-config
- Dev libraries: libssl-dev, libpq-dev, libsqlite3-dev, libxml2-dev, libffi-dev, libyaml-dev
- git, curl, wget, jq, openssl, unzip, ca-certificates
- `apt` is available for installing any additional packages or native libraries you need (e.g. `imagemagick`, `libvips-dev`, `ffmpeg`)

**Database (PostgreSQL 16 + pgvector, already running):**
- Host: `db`
- Port: `5432`
- Database: `app_jzssnoqp`
- Username: `appjzssnoqp`
- Password: `app123jzssnoqp`
- Extensions installed: plpgsql, pgcrypto, pg_trgm, pg_stat_statements, vector

**Redis (already running):**
- Host: `redis`
- Port: `6379`

**The application MUST listen on port `8018`.**

**The following environment variables are injected into the container via `.env`:**
- `DATABASE_URL=postgresql://appjzssnoqp:app123jzssnoqp@db:5432/app_jzssnoqp`
- `REDIS_URL=redis://redis:6379/0`
- `SECRET_KEY_BASE=a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2`
- `PORT=8018`
- `RAILS_ENV=development`
- `ACTIVE_RECORD_ENCRYPTION_PRIMARY_KEY`, `ACTIVE_RECORD_ENCRYPTION_DETERMINISTIC_KEY`, `ACTIVE_RECORD_ENCRYPTION_KEY_DERIVATION_SALT` (Active Record encryption keys)

### What you need to do

1. Create a complete Ruby on Rails project inside `/app` (Gemfile, configuration, routes, models, controllers, migrations, Vue 3 frontend, etc.)
2. Run `bundle install` to install Ruby dependencies
3. Run `pnpm install` to install JS dependencies
4. Run database migrations
5. Create the following 5 evaluation users (you must create an Account first):

| Role | Name | Email | Password | Role |
|------|------|-------|----------|------|
| Admin | EvalAdmin | admin@eval.test | Password1! | administrator |
| Agent | EvalAgent | agent@eval.test | Password1! | agent |
| Custom Report | EvalCustomReportManage | custom_report@eval.test | Password1! | agent |
| Custom Conv | EvalCustomConvManage | custom_conv@eval.test | Password1! | agent |
| Zero Inbox | EvalZeroInbox | zero_inbox@eval.test | Password1! | agent |

6. Start the application server, listening on `0.0.0.0:8018`
7. Start Sidekiq for background job processing

### Key technical requirements

- **API format**: REST JSON, organized by audience with versioned paths (the path prefixes below are part of the API contract evaluated by the harness; do not change them):
  - main tenant-scoped API: `/api/v1/accounts/:account_id/...` (account-scoped CRUD)
  - reporting API: `/api/v2/...` (cross-tenant or aggregated reporting endpoints)
  - platform-level admin API: `/platform/api/v1/...` (cross-tenant management, gated by a platform token)
  - public unauthenticated API: `/public/api/v1/...` (e.g., webhooks, public endpoints)
  - embeddable widget API: `/api/v1/widget/...` (for the embeddable widget client)
- **Authentication**: support for multiple authentication mechanisms:
  1. A user access token for agents/admins, obtained via a sign-in endpoint (e.g., `POST /auth/sign_in`) and sent in a custom request header (the recommended header name is `api_access_token`; alternative names such as `X-Auth-Token` or `Authorization: Bearer ...` are acceptable as long as the contract is honoured). Token-based auth libraries (e.g., DeviseTokenAuth, Devise + JWT, or any equivalent) may be used.
  2. A platform-level admin token for cross-tenant administration endpoints (used through `/platform/api/v1/...`).
  3. A bot/integration token for automated agent bots.
  4. A widget/contact token for embeddable widget clients.
  5. A session cookie for browser-based access.
- **Framework**: any backend web framework supporting the prescribed REST API contract (Ruby on Rails ~> 7.1 is the recommended stack for full feature parity; alternatives such as Django + DRF, Express, NestJS, or Phoenix are acceptable)
- **Frontend**: any modern SPA framework (Vue 3 + Pinia + Vue Router + Vite is the recommended stack; alternatives such as React + Redux + Vite, or Svelte + SvelteKit, are acceptable)
- **Real-time communication**: any WebSocket or SSE library (e.g., Action Cable for Rails, Socket.IO for Node.js, Django Channels, or any raw `ws` implementation)
- **Background jobs**: any Redis-backed queue with cron-style scheduling (e.g., Sidekiq + sidekiq-cron for Ruby, Bull + bull-board for Node.js, Celery + celery-beat for Python, RQ + rq-scheduler)
- **Authorization**: any policy-based authorization library (e.g., Pundit for Rails, CanCanCan, casl.js for Node.js, django-guardian for Django)
- **File storage**: any storage abstraction with local-disk support (e.g., ActiveStorage for Rails, CarrierWave, Shrine, multer for Node.js, django-storages for Django; local-disk storage is sufficient for evaluation)
- **Multi-tenant**: each tenant workspace (named `Account` in the data-model contract) is an independent environment with full data isolation
- **Note**: the evaluation script may execute language-native code inside the container via `docker exec` (for example, `bundle exec rails runner '...'` for Ruby/Rails; `python manage.py shell -c '...'` for Django; `node -e '...'` for Node.js; or any equivalent runtime evaluator). The container name and runner command are read from env vars (defaults: `APP_CONTAINER_NAME=jzssnoqp-app`, `APP_RUNNER_CMD="bundle exec rails runner"`).

---

## Tester Workflow

### Before testing: start the environment

```bash
cd <repo-root>/tasks/task_jzssnoqp/docker
docker pull shadetocloak/task_jzssnoqp-app:latest
docker compose up -d
docker compose ps   # verify all 4 containers are running (app, db, worker, redis)
```

### During testing: send the prompt above + the contents of task.md to the model

The model will write code, install dependencies, and start the server inside the container via `docker exec`.

### After testing: run the evaluation

```bash
cd <repo-root>/check/task_jzssnoqp
./test_model_output.sh
```
