# SaaSBench Test Prompt — task_lgzivily (Clinical Practice Management Suite)

> **How to use:**
> 1. Start the Docker environment first:
>    `cd /path/to/SaaSBench_tasks/tasks/task_lgzivily/docker && docker compose up -d`
> 2. Send the **Prompt** section below to the model under test.
> 3. After the model finishes writing code, run
>    `./check/task_lgzivily/test_model_output.sh` to see the score.

---

## Prompt

> **<!-- _BENCH_ANTI_CHEAT_BANNER -->Mandatory anti-cheat policy.** You MUST implement
> the platform from scratch within this Docker environment. Cloning, copying,
> or otherwise importing any pre-existing open-source codebase (via
> `git clone`, `wget`, `curl`, container image extraction, package downloads
> of unrelated projects, etc.) is strictly forbidden and will be detected by
> the harness. Trajectories that fetch external source repositories receive a
> score of 0 regardless of the resulting test outcomes.

You are a senior full-stack engineer specializing in healthcare-grade web
applications. Your task is to build a complete, production-quality
**clinical practice management + EHR** system from scratch inside an
already-running Docker environment.

### Environment

The Docker environment is already up and running — you do not need to pull
images or start containers.

You work inside the container `task_lgzivily_app` (note the **underscore**
separators), with `/var/www/html` as the working directory. The bash tool you have access to executes every command **inside** that container automatically — you do **not** need to (and must not) wrap your commands with `docker exec ...` yourself. Just type plain shell commands as if you were ssh-ed into that box; the harness routes them. <!-- _SAASBENCH_AGENT_IN_CONTAINER -->

**Tools pre-installed in the container** (Ubuntu 22.04):

- PHP 8.1 CLI + ~60 PHP extensions (incl. bcmath, ctype, curl, dom, fileinfo,
  filter, gd, iconv, intl, mbstring, mysqli, mysqlnd, openssl, pdo,
  pdo_mysql, pdo_pgsql, pdo_sqlite, pgsql, redis, session, soap, sockets,
  sodium, sqlite3, tokenizer, xml, xmlreader, xmlwriter, xsl, zip, zlib,
  OPcache — run `php -m` in the container for the full list)
- Composer 2 (the image may pre-configure a packagist mirror for faster installs; the default registry also works)
- Node.js 20 + npm + pnpm + yarn + npx
- Python 3.10 + pip, Go
- PostgreSQL client 14 (psql, pg_isready); MariaDB / MySQL client; redis-cli; sqlite3
- Build essentials: gcc 11, g++, make, cmake, pkg-config
- Dev libraries: libssl-dev, libpq-dev, libsqlite3-dev, libxml2-dev, libffi-dev
- git, curl, wget, jq, openssl, unzip, ca-certificates
- `apt` is available for installing any additional packages (e.g. a web server: `apache2 libapache2-mod-php8.1`, `nginx php8.1-fpm`, or just use the built-in `php -S`)

**Database (MariaDB 11.x, already running):**

| Field | Value |
|---|---|
| Host | `db` (in-container) |
| Port | `3306` (in-container; published as `3310` on host) |
| Database | `app_lgzivily` |
| Username | `applgzivily` |
| Password | `app123lgzivily` |
| Root password | `rootpw` (only for database bootstrap) |

**The application MUST listen on container port `80`** (the web server you
install — Apache, nginx, or `php -S` — must bind there). The container's
default process is `tail -f /dev/null`; you are responsible for installing
and starting your chosen web server.

### What you need to do

1. Create a complete PHP/Laminas-MVC project rooted at `/var/www/html`
   (composer.json, configuration, routes, entities, controllers, services,
   migrations, etc. per the spec in `task.md`).
2. Run `composer install --no-dev --optimize-autoloader` to install
   PHP dependencies.
3. Run `npm install --no-audit --legacy-peer-deps` to install frontend
   dependencies, then `npx gulp default` to build the SASS theme bundle
   into `public/themes/`.
4. Generate the OAuth2 RSA keypair into
   `/var/www/html/sites/default/documents/oauth2/{private,public}.key`
   (create the directory chain first if it doesn't exist:
   `sites/default/documents/{oauth2,certificates,logs_and_misc/{methods,random_keys,temp},css,template,era,edi,mpdf,couchdb,letter_templates,custom_menus}`).
5. Initialize the database schema (create the **282 tables** + ACL seed +
   admin user) using your application's installer or migration tool. The
   admin user must have username `admin` and password `pass`.

6. Create the following **7 evaluation users** (admin is created by the
   installer; create the other 6 yourself) — all with password `pass`:

   | Username | Role (ARO group) |
   |---|---|
   | `admin` | Administrators |
   | `evalphys` | Physicians |
   | `evalclin` | Clinicians |
   | `evalfo` | Front Office |
   | `evalacct` | Accounting |
   | `evalrec` | Receptionist |
   | `evalemerg` | Emergency Login |

