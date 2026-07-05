#!/usr/bin/env bash
# Deploy Road to Ussuri to Google Cloud Run.
#
# Usage:
#   PROJECT_ID=my-proj GROQ_API_KEY=gsk_... ./deploy/deploy_cloud_run.sh
#
# Optional env: REGION (default europe-west1), SERVICE (default road-to-ussuri),
#               GROQ_MODEL (default llama-3.3-70b-versatile), ALLOW_UNAUTH (default true)
set -euo pipefail

PROJECT_ID="${PROJECT_ID:?set PROJECT_ID}"
GROQ_API_KEY="${GROQ_API_KEY:?set GROQ_API_KEY}"
REGION="${REGION:-europe-west1}"
SERVICE="${SERVICE:-road-to-ussuri}"
GROQ_MODEL="${GROQ_MODEL:-llama-3.3-70b-versatile}"
ALLOW_UNAUTH="${ALLOW_UNAUTH:-true}"
SECRET_NAME="groq-api-key"

echo "▶ project=$PROJECT_ID region=$REGION service=$SERVICE"
gcloud config set project "$PROJECT_ID" >/dev/null

echo "▶ enabling required APIs…"
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com >/dev/null

echo "▶ storing GROQ_API_KEY in Secret Manager ($SECRET_NAME)…"
if ! gcloud secrets describe "$SECRET_NAME" >/dev/null 2>&1; then
  gcloud secrets create "$SECRET_NAME" --replication-policy=automatic >/dev/null
fi
printf '%s' "$GROQ_API_KEY" | gcloud secrets versions add "$SECRET_NAME" --data-file=- >/dev/null

AUTH_FLAG="--allow-unauthenticated"
[ "$ALLOW_UNAUTH" = "true" ] || AUTH_FLAG="--no-allow-unauthenticated"

echo "▶ deploying from source (Cloud Build uses the Dockerfile)…"
gcloud run deploy "$SERVICE" \
  --source . \
  --region "$REGION" \
  $AUTH_FLAG \
  --port 8080 \
  --memory 512Mi \
  --cpu 1 \
  --min-instances 0 \
  --max-instances 3 \
  --set-env-vars "GROQ_MODEL=${GROQ_MODEL}" \
  --set-secrets "GROQ_API_KEY=${SECRET_NAME}:latest"

URL=$(gcloud run services describe "$SERVICE" --region "$REGION" --format='value(status.url)')
echo "✔ deployed: $URL"
echo "   open $URL in a browser to play."
