# AWS G6e Deployment

This deployment creates one EC2 G6e instance running:

- vLLM OpenAI-compatible server on port `8000`.
- LiteLLM gateway on port `4000`.
- SSM access for operational debugging.

It defaults to `Qwen/Qwen2.5-Coder-32B-Instruct-AWQ` as `coding-local`.

## Deploy

From the repository root:

```bash
./deploy/aws-g6e/deploy.sh
```

The script detects your public IP and passes it as `allowed_cidr`, so the gateway is not opened to the internet.

## Test

```bash
./tests/test_gateway.py
```

The test reads Terraform outputs from `deploy/aws-g6e`, waits for the gateway, and sends one chat completion to `coding-default`.

## Inspect

```bash
cd deploy/aws-g6e
terraform output
terraform output -raw ssm_start_session_command
```

On the instance:

```bash
journalctl -u vllm-coder -f
journalctl -u litellm-gateway -f
```

## Destroy

```bash
cd deploy/aws-g6e
terraform destroy
```
