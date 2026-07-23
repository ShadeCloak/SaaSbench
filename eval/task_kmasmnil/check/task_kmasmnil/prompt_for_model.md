# SaaSBench Test Prompt — task_kmasmnil (Experience Management Platform)

> **How to use:**
> 1. Start the Docker environment first: `cd /Users/bytedance/Downloads/qingnan/SaaSBench_tasks/tasks/task_kmasmnil/docker && docker compose up -d`
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

You are a senior full-stack engineer. Your task is to build a complete Experience Management (XM) platform from scratch inside an already-running Docker environment — a full-stack web application that supports survey creation, distribution, and analysis.

### Environment

The Docker environment is already up and running — you do not need to pull images or start containers.

You work inside the container `xm_app`, with `/app` as the working directory (it is empty — you'll write all source code and run `pnpm install` from scratch; expect the install to take a few minutes since there is no pre-warmed cache). The bash tool you have access to executes every command **inside** that container automatically — you do **not** need to (and must not) wrap your commands with `docker exec ...` yourself. Just type plain shell commands as if you were ssh-ed into that box; the harness routes them. <!-- _SAASBENCH_AGENT_IN_CONTAINER -->

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

**Database (PostgreSQL 16 + pgvector, already running):**
- Host: `db`
- Port: `5432`
- Database: `app_kmasmnil`
- Username: `appkmasmnil`
- Password: `app123kmasmnil`
- DATABASE_URL: `postgresql://appkmasmnil:app123kmasmnil@db:5432/app_kmasmnil`

**Redis (already running):**
- Host: `redis`
- Port: `6379`
- REDIS_URL: `redis://redis:6379`

**The application MUST listen on port `8024`.**

**Environment variables already set in the container (from `.env`):**
- `DATABASE_URL`, `REDIS_URL` — already configured correctly
- `NEXTAUTH_URL=http://localhost:8024`
- `NEXTAUTH_SECRET=a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2`
- `ENCRYPTION_KEY=c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5b6c7d8e9f0a1b2c3d4e5f6a7b8c9d0`
- `CRON_SECRET=xm_cron_secret_k8m7n6p5q4r3s2t1`
- `EMAIL_VERIFICATION_DISABLED=1`
- `RATE_LIMITING_DISABLED=1`
- `PORT=8024`
- `NODE_ENV=production`

### What you need to do

1. Create a complete full-stack project inside `/app`. A monorepo layout is recommended (e.g., pnpm workspaces + Turborepo when targeting a Next.js stack; equivalent setups exist for other ecosystems). The implementation may use any modern full-stack framework — Next.js App Router is recommended for full feature parity; alternatives include Remix, SvelteKit, Nuxt, or a separated frontend + backend (e.g., React/Vue SPA + Node/Python API).
2. Define a database schema covering all data models. Prisma is recommended (the recommended schema location is `packages/database/schema.prisma`), but any TypeScript/JavaScript ORM is acceptable: Drizzle, Kysely, TypeORM, MikroORM, etc. The schema file location may differ for non-Prisma ORMs.
3. Run `pnpm install` (or `npm install` / `yarn install`) to install dependencies
4. Apply the schema to the database (`npx prisma generate` + `npx prisma db push`, or your ORM's equivalent migration command)
5. Create the following evaluation fixtures (the ID values listed are evaluation fixtures the evaluator will query — preserve them exactly; the ID format itself is implementation-specific):
   - **Organization**: id=`c19d51cebo3od2b1d7homp9wl`, name=`Eval Organization`. Also create a billing/quota record for the organization with unlimited monthly response and MIU quotas. The recommended pattern is an `OrganizationBilling` record with `limits: {monthly: {responses: null, miu: null}}` and `usageCycleAnchor: new Date()`, but the implementation may use different field names — the evaluator looks for fields named like `limits`, `monthly_quota`, `usage_cycle_anchor`, or equivalent.
   - **Project**: id=`c19d51ceb0zesjg8y6fiy8gly`, name=`Eval Project`, belonging to the above organization
   - **Production environment**: id=`c19d51ceb5j2rsrlpzc2svv9a`, type=`production`, belonging to the above project
   - **Development environment**: id=`c19d51ceb0hl9iiqoe3nvn3ig`, type=`development`, belonging to the above project
   - **Admin user**: name=`Eval Admin`, email=`eval_admin@test.com`, password=`EvalAdmin123!@#` (role=`owner` within the organization; equivalent role names such as `admin`/`administrator` are acceptable)
   - **Member user**: name=`Eval Member`, email=`eval_member@test.com`, password=`EvalMember123!@#` (role=`member` within the organization; equivalent role names such as `user`/`developer` are acceptable)
   - **API Key**: raw value=`xmk_evalTestSecretForSmoke2026`, stored in a hashed lookup field. The recommended scheme is a SHA-256 hex digest stored in a field named `hashedKey`, but the hash algorithm (SHA-256 / Argon2 / bcrypt) and the field name are at the implementation's discretion as long as the lookup is deterministic and verifiable. The key grants `manage` permission for both environments associated with the above organization.
6. Build the application (`pnpm build` or your build tool's equivalent)
7. Start the application server, listening on `0.0.0.0:8024`

### Key technical requirements

- **Framework**: any modern full-stack web framework with server-side rendering or SSR-capable routing. Next.js (App Router) + TypeScript is the recommended stack for full feature parity; alternatives such as Remix, SvelteKit, Nuxt, or a separated frontend + backend (e.g., Express/Fastify/NestJS/Hono backend + React/Vue/Svelte frontend) are all acceptable.
- **ORM**: any TypeScript/JavaScript ORM able to express the data model below (Prisma recommended, with the `pgvector` PostgreSQL extension enabled; alternatives: Drizzle, Kysely, TypeORM, MikroORM).
- **Authentication**: any auth library or implementation supporting email/password login (Auth.js / NextAuth v4 recommended for Next.js; alternatives: Lucia, Passport.js, custom JWT-based auth, framework-native session middleware).
- **API design**: REST API with versioned endpoints `/api/v1/`, `/api/v2/`, `/api/v3/`
- **API authentication**: supports the `x-api-key` request header (API Key lookup uses a deterministic hash — SHA-256 hex digest recommended) and session cookies or session tokens.
- **API Key format**: the raw key is hashed (e.g., SHA-256 hex digest, Argon2, or bcrypt) and stored in a lookup field. The hash algorithm and field name are at the implementation's discretion as long as the lookup is deterministic and verifiable (the evaluator looks for fields named like `hashedKey`, `hashed_key`, `key_hash`, or similar).
- **API response format**: success `{ "data": <payload> }`, error `{ "error": { "code": "string", "message": "string" } }`
- **Health-check endpoint**: `GET /api/v2/health`
- **Package manager**: any modern Node package manager is acceptable (pnpm + Turborepo recommended for monorepo workflows; alternatives: pnpm without Turbo, yarn workspaces, npm workspaces, or a single-project setup without workspaces).
- **Cache**: Redis
- **Project structure**: a monorepo layout is recommended (e.g., `apps/web/` for the main application + `packages/database/` for ORM schema + other shared packages), but a single-package layout or a different folder structure is acceptable as long as the data model and API surface match this spec.
- **Tenant hierarchy**: top-level organization, mid-level project, bottom-level environment (with at least two environment types: production and development/staging). The exact entity names are at the implementation's discretion as long as the hierarchical structure is preserved.
- **Password hashing**: a strong, salted password hashing algorithm (bcrypt with cost factor ≥ 10 recommended; Argon2id or scrypt also acceptable).
- **Validation**: any schema validation library (Zod recommended; alternatives: yup, joi, valibot, or framework-native validators).

---

## Tester Workflow

### Before testing: prepare the environment

```bash
cd /Users/bytedance/Downloads/qingnan/SaaSBench_tasks/check/task_kmasmnil
./prepare_workspace.sh
```

This will: pull the `:model` image → start the container → leave `/app` empty and idle (`PID 1 = sleep infinity`) so the model writes everything from scratch.

### During testing: send the prompt above + the contents of task.md to the model

The model will write code, install dependencies, and start the server inside the container via `docker exec`.

### After testing: run the evaluation

```bash
cd /Users/bytedance/Downloads/qingnan/SaaSBench_tasks/check/task_kmasmnil
./test_model_output.sh
```
