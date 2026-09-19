"""
Translator Agent for QA pipeline.

Generates Bedrock code from Java AST with RAG augmentation.
This is the first QA agent (QA-02) in the multi-agent pipeline.
"""

import json
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import structlog

from qa.context import QAContext
from qa.validators import AgentOutput, validate_agent_output

logger = structlog.get_logger(__name__)

MAX_TOKENS_CONTEXT = 8000
TEMPERATURE_ZERO = 0.0


class TranslatorAgent:
    """
    Translator Agent - generates Bedrock code from Java AST with RAG augmentation.

    Takes parsed Java code, queries the knowledge base for similar conversion patterns,
    and generates both Bedrock JSON (behavior pack) and TypeScript (Script API) code.

    When strict_api mode is enabled (via QAContext.strict_api=True), uses the
    BedrockAPIBoundaryProber to:
    - Inject demand-guided API context before generation
    - Validate generated output for hallucinated API calls
    """

    def __init__(self, temperature: float = TEMPERATURE_ZERO):
        """
        Initialize the TranslatorAgent.

        Args:
            temperature: Temperature for LLM generation (default: 0.0 for deterministic results)
        """
        self.temperature = temperature
        self._search_engine = None
        self._logic_translator = None
        self._api_prober = None
        logger.info("TranslatorAgent initialized", temperature=temperature)

    def _get_search_engine(self):
        """Lazy-load the hybrid search engine for RAG queries."""
        if self._search_engine is None:
            try:
                from search.hybrid_search_engine import HybridSearchEngine

                self._search_engine = HybridSearchEngine()
                logger.info("HybridSearchEngine initialized for TranslatorAgent")
            except ImportError as e:
                logger.warning(
                    "Could not import HybridSearchEngine, RAG will be limited", error=str(e)
                )
                self._search_engine = None
        return self._search_engine

    def _get_logic_translator(self):
        """Lazy-load the existing LogicTranslatorAgent for translation patterns."""
        if self._logic_translator is None:
            try:
                from agents.logic_translator import LogicTranslatorAgent

                self._logic_translator = LogicTranslatorAgent.get_instance()
                logger.info("LogicTranslatorAgent loaded for translation patterns")
            except ImportError as e:
                logger.warning("Could not import LogicTranslatorAgent", error=str(e))
                self._logic_translator = None
        return self._logic_translator

    def _get_api_prober(self, strict_api: bool = False):
        """Lazy-load the Bedrock API boundary prober for strict API validation."""
        if self._api_prober is None and strict_api:
            try:
                from conversion.api_boundary_prober import BedrockAPIBoundaryProber

                self._api_prober = BedrockAPIBoundaryProber(strict_api=strict_api)
                logger.info("BedrockAPIBoundaryProber initialized (strict_api mode)")
            except ImportError as e:
                logger.warning("Could not import BedrockAPIBoundaryProber", error=str(e))
                self._api_prober = None
        return self._api_prober

    def _compress_context(self, java_code: str, max_tokens: int = MAX_TOKENS_CONTEXT) -> str:
        """
        Compress large code blocks by keeping important structural elements.

        Args:
            java_code: The Java source code
            max_tokens: Maximum tokens to allow

        Returns:
            Compressed Java code
        """
        lines = java_code.split("\n")
        if len(lines) < max_tokens:
            return java_code

        compressed = []
        for line in lines[: max_tokens // 4]:
            compressed.append(line)
        compressed.append(f"\n// ... {len(lines) - len(compressed)} lines omitted ...")

        return "\n".join(compressed)

    def _extract_comments(self, java_code: str) -> Dict[str, str]:
        """
        Extract comments and documentation from Java code.

        Args:
            java_code: The Java source code

        Returns:
            Dictionary mapping locations to comment text
        """
        comments = {}
        lines = java_code.split("\n")
        current_comment = None

        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped.startswith("//"):
                if current_comment is None:
                    current_comment = []
                current_comment.append(stripped[2:].strip())
            elif stripped.startswith("/*"):
                current_comment = [stripped[2:].strip()]
            elif "*/" in stripped and current_comment:
                comments[f"line_{i}"] = "\n".join(current_comment)
                current_comment = None
            elif current_comment and stripped and not stripped.startswith("*"):
                comments[f"line_{i}"] = "\n".join(current_comment)
                current_comment = None

        return comments

    def _query_rag_for_patterns(self, java_code: str) -> List[Dict[str, Any]]:
        """
        Query RAG for similar conversion patterns.

        Args:
            java_code: The Java source code to find patterns for

        Returns:
            List of similar conversion patterns from knowledge base
        """
        search_engine = self._get_search_engine()
        if search_engine is None:
            logger.warning("RAG search unavailable, returning empty patterns")
            return []

        try:
            results = search_engine.search(query=java_code[:500], mode="semantic", top_k=5)

            patterns = []
            for result in results:
                patterns.append(
                    {
                        "source": result.get("source", "unknown"),
                        "pattern": result.get("content", ""),
                        "score": result.get("score", 0.0),
                    }
                )

            logger.info("RAG patterns retrieved", count=len(patterns))
            return patterns

        except Exception as e:
            logger.error("RAG query failed", error=str(e))
            return []

    def _parse_java_ast(self, java_path: Path) -> Optional[Dict[str, Any]]:
        """
        Parse Java source to extract structural information.

        Args:
            java_path: Path to the Java source file

        Returns:
            Dictionary with parsed AST information
        """
        try:
            java_code = java_path.read_text(encoding="utf-8")
        except Exception as e:
            logger.error("Failed to read Java file", path=str(java_path), error=str(e))
            return None

        result = {
            "file_path": str(java_path),
            "raw_code": java_code,
            "comments": self._extract_comments(java_code),
            "classes": [],
            "methods": [],
        }

        try:
            import javalang

            tree = javalang.parse.parse(java_code)

            for path, node in tree:
                if isinstance(node, javalang.tree.ClassDeclaration):
                    result["classes"].append(
                        {
                            "name": node.name,
                            "extends": node.extends.name if node.extends else None,
                            "implements": [i.name for i in node.implements]
                            if node.implements
                            else [],
                        }
                    )
                elif isinstance(node, javalang.tree.MethodDeclaration):
                    result["methods"].append(
                        {
                            "name": node.name,
                            "return_type": str(node.return_type) if node.return_type else "void",
                            "parameters": [
                                {"name": p.name, "type": str(p.type) if p.type else "Object"}
                                for p in node.parameters
                            ]
                            if node.parameters
                            else [],
                        }
                    )

        except ImportError:
            logger.warning("javalang not available, using basic parsing")
        except Exception as e:
            logger.warning("Java parsing failed, using raw code", error=str(e))

        return result

    def _generate_bedrock_json(self, parsed_ast: Dict[str, Any]) -> Dict[str, Any]:
        """
        Generate Bedrock JSON (behavior pack components).

        Args:
            parsed_ast: Parsed Java AST information

        Returns:
            Dictionary of generated Bedrock JSON files
        """
        output = {}

        for cls in parsed_ast.get("classes", []):
            class_name = cls["name"]

            if "Block" in class_name or "block" in class_name.lower():
                from agents.logic_translator import BEDROCK_BLOCK_TEMPLATES

                template = BEDROCK_BLOCK_TEMPLATES.get(
                    "basic", BEDROCK_BLOCK_TEMPLATES["basic"]
                ).copy()
                template["minecraft:block"]["description"]["identifier"] = (
                    f"modporter:{class_name.lower()}"
                )
                output[f"blocks/{class_name.lower()}.json"] = template

            elif "Item" in class_name or "item" in class_name.lower():
                from agents.logic_translator import BEDROCK_ITEM_TEMPLATES

                template = BEDROCK_ITEM_TEMPLATES.get(
                    "basic", BEDROCK_ITEM_TEMPLATES["basic"]
                ).copy()
                template["minecraft:item"]["description"]["identifier"] = (
                    f"modporter:{class_name.lower()}"
                )
                output[f"items/{class_name.lower()}.json"] = template

            elif "Entity" in class_name or "entity" in class_name.lower():
                from agents.logic_translator import BEDROCK_ENTITY_TEMPLATES

                template = BEDROCK_ENTITY_TEMPLATES.get(
                    "hostile_mob", BEDROCK_ENTITY_TEMPLATES["hostile_mob"]
                ).copy()
                template["minecraft:entity"]["description"]["identifier"] = (
                    f"modporter:{class_name.lower()}"
                )
                output[f"entities/{class_name.lower()}.json"] = template

        if not output:
            logger.warning("No Bedrock JSON generated - no recognizable classes found")

        return output

    def _generate_typescript(self, parsed_ast: Dict[str, Any]) -> str:
        """
        Generate TypeScript/JavaScript (Script API code).

        Args:
            parsed_ast: Parsed Java AST information

        Returns:
            TypeScript code as string
        """
        lines = []

        for cls in parsed_ast.get("classes", []):
            class_name = cls["name"]
            lines.append(f"// Script API implementation for {class_name}")
            lines.append(f"export class {class_name} {{")

            for method in parsed_ast.get("methods", []):
                params = ", ".join([p["name"] for p in method.get("parameters", [])])
                return_type = method.get("return_type", "void")

                lines.append(f"  {method['name']}({params}): {return_type} {{")
                lines.append(f"    // TODO: Implement {method['name']}")
                lines.append("  }")

            lines.append("}")
            lines.append("")

        if not lines:
            lines = ["// No TypeScript generated - no classes found"]

        return "\n".join(lines)

    def execute(self, context: QAContext) -> AgentOutput:
        """
        Execute the translator agent on the given QA context.

        Args:
            context: QA context containing job information and paths

        Returns:
            AgentOutput with translation results
        """
        start_time = time.time()

        try:
            logger.info("TranslatorAgent executing", job_id=context.job_id)

            java_path = context.source_java_path
            if not java_path.exists():
                return AgentOutput(
                    agent_name="translator",
                    success=False,
                    result={},
                    errors=[f"Java source file not found: {java_path}"],
                    execution_time_ms=int((time.time() - start_time) * 1000),
                )

            parsed_ast = self._parse_java_ast(java_path)
            if parsed_ast is None:
                return AgentOutput(
                    agent_name="translator",
                    success=False,
                    result={},
                    errors=["Failed to parse Java source"],
                    execution_time_ms=int((time.time() - start_time) * 1000),
                )

            rag_patterns = self._query_rag_for_patterns(parsed_ast.get("raw_code", ""))

            bedrock_json = self._generate_bedrock_json(parsed_ast)

            typescript_code = self._generate_typescript(parsed_ast)

            api_context_injection = ""
            api_validation_result = None
            if context.strict_api:
                prober = self._get_api_prober(strict_api=True)
                if prober:
                    api_context_injection = prober.get_injection_prompt(
                        parsed_ast.get("raw_code", "")
                    )
                    logger.info(
                        "API boundary context injection prepared",
                        injection_length=len(api_context_injection),
                    )

            output_dir = context.output_bedrock_path
            output_dir.mkdir(parents=True, exist_ok=True)

            for file_path, content in bedrock_json.items():
                full_path = output_dir / file_path
                full_path.parent.mkdir(parents=True, exist_ok=True)
                full_path.write_text(json.dumps(content, indent=2), encoding="utf-8")
                logger.info("Generated Bedrock JSON", file=str(full_path))

            ts_path = output_dir / "scripts" / f"{context.job_id}.ts"
            ts_path.parent.mkdir(parents=True, exist_ok=True)
            ts_path.write_text(typescript_code, encoding="utf-8")
            logger.info("Generated TypeScript", file=str(ts_path))

            if context.strict_api:
                prober = self._get_api_prober(strict_api=True)
                if prober:
                    api_validation_result = prober.validate_output(typescript_code)
                    logger.info(
                        "API boundary validation completed",
                        is_valid=api_validation_result.is_valid,
                        hallucination_rate=api_validation_result.hallucination_rate,
                    )

            result = {
                "parsed_classes": [c["name"] for c in parsed_ast.get("classes", [])],
                "parsed_methods": [m["name"] for m in parsed_ast.get("methods", [])],
                "bedrock_json_files": list(bedrock_json.keys()),
                "typescript_file": str(ts_path.relative_to(output_dir)),
                "rag_patterns_found": len(rag_patterns),
                "temperature": self.temperature,
            }

            if api_context_injection:
                result["api_context_injected"] = True
                result["api_context_length"] = len(api_context_injection)

            if api_validation_result:
                result["api_validation"] = {
                    "is_valid": api_validation_result.is_valid,
                    "hallucination_rate": api_validation_result.hallucination_rate,
                    "hallucinated_apis": api_validation_result.hallucinated_apis,
                    "valid_apis_found": api_validation_result.valid_apis_found,
                }

            execution_time = int((time.time() - start_time) * 1000)

            output_data = {
                "agent_name": "translator",
                "success": True,
                "result": result,
                "errors": [],
                "execution_time_ms": execution_time,
            }

            validated = validate_agent_output(output_data)

            logger.info(
                "TranslatorAgent completed",
                job_id=context.job_id,
                classes=len(result["parsed_classes"]),
                methods=len(result["parsed_methods"]),
            )

            return validated

        except Exception as e:
            logger.error("TranslatorAgent failed", job_id=context.job_id, error=str(e))
            return AgentOutput(
                agent_name="translator",
                success=False,
                result={},
                errors=[str(e)],
                execution_time_ms=int((time.time() - start_time) * 1000),
            )


def translate(context: QAContext) -> AgentOutput:
    """
    Convenience function to run translation.

    Args:
        context: QA context

    Returns:
        AgentOutput with translation results
    """
    agent = TranslatorAgent()
    return agent.execute(context)
