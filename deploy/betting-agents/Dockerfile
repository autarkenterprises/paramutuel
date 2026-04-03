# Scout loop image: installed `paramutuel-bettor` CLI + optional periodic recommend JSON to stdout.
FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml /app/pyproject.toml
COPY agents /app/agents

RUN pip install --no-cache-dir .

COPY deploy/betting-agents/entrypoint-scout-loop.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["/entrypoint.sh"]
