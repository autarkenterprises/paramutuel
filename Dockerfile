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

EXPOSE 8080

CMD ["python3", "-m", "service.indexer.live_api", "--host", "0.0.0.0", "--port", "8080", "--network", "base-sepolia", "--deployments-config-path", "config/deployments.json"]
