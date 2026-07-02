#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

REGION="${AWS_REGION:-${AWS_DEFAULT_REGION:-us-east-2}}"
INSTANCE_TYPE="${INSTANCE_TYPE:-ml.g5.12xlarge}"

terraform init
terraform apply \
  -var "region=${REGION}" \
  -var "instance_type=${INSTANCE_TYPE}" \
  -auto-approve

terraform output
