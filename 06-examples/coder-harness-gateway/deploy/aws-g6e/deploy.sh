#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-2}}"
PUBLIC_IP="$(curl -fsS https://checkip.amazonaws.com | tr -d '[:space:]')"

terraform init
terraform apply \
  -var "region=${REGION}" \
  -var "allowed_cidr=${PUBLIC_IP}/32" \
  -auto-approve

terraform output
