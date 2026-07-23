# SaaSBench Test Prompt — task_mjobbzsi (Real-Time Video Conferencing Platform)

> **How to use:**
> 1. Start the Docker environment first: `cd <repo_root>/tasks/task_mjobbzsi/docker && docker compose up -d`
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

You are a senior full-stack engineer. Your task is to build a complete real-time video conferencing platform from scratch inside an already-running Docker environment.

### Environment

The Docker environment is already up and running — you do not need to pull images or start containers.

You work inside the container `mjobbzsi-app-1`, with `/app` as the working directory (currently empty). The bash tool you have access to executes every command **inside** that container automatically — you do **not** need to (and must not) wrap your commands with `docker exec ...` yourself. Just type plain shell commands as if you were ssh-ed into that box; the harness routes them. <!-- _SAASBENCH_AGENT_IN_CONTAINER -->

**Tools pre-installed in the container** (Debian 12 / `node:20-bookworm` based):
- Node.js 20 + npm + pnpm + yarn + npx
- Python 3 + pip
- Globally installed npm: TypeScript 5, ts-node, vite, sass, webpack 5, nx, jest, prettier, eslint, nodemon, pm2
- Build essentials: gcc, g++, make, cmake, pkg-config
- git, curl, wget, jq, openssl, unzip, ca-certificates
- `apt` is available for installing any additional packages or language toolchains you need

**Required nginx routing (you must install and configure nginx yourself — `apt install -y nginx`):**
- Listen on container port `80` (mapped to host `8026`)
- Document root: `/app/build`
- SSI enabled (used for server-side includes in `config.js` — set `ssi on;` in the `server` block)
- `/http-bind` → proxied to the XMPP container's BOSH endpoint (`http://xmpp.conference.local:5280/http-bind`)
- `/xmpp-websocket` → proxied to the XMPP container's WebSocket endpoint (`http://xmpp.conference.local:5280/xmpp-websocket`, with `Upgrade`/`Connection` headers)
- `/colibri-ws/` → proxied to the video-bridge service's signalling WebSocket (`http://mjobbzsi-jvb-1:9090/colibri-ws/`, with `Upgrade`/`Connection` headers)
- `/external_api.js` → alias to `/app/build/libs/external_api.min.js`
- `/{room}` → SPA route falling back to `/index.html` (use `try_files $uri /index.html;`)

**XMPP server (already running, container `mjobbzsi-xmpp-1`):**
- Container: `mjobbzsi-xmpp-1`
- XMPP domain: `conference.local`
- Guest domain: `guest.conference.local`
- MUC domain: `muc.conference.local`
- Auth domain: `auth.conference.local`
- In-container ports: 5222 (XMPP), 5280 (HTTP/BOSH/WebSocket)
- Authentication mode: anonymous (ENABLE_AUTH=0)

**Conference Focus service (already running, container `mjobbzsi-focus-1`):**
- Container: `mjobbzsi-focus-1`
- XMPP server connection: `xmpp.conference.local:5222`
- Focus JID: `focus@auth.conference.local`

**Video Bridge (already running, container `mjobbzsi-jvb-1`):**
- Container: `mjobbzsi-jvb-1`
- UDP media port: 10000
- Signaling WebSocket port: 9090 (in-container)
- XMPP server connection: `xmpp.conference.local:5222`

**No traditional database.** All signalling and state are managed via the XMPP protocol.

**The application MUST be reachable on host port `8026`** (the app container's port `80` is mapped to host `8026`; nginx — which you install yourself — should listen on container port `80`).

### What you need to do

1. Create a complete React + Redux video-conferencing frontend project inside `/app` (package.json, webpack config, React components, Redux store, etc.)
2. Run `npm install` to install dependencies
3. Build the frontend with Webpack and output to the `/app/build` directory
4. Make sure the `/app/build` directory contains the following structure:
   - `index.html` — main page (must load config.js, interface_config.js, the meeting library bundle, and app.bundle)
   - `config.js` — conference configuration (XMPP domain set to `conference.local`, BOSH path `/http-bind`)
   - `interface_config.js` — UI configuration
   - `libs/` — JS bundles (app.bundle.min.js, external_api.min.js, meeting library bundle, etc.)
   - `css/` — stylesheets
   - `images/`, `sounds/`, `fonts/`, `lang/` — static assets
5. Install and start nginx (`apt install -y nginx`), drop the conf file above into `/etc/nginx/sites-enabled/default`, and start the daemon (`nginx` or `service nginx start`). After any later change to `/app/build`, just `nginx -s reload`.

### Key technical requirements

- **Frontend framework**: React 18 + Redux 4 + redux-thunk (recommended; equivalent stacks accepted)
- **UI library**: any modern React-compatible UI toolkit (e.g. Material UI, Chakra, Ant Design, Tailwind + headless components — pick what you are most productive with)
- **Build tool**: Webpack 5 + Babel
- **State management**: Redux with a registry pattern (one place to register reducers / middleware / state listeners) — concrete naming is up to you
- **Real-time communication**: WebRTC + XMPP WebSocket/BOSH (via a JavaScript meeting client library)
- **Internationalisation**: i18next
- **IFrame External API**: provides a `postMessage` interface that lets third parties embed and control conferences
- **HTTP endpoints**:
  - `GET /` — returns the HTML home page
  - `GET /config.js` — conference configuration
  - `GET /external_api.js` — IFrame API script
  - `GET /{room}` — conference-room page (SPA route)
- **Authentication mode**: anonymous by default (XMPP ANONYMOUS); also supports JWT, XMPP SASL, room passwords
- **Key configuration in `config.js`**:
  ```javascript
  var config = {
      hosts: {
          domain: "conference.local",
          anonymousdomain: "guest.conference.local",
          muc: "muc.conference.local"
      },
      bosh: "/http-bind",
      websocket: "ws://localhost:8026/xmpp-websocket",
      // ...
  };
  ```

---

## Tester Workflow

### Before testing: start the environment

```bash
cd <repo_root>/tasks/task_mjobbzsi/docker
docker compose up -d
docker compose ps   # verify all 4 containers are running (app, xmpp, focus, jvb)
```

### During testing: send the prompt above + the contents of task.md to the model

The model will write code, install dependencies, build the frontend and configure nginx inside the container via `docker exec`.

### After testing: run the evaluation

```bash
cd <repo_root>/check/task_mjobbzsi
./test_model_output.sh
```
