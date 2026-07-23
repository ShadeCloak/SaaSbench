# SaaSBench Test Prompt — task_uybznoms (Headless CMS Framework)

> **How to use:**
> 1. Start the Docker environment first: `cd /path/to/SaaSBench_tasks/tasks/task_uybznoms/docker && docker compose up -d`
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

You are a senior full-stack engineer. Your task is to build a complete configurable Headless CMS framework from scratch inside an already-running Docker environment.

### Environment

The Docker environment is already up and running — you do not need to pull images or start containers.

You work inside the container `app_uybznoms`, with `/app` as the working directory (currently empty). The bash tool you have access to executes every command **inside** that container automatically — you do **not** need to (and must not) wrap your commands with `docker exec ...` yourself. Just type plain shell commands as if you were ssh-ed into that box; the harness routes them. <!-- _SAASBENCH_AGENT_IN_CONTAINER -->

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

**Database (PostgreSQL 15 + PostGIS, already running):**
- Host: `db`
- Port: `5432`
- Database: `app_uybznoms`
- Username: `appuybznoms`
- Password: `app123uybznoms`
- Extensions installed: uuid-ossp, postgis

**The application MUST listen on port `8002`** (in-container port).

### What you need to do

1. Create a complete TypeScript project inside `/app` using a modern full-stack framework (Next.js 15 App Router recommended) — package.json, tsconfig.json, configuration files, source code, etc.
2. Run `pnpm install` to install dependencies
3. Configure the database connection to PostgreSQL (any TypeScript ORM; Drizzle ORM recommended)
4. Run database migrations (the framework should auto-generate the schema from configuration and migrate)
5. Create the following evaluation users:
   - Admin: email=`admin@example.com`, password=`admin123` (role=admin)
   - Editor: email=`editor@test.com`, password=`Test1234!` (role=editor)
   - Restricted User: email=`restricted@test.com`, password=`Test1234!` (role=user)
6. Start the application server, listening on `0.0.0.0:8002`

### Key technical requirements

- **API prefix**: every REST endpoint lives under `/api`
- **Authentication**: JWT + cookie sessions + API keys; supports endpoints such as `/api/users/login` (login) and `/api/users/me` (current user), plus the first-time setup endpoint for initial admin user creation at **`POST /api/users/first-register`** — this exact path is REQUIRED: the evaluation harness creates the first admin (and the token every downstream check depends on) by POSTing to `/api/users/first-register`, so `/api/setup` or `/admin/install` will NOT work
- **Framework**: any modern full-stack framework (Next.js 15 App Router + TypeScript 5.x recommended for full feature parity; alternatives: Remix, SvelteKit, NestJS + a Vite frontend)
- **ORM**: any TypeScript ORM (Drizzle ORM recommended for type safety; alternatives: Prisma, Kysely, TypeORM)
- **GraphQL**: any GraphQL server library (`graphql-js` recommended; alternatives: Apollo Server, graphql-yoga, Mercurius)
- **Field types**: the framework should support approximately 21 field types covering basic data types, content types, structural types, and relational types. The recommended set includes: text, textarea, number, email, date, checkbox, select, radio, relationship, upload, richText, code, json, blocks, array, group, collapsible, row, tabs, ui, point, join. Implementations may include a configurable subset (recommended: at least 18 of the 21 listed types).
- **Versioning**: document version control with draft/published states
- **Access control**: granular field-level and collection-level permissions
- **Hook system**: field-level and collection-level hooks
- **File upload**: image processing (resizing, focal-point cropping)
- **Internationalisation**: field-level localisation
- **Package manager**: pnpm

---

## Tester Workflow

### Before testing: start the environment

```bash
cd /path/to/SaaSBench_tasks/tasks/task_uybznoms/docker
docker pull shadetocloak/task_uybznoms-app:latest
docker compose up -d
docker compose ps   # verify both containers are running (app + db)
```

### During testing: send the prompt above + the contents of task.md to the model

The model will write code, install dependencies, and start the server inside the container via `docker exec`.

### After testing: run the evaluation

```bash
cd /path/to/SaaSBench_tasks/check/task_uybznoms
./test_model_output.sh
```
