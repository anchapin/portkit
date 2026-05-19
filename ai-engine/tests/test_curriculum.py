#!/usr/bin/env python3
"""
Tests for PortKit Curriculum Learning
======================================
Tests for Issue #1585: Implement curriculum learning for GRPO training

Test Naming: test_<feature>_<scenario>_<expected>
Test Markers: @pytest.mark.unit
"""

import sys
from pathlib import Path

# Ensure ai-engine is in path for imports
ai_engine_root = Path(__file__).parent.parent
if str(ai_engine_root) not in sys.path:
    sys.path.insert(0, str(ai_engine_root))

from mmsd.tinker.curriculum import (
    Difficulty,
    CurriculumConfig,
    TrainingExample,
    count_java_entities,
    count_event_patterns,
    measure_api_depth,
    count_output_files,
    classify_difficulty,
    compute_example_metrics,
    load_training_examples,
    get_curriculum_weights,
    sample_curriculum_batch,
)


class TestDifficultyClassification:
    """Tests for Issue #1604: Define difficulty classification criteria."""
    
    def test_java_entity_counting(self):
        """Count Java entities in user message."""
        text = """
        public class MyBlock extends Block {
            private final Item item;
            private Entity entity;
        }
        """
        count = count_java_entities(text)
        assert count >= 3  # Block, Item, Entity
    
    def test_event_pattern_counting(self):
        """Count event patterns in code."""
        text = """
        @SubscribeEvent
        public void onPlayerInteract(PlayerInteractEvent event) {
            events.tick(function(e) {});
        }
        """
        count = count_event_patterns(text)
        assert count >= 2  # @SubscribeEvent, PlayerInteractEvent
    
    def test_api_depth_measurement(self):
        """Measure API chain depth."""
        # Shallow API: world.sendMessage = 1 dot
        assert measure_api_depth("world.sendMessage") == 1
        # Medium API: world.afterEvents.tick.subscribe = 3 dots
        assert measure_api_depth("world.afterEvents.tick.subscribe") == 3
        # Deep API: world.afterEvents.playerInteractWithBlock.subscribe = 3 dots (not 4)
        assert measure_api_depth("world.afterEvents.playerInteractWithBlock.subscribe") == 3
    
    def test_output_file_counting(self):
        """Count output files/sections."""
        manifest = '"format_version": 2, "header": {}, "modules": []'
        script = "import { world } from '@minecraft/server';"
        assert count_output_files(manifest) == 1  # manifest only
        assert count_output_files(script) == 1   # script only
        assert count_output_files(manifest + script) == 2  # both
    
    def test_classify_difficulty_easy(self):
        """Classify easy examples."""
        diff, score = classify_difficulty(
            java_entity_count=2,
            event_pattern_count=1,
            api_chain_depth=1,
            output_file_count=1,
        )
        assert diff == Difficulty.EASY
        assert score < 0.25
    
    def test_classify_difficulty_medium(self):
        """Classify medium examples."""
        diff, score = classify_difficulty(
            java_entity_count=3,
            event_pattern_count=2,
            api_chain_depth=1,
            output_file_count=2,
        )
        assert diff == Difficulty.MEDIUM
        assert 0.25 <= score < 0.50
    
    def test_classify_difficulty_hard(self):
        """Classify hard examples."""
        diff, score = classify_difficulty(
            java_entity_count=10,
            event_pattern_count=10,
            api_chain_depth=4,
            output_file_count=4,
        )
        assert diff == Difficulty.HARD
        assert score >= 0.50


class TestCurriculumConfig:
    """Tests for CurriculumConfig."""
    
    def test_default_config(self):
        """Test default curriculum configuration."""
        config = CurriculumConfig()
        
        assert config.phase1_end == 0.30
        assert config.phase2_end == 0.60
        assert config.phase3_end == 1.00
        
        # Phase 1: Easy only
        assert config.phase1_weights[Difficulty.EASY] == 1.0
        assert config.phase1_weights[Difficulty.MEDIUM] == 0.0
        
        # Phase 3: Hard weighted higher
        assert config.phase3_weights[Difficulty.HARD] > config.phase3_weights[Difficulty.EASY]
    
    def test_custom_weights(self):
        """Test custom phase weights."""
        config = CurriculumConfig(
            phase3_weights={Difficulty.EASY: 0.1, Difficulty.MEDIUM: 0.2, Difficulty.HARD: 0.7}
        )
        assert config.phase3_weights[Difficulty.HARD] == 0.7


