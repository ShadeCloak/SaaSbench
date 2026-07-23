# SaaSBench Test Prompt — task_cqfnbfay (Document Signing & Form Filling Platform)

> **How to use** (`$REPO_ROOT` = the directory where you cloned the SaaSBench_tasks repo):
> 1. Start the Docker environment first: `cd "$REPO_ROOT/tasks/task_cqfnbfay/docker" && docker compose up -d`
> 2. Send the "Prompt" section below to the model under test
> 3. After the model finishes writing code, run `"$REPO_ROOT/check/task_cqfnbfay/test_model_output.sh"` to see the score

---

## Prompt


> **<!-- _BENCH_ANTI_CHEAT_BANNER -->Mandatory anti-cheat policy.** You MUST implement
> the platform from scratch within this Docker environment. Cloning, copying,
> or otherwise importing any pre-existing open-source codebase (via
> `git clone`, `wget`, `curl`, container image extraction, package downloads
> of unrelated projects, etc.) is strictly forbidden and will be detected by
> the harness. Trajectories that fetch external source repositories receive a
> score of 0 regardless of the resulting test outcomes. Use the listed
> dependencies (Node/Ruby/Python/etc. and the official package registries)
> only.
>
> **In particular, the following e-signature-domain "shortcut" libraries are
> forbidden — relying on them constitutes cheating and will be flagged by
> the harness, scoring the trajectory as 0 (`cheat_detected=true`):**
> - **Ruby gems**: any `docuseal*` gem, `docusign-esign`, `hellosign`,
>   `pdf-forms`, `signhero`
> - **Python libraries** (if you choose to implement parts in Python):
>   `docuseal`, `docusign-esign`, `hellosign-sdk`, `pyhanko`,
>   `endesive`, `pysignpdf`
> - **Node packages**: `@docuseal/embed`, `docusign-esign`, `hellosign-sdk`
> - **Docker images**: `docuseal/*`, `docusealco/*`, `hellosign/*`,
>   `docusign/*`
>
> Generic primitives ARE allowed: `hexapdf`, `prawn`, `pdf-reader`, `origami`,
> `Devise`, `CanCanCan`, `Sidekiq`, `pyjwt`, `bcrypt`, `cryptography`, etc.

You are a senior full-stack engineer. Your task is to build a complete e-signature platform from scratch inside an already-running Docker environment.

### Environment

The Docker environment is already up and running — you do not need to pull images or start containers.

You work inside the container `cqfnbfay-app-1`, with `/app` as the working directory (it is empty — you'll write all source code from scratch and run `bundle install` + `yarn install` yourself; expect a few minutes for those installs since there is no pre-warmed cache). The bash tool you have access to executes every command **inside** that container automatically — you do **not** need to (and must not) wrap your commands with `docker exec ...` yourself. Just type plain shell commands as if you were ssh-ed into that box; the harness routes them. <!-- _SAASBENCH_AGENT_IN_CONTAINER -->

**Tools pre-installed in the container:**
- Ruby runtime + Bundler
- Node.js + npm
- Yarn (Node.js package manager)
- Git
- PostgreSQL client libraries
- Redis client
- ImageMagick / libvips (image processing)
- Standard build tools (gcc, make, build-base)

> Note: the container is based on Alpine Linux and uses `apk` instead of `apt-get` to install packages.

**Database (PostgreSQL 16, already running):**
- Host: `db`
- Port: `5432`
- Database: `app_cqfnbfay`
- Username: `appcqfnbfay`
- Password: `app123cqfnbfay`
- Extensions installed: plpgsql, btree_gin

**Redis (already running):**
- Host: `redis`
- Port: `6379`

**The application MUST listen on port `8021`.**

### What you need to do

1. Create a complete Ruby on Rails project inside `/app` (Gemfile, configuration, routes, models, controllers, migrations, etc.)
2. Run `bundle install` to install Ruby dependencies
3. Run `yarn install` to install frontend dependencies
4. Run database migrations
5. Create the following evaluation user:
   - first_name=`Eval`, last_name=`Admin`, email=`eval@test.com`, password=`EvalPass123!`
   - Belonging Account: name=`EvalCo`
   - Also create EncryptedConfig (APP_URL and ESIGN_CERTS)
6. Precompile frontend assets (`RAILS_ENV=production bundle exec rake assets:precompile`)
7. Start the application server, listening on `0.0.0.0:8021`

### Key technical requirements

- **Framework**: a Ruby web framework (e.g. Rails) backed by PostgreSQL
- **Authentication**: a database-backed authentication library (e.g. Devise, Sorcery) supporting password reset, "remember me", validation, trackable login, and lockable accounts; two-factor (TOTP) is required for the admin surface
- **Authorization**: a role-based authorization library (e.g. CanCanCan, Pundit) enforcing account-level data isolation (every query funnels through `current_user.account` or equivalent)
- **API**: all API routes live under the `/api/` namespace and use `X-Auth-Token` (Bearer-style header) for authentication
- **Background jobs**: a Redis-backed background job library (e.g. Sidekiq, Resque, GoodJob); may be embedded into the web server process or run as a separate worker
- **Frontend**: a JS-based reactive framework (e.g. Vue, React, Stimulus) plus Tailwind-style utility CSS for the operator dashboard and the public signing form; ERB / equivalent server-rendered templates may be mixed in
- **File handling**: an Active-Storage-style attachment subsystem (or equivalent — local disk is fine for the benchmark, but the design must allow swapping in S3/GCS/Azure backends without code surgery)
- **Search**: full-text search built on PostgreSQL native facilities (tsvector + GIN/trigram, or the `pg_search` gem) — no external Elasticsearch/Meilisearch
- **ORM**: ActiveRecord (or any ORM that maps to PostgreSQL) — the migrations and schema must live under `db/migrate/` with the conventional Rails timestamp prefix
- **Server**: any Rack-compatible web server that listens on `0.0.0.0:8021`; Puma is the conventional choice
- **Environment variables** are pre-configured in `.env`: DATABASE_URL, REDIS_URL, SECRET_KEY_BASE, PORT=8021, etc.
- The evaluation script will execute Ruby code inside the container via `docker exec cqfnbfay-app-1 bash -c "cd /app && RAILS_ENV=production bundle exec rails runner '...'"`, so a Rails-style `bundle exec rails runner` entry point must be available.

---

## Tester Workflow

### Before testing: prepare the environment

```bash
cd "$REPO_ROOT/check/task_cqfnbfay"
./prepare_workspace.sh
```

### During testing: send the prompt above + the contents of task.md to the model

The model will write code, install dependencies, and start the server inside the container via `docker exec`.

### After testing: run the evaluation

```bash
cd "$REPO_ROOT/check/task_cqfnbfay"
./test_model_output.sh
```
