FROM python:3.12.10-slim-bookworm@sha256:fd95fa221297a88e1cf49c55ec1828edd7c5a428187e67b5d1805692d11588db

ARG TRADER_GIT_SHA
RUN printf '%s\n' "$TRADER_GIT_SHA" | grep -Eq '^[0-9a-f]{40}$'

LABEL org.opencontainers.image.title="Nishiki Research Protocol v2 collector" \
      org.opencontainers.image.revision="$TRADER_GIT_SHA"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    TRADER_GIT_SHA="$TRADER_GIT_SHA"

WORKDIR /app
COPY apps/__init__.py /app/apps/__init__.py
COPY apps/ops/__init__.py /app/apps/ops/__init__.py
COPY apps/ops/research_v2_snapshot.py /app/apps/ops/research_v2_snapshot.py
COPY apps/ops/research_v2_snapshot_review.py /app/apps/ops/research_v2_snapshot_review.py
COPY apps/ops/research_v2_daily.py /app/apps/ops/research_v2_daily.py
COPY docs/progress/phase-2-research-v2-data-sources.json \
  /app/docs/progress/phase-2-research-v2-data-sources.json

USER 1002:1002

ENTRYPOINT ["python", "-m", "apps.ops.research_v2_daily"]
CMD ["--data-dir", "/data/research-v2"]
