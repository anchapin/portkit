import asyncio
import logging
from typing import List, Dict, Any
import uuid

from .correction_store import CorrectionStore
from ..training_manager import AITrainingDataItem, train_model_with_feedback

logger = logging.getLogger(__name__)

class FeedbackLearningPipeline:
    """
    Automates the learning process from user feedback and corrections.
    """

    def __init__(self, correction_store: CorrectionStore):
        self.correction_store = correction_store

    async def process_new_feedback(self, db_session):
        """
        Main entry point for periodic feedback processing.
        """
        logger.info("Starting feedback learning cycle...")
        
        # 1. Get approved corrections that haven't been applied yet
        corrections = await self.correction_store.get_corrections(status="approved")
        
        if not corrections:
            logger.info("No new approved corrections to process.")
            return
            
        logger.info(f"Processing {len(corrections)} approved corrections for learning.")
        
        # 2. Convert corrections to training data items
        training_items = self._convert_to_training_items(corrections)
        
        # 3. Trigger RL training loop with these items
        if training_items:
            result = await train_model_with_feedback(training_items)
            logger.info(f"RL training cycle complete: {result}")
            
            # 4. Mark corrections as applied
            for correction in corrections:
                await self.correction_store.mark_applied(uuid.UUID(correction["id"]))
                
        logger.info("Feedback learning cycle complete.")

    def _convert_to_training_items(self, corrections: List[Dict[str, Any]]) -> List[AITrainingDataItem]:
        """Transform database corrections into RL training data."""
        items = []
        for c in corrections:
            # We treat a correction as strong positive reinforcement for the corrected output
            # and negative for the original output
            item = {
                "job_id": c["job_id"],
                "input_file_path": f"corrections/{c['id']}_input.java", # Virtual path
                "output_file_path": f"corrections/{c['id']}_output.json", # Virtual path
                "feedback": {
                    "feedback_type": "correction",
                    "comment": c.get("correction_rationale", ""),
                    "original_output": c["original_output"],
                    "corrected_output": c["corrected_output"],
                    "created_at": c["submitted_at"]
                }
            }
            items.append(item)
        return items

def create_feedback_pipeline(db_session) -> FeedbackLearningPipeline:
    store = CorrectionStore()
    asyncio.create_task(store.initialize(db_session))
    return FeedbackLearningPipeline(store)
