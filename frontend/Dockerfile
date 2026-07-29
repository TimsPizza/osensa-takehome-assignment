FROM node:22.23.1-alpine3.24 AS build

WORKDIR /app

RUN corepack enable \
    && corepack prepare pnpm@10.7.1 --activate

COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc ./
RUN pnpm install --frozen-lockfile

COPY . .
RUN pnpm build

FROM caddy:2.11.3-alpine

COPY Caddyfile /etc/caddy/Caddyfile
COPY --from=build /app/build /srv

USER 10001:10001
