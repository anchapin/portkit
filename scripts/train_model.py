import asyncio
import json
import logging
import os
import sys
from typing import List

# Add ai-engine to path
sys.path.append(os.path.join(os.getcwd(), "ai-engine"))

from training_manager import fetch_training_data_from_backend, train_model_with_feedback

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def load_mmsd_data(file_path: str, limit: int = 10) -> List[dict]:
    """Load and format data from mmsd synthesis pairs."""
    data = []
    if not os.path.exists(file_path):
        logger.warning(f"MMSD file not found: {file_path}")
        return data

    try:
        with open(file_path, "r") as f:
            for i, line in enumerate(f):
                if i >= limit:
                    break
                item = json.loads(line)
                data.append({
                    "job_id": f"mmsd-{i}",
                    "input_file_path": "synthetic/java",
                    "output_file_path": "synthetic/bedrock",
                    "java_source": item.get("java_source", ""),
                    "bedrock_source": item.get("bedrock_source", ""),
                    "instruction": item.get("instruction", ""),
                    "feedback": {
                        "feedback_type": "thumbs_up",
                        "comment": "Synthetic high-quality pair",
                        "created_at": "2026-05-19T00:00:00Z"
                    }
                })
        logger.info(f"Loaded {len(data)} items from {file_path}")
    except Exception as e:
        logger.error(f"Error loading MMSD data: {e}")
    
    return data

async def run_training():
    backend_url = os.getenv("PORTKIT_BACKEND_URL", "http://localhost:8000")
    mmsd_path = "ai-engine/mmsd/synthesis_pairs.jsonl"
    
    # Try to load MMSD data first as requested
    training_data = await load_mmsd_data(mmsd_path)

    if not training_data:
        logger.info(f"Connecting to backend at {backend_url}")
        # Fetch training data
        training_data = await fetch_training_data_from_backend(backend_url)

    if not training_data:
        logger.warning("No training data found. Generating small demo sample...")
        # Synthetic data for testing the pipeline
        training_data = [
            {
                "job_id": "demo-job-1",
                "input_file_path": "demo/java/Sword.java",
                "output_file_path": "demo/bedrock/sword.json",
                "feedback": {
                    "feedback_type": "thumbs_up",
                    "comment": "Perfect conversion of NBT tags.",
                    "created_at": "2026-05-19T00:00:00Z"
                }
            }
        ]

    # Run RL training loop
    logger.info(f"Starting RL training loop with {len(training_data)} items...")
    result = await train_model_with_feedback(training_data)
    
    logger.info(f"Training completed: {result}")

if __name__ == "__main__":
    asyncio.run(run_training())
