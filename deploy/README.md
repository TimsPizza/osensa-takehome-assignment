# Production MQTT deployment

The production stack terminates public WSS traffic at Caddy and keeps the
Mosquitto listener private to the Compose network.

## Prerequisites

- Point `MQTT_DOMAIN` to the VPS public IP.
- Allow inbound TCP 80 and 443 in the OCI security list/NSG and host firewall.
- Allow inbound UDP 443 only if HTTP/3 is desired.
- Do not expose ports 1883 or 9001.

## Configure

Create the production environment file:

```sh
cp .env.production.example .env.production
```

Set:

- `MQTT_DOMAIN`: the Broker hostname, such as `mqtt.example.com`.
- `FRONTEND_ORIGIN`: the exact HTTPS origin allowed to open the WebSocket.
- `ACME_EMAIL`: the address used for certificate operations.

Generate unique credentials and the hashed Mosquitto password file:

```sh
./deploy/init-production-secrets.sh
```

The initializer refuses to overwrite existing credentials. Secret files stay
under `deploy/secrets/` and are excluded from Git.

## Deploy

```sh
docker compose \
  --env-file .env.production \
  -f compose.yaml \
  -f compose.production.yaml \
  up -d --build --wait
```

Caddy obtains and renews the public certificate. The browser endpoint is:

```text
wss://<MQTT_DOMAIN>/mqtt
```

Enter the `restaurant-console` username in the WebUI Broker settings. Read its
password on the VPS with:

```sh
sed -n '1p' deploy/secrets/mqtt-restaurant-console-password
```

The WebUI stores the endpoint in local storage and credentials in session
storage. Closing the browser tab clears the credential.

## Authorization model

- `table-1` through `table-4` can publish orders and read state only for their
  own table.
- `restaurant-console` is the privileged four-table demo/operator identity.
- `restaurant-backend` consumes all table requests and is the only identity
  allowed to publish status, retained table snapshots, and kitchen pressure.
- Anonymous clients are rejected.

The Boundary Lab intentionally generates abusive load and therefore belongs to
the privileged console role. A customer terminal deployment should not expose
that panel.

## Operations

Inspect service state and recent logs:

```sh
docker compose \
  --env-file .env.production \
  -f compose.yaml \
  -f compose.production.yaml \
  ps

docker compose \
  --env-file .env.production \
  -f compose.yaml \
  -f compose.production.yaml \
  logs --tail=100 broker backend caddy
```

Caddy certificate state lives in named volumes. Container logs rotate at three
10 MB files per service. Mosquitto and the backend also have explicit connection,
packet, queue, registry, memory, and process limits.
