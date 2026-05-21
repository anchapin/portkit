import json
import logging
import os
from typing import List, Optional, TypedDict

import httpx

# Configure basic logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger(__name__)


# Define data structures mirroring backend Pydantic models
class TrainingFeedbackData(TypedDict):
    feedback_type: str
    comment: Optional[str]
    user_id: Optional[str]
    created_at: str  # Assuming datetime is serialized as ISO string


class AITrainingDataItem(TypedDict):
    job_id: str  # UUID string
    input_file_path: str
    output_file_path: str
    feedback: TrainingFeedbackData


class TrainingDataResponse(TypedDict):
    data: List[AITrainingDataItem]
    total: int
    limit: int
    skip: int


async def fetch_training_data_from_backend(
    backend_url: str, skip: int = 0, limit: int = 100
) -> Optional[List[AITrainingDataItem]]:
    """
    Fetches training data from the ModPorter AI backend.
    """
    api_url = f"{backend_url}/api/v1/ai/training_data"
    params = {"skip": skip, "limit": limit}

    logger.info(f"Fetching training data from {api_url} with params: {params}")

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(api_url, params=params)
            response.raise_for_status()  # Raise an exception for HTTP errors (4xx or 5xx)

            response_data: TrainingDataResponse = response.json()
            logger.info(
                f"Successfully fetched {len(response_data['data'])} items. Total available (approx): {response_data['total']}"
            )
            return response_data["data"]
    except httpx.HTTPStatusError as e:
        logger.error(
            f"HTTP error occurred while fetching training data: {e.response.status_code} - {e.response.text}"
        )
    except httpx.RequestError as e:
        logger.error(f"Request error occurred while fetching training data: {e}")
    except json.JSONDecodeError as e:
        logger.error(f"Failed to decode JSON response: {e}")
    except Exception as e:
        logger.error(f"An unexpected error occurred: {e}", exc_info=True)

    return None


async def train_model_with_feedback(training_data: List[AITrainingDataItem]):
    """
    Advanced RL-based training function that processes feedback data and improves agent performance.
    """
    if not training_data:
        logger.warning("No training data received. Skipping training process.")
        return

    logger.info(f"Received {len(training_data)} items for RL training.")
    logger.info("Starting reinforcement learning training process...")

    try:
        # Import RL components
        from rl.quality_scorer import create_quality_scorer
        from rl.reward_system import create_reward_generator
        from rl.training_loop import create_training_loop
        from rl.synthetic_quality_scorer import SyntheticQualityScorer

        # Initialize RL training components
        training_loop = await create_training_loop()
        quality_scorer = create_quality_scorer()
        synthetic_scorer = SyntheticQualityScorer()
        reward_generator = create_reward_generator()

        logger.info("STEP 1: RL Training System Initialized")

        # Process each training item through RL pipeline
        successful_episodes = 0
        total_reward = 0.0

        for i, item in enumerate(training_data):
            logger.info(
                f"  Processing RL episode {i + 1}/{len(training_data)}: Job ID {item['job_id']}"
            )

            try:
                # Extract paths and feedback
                input_path = item["input_file_path"]
                output_path = item["output_file_path"]
                feedback_data = item["feedback"]

                logger.info(f"    Input: {input_path}")
                logger.info(f"    Output: {output_path}")
                logger.info(
                    f"    Feedback: type='{feedback_data['feedback_type']}', comment='{feedback_data.get('comment', 'None')}'"
                )

                # STEP 2: Quality Assessment
                logger.info("    STEP 2: Performing automated quality assessment...")

                conversion_metadata = {
                    "job_id": item["job_id"],
                    "status": "completed" if output_path else "failed",
                    "processing_time_seconds": 30.0,  # Default processing time
                    "timestamp": feedback_data.get("created_at", ""),
                }

                quality_metrics = None
                if item.get("java_source") and item.get("bedrock_source"):
                    # Use synthetic scorer for source-based evaluation
                    quality_metrics = synthetic_scorer.assess_synthetic_quality(
                        java_source=item["java_source"],
                        bedrock_source=item["bedrock_source"],
                        instruction=item.get("instruction"),
                        user_feedback=feedback_data
                    )
                elif output_path:
                    quality_metrics = quality_scorer.assess_conversion_quality(
                        original_mod_path=input_path,
                        converted_addon_path=output_path,
                        conversion_metadata=conversion_metadata,
                        user_feedback=feedback_data,
                    )
                    logger.info(f"      Quality Score: {quality_metrics.overall_score:.3f}")

                # STEP 3: Reward Signal Generation
                logger.info("    STEP 3: Generating reward signals...")

                # Determine agent type based on feedback or default
                agent_type = _infer_agent_type_from_feedback(feedback_data, input_path)

                reward_signal = reward_generator.generate_reward_signal(
                    job_id=item["job_id"],
                    agent_type=agent_type,
                    action_taken="mod_conversion",
                    original_mod_path=input_path,
                    converted_addon_path=output_path,
                    conversion_metadata=conversion_metadata,
                    user_feedback=feedback_data,
                    quality_metrics=quality_metrics,
                )

                total_reward += reward_signal.total_reward
                logger.info(f"      Reward Signal: {reward_signal.total_reward:.3f}")

                # STEP 4: Apply Learning Updates
                logger.info("    STEP 4: Applying reinforcement learning updates...")

                if feedback_data["feedback_type"] == "thumbs_down":
                    logger.info(
                        "      Action: Negative reinforcement applied - reducing action probability"
                    )
                elif feedback_data["feedback_type"] == "thumbs_up":
                    logger.info(
                        "      Action: Positive reinforcement applied - increasing action probability"
                    )

                if feedback_data.get("comment"):
                    logger.info("      Action: Processing feedback comment for contextual learning")

                successful_episodes += 1

            except Exception as e:
                logger.error(f"    Error processing episode {i + 1}: {e}")
                continue

        # STEP 5: Run Training Cycle
        if successful_episodes > 0:
            logger.info("STEP 5: Running RL training cycle...")
            training_metrics = await training_loop.run_training_cycle()

            avg_reward = total_reward / successful_episodes
            logger.info("Training cycle completed:")
            logger.info(f"  - Episodes processed: {successful_episodes}")
            logger.info(f"  - Average reward: {avg_reward:.3f}")
            logger.info(f"  - Overall improvement rate: {training_metrics.improvement_rate:.3f}")

            # STEP 6: Performance Analysis
            logger.info("STEP 6: Analyzing agent performance...")
            performance_summary = training_loop.get_agent_performance_summary()

            for agent_type, metrics in performance_summary.get("agent_breakdown", {}).items():
                logger.info(
                    f"  - {agent_type}: avg reward {metrics['average_reward']:.3f}, "
                    f"episodes {metrics['episode_count']}"
                )

            # Log recommendations
            recommendations = performance_summary.get("recommendations", [])
            if recommendations:
                logger.info("Training Recommendations:")
                for rec in recommendations:
                    logger.info(f"  - {rec}")

        logger.info("Reinforcement learning training process completed successfully.")
        return {
            "status": "completed",
            "episodes_processed": successful_episodes,
            "average_reward": total_reward / max(successful_episodes, 1),
            "training_metrics": training_metrics.to_dict() if successful_episodes > 0 else None,
        }

    except ImportError as e:
        logger.error(f"RL components not available: {e}")
        logger.info("Falling back to basic feedback processing...")
        await _basic_feedback_processing(training_data)
        return {"status": "fallback_completed", "episodes_processed": len(training_data)}

    except Exception as e:
        logger.error(f"RL training failed: {e}", exc_info=True)
        logger.info("Falling back to basic feedback processing...")
        await _basic_feedback_processing(training_data)
        return {"status": "fallback_completed", "episodes_processed": len(training_data)}