class TestCurriculumWeights:
    """Tests for Issue #1610: Implement curriculum phases."""
    
    def test_phase1_weights_early(self):
        """Phase 1 (0-30%): Easy only."""
        config = CurriculumConfig()
        weights = get_curriculum_weights(step=0, max_steps=100, config=config)
        
        assert weights[Difficulty.EASY] == 1.0
        assert weights[Difficulty.MEDIUM] == 0.0
        assert weights[Difficulty.HARD] == 0.0
    
    def test_phase2_weights_mid(self):
        """Phase 2 (30-60%): Easy + Medium."""
        config = CurriculumConfig()
        weights = get_curriculum_weights(step=50, max_steps=100, config=config)
        
        # Should be interpolated between phase1 and phase2 weights
        assert weights[Difficulty.EASY] > 0
        assert weights[Difficulty.MEDIUM] > 0
        assert weights[Difficulty.HARD] == 0.0
    
    def test_phase3_weights_late(self):
        """Phase 3 (60-100%): All difficulties, hard weighted higher."""
        config = CurriculumConfig()
        weights = get_curriculum_weights(step=99, max_steps=100, config=config)
        
        # All difficulties active
        assert weights[Difficulty.EASY] > 0
        assert weights[Difficulty.MEDIUM] > 0
        assert weights[Difficulty.HARD] > 0
        
        # Hard weighted higher than easy at end of training
        assert weights[Difficulty.HARD] > weights[Difficulty.EASY]
    
    def test_weight_progression(self):
        """Weight harder examples higher as training progresses (Issue #1616)."""
        config = CurriculumConfig()
        
        # Early: easy dominant
        early_weights = get_curriculum_weights(step=10, max_steps=100, config=config)
        easy_early = early_weights[Difficulty.EASY]
        hard_early = early_weights[Difficulty.HARD]
        
        # Late: hard dominant
        late_weights = get_curriculum_weights(step=90, max_steps=100, config=config)
        easy_late = late_weights[Difficulty.EASY]
        hard_late = late_weights[Difficulty.HARD]
        
        # Hard weight should increase significantly
        assert hard_late > hard_early
        # Easy weight should decrease
        assert easy_late < easy_early


class TestCurriculumSampling:
    """Tests for curriculum batch sampling."""
    
    def test_sample_batch_size(self):
        """Sample returns correct batch size."""
        examples = [
            TrainingExample(idx=0, messages=[], difficulty=Difficulty.EASY, difficulty_score=0.1,
                          java_entity_count=1, event_pattern_count=1, api_chain_depth=1, output_file_count=1),
            TrainingExample(idx=1, messages=[], difficulty=Difficulty.EASY, difficulty_score=0.1,
                          java_entity_count=1, event_pattern_count=1, api_chain_depth=1, output_file_count=1),
            TrainingExample(idx=2, messages=[], difficulty=Difficulty.MEDIUM, difficulty_score=0.3,
                          java_entity_count=2, event_pattern_count=2, api_chain_depth=2, output_file_count=2),
        ]
        
        batch = sample_curriculum_batch(examples, step=50, max_steps=100, batch_size=2, seed=42)
        
        assert len(batch) == 2
        assert all(i in [0, 1, 2] for i in batch)
    
    def test_sample_reproducible(self):
        """Same seed gives same sample."""
        examples = [
            TrainingExample(idx=i, messages=[], difficulty=Difficulty.EASY, difficulty_score=0.1,
                          java_entity_count=1, event_pattern_count=1, api_chain_depth=1, output_file_count=1)
            for i in range(10)
        ]
        
        import random
        random.seed(42)
        batch1 = sample_curriculum_batch(examples, step=50, max_steps=100, batch_size=5, seed=42)
        random.seed(42)
        batch2 = sample_curriculum_batch(examples, step=50, max_steps=100, batch_size=5, seed=42)
        
        assert batch1 == batch2


class TestDataLoading:
    """Tests for Issue #1609: Classify existing 1260 training examples."""
    
    def test_load_training_examples(self, tmp_path):
        """Test loading and classifying training examples."""
        # Create temp training data - use proper JSON format with actual newlines
        test_data = tmp_path / "test_train.jsonl"
        test_data.write_text(
            '{"messages":[{"role":"user","content":"class MyBlock extends Block {}"},{"role":"assistant","content":"format_version: 2"}]}\n'
        )
        
        examples = load_training_examples(str(test_data))
        
        assert len(examples) == 1
        assert examples[0].difficulty in Difficulty
        assert examples[0].java_entity_count >= 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])