# Migration runner image, deployed as a Cloud Run Job (not a Cloud Run
# service) -- invoked synchronously by cloudbuild/deploy.yaml via
# `gcloud run jobs execute --wait`. Runs with VPC access so it can reach
# the private-IP-only Cloud SQL instance, which Cloud Build's default
# worker pool cannot.
#
# Build context MUST be the repo root (needs agent/ as a sibling):
#   docker build -f db/migrations/Dockerfile -t <tag> .
FROM python:3.12-slim

WORKDIR /app

COPY agent/requirements.txt ./agent-requirements.txt
RUN pip install --no-cache-dir -r agent-requirements.txt

COPY agent/csr_agent/ ./agent/csr_agent/
COPY db/ ./db/

ENTRYPOINT ["python", "db/migrations/run_migrations.py"]
