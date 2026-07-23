# SaaSBench Test Prompt — task_aoiwqoiq (Community Forum Platform)

> **How to use:**
> 1. Start the Docker environment first: `cd ${REPO_ROOT}/tasks/task_aoiwqoiq/docker && docker compose up -d`
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
>
> Additionally, you MUST NOT install any pre-existing community-forum-specific
> library, plugin, or framework template (such as `flarum`, `nodebb`,
> `vanilla-forum`, `phpbb`, `vbulletin`, `forem`, or any equivalent
> off-the-shelf forum/community platform package). Generic Ruby /
> Rails / Ember / Node libraries such as `rails`, `activerecord`, `pg`,
> `sidekiq`, `redis`, `puma`, `unicorn`, `devise`, `pundit`, `rack`, `nokogiri`,
> `image_processing`, `bcrypt`, `jwt`, `pg_search`, `acts-as-taggable-on` are
> permitted as long as they are used as low-level building blocks.

You are a senior full-stack engineer. Your task is to build a complete community forum platform from scratch inside an already-running Docker environment.

### Environment

The Docker environment is already up and running — you do not need to pull images or start containers.

You work inside the container `task_aoiwqoiq-app`, with `/app` as the working directory (currently empty). The bash tool you have access to executes every command **inside** that container automatically — you do **not** need to (and must not) wrap your commands with `docker exec ...` yourself. Just type plain shell commands as if you were ssh-ed into that box; the harness routes them. <!-- _SAASBENCH_AGENT_IN_CONTAINER -->

**Tools pre-installed in the container** (Ubuntu 22.04):
- Ruby (`ruby-full` + `ruby-dev`) + Bundler (a mirror is preconfigured for `gem` and `bundle`)
- Rust (rustup-installed `stable` toolchain at `/root/.cargo/bin/`, on `PATH`; a mirror is preconfigured for `cargo`)
- Node.js 20 + npm + pnpm + yarn + npx
- Python 3.10 + pip, Go
- Native libraries: libpq-dev, libxml2-dev, libxslt1-dev, libmagickwand-dev, imagemagick, libffi-dev, libidn11-dev, libicu-dev, libvips-dev, ffmpeg, libyaml-dev
- PostgreSQL client 14 (psql, pg_isready); MariaDB / MySQL client; redis-cli; sqlite3
- Build essentials: gcc 11, g++, make, cmake, pkg-config
- git, curl, wget, jq, openssl, unzip, ca-certificates
- `apt` is available for installing any additional packages you need

**Database (PostgreSQL 16, already running):**
- Host: `db`
- Port: `5432`
- Database: `app_aoiwqoiq`
- Username: `appaoiwqoiq`
- Password: `app123aoiwqoiq`
- Extensions installed: pg_trgm, hstore, unaccent, uuid-ossp, vector

**Redis (already running):**
- Host: `redis`
- Port: `6379`

**The application MUST listen on port `8020`.**

### What you need to do

1. Create a complete Ruby on Rails project inside `/app` (Gemfile, configuration, routes, models, controllers, migrations, etc.)
2. Run `bundle install` to install dependencies
3. Run database migrations
4. Create the following 3 evaluation users:
   - Admin: username=`eval_admin`, email=`eval_admin@eval.test`, password=`EvalPass12345!` (admin=true, trust_level=4)
   - Moderator: username=`eval_moderator`, email=`eval_mod@eval.test`, password=`EvalPass12345!` (moderator=true, trust_level=4)
   - User: username=`eval_user`, email=`eval_user@eval.test`, password=`EvalPass12345!` (trust_level=1)
5. Start the application server, listening on `0.0.0.0:8020`

### Key technical requirements

- **No `/api/` prefix**: JSON responses are triggered by the URL suffix `.json` or by the `Accept: application/json` header
- **Authentication**: support the request headers `Api-Key` + `Api-Username` (server-to-server style) **and/or** `User-Api-Key` + `Api-Username` (mobile-client style). The evaluator probes both header names, so supporting either one is sufficient.
- **Framework**: a JVM-free Ruby web framework (Rails ~> 8.0 is the reference; any equivalent rack-based Ruby framework that satisfies the same routes/contracts is acceptable)
- **ORM**: ActiveRecord (or any equivalent Ruby ORM that issues compatible SQL) + PostgreSQL
- **Cache**: Redis
- **Background jobs**: Sidekiq (or any equivalent Redis-backed Ruby job system)
- **Note**: The evaluation script will execute Ruby code inside the container via `docker exec task_aoiwqoiq-app rails runner "..."`, so the `rails` command MUST be available on PATH

---

## Tester Workflow

### Before testing: start the environment

```bash
cd ${REPO_ROOT}/tasks/task_aoiwqoiq/docker
docker pull ${APP_IMAGE:-task_aoiwqoiq/app}:${IMAGE_TAG:-baseline} 2>/dev/null || true
docker compose up -d
docker compose ps   # verify all 3 containers are running
```

### During testing: send the prompt above + the contents of task.md to the model

The model will write code, install dependencies, and start the server inside the container via `docker exec`.

### After testing: run the evaluation

```bash
cd ${REPO_ROOT}/check/task_aoiwqoiq
./test_model_output.sh
```
