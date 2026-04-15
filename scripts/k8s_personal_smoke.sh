#!/usr/bin/env bash

set -euo pipefail

CLUSTER_NAME="${CLUSTER_NAME:-deepwork-personal}"
NAMESPACE="${NAMESPACE:-default}"
MANIFEST_PATH="${MANIFEST_PATH:-deploy/kubernetes-personal.yaml}"
APP_NAME="${APP_NAME:-deepwork-personal}"
SERVICE_NAME="${SERVICE_NAME:-deepwork-personal}"
LOCAL_PORT="${LOCAL_PORT:-18000}"
IMAGE_REF="${IMAGE_REF:-yavarkhodadadi/deep-work-4dx:latest}"
COOKIE_JAR="$(mktemp)"
SESSION_JSON="$(mktemp)"
PORT_FORWARD_PID=""

cleanup() {
  if [[ -n "${PORT_FORWARD_PID}" ]]; then
    kill "${PORT_FORWARD_PID}" >/dev/null 2>&1 || true
  fi
  rm -f "${COOKIE_JAR}"
  rm -f "${SESSION_JSON}"
}

trap cleanup EXIT

require_bin() {
  command -v "$1" >/dev/null 2>&1 || {
    echo "Missing required dependency: $1" >&2
    exit 1
  }
}

require_bin kind
require_bin kubectl
require_bin curl

start_port_forward() {
  if [[ -n "${PORT_FORWARD_PID}" ]]; then
    kill "${PORT_FORWARD_PID}" >/dev/null 2>&1 || true
  fi
  kubectl port-forward svc/"${SERVICE_NAME}" "${LOCAL_PORT}:8000" >/tmp/deepwork-port-forward.log 2>&1 &
  PORT_FORWARD_PID=$!
  sleep 5
}

wait_for_http() {
  local attempts=0
  until curl -fsS "http://127.0.0.1:${LOCAL_PORT}/" >/dev/null; do
    attempts=$((attempts + 1))
    if [[ "${attempts}" -ge 20 ]]; then
      echo "App did not become reachable on port-forwarded HTTP endpoint" >&2
      return 1
    fi
    sleep 2
  done
}

if ! kind get clusters | grep -qx "${CLUSTER_NAME}"; then
  kind create cluster --name "${CLUSTER_NAME}"
fi

if docker image inspect "${IMAGE_REF}" >/dev/null 2>&1; then
  kind load docker-image "${IMAGE_REF}" --name "${CLUSTER_NAME}"
fi

kubectl delete -f "${MANIFEST_PATH}" --ignore-not-found=true --wait=true >/dev/null 2>&1 || true
kubectl apply -f "${MANIFEST_PATH}"
kubectl rollout status deployment/"${APP_NAME}" --timeout=180s

start_port_forward
wait_for_http

curl -fsS -c "${COOKIE_JAR}" -b "${COOKIE_JAR}" \
  -d "email=admin@example.com&password=password" \
  "http://127.0.0.1:${LOCAL_PORT}/bootstrap" >/dev/null

curl -fsS -L -c "${COOKIE_JAR}" -b "${COOKIE_JAR}" \
  -d "email=admin@example.com&password=password" \
  "http://127.0.0.1:${LOCAL_PORT}/login" >/dev/null

curl -fsS -c "${COOKIE_JAR}" -b "${COOKIE_JAR}" \
  -d "email=member@example.com&password=password" \
  "http://127.0.0.1:${LOCAL_PORT}/admin/users" >/dev/null

curl -fsS -c "${COOKIE_JAR}" -b "${COOKIE_JAR}" \
  -d "title=Ship+v1&description=Deliver+the+first+release" \
  "http://127.0.0.1:${LOCAL_PORT}/goals" >/dev/null

goal_page="$(curl -fsS -L -c "${COOKIE_JAR}" -b "${COOKIE_JAR}" "http://127.0.0.1:${LOCAL_PORT}/goals")"
goal_id="$(printf '%s' "${goal_page}" | python3 -c 'import re,sys; data=sys.stdin.read(); match=re.search(r"/goals/(\d+)", data); print(match.group(1) if match else "")')"

if [[ -z "${goal_id}" ]]; then
  echo "Unable to discover goal id from goals page" >&2
  exit 1
fi

curl -fsS -c "${COOKIE_JAR}" -b "${COOKIE_JAR}" \
  -d "content=Finished+the+API+contract" \
  "http://127.0.0.1:${LOCAL_PORT}/goals/${goal_id}/milestones" >/dev/null

curl -fsS -c "${COOKIE_JAR}" -b "${COOKIE_JAR}" \
  -d "content=Need+one+more+review+pass" \
  "http://127.0.0.1:${LOCAL_PORT}/goals/${goal_id}/notes" >/dev/null

curl -fsS -c "${COOKIE_JAR}" -b "${COOKIE_JAR}" \
  -d "goal_id=${goal_id}&planned_minutes=25" \
  "http://127.0.0.1:${LOCAL_PORT}/api/sessions/start" >"${SESSION_JSON}"

session_id="$(python3 -c 'import json; import pathlib; data=json.loads(pathlib.Path("'"${SESSION_JSON}"'").read_text()); print(data["session"]["id"])')"

curl -fsS -c "${COOKIE_JAR}" -b "${COOKIE_JAR}" \
  -d "note=Focused+work+completed" \
  "http://127.0.0.1:${LOCAL_PORT}/api/sessions/${session_id}/complete" >/dev/null

curl -fsS -c "${COOKIE_JAR}" -b "${COOKIE_JAR}" \
  -d "goal-${goal_id}=5" \
  "http://127.0.0.1:${LOCAL_PORT}/weekly-review/commitments" >/dev/null

pod_name="$(kubectl get pods -l app=${APP_NAME} -o jsonpath='{.items[0].metadata.name}')"
kubectl delete pod "${pod_name}" --wait=true
kubectl rollout status deployment/"${APP_NAME}" --timeout=180s
start_port_forward
wait_for_http

post_restart_goal_page="$(curl -fsS -c "${COOKIE_JAR}" -b "${COOKIE_JAR}" "http://127.0.0.1:${LOCAL_PORT}/goals/${goal_id}")"
post_restart_dashboard="$(curl -fsS -c "${COOKIE_JAR}" -b "${COOKIE_JAR}" "http://127.0.0.1:${LOCAL_PORT}/dashboard")"

grep -q "Finished the API contract" <<<"${post_restart_goal_page}"
grep -q "Need one more review pass" <<<"${post_restart_goal_page}"
grep -q "Ship v1" <<<"${post_restart_dashboard}"

echo "Personal Kubernetes smoke passed for ${APP_NAME} using ${IMAGE_REF}"
