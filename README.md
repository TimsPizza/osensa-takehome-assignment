# OSENSA Take-home Assignment

Restaurant orders travel through MQTT over WebSockets:

```text
Svelte client ── ORDER ──> Mosquitto ──> Python service
Svelte client <── STATUS ─ Mosquitto <── Python service
```

Pydantic models own the public wire contract, and the frontend receives generated
Zod schemas and TypeScript types. The Svelte UI supports four tables, concurrent
orders, live lifecycle updates, reconnect feedback, and retryable failures. The
backend processes up to eight orders concurrently with a random one-to-five-second
delay.

## Prerequisites

- Docker with Compose
- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Node.js with Corepack

## Run the app

```sh
docker compose up --build --wait
```

Mosquitto exposes its development WebSocket listener at
`ws://127.0.0.1:9001/mqtt`. It is bound to localhost and intentionally allows
anonymous access. Do not expose this validation configuration to the internet.

In another terminal:

```sh
cd frontend
corepack pnpm install
corepack pnpm dev
```

Open `http://localhost:5173`. Local development automatically connects to
`ws://localhost:9001/mqtt`. Set `VITE_MQTT_URL` to override the broker URL; an
HTTPS deployment defaults to same-origin `wss://<host>/mqtt`.

Run the backend MQTT round-trip tests while the stack is running:

```sh
cd backend
RUN_MQTT_INTEGRATION=1 uv run pytest tests/integration/test_mqtt_flow.py
```

The normal integration suite includes malformed payload, idempotency, conflict,
and lifecycle checks. Burst and saturation tests are opt-in because they take
longer and intentionally fill the processing queue:

```sh
RUN_MQTT_INTEGRATION=1 RUN_MQTT_LOAD=1 \
  uv run pytest tests/integration/test_mqtt_flow.py -m load
```

Run the real browser MQTT client test:

```sh
cd frontend
corepack pnpm exec playwright install chromium
VITE_RUN_MQTT_INTEGRATION=1 corepack pnpm test:mqtt
```

Stop the stack:

```sh
docker compose down
```

## Generate frontend contracts

Install frontend dependencies once, then generate or verify the committed output:

```sh
cd frontend
corepack pnpm install
corepack pnpm contract:gen
corepack pnpm contract:check
```

Only models listed in `backend/app/models.py` under `CODEGEN_TARGETS` are exported.
Generated files must not be edited by hand.

## Local checks

```sh
cd backend
uv run pytest
uv run ruff check .
uv run ruff format --check .

cd ../frontend
corepack pnpm check
corepack pnpm lint
corepack pnpm test
corepack pnpm build
```
