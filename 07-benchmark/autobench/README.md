# SageMaker GenAI Inference Benchmarking

Configuration-driven LLM inference benchmarking across SageMaker Managed Inference, HyperPod EKS, and Bedrock BYOM. One config file drives all execution paths.

## Architecture

```
benchmarks.yaml (single source of truth)
       │
       ├── sdk/download_models.py         → Stage weights from HuggingFace to S3
       ├── sdk/quantize_models.py         → Create AWQ/GPTQ checkpoints (GPU Processing Job)
       ├── sdk/benchmark.py               → SageMaker Managed Inference (FTP/reserved capacity)
       ├── sdk/benchmark_hyperpod.py      → HyperPod EKS (kubectl + direct-URL)
       └── sdk/benchmark_bedrock_byom.py  → Bedrock BYOM (Mantle API + RU reservations)
```

All paths use **SageMaker AI Benchmarking (NVIDIA AIPerf)** as the load generator.

## Quick Start

```bash
cd sdk
uv venv && source .venv/bin/activate
uv pip install -r requirements.txt

# 1. Copy and configure
cp benchmarks.yaml.example benchmarks.yaml
# Edit benchmarks.yaml with your account ID, region, role ARN, etc.

# 2. Stage model weights to S3
python download_models.py --submit --region us-east-2 --model=gemma

# 3. Update s3_model_uri in benchmarks.yaml with the printed URI

# 4. Run benchmarks
python benchmark.py --model=gemma              # SageMaker MI
python benchmark_hyperpod.py --model=gemma     # HyperPod EKS
python benchmark_bedrock_byom.py --model=gemma # Bedrock BYOM
```

## Execution Paths

| Path | Script | Deploy Method | Compute |
|------|--------|---------------|---------|
| **SageMaker MI** | `benchmark.py` | `create_model` → endpoint | FTP reserved or on-demand |
| **HyperPod EKS** | `benchmark_hyperpod.py` | `kubectl apply` → NLB | FTP node group |
| **Bedrock BYOM** | `benchmark_bedrock_byom.py` | Mantle API import + RU reservation | AWS-managed |

## Configuration

All configuration lives in `benchmarks.yaml`. See [`benchmarks.yaml.example`](benchmarks.yaml.example) for a complete template with all features documented.

### Key Sections

| Section | Purpose |
|---------|---------|
| `athena` | Central results bucket + region |
| `workloads` | Business use cases → benchmark parameters |
| `models` | Model definitions shared across all paths |
| `sagemaker_defaults` + `sagemaker_benchmarks` | SMAI-specific config |
| `hyperpod_defaults` + `hyperpod_benchmarks` | HyperPod-specific config |
| `byom_defaults` + `byom_benchmarks` | Bedrock BYOM-specific config |

### Model Config Structure

Models are defined once and shared across all three paths:

```yaml
models:
  my-model-vllm:
    model_name: org/Model-Name        # HuggingFace ID
    instance_type: ml.p6-b200.48xlarge
    num_gpus: 8
    s3_model_uri: "s3://..."          # Pre-staged weights
    endpoint_name: ""                  # Optional: benchmark a pre-existing endpoint (skip deploy)
    env:                               # SMAI: SM_VLLM_* env vars
      SM_VLLM_KV_CACHE_DTYPE: "fp8"
    hyperpod_args:                     # HyperPod: vLLM CLI args
      - "--kv-cache-dtype"
      - "fp8"
    hyperpod_env:                      # HyperPod: pod env vars
      VLLM_USE_FLASHINFER_MOE_FP4: "1"
    byom:                              # Bedrock BYOM: import config
      base_model_id: "provider.model"
      model_id: ""                     # filled after import
```

### Capacity Modes (SMAI)

SageMaker Managed Inference supports two capacity modes, controlled by the
presence or absence of `ml_reservation_arn` in `sagemaker_defaults`:

| Mode | Config | When to use |
|------|--------|-------------|
| **FTP reserved** | `ml_reservation_arn: arn:aws:sagemaker:...` | p-family instances with Training Plan |
| **On-demand** | omit `ml_reservation_arn` | g-family instances or when no FTP available |

On-demand mode simply omits the `CapacityReservationConfig` from the endpoint
config. No code changes needed — just remove the ARN from your config.

### Pre-existing Endpoints

To benchmark an endpoint that was deployed outside of AutoBench (e.g., by
another team member or via the console), set `endpoint_name` at the model level:

```yaml
models:
  my-model:
    model_name: org/Model-Name
    instance_type: ml.g7e.24xlarge
    endpoint_name: "my-existing-endpoint"  # skip deploy, benchmark directly
```

Or use the `--endpoint` CLI flag:

```bash
python benchmark.py --endpoint my-existing-endpoint --model=my-model
```

Both approaches skip deployment and cleanup — AutoBench only runs the
benchmark jobs against the specified endpoint.

### Pre-existing HyperPod Deployments

To benchmark a model deployed on HyperPod outside of AutoBench (e.g., via the
Inference Operator, manual kubectl, or any method that produces a reachable URL),
set `hyperpod_url` at the model level:

