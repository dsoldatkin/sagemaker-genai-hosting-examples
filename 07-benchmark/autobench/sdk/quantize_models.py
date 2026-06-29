#!/usr/bin/env python3
"""
Model quantization — produces pre-quantized checkpoints for AWQ and GPTQ.

Downloads model weights from HuggingFace (or S3), applies quantization, and
uploads the quantized checkpoint to S3 for benchmarking.

Requires GPU compute: AWQ and GPTQ both need to run model forward passes
for calibration. Submit as a Processing Job with a GPU instance.

Usage:
    python quantize_models.py --validate                          Show what would be quantized
    python quantize_models.py --method=awq --region=us-east-2    Quantize AWQ locally
    python quantize_models.py --method=gptq --region=us-east-2   Quantize GPTQ locally
    python quantize_models.py --method=all --region=us-east-2    Both methods
    python quantize_models.py --submit --region=us-east-2        Submit as Processing Job (GPU)
    python quantize_models.py --submit --method=awq              AWQ only, remote

Output: s3://sagemaker-benchmark-{region}-{account}/models/{model_key}/
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

import boto3
import yaml

ENTRYPOINT_MODE = os.environ.get("SM_PROCESSING_MODE") == "quantize"

# Calibration dataset: we use a small sample of text for quantization calibration.
# For production quality, use domain-specific data (e.g., gov_report samples).
CALIBRATION_SAMPLES = 128
CALIBRATION_SEQ_LEN = 2048


def load_config(path="../benchmarks-phase2.yaml"):
    if ENTRYPOINT_MODE:
        path = "/opt/ml/processing/input/config/benchmarks-phase2.yaml"
    with open(path) as f:
        return yaml.safe_load(f)


def get_account(region="us-east-2"):
    return boto3.client("sts", region_name=region).get_caller_identity()["Account"]


def ensure_bucket(bucket, region):
    s3 = boto3.client("s3", region_name=region)
    try:
        s3.head_bucket(Bucket=bucket)
    except Exception:
        try:
            if region == "us-east-1":
                s3.create_bucket(Bucket=bucket)
            else:
                s3.create_bucket(Bucket=bucket, CreateBucketConfiguration={"LocationConstraint": region})
            print(f"  ✓ Created bucket: {bucket}")
        except Exception:
            pass


def check_s3_exists(bucket, prefix, region):
    """Check if quantized model already exists in S3."""
    s3 = boto3.client("s3", region_name=region)
    try:
        s3.head_object(Bucket=bucket, Key=f"{prefix}config.json")
        return True
    except Exception:
        return False


def get_calibration_data(tokenizer, n_samples=CALIBRATION_SAMPLES, seq_len=CALIBRATION_SEQ_LEN):
    """Generate calibration data for quantization.

    Uses wikitext-2 as default calibration corpus. For higher quality,
    replace with domain-specific data (e.g., gov_report samples).
    """
    from datasets import load_dataset

    print(f"  📚 Loading calibration data (n={n_samples}, seq_len={seq_len})...")
    dataset = load_dataset("wikitext", "wikitext-2-raw-v1", split="train")

    # Concatenate text and tokenize into fixed-length sequences
    text = "\n\n".join(dataset["text"])
    tokens = tokenizer(text, return_tensors="pt")
    input_ids = tokens.input_ids[0]

    # Split into calibration samples
    samples = []
    for i in range(0, len(input_ids) - seq_len, seq_len):
        if len(samples) >= n_samples:
            break
        samples.append(input_ids[i:i + seq_len].unsqueeze(0))

    print(f"  ✓ Generated {len(samples)} calibration samples")
    return samples


def quantize_awq(model_name, output_dir, region, account):
    """Quantize model using AWQ (Activation-aware Weight Quantization).

    AWQ INT4: 4-bit weight quantization with group size 128.
    Preserves ~97-99% of FP16 quality on most benchmarks.
    """
    print(f"\n{'='*60}")
    print(f"[AWQ INT4] Quantizing: {model_name}")
    print(f"  Config: w_bit=4, group_size=128, zero_point=True")
    print(f"{'='*60}")

    output_path = Path(output_dir) / "awq"
    output_path.mkdir(parents=True, exist_ok=True)

    # Install AWQ
    subprocess.run(
        ["pip", "install", "-q", "autoawq", "transformers", "accelerate", "datasets"],
        check=True, capture_output=True
    )

    from awq import AutoAWQForCausalLM
    from transformers import AutoTokenizer

    # Load model and tokenizer
    print(f"  ⬇️  Loading model for quantization...")
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)
    model = AutoAWQForCausalLM.from_pretrained(
        model_name,
        trust_remote_code=True,
        safetensors=True,
    )

    # Quantize
    quant_config = {
        "zero_point": True,
        "q_group_size": 128,
        "w_bit": 4,
        "version": "GEMM",  # GEMM kernel (fastest for batch inference)
    }
    print(f"  ⚙️  Quantizing (this takes 30-60 min for 31B params)...")
    model.quantize(tokenizer, quant_config=quant_config)

    # Save
    print(f"  💾 Saving quantized model to {output_path}...")
    model.save_quantized(str(output_path))
    tokenizer.save_pretrained(str(output_path))

    # Upload to S3
    bucket = f"sagemaker-benchmark-{region}-{account}"
    s3_prefix = "models/gemma-4-31b-int4-awq/"
    s3_uri = f"s3://{bucket}/{s3_prefix}"

    if check_s3_exists(bucket, s3_prefix, region):
        print(f"  ⏭️  Already in S3: {s3_uri}")
    else:
        ensure_bucket(bucket, region)
        print(f"  ⬆️  Uploading to {s3_uri}...")
        subprocess.run(
            ["aws", "s3", "sync", str(output_path), s3_uri, "--region", region],
            check=True
        )

    print(f"  ✓ AWQ quantization complete: {s3_uri}")
    return s3_uri


def quantize_gptq(model_name, output_dir, region, account):
    """Quantize model using GPTQ (8-bit).

    GPTQ INT8: 8-bit weight quantization with group size 128.
    Preserves ~99%+ of FP16 quality (nearly lossless).
    """
    print(f"\n{'='*60}")
    print(f"[GPTQ INT8] Quantizing: {model_name}")
    print(f"  Config: bits=8, group_size=128, desc_act=False")
    print(f"{'='*60}")

    output_path = Path(output_dir) / "gptq"
    output_path.mkdir(parents=True, exist_ok=True)

    # Install GPTQ
    subprocess.run(
        ["pip", "install", "-q", "auto-gptq", "transformers", "accelerate", "datasets", "optimum"],
        check=True, capture_output=True
    )

    from transformers import AutoTokenizer
    from auto_gptq import AutoGPTQForCausalLM, BaseQuantizeConfig

    # Load tokenizer for calibration data
    print(f"  ⬇️  Loading tokenizer...")
    tokenizer = AutoTokenizer.from_pretrained(model_name, trust_remote_code=True)

    # Prepare calibration dataset
    calibration_data = get_calibration_data_gptq(tokenizer)

    # Configure quantization
    quantize_config = BaseQuantizeConfig(
        bits=8,
        group_size=128,
        desc_act=False,  # False = faster inference, minimal quality loss
        sym=True,        # Symmetric quantization
    )

    # Load model
    print(f"  ⬇️  Loading model for quantization...")
    model = AutoGPTQForCausalLM.from_pretrained(
        model_name,
        quantize_config=quantize_config,
        trust_remote_code=True,
    )

    # Quantize with calibration data
    print(f"  ⚙️  Quantizing (this takes 30-90 min for 31B params)...")
    model.quantize(calibration_data)

    # Save
    print(f"  💾 Saving quantized model to {output_path}...")
    model.save_quantized(str(output_path))
    tokenizer.save_pretrained(str(output_path))

    # Upload to S3
    bucket = f"sagemaker-benchmark-{region}-{account}"
    s3_prefix = "models/gemma-4-31b-int8/"
    s3_uri = f"s3://{bucket}/{s3_prefix}"

    if check_s3_exists(bucket, s3_prefix, region):
        print(f"  ⏭️  Already in S3: {s3_uri}")
    else:
        ensure_bucket(bucket, region)
        print(f"  ⬆️  Uploading to {s3_uri}...")
        subprocess.run(
            ["aws", "s3", "sync", str(output_path), s3_uri, "--region", region],
            check=True
        )

    print(f"  ✓ GPTQ quantization complete: {s3_uri}")
    return s3_uri


def get_calibration_data_gptq(tokenizer, n_samples=CALIBRATION_SAMPLES, seq_len=CALIBRATION_SEQ_LEN):
    """Prepare calibration data in the format GPTQ expects.

    Returns list of dicts with 'input_ids' and 'attention_mask'.
    """
    from datasets import load_dataset

    print(f"  📚 Loading calibration data for GPTQ (n={n_samples}, seq_len={seq_len})...")
    dataset = load_dataset("wikitext", "wikitext-2-raw-v1", split="train")

    # Filter empty lines and tokenize
    texts = [t for t in dataset["text"] if len(t.strip()) > 50][:n_samples * 2]
    samples = []
    for text in texts:
        if len(samples) >= n_samples:
            break
        encoded = tokenizer(
            text,
            truncation=True,
            max_length=seq_len,
            return_tensors="pt",
            padding="max_length",
        )
        if encoded.input_ids.shape[1] >= seq_len // 2:  # Skip very short samples
            samples.append({
                "input_ids": encoded.input_ids[0],
                "attention_mask": encoded.attention_mask[0],
            })

    print(f"  ✓ Prepared {len(samples)} calibration samples")
    return samples


def submit_job(args):
    """Submit quantization as a SageMaker Processing Job with GPU."""
    config = load_config(args.config)
    defaults = config.get("sagemaker_defaults", {})
    region = args.region
    role = defaults.get("role_arn")
    if not role:
        raise ValueError("'role_arn' must be set in sagemaker_defaults")
    account = get_account(region)
    bucket = f"sagemaker-benchmark-{region}-{account}"

    method_suffix = f"-{args.method}" if args.method != "all" else ""
    job_name = f"quant{method_suffix}-{datetime.now().strftime('%m%d-%H%M%S')}"[:63]

    # Upload config + script
    s3 = boto3.client("s3", region_name=region)
    ensure_bucket(bucket, region)
    config_key = f"processing-configs/{job_name}/benchmarks-phase2.yaml"
    script_key = f"processing-configs/{job_name}/quantize_models.py"
    s3.put_object(Bucket=bucket, Key=config_key, Body=open(args.config).read())
    s3.put_object(Bucket=bucket, Key=script_key, Body=open(__file__).read())

    container_args = ["--region", region, "--method", args.method]

    sm = boto3.client("sagemaker", region_name=region)

    # Use a GPU instance for quantization — need enough VRAM for 31B model
    # g5.12xlarge: 4× A10G (96GB total) — sufficient for 31B in FP16 with offloading
    # p4d.24xlarge: 8× A100 (320GB total) — fastest, but expensive
    # ml.g5.12xlarge is the sweet spot for cost vs speed
    instance_type = args.instance or "ml.g5.12xlarge"

    print(f"\n{'='*60}")
    print(f"Submitting quantization job: {job_name}")
    print(f"  Region: {region}")
    print(f"  Method: {args.method}")
    print(f"  Instance: {instance_type}")
    print(f"  Disk: 2TB (model weights + quantized output)")
    print(f"{'='*60}\n")

    sm.create_processing_job(
        ProcessingJobName=job_name,
        ProcessingResources={
            "ClusterConfig": {
                "InstanceCount": 1,
                "InstanceType": instance_type,
                "VolumeSizeInGB": 2000,
            }
        },
        AppSpecification={
            "ImageUri": f"763104351884.dkr.ecr.{region}.amazonaws.com/pytorch-training:2.5.1-gpu-py311-cu124",
            "ContainerEntrypoint": ["python3", "/opt/ml/processing/input/script/quantize_models.py"],
            "ContainerArguments": container_args,
        },
        Environment={
            "SM_PROCESSING_MODE": "quantize",
            "HF_TOKEN": os.environ.get("HF_TOKEN", ""),
            "TRANSFORMERS_CACHE": "/tmp/hf_cache",
        },
        ProcessingInputs=[
            {
                "InputName": "config",
                "S3Input": {
                    "S3Uri": f"s3://{bucket}/{config_key}",
                    "LocalPath": "/opt/ml/processing/input/config",
                    "S3DataType": "S3Prefix",
                    "S3InputMode": "File",
                },
            },
            {
                "InputName": "script",
                "S3Input": {
                    "S3Uri": f"s3://{bucket}/{script_key}",
                    "LocalPath": "/opt/ml/processing/input/script",
                    "S3DataType": "S3Prefix",
                    "S3InputMode": "File",
                },
            },
        ],
        ProcessingOutputConfig={
            "Outputs": [{
                "OutputName": "dummy",
                "S3Output": {
                    "S3Uri": f"s3://{bucket}/processing-configs/{job_name}/output/",
                    "LocalPath": "/opt/ml/processing/output",
                    "S3UploadMode": "EndOfJob",
                },
            }]
        },
        RoleArn=role,
        StoppingCondition={"MaxRuntimeInSeconds": 86400},  # 24h max
        NetworkConfig={"EnableNetworkIsolation": False},
    )

    print(f"  ✓ Job submitted: {job_name}")
    print(f"  Monitor: aws sagemaker describe-processing-job --processing-job-name {job_name} --region {region}")
    print(f"\n  After completion, update benchmarks-phase2.yaml s3_model_uri fields:")
    print(f"    gemma-4-31b-int4-awq: s3://sagemaker-benchmark-{region}-{account}/models/gemma-4-31b-int4-awq/")
    print(f"    gemma-4-31b-int8:     s3://sagemaker-benchmark-{region}-{account}/models/gemma-4-31b-int8/")


def run_quantization(region, method="all", config_path="../benchmarks-phase2.yaml"):
    """Run quantization locally (requires GPU)."""
    config = load_config(config_path)
    account = get_account(region)
    model_name = "google/gemma-4-31B-it"  # From config
    output_dir = "/tmp/quantized_models"

    results = []

    if method in ("all", "awq"):
        try:
            uri = quantize_awq(model_name, output_dir, region, account)
            results.append({"method": "awq", "s3_uri": uri, "success": True})
        except Exception as e:
            print(f"  ✗ AWQ failed: {e}")
            import traceback
            traceback.print_exc()
            results.append({"method": "awq", "error": str(e), "success": False})

    if method in ("all", "gptq"):
        try:
            uri = quantize_gptq(model_name, output_dir, region, account)
            results.append({"method": "gptq", "s3_uri": uri, "success": True})
        except Exception as e:
            print(f"  ✗ GPTQ failed: {e}")
            import traceback
            traceback.print_exc()
            results.append({"method": "gptq", "error": str(e), "success": False})

    # Summary
    print(f"\n{'═'*60}")
    print("QUANTIZATION SUMMARY")
    print(f"{'═'*60}")
    ok = sum(1 for r in results if r["success"])
    print(f"Total: {len(results)} | Success: {ok} | Failed: {len(results) - ok}")
    print(f"\nUpdate benchmarks-phase2.yaml s3_model_uri fields:")
    for r in results:
        if r["success"]:
            model_key = "gemma-4-31b-int4-awq" if r["method"] == "awq" else "gemma-4-31b-int8"
            print(f"  {model_key}: \"{r['s3_uri']}\"")


def validate(config_path):
    """Show what would be quantized."""
    config = load_config(config_path)
    models = config.get("models", {})

    print("Quantization targets:\n")
    quant_models = []
    for key, m in models.items():
        env = m.get("env", {})
        quant = env.get("SM_VLLM_QUANTIZATION", "")
        if quant in ("awq", "gptq"):
            quant_models.append((key, m, quant))
            status = "✓ s3_model_uri set" if m.get("s3_model_uri") else "⚠ needs quantized checkpoint"
            print(f"  {key}")
            print(f"    method: {quant.upper()}")
            print(f"    base model: {m['model_name']}")
            print(f"    instance: {m['instance_type']}")
            print(f"    status: {status}")
            print()

    runtime_models = []
    for key, m in models.items():
        env = m.get("env", {})
        quant = env.get("SM_VLLM_QUANTIZATION", "")
        if quant not in ("awq", "gptq"):
            runtime_models.append((key, m))

    if runtime_models:
        print("Runtime quantization (no pre-quantized checkpoint needed):\n")
        for key, m in runtime_models:
            env = m.get("env", {})
            dtype = env.get("SM_VLLM_DTYPE", "auto")
            quant = env.get("SM_VLLM_QUANTIZATION", "none")
            print(f"  {key}: dtype={dtype}, quantization={quant}")

    print(f"\n{'─'*40}")
    print(f"Pre-quantization needed: {len(quant_models)} model(s)")
    print(f"Runtime-only: {len(runtime_models)} model(s)")


def main():
    if ENTRYPOINT_MODE:
        # Running inside Processing Job
        parser = argparse.ArgumentParser()
        parser.add_argument("--region", required=True)
        parser.add_argument("--method", default="all", choices=["all", "awq", "gptq"])
        args = parser.parse_args()
        # Install dependencies
        subprocess.run(
            ["pip", "install", "-q", "autoawq", "auto-gptq", "transformers",
             "accelerate", "datasets", "optimum", "pyyaml", "safetensors"],
            check=True, capture_output=True
        )
        run_quantization(args.region, args.method)
        return

    parser = argparse.ArgumentParser(
        description="Quantize model weights (AWQ INT4, GPTQ INT8) and upload to S3.",
        epilog="""
