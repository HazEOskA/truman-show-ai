#!/usr/bin/env bash
set -Eeuo pipefail

# One-command Cloud Shell deploy for Hydra. This is intentionally a thin wrapper
# around the repository's existing deploy path. Gemini uses Vertex AI with the
# Cloud Run worker service account: no API key is created, pasted or mounted.

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

REGION="${REGION:-europe-central2}"
VERTEX_LOCATION="${VERTEX_LOCATION:-global}"
REPO="${REPO:-hydra}"
TAG="${TAG:-latest}"
SQL_INSTANCE_NAME="${SQL_INSTANCE_NAME:-hydra-db}"
DSN_SECRET="${DSN_SECRET:-hydra-dsn}"

fail() {
  printf 'ERROR: %s\n' "$*" >&2
  exit 2
}

need() {
  command -v "$1" >/dev/null 2>&1 || fail "$1 not found"
}

need gcloud
need python3
need curl

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null || true)}"
[[ -n "$PROJECT_ID" && "$PROJECT_ID" != "(unset)" ]] || \
  fail 'No GCP project. Set PROJECT_ID or run: gcloud config set project YOUR_PROJECT_ID'

ACTIVE_ACCOUNT="$(gcloud auth list --filter=status:ACTIVE --format='value(account)' 2>/dev/null | head -n1)"
[[ -n "$ACTIVE_ACCOUNT" ]] || fail 'No active gcloud account. Run: gcloud auth login'

SQL_INSTANCE="${SQL_INSTANCE:-${PROJECT_ID}:${REGION}:${SQL_INSTANCE_NAME}}"

printf 'Project : %s\n' "$PROJECT_ID"
printf 'Account : %s\n' "$ACTIVE_ACCOUNT"
printf 'Region  : %s\n' "$REGION"
printf 'SQL     : %s\n' "$SQL_INSTANCE"
printf 'DSN sec : %s\n' "$DSN_SECRET"
printf 'Gemini  : Vertex AI via Cloud Run service account (%s)\n\n' "$VERTEX_LOCATION"

# Fail before spending Cloud Build time if required persistent resources are absent.
gcloud sql instances describe "$SQL_INSTANCE_NAME" \
  --project="$PROJECT_ID" >/dev/null 2>&1 || \
  fail "Cloud SQL instance '$SQL_INSTANCE_NAME' not found or inaccessible in project '$PROJECT_ID'. Create it per docs/DEPLOY.md first."

gcloud secrets describe "$DSN_SECRET" --project="$PROJECT_ID" >/dev/null 2>&1 || \
  fail "Secret '$DSN_SECRET' not found or inaccessible. Create the DSN secret per docs/DEPLOY.md first."

printf '\n=== VERTEX AI ===\n'
gcloud services enable aiplatform.googleapis.com \
  --project="$PROJECT_ID" --quiet >/dev/null
printf 'Vertex AI API     : enabled\n'

printf '\n=== BUILD + DEPLOY (existing repository path) ===\n'
python3 scripts/deploy_cloudrun.py \
  --project "$PROJECT_ID" \
  --region "$REGION" \
  --repo "$REPO" \
  --tag "$TAG" \
  --sql-instance "$SQL_INSTANCE" \
  --dsn-secret "$DSN_SECRET"

service_value() {
  local service="$1" field="$2"
  gcloud run services describe "$service" \
    --project="$PROJECT_ID" --region="$REGION" \
    --format="value(${field})"
}

# deploy_cloudrun.py does not replace the service account, so keep whatever the
# worker already uses. If Cloud Run reports no explicit SA, it uses the project's
# default Compute service account.
WORKER_SA="$(service_value hydra-worker 'spec.template.spec.serviceAccountName')"
if [[ -z "$WORKER_SA" ]]; then
  PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
  WORKER_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"
fi

printf '\n=== GEMINI AUTH: VERTEX / SERVICE ACCOUNT ===\n'
printf 'Worker service account: %s\n' "$WORKER_SA"

gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${WORKER_SA}" \
  --role="roles/aiplatform.user" \
  --condition=None \
  --quiet >/dev/null

gcloud run services update hydra-worker \
  --project="$PROJECT_ID" \
  --region="$REGION" \
  --update-env-vars="GOOGLE_GENAI_USE_VERTEXAI=true,GOOGLE_CLOUD_PROJECT=${PROJECT_ID},GOOGLE_CLOUD_LOCATION=${VERTEX_LOCATION}" \
  --quiet >/dev/null

printf 'Gemini credentials : ADC/service account (no API key)\n'

ready_or_fail() {
  local service="$1"
  local ready
  ready="$(
    gcloud run services describe "$service" \
      --project="$PROJECT_ID" --region="$REGION" --format=json \
      | python3 -c 'import json,sys; d=json.load(sys.stdin); print(next((c.get("status", "") for c in d.get("status", {}).get("conditions", []) if c.get("type") == "Ready"), ""))'
  )"
  [[ "$ready" == "True" ]] || fail "Cloud Run service '$service' is not Ready (status=${ready:-unknown})"
}

API_URL="$(service_value hydra-api 'status.url')"
OBS_URL="$(service_value hydra-observatory 'status.url')"
WORKER_URL="$(service_value hydra-worker 'status.url')"

[[ -n "$API_URL" ]] || fail 'hydra-api has no Cloud Run URL'
[[ -n "$OBS_URL" ]] || fail 'hydra-observatory has no Cloud Run URL'
[[ -n "$WORKER_URL" ]] || fail 'hydra-worker has no Cloud Run URL'

printf '\n=== SMOKE ===\n'
ready_or_fail hydra-api
ready_or_fail hydra-observatory
ready_or_fail hydra-worker

HEALTH_JSON="$(curl --fail --silent --show-error --max-time 30 "$API_URL/health")" || \
  fail "API health check failed: $API_URL/health"
printf 'API health       : %s\n' "$HEALTH_JSON"

curl --fail --silent --show-error --location --max-time 30 \
  --output /dev/null "$OBS_URL" || fail "Observatory smoke failed: $OBS_URL"
printf 'Observatory HTTP : OK\n'
printf 'Worker readiness : READY (Cloud Run latest revision passed startup/readiness)\n'

API_REV="$(service_value hydra-api 'status.latestReadyRevisionName')"
OBS_REV="$(service_value hydra-observatory 'status.latestReadyRevisionName')"
WORKER_REV="$(service_value hydra-worker 'status.latestReadyRevisionName')"

cat <<SUMMARY

============================================================
HYDRA CLOUD RUN DEPLOY: PASS
Project: $PROJECT_ID
Region : $REGION

hydra-api
  URL      $API_URL
  revision $API_REV

hydra-observatory
  URL      $OBS_URL
  city     $OBS_URL/city
  revision $OBS_REV

hydra-worker
  URL      $WORKER_URL (private)
  revision $WORKER_REV
  service account $WORKER_SA
  Gemini auth Vertex AI / ADC
  Vertex location $VERTEX_LOCATION

Smoke:
  API /health  PASS
  Observatory  PASS
  Worker Ready PASS

Cloud worker logs:
  gcloud run services logs read hydra-worker --project=$PROJECT_ID --region=$REGION --limit=100

Deterministic local comparison run:
  python3 scripts/run_world.py --seed 20260826 --days 1
============================================================
SUMMARY
