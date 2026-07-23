# SaaSBench Test Prompt — task_ubsmhopy (Password Manager Server)

> **How to use:**
> 1. Start the Docker environment first: `cd <SaaSBench_tasks_root>/tasks/task_ubsmhopy/docker && docker compose up -d`
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

You are a senior backend engineer. Your task is to build a password-manager server compatible with a standard password-manager client API protocol from scratch inside an already-running Docker environment.

### Environment

The Docker environment is already up and running — you do not need to pull images or start containers.

You work inside the container `app_ubsmhopy`, with `/app` as the working directory (currently empty). The bash tool you have access to executes every command **inside** that container automatically — you do **not** need to (and must not) wrap your commands with `docker exec ...` yourself. Just type plain shell commands as if you were ssh-ed into that box; the harness routes them. <!-- _SAASBENCH_AGENT_IN_CONTAINER -->

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
- Database: `app_ubsmhopy`
- Username: `appubsmhopy`
- Password: `app123ubsmhopy`
- DATABASE_URL: `postgresql://appubsmhopy:app123ubsmhopy@db:5432/app_ubsmhopy`

**The application MUST listen on port `8035`.**

The container has the following environment variables set:
- `ROCKET_ADDRESS=0.0.0.0`
- `ROCKET_PORT=8035`
- `DATABASE_URL=postgresql://appubsmhopy:app123ubsmhopy@db:5432/app_ubsmhopy`
- `ADMIN_TOKEN=admin_token_ubsmhopy`
- `DOMAIN=http://localhost:8035`

### What you need to do

1. Create a complete Rust project inside `/app` (Cargo.toml, src/, migrations/, etc.) implementing a password-manager server compatible with the prescribed password-manager client API protocol
2. Use Rocket 0.5 as the web framework and Diesel as the ORM
3. Build the project: `cargo build --features postgresql --release`
4. Run database migrations (Diesel migrations or embedded migrations)
5. Create the following 3 evaluation users (via API registration or by writing directly to the database):
   - Admin: email=`eval_admin@test.com`, name=`Eval Admin`, password=`EvalMasterPassword123!`
   - User: email=`eval_user@test.com`, name=`Eval User`, password=`EvalMasterPassword123!`
   - User B: email=`eval_user_b@test.com`, name=`Eval User B`, password=`EvalMasterPassword123!`
6. Start the application server, listening on `0.0.0.0:8035`

### User registration protocol

Registration follows the standard password-manager protocol:
- The client first derives the master password using a KDF (PBKDF2-SHA256): `derived = PBKDF2(password, email, 600000)`
- It then derives once more: `masterPasswordHash = base64(PBKDF2(derived, password, 1))`
- It sends `masterPasswordHash` to `POST /api/accounts/register`
- The server hashes it with Argon2 using its own salt before storing

### Key technical requirements

- **API prefixes**: most APIs live under `/api/`, identity APIs under `/identity/`, and the admin panel under `/admin/`
- **Authentication**: OAuth2 Bearer Token (JWT), obtained via `POST /identity/connect/token`
- **Framework (REQUIRED)**: Rust + Rocket 0.5 + Diesel. While the functional/API checks are contract-based, several non-trivial ArchitectureQuality checks are scored by an LLM judge against Rust-specific idioms — `ARCH_DIESEL` judges Diesel usage (`schema.rs`, `table!` macros, `#[derive(Queryable)]`, versioned `up.sql`/`down.sql` migrations) and `ARCH_GUARDS` judges Rocket Request Guards (`FromRequest` impls, typed `Outcome::Failure`). A non-Rust/Rocket/Diesel stack (Actix, Go + Gin, Node + Fastify) cannot satisfy these rubrics and will forfeit those points, so Rocket + Diesel are required for full scoring.
- **WebSocket**: must support real-time notification push
- **Admin panel**: authenticated via `ADMIN_TOKEN` (token POSTed to `/admin/`)
- **Send feature**: supports encrypted sharing (text and file types)
- **Organization features**: supports organisations, Collections, member management, role-based permissions
- **Emergency access**: supports Emergency Access (View and Takeover types)
- **Two-factor authentication**: TOTP Authenticator support
- **Cipher types**: Login(1), SecureNote(2), Card(3), Identity(4)
- **Response format**: lists are wrapped as `{data: [...], object: "list", continuationToken: null}`
- **Error format**: not unified — auth errors return HTML 401, API errors return plain text, validation errors return JSON

---

## Tester Workflow

### Before testing: prepare the environment

```bash
cd <SaaSBench_tasks_root>/check/task_ubsmhopy
./prepare_workspace.sh
```

This will automatically back up the previous workspace, start the Docker container, and wait for it to be ready.

### During testing: send the prompt above + the contents of task.md to the model

The model will write code, install dependencies, and start the server inside the container via `docker exec`.

### After testing: run the evaluation

```bash
cd <SaaSBench_tasks_root>/check/task_ubsmhopy
./test_model_output.sh
```
