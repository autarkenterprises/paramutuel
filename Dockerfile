FROM python:3.12-slim

WORKDIR /app

# The indexer service currently uses Python stdlib only.
COPY service /app/service
COPY config /app/config

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app
ENV INDEXER_NETWORK=base-sepolia
ENV DEPLOYMENTS_CONFIG_PATH=config/deployments.json
ENV INDEXER_DB_PATH=/tmp/indexer.db
ENV INDEXER_POLL_INTERVAL_SECONDS=15
# Zero-UI Cloud Run: public Base Sepolia RPC + factory deploy block (override in console if needed).
ENV RPC_URL_BASE_SEPOLIA=https://sepolia.base.org
ENV INDEXER_FROM_BLOCK=39608044
ENV PORT=8080

EXPOSE 8080

# Omit --port so Cloud Run's PORT is used; local default is 8080 via ENV above.
CMD ["python3", "-m", "service.indexer.live_api", "--host", "0.0.0.0", "--network", "base-sepolia", "--deployments-config-path", "config/deployments.json"]