examples:
  %(prog)s --validate                             Show what needs quantizing
  %(prog)s --method=awq --region=us-east-2        Quantize AWQ locally (needs GPU)
  %(prog)s --method=gptq --region=us-east-2       Quantize GPTQ locally (needs GPU)
  %(prog)s --method=all --region=us-east-2        Both methods
  %(prog)s --submit --region=us-east-2            Submit as Processing Job (GPU instance)
  %(prog)s --submit --method=awq --instance=ml.p4d.24xlarge  AWQ on p4d (fast)
        """,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("config", nargs="?", default="../benchmarks-phase2.yaml",
                        help="Path to config (default: ../benchmarks-phase2.yaml)")
    parser.add_argument("--validate", action="store_true",
                        help="Show quantization targets and exit")
    parser.add_argument("--method", default="all", choices=["all", "awq", "gptq"],
                        help="Quantization method (default: all)")
    parser.add_argument("--region", default="us-east-2",
                        help="AWS region for S3 output")
    parser.add_argument("--submit", action="store_true",
                        help="Submit as a remote Processing Job (GPU, 24h timeout)")
    parser.add_argument("--instance", default=None,
                        help="Instance type for Processing Job (default: ml.g5.12xlarge)")
    args = parser.parse_args()

    if args.validate:
        validate(args.config)
        return

    if args.submit:
        submit_job(args)
        return

    # Local execution (needs GPU)
    run_quantization(args.region, args.method, args.config)


if __name__ == "__main__":
    main()
