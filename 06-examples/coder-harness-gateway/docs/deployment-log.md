# Deployment Log

## 2026-07-01 SageMaker vLLM Endpoint

Endpoint:

```text
coder-vllm-61ed21e8
```

Region:

```text
us-east-2
```

Model:

```text
Qwen/Qwen2.5-Coder-32B-Instruct-AWQ
```

Image:

```text
763104351884.dkr.ecr.us-east-2.amazonaws.com/djl-inference:0.36.0-lmi26.0.0-cu130
```

Instance:

```text
ml.g5.12xlarge
```

Reason for instance choice:

- `ml.g6e.* for endpoint usage` quota is `0` in this account and region.
- `ml.g5.12xlarge for endpoint usage` quota is `1`.
- The 32B AWQ model loaded successfully with vLLM tensor parallelism across 4 GPUs.

Validation:

```bash
./tests/test_sagemaker_endpoint.py
```

Observed completion:

```python
def square(n):
    return n * n
```

Notes:

- Initial endpoint creation failed once due to IAM role propagation. Terraform now includes a `time_sleep` wait before creating SageMaker model/config resources.
- The original EC2 G6e test instance was destroyed before the SageMaker deployment.
