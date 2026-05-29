FROM oven/bun:1.3.3

WORKDIR /app

COPY package.json bun.lock ./
COPY packages/frontend/package.json ./packages/frontend/package.json

RUN bun install --frozen-lockfile

COPY packages/frontend ./packages/frontend

WORKDIR /app/packages/frontend

EXPOSE 5173

CMD ["bun", "run", "dev"]
