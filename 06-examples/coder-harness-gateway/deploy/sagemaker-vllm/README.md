# SageMaker vLLM Endpoint

This deployment creates a SageMaker real-time endpoint using the AWS DJL/LMI inference container with vLLM rolling batch enabled.

Default model:

```text
Qwen/Qwen2.5-Coder-32B-Instruct-AWQ
```

Default tested instance in this account:

```text
ml.g5.12xlarge
```

Reason: `ml.g6e.* for endpoint usage` quota is currently `0` in `us-east-2` for this account. After the quota is raised, deploy with:

```bash
INSTANCE_TYPE=ml.g6e.2xlarge ./deploy/sagemaker-vllm/deploy.sh
```

## Deploy

```bash
./deploy/sagemaker-vllm/deploy.sh
```

## Test

```bash
./tests/test_sagemaker_endpoint.py
```

The test reads `terraform output -json` from this deployment and invokes the SageMaker endpoint through `boto3`.

## Destroy

```bash
cd deploy/sagemaker-vllm
terraform destroy -var "region=${AWS_REGION:-us-east-2}" -var "instance_type=ml.g5.12xlarge"
```
