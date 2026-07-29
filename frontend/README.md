# OSENSA Restaurant Frontend

Svelte 5 client for the restaurant ordering flow. It communicates directly with
Mosquitto over WebSockets; there is no REST API.

Run the broker and backend from the repository root, then start the UI:

```sh
corepack pnpm install
corepack pnpm dev
```

The default local broker URL is `ws://localhost:9001/mqtt`. Set
`VITE_MQTT_URL` when the broker is hosted elsewhere.

See the repository root README for validation and contract-generation commands.
