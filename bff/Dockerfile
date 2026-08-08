# CSRSupport BFF -- Cloud Run service.
#
# Build context MUST be the repo root, not bff/ -- this Dockerfile reaches
# up to shared/, which lives at the repo root alongside bff/ and agent/ as
# a sibling, not inside either service's own directory:
#   docker build -f bff/Dockerfile -t <tag> .
# (see cloudbuild/deploy.yaml, which invokes it this way).
FROM python:3.12-slim AS base

WORKDIR /app

# shared/ is a genuine cross-service dependency (numeric_provenance.py,
# messages.py -- see shared/guardrails/numeric_provenance.py's docstring
# for why it isn't owned by either service's own package). Copied in
# alongside the BFF's own code; NOT the agent/ package, which the BFF must
# never depend on directly.
COPY bff/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ ./shared/
COPY bff/app/ ./app/

# Cloud Run injects $PORT; default matches infra/modules/cloud_run's
# container_port expectation for local `docker run`.
ENV PORT=8080
EXPOSE 8080

CMD exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