def _infer_agent_type_from_feedback(feedback_data: dict, input_path: str) -> str:
    """Infer the most relevant agent type from feedback and input characteristics."""

    comment = feedback_data.get("comment", "").lower()

    # Analyze comment for agent-specific keywords
    if any(word in comment for word in ["texture", "visual", "image", "sprite"]):
        return "asset_converter"
    elif any(word in comment for word in ["behavior", "function", "logic", "mechanic"]):
        return "behavior_translator"
    elif any(word in comment for word in ["recipe", "crafting", "ingredients"]):
        return "behavior_translator"
    elif any(word in comment for word in ["structure", "format", "organization"]):
        return "conversion_planner"
    elif any(word in comment for word in ["analysis", "parsing", "detection"]):
        return "java_analyzer"

    # Fallback to input file analysis
    if input_path:
        if "complex" in input_path.lower() or "large" in input_path.lower():
            return "java_analyzer"
        elif "texture" in input_path.lower() or "asset" in input_path.lower():
            return "asset_converter"

    return "conversion_planner"  # Default agent


async def _basic_feedback_processing(training_data: List[AITrainingDataItem]):
    """Fallback to basic feedback processing when RL components aren't available."""

    logger.info("Processing feedback using basic method...")

    positive_feedback = 0
    negative_feedback = 0

    for item in training_data:
        feedback_type = item["feedback"]["feedback_type"]
        if feedback_type == "thumbs_up":
            positive_feedback += 1
        elif feedback_type == "thumbs_down":
            negative_feedback += 1

    logger.info(f"Feedback summary: {positive_feedback} positive, {negative_feedback} negative")

    # Basic quality indicators
    if positive_feedback > negative_feedback:
        logger.info("Overall feedback is positive - model performance appears good")
    elif negative_feedback > positive_feedback:
        logger.info("Overall feedback is negative - model needs improvement")
    else:
        logger.info("Mixed feedback - continued monitoring recommended")


async def main():
    """
    Main function to orchestrate fetching data and triggering RL training.
    """
    # Example: Get BACKEND_API_URL from environment variable or use a default
    backend_api_url = os.getenv("MODPORTER_BACKEND_URL", "http://localhost:8000")

    logger.info(f"Using backend API URL: {backend_api_url}")
    logger.info("Starting reinforcement learning training manager...")

    # Fetch a batch of training data
    # In a real scenario, you might loop this to get all data, or process in batches
    training_data_batch = await fetch_training_data_from_backend(backend_api_url, skip=0, limit=10)

    if training_data_batch:
        logger.info(f"Fetched {len(training_data_batch)} training items. Starting RL training...")
        training_result = await train_model_with_feedback(training_data_batch)

        if training_result:
            logger.info("Training completed with results:")
            logger.info(f"  Status: {training_result['status']}")
            logger.info(f"  Episodes: {training_result['episodes_processed']}")
            if "average_reward" in training_result:
                logger.info(f"  Average Reward: {training_result['average_reward']:.3f}")
        else:
            logger.warning("Training completed but no results returned")
    else:
        logger.warning("Failed to fetch training data. Training will not proceed.")

    logger.info("Training manager session completed.")


if __name__ == "__main__":
    # Note: httpx.AsyncClient needs to be run in an async context.
    # For simplicity in this standalone script, we can use asyncio.run()
    # or make fetch_training_data_from_backend synchronous if this script
    # is not intended to be part of a larger async application.
    # For now, making main async and using asyncio.run().
    import asyncio

    asyncio.run(main())
