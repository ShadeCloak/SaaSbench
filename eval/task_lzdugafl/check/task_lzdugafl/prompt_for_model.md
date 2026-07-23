# SaaSBench Test Prompt — task_lzdugafl (Professional Time Tracking Management System)

> **How to use:**
> 1. Start the Docker environment first: `cd <repo_root>/tasks/task_lzdugafl/docker && docker compose up -d`
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

You are a senior full-stack engineer. Your task is to build a complete professional time-tracking and project-management system from scratch inside an already-running Docker environment.

### Environment

The Docker environment is already up and running — you do not need to pull images or start containers.

You work inside the container `timetracker-app`, with `/app` as the working directory (currently empty). The bash tool you have access to executes every command **inside** that container automatically — you do **not** need to (and must not) wrap your commands with `docker exec ...` yourself. Just type plain shell commands as if you were ssh-ed into that box; the harness routes them. <!-- _SAASBENCH_AGENT_IN_CONTAINER -->

**Tools pre-installed in the container** (Ubuntu 22.04):
- PHP 8.1 CLI + ~60 PHP extensions (incl. bcmath, ctype, curl, dom, fileinfo, filter, gd, iconv, intl, mbstring, mysqli, mysqlnd, openssl, pdo, pdo_mysql, pdo_pgsql, pdo_sqlite, pgsql, redis, session, soap, sockets, sodium, sqlite3, tokenizer, xml, xmlreader, xmlwriter, xsl, zip, zlib, OPcache — run `php -m` in the container for the full list)
- Composer 2 (a package mirror may be pre-configured)
- Node.js 20 + npm + pnpm + yarn + npx
- Python 3.10 + pip, Go
- PostgreSQL client 14 (psql, pg_isready); MariaDB / MySQL client; redis-cli; sqlite3
- Build essentials: gcc 11, g++, make, cmake, pkg-config
- Dev libraries: libssl-dev, libpq-dev, libsqlite3-dev, libxml2-dev, libffi-dev
- git, curl, wget, jq, openssl, unzip, ca-certificates
- `apt` is available for installing any additional packages (e.g. a web server: `apache2 libapache2-mod-php8.1`, `nginx php8.1-fpm`, or just use the built-in `php -S`)

**Database (MySQL 8.0, already running):**
- Host: `db`
- Port: `3306` (in-container port)
- Database: `timetracker_db`
- Username: `tt_user`
- Password: `tt_pass`

**The application MUST listen on container port `80`** (mapped to host port `8001`). The container ships no web server by default — install one yourself (e.g. `apt install -y apache2 libapache2-mod-php8.1` with `DocumentRoot /app/public` and `mod_rewrite`, or `apt install -y nginx php8.1-fpm`, or use `php -S 0.0.0.0:80 -t /app/public`).

### What you need to do

1. Create a complete PHP project inside `/app` (composer.json, configuration, routes, entities, controllers, migrations, etc.) — Symfony 6.4 is the recommended framework
2. Create an application `.env` (or equivalent config) configuring `DATABASE_URL` to connect to the database
3. Run `composer install` to install dependencies
4. Run database migrations (`php bin/console doctrine:migrations:migrate`)
5. Create the following 3 evaluation users:
   - Admin: username=`eval_admin`, email=`eval_admin@test.com`, password=`EvalPass123!` (role: ROLE_SUPER_ADMIN)
   - Teamlead: username=`teamlead`, email=`teamlead@test.com`, password=`Teamlead123!` (role: ROLE_TEAMLEAD)
   - User: username=`testuser`, email=`user@test.com`, password=`User123!@#` (role: ROLE_USER)
6. Clear and warm up the application cache as your framework requires (e.g., `php bin/console cache:clear && php bin/console cache:warmup` for Symfony; the equivalent for other frameworks)
7. Set permissions (`chown -R www-data:www-data /app/var`)
8. Start your chosen web server, listening on container port `80`, with the document root pointing at `/app/public` (the framework's front controller)

### Key technical requirements

- **Framework**: any PHP web framework (Symfony 6.4 recommended for full feature parity; alternatives: Laravel, Slim, custom PSR-7/PSR-15)
- **ORM**: any PHP ORM (Doctrine ORM 2.x recommended; alternatives: Eloquent, raw PDO with custom DAO)
- **Frontend**: server-rendered templates (Twig / Blade / native PHP) + Bootstrap 5 + any admin theme (Tabler recommended; alternatives: AdminLTE, CoreUI)
- **API**: REST + JSON, every API path is prefixed with `/api` (path prefix is configurable via env)
- **API authentication**: Bearer Token authentication. The header name is configurable (default `X-AUTH-TOKEN`; the implementation may also accept `Authorization: Bearer <token>` or `X-API-Key`)
- **Serialization**: any JSON serialization library (JMS Serializer, Symfony Serializer, etc.)
- **API documentation**: OpenAPI / Swagger via any spec generator (NelmioApiDocBundle, swagger-php, OpenAPI-Generator, etc.)
- **i18n**: any translation library supporting 30+ languages (Symfony Translation, Laravel Lang, gettext, etc.)
- **CORS**: any CORS middleware (NelmioCorsBundle, Laravel CORS middleware, custom)
- **Build tool**: any frontend bundler (Webpack Encore / Vite / esbuild / Mix)
- **Web server**: any PHP-capable web server you install (Apache + mod_php, nginx + php-fpm, or `php -S`), with `DocumentRoot=/app/public` and URL rewriting enabled (`mod_rewrite` or nginx `try_files`)
- **Role system**: four-tier roles using a consistent naming convention (recommended for Symfony-style: `ROLE_USER` / `ROLE_TEAMLEAD` / `ROLE_ADMIN` / `ROLE_SUPER_ADMIN`; alternatives: `user` / `team_lead` / `admin` / `super_admin` for other frameworks)
- **API health endpoint**: `GET /api/ping` returns `{"message":"pong"}` (this is an interface contract — the response body must be exactly `{"message":"pong"}`)
- **Note**: the evaluation may execute framework-native CLI commands inside the container via `docker exec` (e.g., `php bin/console` for Symfony, `php artisan` for Laravel, `php -r` for any framework). The container name is provided via env var (default: `timetracker-app`).

---

## Tester Workflow

### Before testing: start the environment

```bash
cd <repo_root>/tasks/task_lzdugafl/docker
docker pull shadetocloak/task_lzdugafl-app:latest
docker compose up -d
docker compose ps   # verify both the app and db containers are running
```

### During testing: send the prompt above + the contents of task.md to the model

The model will write code, install dependencies, run migrations, create users, install and start a web server (Apache / nginx / `php -S`) on container port 80, all inside the container via `docker exec`. The container's default process is `tail -f /dev/null`, so the model is responsible for launching the web server itself.

### After testing: run the evaluation

```bash
cd <repo_root>/check/task_lzdugafl
./test_model_output.sh
```
