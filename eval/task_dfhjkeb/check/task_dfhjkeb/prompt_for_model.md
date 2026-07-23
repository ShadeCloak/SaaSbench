# SaaSBench Test Prompt — task_dfhjkeb (Full-Featured E-Commerce Platform)

> **How to use:**
> 1. Start the Docker environment first: `cd <repo_root>/tasks/task_dfhjkeb/docker && docker compose up -d`
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

You are a senior full-stack engineer. Your task is to build a complete enterprise-grade e-commerce platform from scratch inside an already-running Docker environment.

### Environment

The Docker environment is already up and running — you do not need to pull images or start containers.

You work inside the container `ecommerce-app`, with `/app` as the working directory (currently empty). <!-- _SAASBENCH_AGENT_IN_CONTAINER -->
The bash tool you have access to executes every command **inside** that container automatically — you do **not** need to (and must not) wrap your commands with `docker exec ...` yourself. Just type plain shell commands as if you were ssh-ed into that box; the harness routes them.

```bash
# wrong: nested docker exec, will fail with quoting errors
docker exec ecommerce-app bash -c "ls -la"

# right: just run the command
ls -la
```

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

**Database (PostgreSQL 16, already running):**
- Host: `db`
- Port: `5432`
- Database: `app_db`
- Username: `app`
- Password: `app123`
- Extensions installed: uuid-ossp, pgcrypto

**Redis (already running):**
- Host: `redis`
- Port: `6379`

**The application MUST listen on port `8003`.**

### What you need to do

1. Create a complete TypeScript / Node.js project inside `/app` (modular architecture, a workflow / step-builder layer, an ORM of your choice, and an HTTP framework such as Express.js / Fastify / Koa)
2. Install your project's Node.js dependencies (`npm install` / `pnpm install` / `yarn install` as appropriate)
3. Run database migrations
4. Create the following evaluation users (via your application's CLI, an admin endpoint, or direct SQL INSERT):
   - Admin: email=`eval_admin@test.com`, password=`EvalAdmin123!`
   - Super Admin: email=`eval_superadmin@test.com`, password=`EvalSuperAdmin123!`
   - Limited Admin: email=`eval_limited@test.com`, password=`EvalLimited123!`
   - No Role User: email=`eval_norole@test.com`, password=`EvalNoRole123!`
   - Product Reader: email=`eval_prodreader@test.com`, password=`EvalProdReader123!`
   - Product Full Reader: email=`eval_prodfull@test.com`, password=`EvalProdFull123!`
   - Customer (storefront side): email=`eval_customer@test.com`, password=`EvalCustomer123!`
5. Start the application server, listening on `0.0.0.0:8003`

### Key technical requirements

- **Framework**: Modular framework on top of an HTTP framework of your choice (e.g., Express.js, Fastify, Koa), with approximately 30+ independent domain modules and a dependency-injection container of your choice (e.g., Awilix, InversifyJS, TypeDI, or any IoC library)
- **API routes**: REST + JSON, organized into back-office (`/admin/*` or similar) and storefront (`/store/*` or similar) families. The implementation should expose approximately 400+ endpoints across both families.
- **Authentication**: multi-provider architecture, supporting Email/Password, JWT Bearer Token, Session Cookie, and API Key authentication (with two key types: a public-side key for storefront use and a server-side key for admin use; common naming conventions include publishable/secret, public/private, or client/server)
- **ORM**: any TypeScript ORM that supports declarative entity definitions (e.g., MikroORM 6.x, Prisma, TypeORM). IDs should follow a consistent prefixed format (e.g., ULID-based `prod_xxx`, `cart_xxx`, `order_xxx`, or UUID-based equivalent)
- **TypeScript config**: use a `moduleResolution` setting that supports package sub-path exports (e.g., `"Node16"`, `"NodeNext"`, or `"bundler"` in `tsconfig.json`)
- **Database**: PostgreSQL 16, approximately 100+ data entities, soft-delete using a `deleted_at` timestamp column
- **Workflow engine**: declarative workflow definition API (e.g., `createWorkflow` / `createStep` builders, or any equivalent step-builder pattern), supporting compensating rollback (saga pattern), idempotent execution, and event emission
- **Frontend**: any modern SPA framework (React 18 + Vite recommended) with a UI component library (e.g., Radix UI + Tailwind CSS, Material UI, Ant Design), data fetching library (e.g., TanStack Query, SWR, RTK Query), and internationalization library (e.g., i18next, react-intl)
- **Money calculation**: use exact-decimal arithmetic (e.g., a `BigNumber`-style type, `Decimal.js`, or integer-cents). Persist amounts in `numeric` (or equivalent decimal) DB columns. The implementation may also store raw amounts in JSON columns for currency-conversion preservation.
- **Error format**: `{"type": "<error_type>", "message": "..."}`; type mapping is documented in §2 of the requirements doc
- **Pagination**: every list endpoint accepts `limit`, `offset`, `order`, `fields` query parameters
- **Field selection (REQUIRED syntax)**: the `fields` query parameter supports field-level filtering and relation expansion using the `+field` / `*relation` prefix syntax (e.g. `?fields=+claims,*items,*fulfillments`). The evaluation harness issues requests with this exact `+`/`*` syntax, so you **MUST** implement it — JSON:API `include=` or GraphQL-style selection will not satisfy the checks.

### Environment variables

The following environment variables are already set in the container (no manual configuration required):

| Variable | Value |
|------|-----|
| `DATABASE_URL` | `postgres://app:app123@db:5432/app_db?sslmode=disable` |
| `REDIS_URL` | `redis://redis:6379` |
| `JWT_SECRET` | `supersecret_jwt_key_for_dev` |
| `COOKIE_SECRET` | `supersecret_cookie_key_for_dev` |
| `NODE_ENV` | `development` |
| `PORT` | `8003` |
| `WORKER_MODE` | `shared` |

---

## Tester Workflow

### Before testing: start the environment

```bash
cd <repo_root>/tasks/task_dfhjkeb/docker
docker compose up -d
docker compose ps   # verify all 3 containers are running (ecommerce-app, ecommerce-db, ecommerce-redis)
```

### During testing: send the prompt above + the contents of task.md to the model

The model will write code, install dependencies, and start the server inside the container.

### After testing: run the evaluation

```bash
cd <repo_root>/check/task_dfhjkeb
./test_model_output.sh
```
