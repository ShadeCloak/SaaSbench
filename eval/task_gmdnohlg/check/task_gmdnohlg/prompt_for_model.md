# SaaSBench Test Prompt — task_gmdnohlg (CloudCollab Platform)

> **How to use:**
> 1. Start the Docker environment first: `cd <repo_root>/tasks/task_gmdnohlg/docker && docker compose up -d`
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

You are a senior full-stack engineer. Your task is to build a complete self-hosted file-sync and collaboration platform (CloudCollab Platform) from scratch inside an already-running Docker environment.

### Environment

The Docker environment is already up and running — you do not need to pull images or start containers.

You work inside the container `cloudcollab_app`, with `/app` as the working directory (currently empty). The bash tool you have access to executes every command **inside** that container automatically — you do **not** need to (and must not) wrap your commands with `docker exec ...` yourself. Just type plain shell commands as if you were ssh-ed into that box; the harness routes them. <!-- _SAASBENCH_AGENT_IN_CONTAINER -->

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

**Database (PostgreSQL 16, already running):**
- Host: `db`
- Port: `5432`
- Database: `app_gmdnohlg`
- Username: `appgmdnohlg`
- Password: `app123gmdnohlg`
- Extensions installed: uuid-ossp, pg_trgm

**The application MUST listen on container port `8033`** (mapped 1:1 to host port `8033`). The container ships no web server by default — install one yourself (e.g. `apt install -y apache2 libapache2-mod-php8.1` and configure it to listen on 8033 with `DocumentRoot /app/public` or `/app`, or use `apt install -y nginx php8.1-fpm`, or simply `php -S 0.0.0.0:8033 -t /app/public`).

### What you need to do

1. Create a complete PHP project inside `/app` (composer.json, routes, controllers, data models, database migrations, etc.)
2. Run `composer install` to install PHP dependencies
3. Run `npm install && npm run build` to install frontend dependencies and build
4. Run database migrations and create 93+ tables (table prefix `cc_`)
5. Create the following 4 evaluation users:
   - Admin: username=`eval_admin`, password=`evalAdmin123!` (admin role)
   - User1: username=`eval_user1`, password=`evalUser123!` (member of testgroup1 and testgroup2)
   - User2: username=`eval_user2`, password=`evalUser456!` (member of testgroup1)
   - SubAdmin: username=`eval_subadmin`, password=`evalSubadmin123!` (member of testgroup1, and subadmin of testgroup1)
6. Start your chosen web server and make sure the application responds on port `8033`

### Key technical requirements

- **Language**: PHP 8.1+ (the implementation may use any PHP web framework — examples: Symfony, Laravel, Slim, Phalcon, or a custom one built on PSR-7/PSR-15)
- **Database access**: a lightweight database access layer (e.g., raw PDO, Doctrine DBAL, Eloquent, or any DBAL-style library — full ORM is not required)
- **Frontend**: any modern SPA framework (e.g., Vue 3, React, Svelte) with a build tool (e.g., Vite, Webpack)
- **Database**: PostgreSQL with table prefix `cc_` (e.g., `cc_users`, `cc_filecache`)
- **Three-layer API protocol**:
  1. **Administrative API** (under `/api/v2/...`) — user/group/sharing/app management; JSON responses follow a consistent envelope structure with `meta` (status / statuscode / message) and `data` fields under a top-level `api` key, as required by the evaluator
  2. **REST API** (standard routes) — frontend interaction
  3. **WebDAV/CalDAV/CardDAV** (typically under `/remote/...` and `/dav/...`) — implemented using any RFC-compliant DAV server library
- **Authentication**: Session, Bearer token (device-specific app passwords), Basic Auth (for DAV clients), OAuth2
- **Permission bitmasks**: bitwise-OR-combinable flags — READ=1, UPDATE=2, CREATE=4, DELETE=8, SHARE=16; the value 31 represents ALL permissions combined
- **Web server**: any PHP-capable web server you install yourself (Apache + mod_php, nginx + php-fpm, or the built-in `php -S` CLI server)

---

## Tester Workflow

### Before testing: start the environment

```bash
cd <repo_root>/tasks/task_gmdnohlg/docker
docker compose up -d
docker compose ps   # verify both containers are running (app + db)
```

### During testing: send the prompt above + the contents of task.md to the model

The model will write code, install dependencies, and start the server inside the container via `docker exec`.

### After testing: run the evaluation

```bash
cd <repo_root>/check/task_gmdnohlg
./test_model_output.sh
```
