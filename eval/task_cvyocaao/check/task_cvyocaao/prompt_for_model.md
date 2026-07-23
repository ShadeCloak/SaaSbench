# SaaSBench Test Prompt — task_cvyocaao (Identity and Access Management Platform)

> **How to use:**
> 1. Start the Docker environment first: `cd "$REPO_ROOT/tasks/task_cvyocaao/docker" && docker compose up -d` (where `$REPO_ROOT` is the SaaSBench repository root on your machine)
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
> Additionally, you MUST NOT install or use any pre-existing IAM-specific
> library or framework that provides ready-made identity, OIDC, OAuth, SAML
> or realm management abstractions (such as `python-keycloak`, `authlib`,
> `casdoor`, `python3-saml`, `keycloak-admin`, `oauth2-proxy`, `keycloak-js`,
> `mod_auth_openidc`, etc.). General-purpose primitives are allowed — for
> example: `cryptography`, `bcrypt`, `argon2-cffi`, `pyjwt` / JWT signing
> libraries (when used as low-level token primitives, not as IAM platforms),
> `psycopg2` / DB drivers, web frameworks (`fastapi`, `flask`, `quarkus`,
> `spring-boot`), and template engines. The boundary is: you must implement
> the IAM concepts (realms, clients, flows, tokens) yourself.

You are a senior full-stack engineer. Your task is to build a complete Identity and Access Management (IAM) platform from scratch inside an already-running Docker environment.

### Environment

The Docker environment is already up and running — you do not need to pull images or start containers.

You work inside the container `app_cvyocaao`, with `/app` as the working directory (currently empty). The bash tool you have access to executes every command **inside** that container automatically — you do **not** need to (and must not) wrap your commands with `docker exec ...` yourself. Just type plain shell commands as if you were ssh-ed into that box; the harness routes them. <!-- _SAASBENCH_AGENT_IN_CONTAINER -->

**Tools pre-installed in the container** (Ubuntu 22.04):
- OpenJDK 17 (`JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64`) + Maven + Gradle (Maven Aliyun mirror configured)
- Node.js 20 + npm + pnpm + yarn + npx
- Python 3.10 + pip, Go
- PostgreSQL client 14 (psql, pg_isready); MariaDB / MySQL client; redis-cli; sqlite3
- Build essentials: gcc 11, g++, make, cmake, pkg-config
- Dev libraries: libssl-dev, libpq-dev, libsqlite3-dev, libxml2-dev, libffi-dev
- git, curl, wget, jq, openssl, unzip, ca-certificates
- `apt` is available for installing any additional packages or language toolchains you need

**Database (PostgreSQL 16, already running):**
- Host: `db`
- Port: `5432`
- Database: `app_cvyocaao`
- Username: `appcvyocaao`
- Password: `app123cvyocaao`
- JDBC URL: `jdbc:postgresql://db:5432/app_cvyocaao`

**The application MUST listen on port `8027`.**

### What you need to do

1. Create a complete JVM-based project inside `/app` (build manifest, configuration, entities, REST resources, database migrations, etc.)
2. Build the project with a standard JVM build tool (Maven or Gradle)
3. Manage database schema with a declarative migration tool
4. Create the bootstrap admin user:
   - Realm: `master`
   - Username: `admin`
   - Password: `admin`
   - Client ID: `admin-cli` (public client, used to obtain the Admin token)
5. Start the application server, listening on `0.0.0.0:8027`
6. The health-check endpoint `/health/ready` MUST return `{"status": "UP"}`

### Key technical requirements

- **Multi-tenant Realm isolation**: each Realm is an independent identity namespace with its own users, clients, roles, and authentication flows
- **Admin REST API**: path `/admin/realms/{realm}/`, authenticated via Bearer token (obtained through the master realm's password grant)
- **OIDC endpoints**: path `/realms/{realm}/protocol/openid-connect/` (token, authorize, userinfo, introspection, revocation, JWKS)
- **Well-Known**: `/realms/{realm}/.well-known/openid-configuration` returns the OIDC Discovery document
- **API response conventions**:
  - Create: HTTP 201 + empty body + `Location` header
  - Update: HTTP 204 + empty body
  - Delete: HTTP 204 + empty body
  - List: JSON array, paginated with `first`/`max`
  - Errors (Admin): `{"errorMessage": "..."}`
  - Errors (OAuth): `{"error": "...", "error_description": "..."}` (RFC 6749)
- **Framework**: a JVM-based web framework (e.g., Quarkus, Spring Boot, Micronaut)
- **ORM**: a JPA-compliant ORM connected to PostgreSQL (e.g., Hibernate ORM, EclipseLink)
- **Database migrations**: a declarative migration tool (e.g., Liquibase, Flyway)
- **Cache**: embedded distributed cache, local mode (e.g., Infinispan or any equivalent JVM-embedded distributed cache library)
- **Frontend**: a modern SPA framework with a JS build tool, for both Admin Console and Account Console (e.g., React + Vite, Vue + Vite, Angular + CLI)
- **Templates**: a JVM template engine for login / registration pages (e.g., FreeMarker, Thymeleaf)
- **Build tools**: a JVM build tool for the backend (Maven or Gradle); a JS build tool with a package manager for the frontend (e.g., Vite + pnpm/npm/yarn)
- **Crypto**: a JCA-compatible cryptography provider supporting RSA, EC, EdDSA, AES, HMAC (e.g., Bouncy Castle, default JDK providers)

### Evaluation user information

Evaluation uses the master realm's bootstrap admin:
- Username: `admin`
- Password: `admin`
- Client ID: `admin-cli`

The evaluation creates a test realm `eval-test-realm` and a test client `eval-test-client` (secret: `eval-secret`), and operates through the Admin REST API.

---

## Tester Workflow

### Before testing: start the environment

```bash
# $REPO_ROOT = the SaaSBench repository root on your machine
cd "$REPO_ROOT/check/task_cvyocaao"
./prepare_workspace.sh        # starts the model-mode container with an empty /app
```

### During testing: send the prompt above + the contents of task.md to the model

The model will write code, build the project, and start the server inside the container via `docker exec`.

### After testing: run the evaluation

```bash
cd "$REPO_ROOT/check/task_cvyocaao"
./test_model_output.sh
```
