# SaaSBench Test Prompt — task_rjhcjrst (Personal Finance Manager)

> **How to use:**
> 1. Start the Docker environment first: `cd <REPO_ROOT>/tasks/task_rjhcjrst/docker && docker compose up -d`
> 2. Send the "Prompt" section below + the contents of `tasks/task_rjhcjrst/task/task.md` to the model under test
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

You are a senior PHP/Laravel engineer. Your task is to build a complete self-hosted Personal Finance Manager (PFM) platform from scratch inside an already-running Docker environment.

### Environment

The Docker environment is already up and running — you do not need to pull images or start containers.

You work inside the container `task_rjhcjrst-app`, with `/var/www/html` as the working directory. The bash tool you have access to executes every command **inside** that container automatically — you do **not** need to (and must not) wrap your commands with `docker exec ...` yourself. Just type plain shell commands as if you were ssh-ed into that box; the harness routes them. <!-- _SAASBENCH_AGENT_IN_CONTAINER -->

**Tools pre-installed in the container** (Ubuntu 22.04):
- PHP 8.1 CLI + ~60 PHP extensions (incl. bcmath, ctype, curl, dom, fileinfo, filter, gd, iconv, intl, mbstring, mysqli, mysqlnd, openssl, pdo, pdo_mysql, pdo_pgsql, pdo_sqlite, pgsql, redis, session, soap, sockets, sodium, sqlite3, tokenizer, xml, xmlreader, xmlwriter, xsl, zip, zlib, OPcache — run `php -m` in the container for the full list)
- Composer 2 (Aliyun mirror configured)
- Node.js 20 + npm + pnpm + yarn + npx
- Python 3.10 + pip, Go
- PostgreSQL client 14 (psql, pg_isready); MariaDB / MySQL client; redis-cli; sqlite3
- Build essentials: gcc 11, g++, make, cmake, pkg-config
- Dev libraries: libssl-dev, libpq-dev, libsqlite3-dev, libxml2-dev, libffi-dev
- git, curl, wget, jq, openssl, unzip, ca-certificates
- `apt` is available for installing any additional packages (e.g. a web server: `apache2 libapache2-mod-php8.1`, `nginx php8.1-fpm`, or just use the built-in `php -S`)

**Database (MySQL 8.0, already running):**

- Host: `db` (alias `mysql` also works)
- Port: `3306` (in-container; host-side `3309`)
- Database: `app_rjhcjrst`
- Username: `apprjhcjrst`
- Password: `app123rjhcjrst`
- Connection URL example: `mysql://apprjhcjrst:app123rjhcjrst@db:3306/app_rjhcjrst`

**mock-receiver** (HTTP webhook receiver for the P27 test primitive, already running):

- URL inside the container: `http://host.docker.internal:9001`
- Endpoints:
  - `POST /hook` → returns 200 (happy-path webhook target)
  - `POST /always-500` → returns 500 (retry-policy testing)
  - `GET /history?since=<unix_ts>` → list received requests
  - `DELETE /history` → clear
  - `GET /health` → 200 OK
- Used by the BIZ_WEBHOOK_* nodes — do NOT modify it.

**The application MUST listen on container port `80`** (mapped to host port `8022`) with the web server's DocumentRoot pointing at `/var/www/html/public` (Laravel front controller — see `task.md §9.1.1`). The container ships no web server by default — install one yourself (e.g. `apt install -y apache2 libapache2-mod-php8.1` with `mod_rewrite`, or `nginx php8.1-fpm`, or `php -S 0.0.0.0:80 -t /var/www/html/public`).

### What you need to do

