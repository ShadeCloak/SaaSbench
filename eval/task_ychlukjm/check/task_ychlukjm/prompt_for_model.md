# SaaSBench Test Prompt — task_ychlukjm (Enterprise Metadata Management Platform)

> **How to use:**
> 1. Start the Docker environment first: `cd <SAASBENCH_REPO_ROOT>/tasks/task_ychlukjm/docker && docker compose up -d`
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

You are a senior full-stack engineer. Your task is to build a complete enterprise-grade metadata management platform from scratch inside an already-running Docker environment.

### Environment

The Docker environment is already up and running — you do not need to pull images or start containers.

You work inside the container `metadata-platform-app`, with `/app` as the working directory (currently empty). The bash tool you have access to executes every command **inside** that container automatically — you do **not** need to (and must not) wrap your commands with `docker exec ...` yourself. Just type plain shell commands as if you were ssh-ed into that box; the harness routes them. <!-- _SAASBENCH_AGENT_IN_CONTAINER -->

**Tools pre-installed in the container** (Ubuntu 22.04):
- OpenJDK 17 (`JAVA_HOME=/usr/lib/jvm/java-17-openjdk-amd64`) + Maven + Gradle (Maven Aliyun mirror configured)
- Node.js 20 + npm + pnpm + yarn + npx
- Python 3.10 + pip, Go
- PostgreSQL client 14 (psql, pg_isready); MariaDB / MySQL client; redis-cli; sqlite3
- Build essentials: gcc 11, g++, make, cmake, pkg-config
- Dev libraries: libssl-dev, libpq-dev, libsqlite3-dev, libxml2-dev, libffi-dev
- git, curl, wget, jq, openssl, unzip, ca-certificates
- `apt` is available for installing any additional packages or language toolchains you need

**Database (MySQL 8.0, already running):**
- Host: `mysql`
- Port: `3306`
- Database: `app_ychlukjm`
- Username: `appychlukjm`
- Password: `app123ychlukjm`
- Root password: `root123`

**Elasticsearch 7.17 (already running):**
- Host: `elasticsearch`
- Port: `9200`

**Kafka (already running):**
- Bootstrap servers: `kafka:29092`
- Schema Registry: `http://schema-registry:8081`

**Zookeeper (already running):**
- Host: `zookeeper`
- Port: `2181`

**Neo4j 4.4 (already running):**
- URI: `bolt://neo4j:7687`
- Username: `neo4j`
- Password: `neo4j_pass_ychlukjm`

**The application MUST listen on port `8019`.**

### What you need to do

1. Create a complete Java (Spring Boot) + React project inside `/app`
2. Build the backend with Gradle and install frontend dependencies
3. Run database migrations (create the MySQL table structure)
4. Configure authentication so that the following user can log in via the `/logIn` endpoint:
   - Admin: username=`admin`, password=`admin` (system administrator with all permissions)
5. Configure the system service account:
   - Client ID: `__system_service`
   - Client Secret: `SystemServiceSecret2026`
6. Start the application server, listening on `0.0.0.0:8019`
7. Make sure the `/health` endpoint returns a healthy status

### Key technical requirements

- **Primary API layer — GraphQL**: `POST /api/graphql` (also exposed at `/api/v2/graphql`)
- **REST API v3**: OpenAPI 3.0 spec, paths `/openapi/v3/entity/{entityType}/*`
- **REST API v2**: backward-compatible, paths `/openapi/v2/entity/{entityType}/*`
- **Legacy API**: `/entities/*`, `/aspects/*`
- **Authentication**: every API request must carry an `Authorization: Bearer {token}` header
- **Login endpoint**: `POST /logIn`, username/password authentication returning a Token
- **Backend framework (REQUIRED)**: Spring Boot 3.x + Java 17. This is mandatory — the harness's deployment prereqs check for a Spring Boot service module (a `metadata-service` directory) and gate ~130+ downstream checks on it, so Quarkus / Micronaut will fail the deployment gate and cascade-fail nearly everything.
- **Build tool (REQUIRED)**: Gradle 8.x. The harness hard-checks for a `build.gradle` file as a prereq of ~145 downstream nodes; a Maven (`pom.xml`-only) build will fail that gate and cascade-fail the run.
- **Database**: MySQL 8.0 (JDBC URL `jdbc:mysql://mysql:3306/app_ychlukjm?useSSL=false&allowPublicKeyRetrieval=true&characterEncoding=UTF-8`; any equivalent RDBMS — PostgreSQL, MariaDB — is acceptable)
- **Search engine**: any full-text search engine (Elasticsearch 7.17 recommended; alternatives: OpenSearch, Solr), used for entity search and discovery
- **Message queue**: any event-streaming platform (Kafka recommended; alternatives: Pulsar, NATS, Redis Streams), used for publishing/subscribing to metadata-change events
- **Graph database**: optional graph storage for lineage (Neo4j 4.4 recommended; alternatives: JanusGraph, ArangoDB)
- **Event-driven**: a two-stage metadata-change event pipeline — proposal events → committed/log events (recommended naming: MetadataChangeProposal (MCP) → MetadataChangeLog (MCL); equivalent naming is acceptable)
- **Frontend**: any React-based SPA (React 18 + TypeScript recommended) with a GraphQL client (Apollo Client recommended) and any UI library (Ant Design, MUI, Chakra UI)
- **Metadata ingestion CLI**: a Python CLI tool (any Python CLI framework: Click recommended; alternatives: Typer, argparse)
- **Authentication switch**: a boolean env var to toggle auth (e.g., `METADATA_SERVICE_AUTH_ENABLED=true`; the env var name is at the implementation's discretion)
- **GraphiQL debug UI**: `/api/graphiql`
- **Swagger UI**: `/openapi/swagger-ui/index.html`

---

## Tester Workflow

### Before testing: start the environment

```bash
cd <SAASBENCH_REPO_ROOT>/tasks/task_ychlukjm/docker
docker compose up -d
docker compose ps   # verify all containers are running (app + mysql + elasticsearch + kafka + zookeeper + schema-registry + neo4j)
```

### During testing: send the prompt above + the contents of task.md to the model

The model will write code, install dependencies, build the project and start the server inside the container via `docker exec metadata-platform-app`.

### After testing: run the evaluation

```bash
cd <SAASBENCH_REPO_ROOT>/check/task_ychlukjm
./test_model_output.sh
```
