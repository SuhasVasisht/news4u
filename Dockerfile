FROM node:22-bookworm-slim AS base
RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 python3-venv build-essential curl \
  && rm -rf /var/lib/apt/lists/*
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
RUN python3 -m venv "$VIRTUAL_ENV" \
  && pip install --upgrade pip setuptools wheel
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY scripts/news_collector/pyproject.toml scripts/news_collector/README.md ./scripts/news_collector/
COPY scripts/news_collector/news_collector ./scripts/news_collector/news_collector
RUN pip install ./scripts/news_collector

FROM base AS builder
COPY . .
RUN pip install --no-deps ./scripts/news_collector
RUN npm run build

FROM node:22-bookworm-slim AS web-runner
RUN apt-get update \
  && apt-get install -y --no-install-recommends curl tzdata \
  && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app /app
EXPOSE 3000
CMD ["npm", "run", "start"]

FROM node:22-bookworm-slim AS worker-runner
RUN npm install --global @openai/codex@0.153.4
RUN apt-get update \
  && apt-get install -y --no-install-recommends python3 curl tzdata cron \
  && rm -rf /var/lib/apt/lists/*
WORKDIR /app
ENV VIRTUAL_ENV=/opt/venv
ENV PATH="$VIRTUAL_ENV/bin:$PATH"
ENV NODE_ENV=production
COPY --from=base /opt/venv /opt/venv
COPY --from=builder /app /app
CMD ["sh", "/app/scripts/scheduler-entrypoint.sh"]