1. Create a complete PHP PFM project inside `/var/www/html` (the recommended reference stack is Laravel 12 + Passport 12 — `composer.json`, `app/`, `routes/`, `resources/`, `config/`, `database/migrations/`, etc.).
2. Use the frozen Composer vendor (or run `composer install --no-dev --optimize-autoloader` if you absolutely must — it'll be slow).
3. Generate a Laravel `APP_KEY` and write it into `.env` (the `docker-compose.yml` provides `APP_KEY` and `STATIC_CRON_TOKEN` env vars; the in-container `.env` should match).
4. Run database migrations: `php artisan migrate --force` (the schema is described in `task.md §3` — 51 Eloquent models, 59 forward-only migrations).
5. Run `php artisan db:seed --force` to seed the default `transaction_currencies` and roles.
6. Generate Passport OAuth keys: `php artisan passport:keys` (or any equivalent CLI command that writes the OAuth signing keys to `storage/oauth-*.key`), then create at least one `password`-grant client via `php artisan passport:client --password --no-interaction --name="PFM"`. The harness will capture the generated `Client ID` and `Client secret` and pass them to the evaluation as `PASSPORT_CLIENT_ID` / `PASSPORT_CLIENT_SECRET` env vars.
7. Create the primary admin user (`admin@pfm.local` / `secret123`) — the helper script at `/var/www/html/_make_admin_user.php` does this idempotently:
   ```bash
   php /var/www/html/_make_admin_user.php
   ```
8. The 22 RBAC test users (`{owner,ro,full,mng_*,read_*,view_*}_user@pfm.local` + `alice_user@pfm.local`, all with password `EvalRBACPass123!`) are auto-provisioned by the evaluation harness via a helper script. **You must implement `/var/www/html/_make_rbac_user.php`** — a small PHP CLI script that takes user attributes from `argv` (or stdin JSON) and inserts the user with the right RBAC scope into the database. The harness will invoke it via `docker exec`.
9. Start your chosen web server (you'll need to install one — see "tools" above). The application MUST respond on `GET http://localhost:8022/` (HTTP 200/302/401/404/500/503 are all acceptable for the healthcheck — anything that proves the PHP front controller is responding).

### Key technical requirements

- **Framework (REQUIRED)**: You **MUST** use **Laravel 12**. The evaluation harness drives the app through Laravel-specific custom Artisan commands (`php artisan pfm:create-first-user`, `php artisan pfm:create-access-token`, `php artisan pfm:set-mfa`, `php artisan pfm:cron`) and assumes Laravel conventions (Passport-issued OAuth2 tokens, the Laravel Queue subsystem, `APP_KEY`/`Crypt` AES-256-CBC, the `failed_jobs`/`configurations` tables) as described in `task.md`. A different framework (Symfony, Slim, custom PSR-7/PSR-15) will not expose these `artisan` commands and will fail those checks. OAuth2 **must** be Laravel Passport 12.
- **Database**: MySQL 8.0 (`DB_CONNECTION=mysql`); approximately 51 data models with soft-delete semantics; multi-tenant via a `user_group_id` column on every shared table
- **Money**: arbitrary-precision decimal arithmetic — `DECIMAL(32,12)` columns + a big-decimal library (PHP `bcmath` recommended; equivalents in other languages are acceptable). NEVER use floating-point for monetary values.
- **API surface**: approximately 244 endpoints under `/api/v1/`, a JSON:API-style envelope (`{data, included, meta, links}` per the JSON:API spec), OAuth2 bearer token auth, pagination meta under `meta.pagination`
- **CLI namespace prefix**: `pfm:` (e.g. `pfm:create-user`, `pfm:cron`); approximately 85 commands are documented in task.md §10 (the exact count may vary by implementation)
- **Webhooks**: 8 trigger types, signed with an HMAC (the recommended algorithm is **SHA3-512**, an intentional design choice over SHA-256 — see KB for rationale) in a custom header (recommended name `X-PFM-Signature`)
- **AutoBudget**: 6 period boundaries × 3 reset modes (`reset` / `rollover` / `adjusted`)
- **Recurrence**: 5 patterns (`daily`/`weekly`/`monthly`/`ndom`/`yearly`) × 4 weekend modes
- **2FA**: TOTP (e.g. via `pragmarx/google2fa` or any RFC 6238 library), plaintext base32 secret in `users.mfa_secret`, 8 single-use recovery codes
- **RBAC**: approximately 21 fine-grained roles (`OWNER`/`FULL`/`READ_ONLY`/`MANAGE_*`/`READ_*`/`VIEW_*`); UserGroup multi-tenancy
- **Cron**: a single unified scheduled command (e.g. `php artisan pfm:cron` for Laravel; an equivalent for other stacks) orchestrates AutoBudget / Recurrence / Webhook delivery / Bill matching; URL trigger via `GET /api/v1/cron/{STATIC_CRON_TOKEN}` (URL-token auth)

### Evaluation user information

| Role          | Email                       | Password           |
|---------------|-----------------------------|--------------------|
| **admin**     | `admin@pfm.local`           | `secret123`        |
| RBAC × 21 roles | `<role>_user@pfm.local`   | `EvalRBACPass123!` (auto-provisioned by harness) |
| cross-group   | `alice_user@pfm.local`      | `EvalRBACPass123!` |

The 21 RBAC roles are listed in `evaluate/config.py` as `RBAC_USERS` — they are auto-created by the harness via `_make_rbac_user.php` whenever a node calls `P13(role=<role>)`. You do NOT need to create them manually.

### OAuth Passport defaults

- `PASSPORT_CLIENT_ID` and `PASSPORT_CLIENT_SECRET` are captured automatically by the harness from the `php artisan passport:client --password` output.
- The harness's `P13` primitive uses the `password` grant type at `POST /oauth/token`.

The complete requirements document with all 232 evaluation nodes (categories: Setup / API / RBAC / DataModel / BusinessLogic_{Bill,Budget,DoubleEntry,MultiCurrency,PiggyBank,Recurrence,Rule,Webhook,2FA} / Authentication / CLI / CronJobs / Deployment / EdgeCases / Frontend / ArchitectureQuality) is at `tasks/task_rjhcjrst/task/task.md` (≈8000 lines). Knowledge-base clarifications are at `tasks/task_rjhcjrst/kb/knowledge_base.json` (≈110 KB).

---

## Tester Workflow

### Before testing: start the environment

```bash
cd <REPO_ROOT>/tasks/task_rjhcjrst/docker
# generate docker/.env if missing (APP_KEY + STATIC_CRON_TOKEN)
[ -f .env ] || (cp .env.example .env && \
    sed -i "s|^APP_KEY=.*|APP_KEY=base64:$(openssl rand -base64 32 | tr -d '\n')|" .env && \
    sed -i "s|^STATIC_CRON_TOKEN=.*|STATIC_CRON_TOKEN=$(openssl rand -hex 16 | head -c 32)|" .env)
docker pull shadetocloak/task_rjhcjrst-app:latest
docker compose up -d
docker compose ps   # verify 3 containers: app/db/mock-receiver
```

### During testing: send the prompt above + the contents of task.md to the model

The model will write code, install dependencies (`composer install`, `npm install && npm run build`), run migrations, create the admin user, install and start a web server (Apache / nginx / `php -S`) on container port 80, all inside the container via `docker exec`. The container's default process is `tail -f /dev/null`.

### After testing: run the evaluation

```bash
cd <REPO_ROOT>/check/task_rjhcjrst
./test_model_output.sh
```
