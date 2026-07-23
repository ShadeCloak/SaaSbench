# SaaSBench Test Prompt — task_gavmyneb (Learning Management System)

> **How to use:**
> 1. Start the Docker environment first: `cd /path/to/SaaSBench_tasks/tasks/task_gavmyneb/docker && docker compose up -d`
> 2. Send the "Prompt" section below to the model under test (along with `tasks/task_gavmyneb/task/task.md`)
> 3. After the model finishes writing code, run `./test_model_output.sh` to see the score

---

## Prompt


> **<!-- _BENCH_ANTI_CHEAT_BANNER -->Mandatory anti-cheat policy.** You MUST implement
> the platform from scratch within this Docker environment. Cloning, copying,
> or otherwise importing any pre-existing open-source codebase (via
> `git clone`, `wget`, `curl`, container image extraction, package downloads
> of unrelated projects, etc.) is strictly forbidden and will be detected by
> the harness. Trajectories that fetch external source repositories (any
> pre-existing open-source LMS project, regardless of brand) receive a score
> of 0 regardless of the resulting test outcomes. Use the listed dependencies
> (Ruby/Node/etc. and the official package registries) only.

You are a senior full-stack engineer. Your task is to build a complete enterprise-grade Learning Management System (LMS) from scratch inside an already-running Docker environment. The platform must support multi-tenant, multi-role learning workflows across various education segments (e.g., schools, universities, corporate training).

### Environment

The Docker environment is already up and running — you do not need to pull images or start containers.

