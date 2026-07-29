# OSENSA Take-home Assignment

Restaurant orders travel through MQTT over WebSockets:

```text
test client ── ORDER ──> Mosquitto ──> Python service
test client <── FOOD ─── Mosquitto <── Python service
```

The current milestone is a deliberately small, executable vertical slice. Pydantic
models own the public wire contract, the frontend receives generated Zod schemas
and TypeScript types, and Docker Compose proves the broker-to-backend path. The
backend processes up to eight orders concurrently with a random one-to-five-second
delay. The UI is not implemented yet.

## Prerequisites

- Docker with Compose
- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Node.js with Corepack

## Start the validation stack

```sh
docker compose up --build --wait
```

Mosquitto exposes its development WebSocket listener at
`ws://127.0.0.1:9001/mqtt`. It is bound to localhost and intentionally allows
anonymous access. Do not expose this validation configuration to the internet.

Run the real MQTT round-trip test while the stack is running:

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
