# SaaSBench Test Prompt — task_mnmtxiwb (Usage-Based Billing & Metering Platform)

> **How to use:**
> 1. Start the Docker environment first: `cd /path/to/SaaSBench_tasks/tasks/task_mnmtxiwb/docker && docker compose up -d`
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

You are a senior full-stack engineer. Your task is to build a complete usage-based billing and metering platform from scratch inside an already-running Docker environment.

### Environment

The Docker environment is already up and running — you do not need to pull images or start containers.

You work inside the application container (its name is shown by `docker compose ps`; the default is `billing-app`), with `/app` as the working directory (currently empty). The bash tool you have access to executes every command **inside** that container automatically — you do **not** need to (and must not) wrap your commands with `docker exec ...` yourself. Just type plain shell commands as if you were ssh-ed into that box; the harness routes them. <!-- _SAASBENCH_AGENT_IN_CONTAINER -->

**Tools pre-installed in the container** (Ubuntu 22.04):
- Ruby (`ruby-full` + `ruby-dev`) + Bundler (RubyChina mirror configured for `gem` and `bundle`)
- Node.js 20 + npm + pnpm + yarn + npx
- Python 3.10 + pip, Go
- PostgreSQL client 14 (psql, pg_isready); MariaDB / MySQL client; redis-cli; sqlite3
- Build essentials: gcc 11, g++, make, cmake, pkg-config
- Dev libraries: libssl-dev, libpq-dev, libsqlite3-dev, libxml2-dev, libffi-dev, libyaml-dev
- git, curl, wget, jq, openssl, unzip, ca-certificates
- `apt` is available for installing any additional packages or native libraries you need (e.g. `imagemagick`, `libvips-dev`, `ffmpeg`)

**No application dependencies are pre-installed beyond the language toolchains and `bundler` itself.** Declare and install your dependencies yourself (e.g., write a complete `Gemfile` and run `bundle install` for a Ruby stack) — installing a full web framework plus its background-job, GraphQL, and state-machine libraries will take a few minutes on first run. For Ruby stacks the Bundler mirror is already configured to point at `https://gems.ruby-china.com` for faster downloads from inside China.

**Database (PostgreSQL 15, already running):**
- Host: `db` (or `postgres` — both hostnames are reachable)
- Port: `5432`
- Database: `app_db` (configurable via `DB_NAME` env)
- Username: `app` (configurable via `DB_USER` env)
- Password: `changeme` (configurable via `DB_PASSWORD` env)
- Extensions installed: pgcrypto, uuid-ossp

**Redis (already running):**
- Host: `redis`
- Port: `6379`

**Kafka / Redpanda (already running):**
- Host: `kafka`
- Port: `9092`

**Gotenberg — PDF generation service (already running):**
- Host: `gotenberg`
- Port: `3000`

**The application MUST listen on port `3000`** (Docker maps it to host port `8005`).

**The following environment variables are injected into the container via Docker:**
- `RAILS_ENV=development`
- `SECRET_KEY_BASE=a1b2c3d4e5f6...` (already set)
- `DATABASE_URL=postgresql://app:changeme@postgres:5432/app_db`
- `REDIS_URL=redis://redis:6379/0`
- `REDIS_STORE_URL=redis://redis:6379/1`
- `KAFKA_BOOTSTRAP_SERVERS=kafka:9092`
- `GOTENBERG_URL=http://gotenberg:3000`
- `ENCRYPTION_PRIMARY_KEY`, `ENCRYPTION_DETERMINISTIC_KEY`, `ENCRYPTION_KEY_DERIVATION_SALT` (already set)
- `PREMIUM_OVERRIDE=true` (feature-flag toggle that unlocks premium features)

### What you need to do

1. Create a complete Ruby on Rails project inside `/app` (Gemfile, configuration, routes, models, controllers, migrations, GraphQL schema, etc.)
2. Run `bundle install` to install dependencies
3. Generate an RSA key pair for JWT signing. The recommended location is `config/keys/private.pem` / `config/keys/public.pem` (e.g. `mkdir -p config/keys && openssl genpkey -algorithm RSA -out config/keys/private.pem && openssl rsa -pubout -in config/keys/private.pem -out config/keys/public.pem`); the location is at the implementation's discretion as long as the keys are accessible to the application at runtime.
4. Run database migrations
5. Create the following evaluation user:
   - Admin: email=`admin@example.com`, password=`Admin123!` (admin role with full permissions)
   - Also create the supporting records: a tenant organization, a billing-entity record for invoicing, a user-organization membership, an admin role definition, the membership-role assignment, and an API key for REST authentication
6. Start the application server, listening on `0.0.0.0:3000`

### Key technical requirements

- **Framework**: any backend web framework supporting the prescribed REST + GraphQL API contracts (Ruby on Rails ~> 8.0 API mode is recommended for full feature parity; alternatives such as Express + Apollo Server, NestJS, or FastAPI + Strawberry are acceptable)
- **GraphQL**: any GraphQL server library (graphql-ruby recommended for Rails; alternatives: graphql-yoga, Apollo Server, Strawberry-GraphQL); JWT HS256 authentication (3-hour expiry, auto-refresh when < 1 hour remains)
- **REST API**: Bearer API Key authentication (`Authorization: Bearer <api_key>`); keys stored as cryptographic hashes (SHA-256 recommended; bcrypt / Argon2 acceptable)
- **State machines**: any state-machine library (e.g. aasm for Rails; alternatives: statesman, transitions, xstate) for entity lifecycle (e.g. Invoice draft → finalized → paid → voided)
- **Soft delete**: any soft-delete mechanism (e.g. discard for Rails; alternatives: paranoia, a custom `deleted_at` column)
- **Auditing**: any audit-trail library (e.g. paper_trail for Rails; alternatives: audited, a custom audit log)
- **Money**: any decimal-precision money library (e.g. money-rails for Rails; alternatives: the money gem, Python Decimal, Java BigDecimal). NEVER use float for monetary amounts.
- **Background jobs**: any Redis-backed queue (e.g. sidekiq for Rails; alternatives: Bull, Celery, RQ)
- **Kafka**: any Kafka consumer library (e.g. karafka for Rails; alternatives: kafka-node, kafka-python, sarama) for event consumption
- **Multi-tenant**: data isolation at the tenant organization level
- **RBAC**: predefined roles with multiple permission tiers (e.g. `admin` / `manager` / `finance`) plus support for custom roles
- **Premium features**: gated by a feature-flag environment variable (e.g. `PREMIUM_OVERRIDE=true`); the variable name is at the implementation's discretion as long as it is documented
- **Note**: the evaluation may execute language-native code inside the container via `docker exec` (e.g. `bundle exec rails runner '...'` for Ruby/Rails, or the equivalent runner for the chosen language/framework), so the corresponding runner command MUST be available on PATH

---

## Tester Workflow

### Before testing: start the environment

```bash
cd /path/to/SaaSBench_tasks/check/task_mnmtxiwb && ./prepare_workspace.sh
```

### During testing: send the prompt above + the contents of task.md to the model

The model will write code, install dependencies, and start the server inside the container via `docker exec`.

### After testing: run the evaluation

```bash
cd /path/to/SaaSBench_tasks/check/task_mnmtxiwb
./test_model_output.sh
```