```yaml
models:
  my-model:
    model_name: org/Model-Name
    instance_type: ml.p6-b200.48xlarge
    num_gpus: 8
    hyperpod_url: "http://k8s-benchmar-abc123.us-east-2.elb.amazonaws.com/v1"
```

This skips kubectl deploy and cleanup — AutoBench passes the URL directly to the
AI Benchmark Job. Works with `--submit` (the Processing Job uses `vpc_config` to
reach the internal NLB).

### Model Weight Storage

`download_models.py` stores weights in S3 using a normalized path derived from
the HuggingFace model ID (not the config key). This prevents duplicate downloads
when multiple config entries reference the same base model:

```
s3://<bucket>/models/google--gemma-4-31B-it/     ← one copy for all config variants
s3://<bucket>/models/QuantTrio--gemma-4-31B-it-AWQ/
```

## Results Pipeline

Results flow to a central Athena table for cross-model, cross-platform analysis:

```
S3 (AIPerf tar.gz) → athena_writer.py (extract + enrich) → S3 (Hive-partitioned JSON) → Athena → QuickSight
```

Each result row is **self-describing** — includes serving config, vLLM version, dataset, error rate, and a full raw AIPerf JSON blob for ad-hoc queries.

### Athena Setup

```bash
# Create the table (run in Athena console)
# See sdk/athena_ddl.sql for the full DDL

# After benchmarks complete, discover new partitions:
MSCK REPAIR TABLE benchmarking.benchmark_metrics;
```

### Backfill

Re-process existing results with the latest schema:

```bash
python backfill.py --environment=managed-inference
python backfill.py --environment=hyperpod --model=gemma-4-31b-vllm
```

## CLI Reference

All scripts support `--help` for full usage. Common flags:

```bash
--validate          # Show expanded job matrix (no AWS calls)
--model=<substr>    # Filter by model key (substring match)
--workload=<substr> # Filter by workload key (substring match)
--submit            # Submit as unattended Processing Job (5-day timeout)
--deploy-only       # Deploy endpoints/pods only (no benchmark)
--benchmark-only    # Benchmark existing endpoints/pods
--endpoint=<name>   # Benchmark a specific pre-existing endpoint (skip deploy)
--cleanup           # Delete deployed resources
```

### Quantize Models

Create pre-quantized checkpoints (AWQ INT4, GPTQ INT8) and upload to S3:

```bash
python quantize_models.py --validate                          # Show what needs quantizing
python quantize_models.py --submit --region us-east-2         # Submit as GPU Processing Job
python quantize_models.py --submit --method=awq               # AWQ only
python quantize_models.py --method=gptq --region us-east-2    # Run locally (needs GPU)
```

### Backfill Options

Re-process historical benchmark results from S3 tarballs:

```bash
# Backfill all models for an environment
python backfill.py --environment=managed-inference

# Backfill a specific model
python backfill.py --environment=hyperpod --model=deepseek-v4-pro-vllm

# Only process results from a specific date onward
python backfill.py --environment=hyperpod --since=20260527

# Only keep the latest run per (workload × concurrency) — skips old/failed runs
python backfill.py --environment=hyperpod --latest-only

# Combine both: latest results from this week only
python backfill.py --environment=managed-inference --latest-only --since=20260525

# Preview without writing
python backfill.py --environment=hyperpod --dry-run
```

| Flag | Effect |
|------|--------|
| `--since YYYYMMDD[THHMMSS]` | Only process tarballs with path timestamp ≥ this value |
| `--latest-only` | For each (workload, concurrency) combo, only process the most recent tarball |
| `--dry-run` | Preview what would be written without writing to Athena |
| `--model` | Filter to a specific model key |
| `--config` | Path to benchmarks.yaml (default: ../benchmarks.yaml) |


## Infrastructure

For automated HyperPod cluster setup with pre-configured networking (security groups, NLB subnet tags, IRSA), see [`infra/hyperpod-cluster-bootstrap.yaml`](infra/hyperpod-cluster-bootstrap.yaml).

## Key Features

- **Resume-safe** — re-run safely; completed jobs are skipped automatically
- **Gap capture** — failures classified into actionable categories
- **Set-and-forget** — `--submit` runs as Processing Job (5-day timeout, no credential expiry)
- **Single config** — `benchmarks.yaml` drives all paths
- **S3-first model loading** — pre-stage weights to avoid deploy timeouts
- **Centralized results** — athena_writer pushes all results to one region
- **Self-describing records** — every Athena row includes full serving context + config hash
- **Deterministic deduplication** — re-runs overwrite previous results (no duplicates)

## Extending

### Add a New Model

1. Add to `models` in `benchmarks.yaml`
2. Add to the appropriate `*_benchmarks` section
3. Stage weights: `python download_models.py --submit --region <region> --model=<key>`
4. Run: `python benchmark.py --model=<key>`

### Add a New Workload

Add to `workloads` in `benchmarks.yaml`, then reference in benchmark entries.

### Change vLLM Version

Update `sagemaker_image` in `sagemaker_defaults` (SMAI) and/or `vllm_image` in `hyperpod_defaults` (HyperPod).