You work inside the container `lms-web`, with `/usr/src/app` as the working directory (it is empty — you'll write all source code, install all gems and node packages, and build all assets from scratch). The bash tool you have access to executes every command **inside** that container automatically — you do **not** need to (and must not) wrap your commands with `docker exec ...` yourself. Just type plain shell commands as if you were ssh-ed into that box; the harness routes them. <!-- _SAASBENCH_AGENT_IN_CONTAINER -->

**Tools pre-installed in the container:**
- Ruby 3.4 + Bundler 2.5+
- Node.js 20.x + Yarn 1.x (Classic)
- PostgreSQL client 16
- Redis client
- ImageMagick + libvips, poppler-utils (pdftotext)
- libxmlsec1 + xmlsec1 (SAML)
- Build essentials, git, jq, etc.

**Database (PostgreSQL 16, already running, container `lms-db`):**
- Host: `db`
- Port: `5432`
- Pre-created database:
  - `app_gavmyneb` (owner: `appgavmyneb` / `app123gavmyneb`) — task.md §8 standard
- Extensions installed in both: `pg_trgm`, `btree_gist`, `uuid-ossp`, `pgcrypto`

**Redis 7 (already running, container `lms-redis`):**
- Host: `redis`
- Port: `6379`

**The application MUST listen on port `8017`** (mapped to host `localhost:8017`).

**Environment variables already injected (see `.env`):**
- `DATABASE_URL` may be derived from `POSTGRES_HOST` / `POSTGRES_PORT` / `POSTGRES_USER_TASK` / `POSTGRES_PASSWORD_TASK` / `POSTGRES_DB`
- `REDIS_URL=redis://redis:6379/0`
- `SECRET_KEY_BASE`
- `ENCRYPTION_KEY=facdd3a131ddd8988b14f6e4e01039c93cfa0160`
- `APP_ENV=development` (the source baseline implementation also reads `RAILS_ENV` for compatibility)
- `APP_PORT=8017`

### What you need to do

1. Create a complete LMS project inside `/usr/src/app/` (project configuration, routes, models, controllers, database migrations, a modern SPA frontend with a build tool, etc.) — **see `task.md` for the complete spec. You MUST use a Ruby on Rails 8 + React 18 stack: the evaluation harness bootstraps the evaluation users by running `bin/rails runner` inside the container against Canvas-compatible ActiveRecord models (`User`, `Pseudonym`, etc.), so a non-Rails stack (or a Rails app without these models/tables) will fail user creation and every check that depends on it.**
2. Install backend dependencies (e.g., `bundle install --jobs 4` for Ruby; the analogous package manager for other stacks)
3. Install JS dependencies (e.g., `yarn install` or `npm install`)
4. Run database migrations to create the approximately 290+ tables defined in §3 of `task.md`
5. Create initial seed data (default tenant root account, site administrator, default notification types, etc.)
6. Create the following 6 evaluation users (used by the harness):

| Role | Email | Password |
|------|-------|----------|
| admin | eval_admin@test.com | Admin123!@# |
| teacher | eval_teacher@test.com | Admin123!@# |
| student | eval_student@test.com | Admin123!@# |
| observer | eval_observer@test.com | Admin123!@# |
| ta | eval_ta@test.com | Admin123!@# |
| account_admin | eval_account_admin@test.com | Admin123!@# |

7. Build the frontend assets (e.g., `yarn build` → output under `public/dist/` or the framework-equivalent path)
8. Start the application server bound to `0.0.0.0:80` inside the container (container port 80 is mapped to host port 8017). The exact command depends on the chosen stack (e.g., `bundle exec rails server -b 0.0.0.0 -p 80` for Rails / Puma).
9. Start the asynchronous-task worker process inside the `lms-worker` container (e.g., `bundle exec rake jobs:work` for a PostgreSQL-based delayed-job queue, or any equivalent worker for the chosen backend).

### Key technical requirements (refer to `task.md` for full details)

- **Backend (REQUIRED)**: Ruby 3.4 + Rails 8.0 + Puma 7. This is mandatory — the harness drives user setup and several data assertions through `bin/rails runner` against Canvas-style ActiveRecord models (`User`, `Pseudonym`, account/enrollment tables), so other stacks (Django, NestJS/Express, Go, …) will not satisfy those checks.
- **Frontend**: any modern SPA framework (React 18 + React Router 6 + a GraphQL client + a data-fetching layer + a Webpack-compatible bundler is recommended) with TypeScript
- **API**: REST JSON + GraphQL (any production-grade GraphQL server library)
- **Authentication**: support multiple authentication mechanisms (e.g., username/password, federated SAML 2.0, CAS, LDAP, OAuth 2.0 with common identity providers like Google/Microsoft, API Bearer Token, education-specific protocols like LTI 1.3 JWT, encrypted session cookies)
- **RBAC**: a configurable role-based access-control system with multiple base roles, support for custom roles, and approximately 150+ fine-grained permission points with account-chain inheritance
- **Multi-tenant**: account tree (parent_account_id), data scoped by `root_account_id`
- **Async tasks**: any asynchronous task-processing backend (e.g., a PostgreSQL-based delayed-job queue, a Redis-based queue like Sidekiq, RabbitMQ-backed workers, etc.)
- **Endpoints**: a comprehensive REST API (approximately 1700+ endpoints) plus a GraphQL API (dozens of queries and approximately 100 mutations)
- **Health check**: `GET /health_check` (must return `{"status": "..."}` JSON when `Accept: application/json`)
- **i18n**: support 30+ languages
- **Note**: the evaluation executes Ruby code inside the container via `docker exec lms-web bash -c "cd /usr/src/app && bin/rails runner '...'"` (e.g. it creates the 6 evaluation users with `User.find_or_create_by!` + `Pseudonym.find_or_create_by!(unique_id: "eval_<role>@test.com", ...)`). Your app MUST expose a working `bin/rails runner` and Canvas-compatible `User`/`Pseudonym` models for this to succeed.

### Core domains (5 areas defined in task.md)

1. **Identity & Authentication** (§3.1, §4.1) — ~50 entities, ~45 business rules
2. **Courses & Enrollments** (§3.2, §4.2) — ~30 entities, ~40 business rules
3. **Assessments & Grading** (§3.3, §4.3) — ~80 entities, ~50 business rules
4. **Communication & Content** (§3.4, §4.4) — ~55 entities, ~35 business rules
5. **Files, LTI, Frontend & Plugins** (§3.5, §4.5) — ~85 entities, ~35 business rules

---

## Tester Workflow

### Before testing: start the environment

```bash
cd /path/to/SaaSBench_tasks/tasks/task_gavmyneb/docker
docker pull shadetocloak/task_gavmyneb-app:latest
docker compose up -d
docker compose ps   # verify all 4 containers (web, worker, db, redis) are running
```

### During testing: send this prompt + the contents of task.md to the model

The model will write code from scratch, install backend and frontend dependencies (these will take a while on first run — there is no pre-warmed cache), run database migrations, and start the application server + async-task worker inside the container via `docker exec`.

### After testing: run the evaluation

```bash
cd /path/to/SaaSBench_tasks/check/task_gavmyneb
./test_model_output.sh
```

The harness will:
1. Health-check the application at `http://localhost:8017/health_check`
2. Try to create API access tokens for the 6 evaluation users
3. Run the full evaluation DAG (organized into 9 categories: Authentication / Authorization / DataModel / BusinessLogic / API_GraphQL / Frontend / Build / Deployment / ArchitectureQuality) — including LLM-judge nodes that assess code design quality
4. Print the final score (the source-code reference baseline targets ≥95% on the non-LLM-judge subset; model-output runs are typically expected at ≤20%)