7. Set file permissions appropriate for your chosen web server (e.g.
   `chown -R www-data:www-data /var/www/html` if you install Apache or
   nginx + php-fpm; not needed if you run `php -S` as root).
8. Start your web server, listening on container port `80`. Examples:
   - `nohup apache2-foreground > /tmp/web.log 2>&1 &` (after
     `apt install -y apache2 libapache2-mod-php8.1` and configuring
     `DocumentRoot /var/www/html` + `mod_rewrite`)
   - `nohup php -S 0.0.0.0:80 -t /var/www/html > /tmp/web.log 2>&1 &`
     (built-in CLI server; simplest option)

### Key technical requirements (full spec in `task.md`)

- **Server:** PHP 8.1+ via the web server of your choice (Apache + mod_php,
  nginx + php-fpm, or `php -S` for the CLI server), serving from
  `DocumentRoot = /var/www/html`
- **Database:** MariaDB 11.x with `utf8mb4`, exactly **282 tables** as
  described in §3 of `task.md` (3774 columns total across 24 business
  domains — patient demographics, clinical encounters, billing, FHIR,
  scheduling, audit, ACL, immunizations, prescriptions, lab/procedures,
  documents, portal, …).
- **Framework:** Laminas MVC ^3.8 + Symfony ~6.4 components +
  Doctrine DBAL ^4.4 + ADODB ^5.22 wrapper + Twig 3 + Smarty 4 + Mustache.
- **Frontend:** AngularJS 1.8 + jQuery 3.7 + Bootstrap 4.6 + FullCalendar +
  Select2 + DataTables; Gulp 4 + SASS pipeline.
- **API conventions (§2.3 of task.md):**
  - Standard REST: `/apis/{site}/api/...`
  - FHIR R4: `/apis/{site}/fhir/...`
  - Portal: `/apis/{site}/portal/...`
  - OAuth2: `/oauth2/{site}/...`
  - `{site}` defaults to `default`.
- **Auth:** OAuth2 + OpenID Connect via `league/oauth2-server` ^8.4 +
  `steverhoades/oauth2-openid-connect-server` ^3.0.1; SMART on FHIR v2.2.0
  with granular `.cruds` scopes; PKCE for public clients; client
  registration at `/oauth2/{site}/registration`; JWKS at
  `/oauth2/{site}/jwk`; introspection at `/oauth2/{site}/introspect`;
  well-known discovery at `/.well-known/{smart,openid}-configuration`.
- **RBAC:** GACL-style ARO/ACO/AXO model (8 roles: admin/phys/clin/front/
  acct/recep/doc/emergency); `AclMain::aclCheckCore($section, $value, $user)`
  is the single check entry point.
- **HIPAA audit:** Every PHI write goes through `audit_master` +
  `audit_details`; failed logins logged to `log` table; OAuth2 token grants
  logged to `log` with `event=oauth2`.
- **FHIR R4:** 65+ resource types under `/apis/{site}/fhir/` with US Core
  3.1.0 conformance; `/fhir/metadata` returns a CapabilityStatement;
  bulk export ($export) returns 202 + `Content-Location` for polling.
- **Internationalisation:** `lang_languages` + `lang_constants` +
  `lang_definitions` tables (≥ 20 default languages including RTL).
- **Plug-in module system:** custom modules under
  `interface/modules/custom_modules/`, Zend modules under
  `interface/modules/zend_modules/`, registered in `modules` table.

### Notes for the model

- The harness will execute commands inside the container via
  `docker exec task_lgzivily_app …` and will hit endpoints over
  `http://localhost:8030/apis/default/...`, `/oauth2/default/...`,
  `/.well-known/...`.
- The complete and definitive specification is `task.md` (≈ 8 700 lines).
  **Read it carefully — every column, every endpoint, every business rule
  listed there is what the evaluation harness will actually check.**

---

## Tester Workflow

### Before testing: start the environment

```bash
cd /path/to/SaaSBench_tasks/tasks/task_lgzivily/docker
docker pull shadetocloak/task_lgzivily-app:latest
docker compose up -d
docker compose ps   # verify both task_lgzivily_app and task_lgzivily_db are up
```

### During testing: send the prompt above + the contents of task.md to the model

The model writes code, runs `composer install` / `npm install` / its
build pipeline / the schema initializer, creates the 7 users, installs and
starts a web server (Apache / nginx / `php -S`) on container port 80, all
via `docker exec`. The container's CMD is just `tail -f /dev/null`, so the
model is responsible for launching the web server itself.

### After testing: run the evaluation

```bash
cd /path/to/SaaSBench_tasks/check/task_lgzivily
./test_model_output.sh
```
