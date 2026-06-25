#!/usr/bin/env python3
"""
Ollama Deployment Script for PortKit GRPO Models

This script helps deploy trained GRPO models to Ollama for local inference.

Usage:
    python deploy_to_ollama.py --model grpo6
    python deploy_to_ollama.py --model grpo7 --model-path /path/to/model
    python deploy_to_ollama.py --list
"""

import argparse
import subprocess
import sys
from pathlib import Path

DOCS_DIR = Path(__file__).parent.parent / "docs"
MODELFILE_TEMPLATE = DOCS_DIR / "Modelfile.template"
OLLAMA_DEPLOYMENT_GUIDE = DOCS_DIR / "OLLAMA_DEPLOYMENT.md"

# Model configurations
MODELS = {
    "grpo6": {
        "name": "PortKit Coder GRPO6",
        "hf_repo": "alexchapin/portkit-coder-8b-grpo6",
        "description": "Group REINFORCE + SFT init, 200 steps, reward 0.6177",
        "ollama_name": "portkit-coder-grpo6",
    },
    "grpo7": {
        "name": "PortKit Coder GRPO7",
        "hf_repo": "alexchapin/portkit-coder-8b-grpo7",
        "description": "Self-reflection RL, 100 steps, reward 0.6172",
        "ollama_name": "portkit-coder-grpo7",
    },
    "grpo8": {
        "name": "PortKit Coder GRPO8",
        "hf_repo": "alexchapin/portkit-coder-8b-grpo8",
        "description": "Anti-hallucination focus (planned)",
        "ollama_name": "portkit-coder-grpo8",
    },
    "sft1": {
        "name": "PortKit Coder SFT v1",
        "hf_repo": "alexchapin/portkit-coder-8b-sft1",
        "description": "Supervised Fine-tuning, 200 steps",
        "ollama_name": "portkit-coder-sft1",
    },
}


def run_command(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a shell command and return the result."""
    print(f"$ {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if check and result.returncode != 0:
        print(f"Error: {result.stderr}")
        sys.exit(1)
    return result


def check_ollama_installed() -> bool:
    """Check if Ollama is installed and running."""
    try:
        result = run_command(["ollama", "list"], check=False)
        return result.returncode == 0
    except FileNotFoundError:
        return False


def list_models() -> None:
    """List available models with their status."""
    print("\nAvailable PortKit GRPO Models:")
    print("=" * 60)
    for key, model in MODELS.items():
        print(f"\n  {key.upper()}: {model['name']}")
        print(f"    HuggingFace: {model['hf_repo']}")
        print(f"    Description: {model['description']}")
        print(f"    Ollama name: {model['ollama_name']}")
    print("\n" + "=" * 60)


def deploy_model(model_key: str, model_path: str | None, ollama_name: str | None) -> None:
    """Deploy a model to Ollama."""
    if model_key not in MODELS:
        print(f"Unknown model: {model_key}")
        print("Available models: " + ", ".join(MODELS.keys()))
        sys.exit(1)

    model = MODELS[model_key]

    if not check_ollama_installed():
        print("Error: Ollama is not installed or not running.")
        print("Install from: https://ollama.ai")
        sys.exit(1)

    # Check if model path provided, else look for local export
    if model_path is None:
        export_dir = Path(__file__).parent / "exports" / f"{model_key}_merged"
        if export_dir.exists():
            model_path = str(export_dir)
            print(f"Using local export: {model_path}")
        else:
            print(f"No model path provided and no local export found at {export_dir}")
            print(f"Please provide --model-path or export the model first")
            print(f"\nSee {OLLAMA_DEPLOYMENT_GUIDE} for export instructions")
            sys.exit(1)

    # Determine Ollama model name
    name = ollama_name or model["ollama_name"]

    # Create Modelfile in the model directory
    model_dir = Path(model_path)
    modelfile_path = model_dir / "Modelfile"

    if not MODELFILE_TEMPLATE.exists():
        print(f"Error: Modelfile template not found at {MODELFILE_TEMPLATE}")
        sys.exit(1)

    # Copy template
    import shutil

    shutil.copy(MODELFILE_TEMPLATE, modelfile_path)

    # Replace FROM line with actual model path
    gguf_files = list(model_dir.glob("*.gguf")) + list(model_dir.glob("*/**/*.gguf"))
    if gguf_files:
        gguf_path = gguf_files[0].relative_to(model_dir)
        with open(modelfile_path, "r") as f:
            content = f.read()
        content = content.replace(
            "./model/portkit-coder-gguf", f"./{gguf_path.parent}/{gguf_path.name}"
        )
        with open(modelfile_path, "w") as f:
            f.write(content)
        print(f"Updated Modelfile to use GGUF: {gguf_path}")
    else:
        # Update FROM to point to directory
        with open(modelfile_path, "r") as f:
            content = f.read()
        content = content.replace("./model/portkit-coder-gguf", "./model")
        with open(modelfile_path, "w") as f:
            f.write(content)
        print("Updated Modelfile to use model directory (no GGUF found)")

    print(f"\nCreating Ollama model '{name}' from {model_path}...")
    print(f"Using Modelfile: {modelfile_path}")

    # Create model in Ollama
    result = run_command(["ollama", "create", name, "-f", str(modelfile_path)], check=False)

    if result.returncode == 0:
        print(f"\n✅ Model '{name}' created successfully!")
        print(f"\nTo run:")
        print(f"  ollama run {name}")
        print(f"\nTo test with a prompt:")
        print(f"  ollama run {name} 'Translate: world.afterEvents.itemUse.subscribe(() => {{}})'")
    else:
        print(f"\n❌ Failed to create model: {result.stderr}")
        print("\nCommon issues:")
        print("  - Ensure GGUF file or model files are in the directory")
        print("  - Check that Ollama has sufficient disk space")
        print("  - For GPU deployment, ensure nvidia-container-runtime is configured")


def main():
    parser = argparse.ArgumentParser(
        description="Deploy PortKit GRPO models to Ollama",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python deploy_to_ollama.py --list
  python deploy_to_ollama.py --model grpo6 --model-path /path/to/exported/model
  python deploy_to_ollama.py --model grpo8 --ollama-name portkit-coder-v8
        """,
    )
    parser.add_argument("--list", "-l", action="store_true", help="List available models")
    parser.add_argument(
        "--model",
        "-m",
        choices=list(MODELS.keys()),
        help="Model to deploy (grpo6, grpo7, grpo8, sft1)",
    )
    parser.add_argument("--model-path", "-p", help="Path to exported model directory")
    parser.add_argument("--ollama-name", "-o", help="Custom name for the Ollama model")

    args = parser.parse_args()

    if args.list:
        list_models()
    elif args.model:
        deploy_model(args.model, args.model_path, args.ollama_name)
    else:
        parser.print_help()
        print("\nRun with --list to see available models.")
        sys.exit(1)


if __name__ == "__main__":
    main()
