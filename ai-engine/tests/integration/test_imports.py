"""Test basic imports to verify package structure."""

import os


def test_can_import_main():
    """Test that main.py exists and has correct structure without actually importing it.

    This test verifies the package structure exists without requiring heavy dependencies
    like the deleted legacy orchestration that may not be available in legacy environments.
    """
    # Check main.py exists and is readable
    assert os.path.exists("main.py"), "main.py should exist in current directory"
    assert os.path.isfile("main.py"), "main.py should be a file"

    # Read and verify main.py has expected imports and structure
    with open("main.py", "r") as f:
        main_content = f.read()

    # Verify key imports are present
    assert "from fastapi import" in main_content and "FastAPI" in main_content, "main.py should import FastAPI"
    # The legacy `crew.conversion_crew` import was removed in #1201; the LangGraph
    # pipeline is the only conversion path.
    assert "from orchestration.langgraph_pipeline import" in main_content or            "ConversionPipeline" in main_content, (
        "main.py should reference the LangGraph ConversionPipeline"
    )
    assert "ConversionStatusEnum" in main_content, "main.py should define ConversionStatusEnum"
    assert "app = FastAPI" in main_content, "main.py should initialize FastAPI app"


def test_can_import_agents():
    """Test that agent modules exist and have correct structure.

    After Issue #1141 and related refactors:
    - java_analyzer is now a package (agents/java_analyzer/)
    - logic_translator is now a package (agents/logic_translator/)
    - texture_converter is now a package (agents/texture_converter/)
    - model_converter is now a package (agents/model_converter/)
    - bedrock_builder is now a package (agents/bedrock_builder/) per Issue #1742
    """
    agent_items = [
        # Packages (directories with __init__.py)
        ("agents/java_analyzer", "agents/java_analyzer/__init__.py"),
        ("agents/logic_translator", "agents/logic_translator/__init__.py"),
        ("agents/texture_converter", "agents/texture_converter/__init__.py"),
        ("agents/model_converter", "agents/model_converter/__init__.py"),
        ("agents/bedrock_builder", "agents/bedrock_builder/__init__.py"),
        # Modules (.py files)
        ("agents/asset_converter.py", None),
        ("agents/packaging_agent.py", None),
        ("agents/qa_validator.py", None),
    ]

    for item_path, init_file in agent_items:
        is_package = init_file is not None
        if is_package:
            assert os.path.isdir(item_path), f"{item_path} should be a directory (package)"
            assert os.path.isfile(init_file), f"{init_file} should be a file"
            # Verify package has expected structure
            with open(init_file, "r") as f:
                content = f.read()
            assert "class" in content or "__all__" in content, (
                f"{init_file} should define or re-export a class"
            )
        else:
            assert os.path.isfile(item_path), f"{item_path} should be a file"
            # Read and verify agent has expected structure
            with open(item_path, "r") as f:
                content = f.read()
            # Verify agent has basic structure - allow deprecated wrappers that re-export via __all__
            assert "class" in content or "__all__" in content, (
                f"{item_path} should define a class or re-export via __all__"
            )


def test_python_path():
    """Test Python path setup."""
    import os

    # Check if main.py exists
    assert os.path.exists("main.py"), "main.py should exist in current directory"
    assert os.path.exists("agents"), "agents directory should exist"
    assert os.path.exists("agents/__init__.py"), "agents/__init__.py should exist"

    # Verify agent packages have __init__.py files
    for pkg_init in [
        "agents/java_analyzer/__init__.py",
        "agents/logic_translator/__init__.py",
        "agents/texture_converter/__init__.py",
        "agents/model_converter/__init__.py",
    ]:
        assert os.path.exists(pkg_init), f"{pkg_init} should exist for package"
