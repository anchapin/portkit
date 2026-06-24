"""
AST-based and bytecode-based feature extraction for Java mods
"""

from utils.logging_config import get_agent_logger

logger = get_agent_logger("java_analyzer.feature_extractor")

try:
    import tree_sitter_java as ts_java
    from tree_sitter import Language, Parser  # noqa: F401  (re-exported)

    TREE_SITTER_AVAILABLE = True
except ImportError:
    TREE_SITTER_AVAILABLE = False
    ts_java = None
    Parser = None

try:
    import javassist

    JAVASSIST_AVAILABLE = True
except ImportError:
    javassist = None
    JAVASSIST_AVAILABLE = False


FEATURE_ANALYSIS_FILE_LIMIT = 10
METADATA_AST_FILE_LIMIT = 5
DEPENDENCY_ANALYSIS_FILE_LIMIT = 10
GOAL_SELECTOR_PATTERNS = (
    "goalSelector.addGoal",
    "goalSelector.add",
    "targetSelector.addGoal",
    "targetSelector.add",
)
