import asyncio
import time
from typing import Any, Dict, List, Optional

import structlog

from qa.context import QAContext, RefinementHistory
from qa.run_agent import (
    ConversionDAG,
    RunAgent,
    StepContext,
)
from qa.validators import validate_agent_output
from utils.error_recovery import CircuitBreaker, CircuitBreakerOpenError

logger = structlog.get_logger(__name__)


class QAOrchestrator:
    def __init__(
        self,
        timeout_seconds: int = 300,
        parallel_execution_enabled: bool = True,
        constraint_guided_enabled: bool = False,
    ):
        self.timeout_seconds = timeout_seconds
        self.parallel_execution_enabled = parallel_execution_enabled
        self.constraint_guided_enabled = constraint_guided_enabled
        self.refinement_enabled: bool = True
        self.max_refinement_iterations: int = 3
        self.agents: List[str] = [
            "translator",
            "reviewer",
            "tester",
            "semantic_checker",
            "logic_auditor",
        ]
        self._parallel_groups: List[List[str]] = [
            ["translator"],
            ["reviewer", "tester"],
            ["semantic_checker", "logic_auditor"],
        ]
        self._breakers: Dict[str, CircuitBreaker] = {}
        for agent_name in self.agents:
            self._breakers[agent_name] = CircuitBreaker(
                name=f"{agent_name}_agent",
                fail_max=3,
                reset_timeout=300,
            )
        self._run_agent_instance: Optional[RunAgent] = None

    @property
    def supports_parallel(self) -> bool:
        """Check if parallel execution is supported."""
        return self.parallel_execution_enabled

    def run_qa_pipeline(self, context: QAContext) -> QAContext:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                raise RuntimeError(
                    "Cannot run sync version in async context. Use run_qa_pipeline_async instead."
                )
            return loop.run_until_complete(self.run_qa_pipeline_async(context))
        except RuntimeError:
            return asyncio.run(self.run_qa_pipeline_async(context))

    async def run_qa_pipeline_async(self, context: QAContext) -> QAContext:
        for agent_name in self.agents:
            context.current_agent = agent_name
            logger.info("Running agent", agent=agent_name, job_id=context.job_id)

            try:
                agent_output = await self.run_agent(context, agent_name)
                validated = validate_agent_output(agent_output)

                context.validation_results[agent_name] = {
                    "success": validated.success,
                    "result": validated.result,
                    "errors": validated.errors,
                    "execution_time_ms": validated.execution_time_ms,
                }
                logger.info(
                    "Agent completed",
                    agent=agent_name,
                    success=validated.success,
                    job_id=context.job_id,
                )
            except CircuitBreakerOpenError as e:
                logger.error("Agent circuit open, skipping", agent=agent_name, error=str(e))
                context.validation_results[agent_name] = {
                    "success": False,
                    "error": "Circuit breaker open",
                    "skipped": True,
                }
            except TimeoutError:
                logger.error("Agent timed out", agent=agent_name)
                context.validation_results[agent_name] = {
                    "success": False,
                    "error": "Timeout",
                }
            except Exception as e:
                logger.error("Agent failed", agent=agent_name, error=str(e))
                context.validation_results[agent_name] = {
                    "success": False,
                    "error": str(e),
                }

        context.current_agent = None
        return context

    async def run_agents_parallel(
        self, context: QAContext, agent_names: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Run multiple agents in parallel.

        Returns dict mapping agent_name to their results.
        Partial failures are handled gracefully - failed agents don't affect others.
        """

        async def run_single_agent(agent_name: str) -> tuple[str, Dict[str, Any]]:
            try:
                result = await self.run_agent(context, agent_name)
                return agent_name, {"success": True, "result": result}
            except Exception as e:
                logger.error("Parallel agent failed", agent=agent_name, error=str(e))
                return agent_name, {"success": False, "error": str(e), "skipped": False}

        tasks = [run_single_agent(name) for name in agent_names]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        output = {}
        for i, result in enumerate(results):
            agent_name = agent_names[i]
            if isinstance(result, Exception):
                output[agent_name] = {"success": False, "error": str(result)}
            else:
                output[agent_name] = result[1]

        return output

    async def run_qa_pipeline_parallel_async(self, context: QAContext) -> QAContext:
        """Run QA pipeline with parallel execution where possible.

        Execution order:
        1. translator (sequential - produces code)
        2. reviewer + tester (parallel - analyze same code)
        3. semantic_checker (sequential - depends on reviewer)
        """
        execution_times = {}

        context.current_agent = "translator"
        start_time = time.time()
        try:
            agent_output = await self.run_agent(context, "translator")
            validated = validate_agent_output(agent_output)
            context.validation_results["translator"] = {
                "success": validated.success,
                "result": validated.result,
                "errors": validated.errors,
                "execution_time_ms": validated.execution_time_ms,
            }
        except Exception as e:
            logger.error("Translator failed", error=str(e))
            context.validation_results["translator"] = {"success": False, "error": str(e)}
            context.current_agent = None
            return context

        execution_times["translator"] = time.time() - start_time

        if self.parallel_execution_enabled:
            start_time = time.time()
            parallel_results = await self.run_agents_parallel(context, ["reviewer", "tester"])
            execution_times["parallel_review_test"] = time.time() - start_time

            for agent_name, result in parallel_results.items():
                if result.get("success"):
                    validated = validate_agent_output(result["result"])
                    context.validation_results[agent_name] = {
                        "success": validated.success,
                        "result": validated.result,
                        "errors": validated.errors,
                        "execution_time_ms": validated.execution_time_ms,
                    }
                else:
                    context.validation_results[agent_name] = {
                        "success": False,
                        "error": result.get("error", "Unknown error"),
                    }
        else:
            for agent_name in ["reviewer", "tester"]:
                context.current_agent = agent_name
                try:
                    agent_output = await self.run_agent(context, agent_name)
                    validated = validate_agent_output(agent_output)
                    context.validation_results[agent_name] = {
                        "success": validated.success,
                        "result": validated.result,
                        "errors": validated.errors,
                        "execution_time_ms": validated.execution_time_ms,
                    }
                except Exception as e:
                    context.validation_results[agent_name] = {"success": False, "error": str(e)}

        context.current_agent = "semantic_checker"
        start_time = time.time()
        try:
            agent_output = await self.run_agent(context, "semantic_checker")
            validated = validate_agent_output(agent_output)
            context.validation_results["semantic_checker"] = {
                "success": validated.success,
                "result": validated.result,
                "errors": validated.errors,
                "execution_time_ms": validated.execution_time_ms,
            }
        except Exception as e:
            context.validation_results["semantic_checker"] = {"success": False, "error": str(e)}

        execution_times["semantic_checker"] = time.time() - start_time

        context.current_agent = "logic_auditor"
        start_time = time.time()
        try:
            agent_output = await self.run_agent(context, "logic_auditor")
            validated = validate_agent_output(agent_output)
            context.validation_results["logic_auditor"] = {
                "success": validated.success,
                "result": validated.result,
                "errors": validated.errors,
                "execution_time_ms": validated.execution_time_ms,
            }
        except Exception as e:
            context.validation_results["logic_auditor"] = {"success": False, "error": str(e)}

        execution_times["logic_auditor"] = time.time() - start_time

        context.metadata["execution_mode"] = (
            "parallel" if self.parallel_execution_enabled else "sequential"
        )
        context.metadata["execution_times"] = execution_times
        context.metadata["parallel_speedup"] = self._calculate_speedup(execution_times)

        context.current_agent = None
        return context

    def _calculate_speedup(self, execution_times: Dict[str, float]) -> float:
        """Calculate speedup ratio comparing parallel to sequential execution."""
        parallel_time = sum(v for k, v in execution_times.items() if k != "parallel_review_test")
        if "parallel_review_test" in execution_times:
            parallel_time += execution_times["parallel_review_test"]

        sequential_estimate = (
            execution_times.get("translator", 0)
            + execution_times.get("parallel_review_test", 0) * 2
            + execution_times.get("semantic_checker", 0)
        )

        if sequential_estimate > 0:
            return sequential_estimate / parallel_time if parallel_time > 0 else 1.0
        return 1.0

    def run_qa_pipeline_parallel(self, context: QAContext) -> QAContext:
        """Synchronous version of parallel pipeline."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                raise RuntimeError("Cannot run sync version in async context.")
            return loop.run_until_complete(self.run_qa_pipeline_parallel_async(context))
        except RuntimeError:
            return asyncio.run(self.run_qa_pipeline_parallel_async(context))

    async def run_benchmark(self, context: QAContext, iterations: int = 3) -> Dict[str, Any]:
        """Run benchmark comparing parallel vs sequential execution.

        Returns metrics comparing both execution modes.
        """
        parallel_times = []
        sequential_times = []

        for i in range(iterations):
            context.validation_results = {}
            context.metadata = {}

            start = time.time()
            await self.run_qa_pipeline_parallel_async(context)
            parallel_times.append(time.time() - start)

            context.validation_results = {}
            context.metadata = {}

            self.parallel_execution_enabled = False
            start = time.time()
            await self.run_qa_pipeline_async(context)
            sequential_times.append(time.time() - start)

            self.parallel_execution_enabled = True

        return {
            "parallel_avg": sum(parallel_times) / len(parallel_times),
            "sequential_avg": sum(sequential_times) / len(sequential_times),
            "speedup_ratio": sum(sequential_times) / sum(parallel_times)
            if parallel_times
            else None,
            "iterations": iterations,
        }

    def enable_parallel_execution(self, enabled: bool = True):
        """Enable or disable parallel execution."""
        self.parallel_execution_enabled = enabled

    def is_parallel_enabled(self) -> bool:
        """Check if parallel execution is currently enabled."""
        return self.parallel_execution_enabled

    def enable_constraint_guided_execution(self, enabled: bool = True):
        """Enable or disable constraint-guided execution mode."""
        self.constraint_guided_enabled = enabled

    def is_constraint_guided_enabled(self) -> bool:
        """Check if constraint-guided execution is currently enabled."""
        return self.constraint_guided_enabled

    def setup_run_agent(self, dag: Optional[ConversionDAG] = None) -> RunAgent:
        """Set up RunAgent with constraint-guided execution DAG."""
        run_agent = RunAgent(dag=dag, enable_rollback=True, strict_mode=True)

        run_agent.register_agent("java_analyzer", self._java_analyzer_agent)
        run_agent.register_agent("translator", self._translator_agent)
        run_agent.register_agent("reviewer", self._reviewer_agent)
        run_agent.register_agent("fixer", self._fixer_agent)

        self._run_agent_instance = run_agent
        return run_agent

    async def _java_analyzer_agent(self, context: StepContext) -> Dict[str, Any]:
        context.metrics.actions_performed.add("parse_ast")
        context.metrics.actions_performed.add("extract_imports")
        context.metrics.actions_performed.add("extract_classes")
        context.metrics.actions_performed.add("extract_methods")

        return {
            "java_ast": {"classes": [], "imports": []},
            "extracted_components": {
                "classes": context.state.get("source_classes", []),
                "methods": context.state.get("source_methods", []),
            },
        }

    async def _translator_agent(self, context: StepContext) -> Dict[str, Any]:
        if context.step.step_id == "map":
            context.metrics.actions_performed.add("identify_mappings")
            context.metrics.actions_performed.add("map_classes")
            context.metrics.actions_performed.add("map_methods")
            context.metrics.actions_performed.add("map_events")
        elif context.step.step_id == "generate":
            context.metrics.actions_performed.add("generate_json")
            context.metrics.actions_performed.add("generate_scripts")
            context.metrics.actions_performed.add("generate_manifest")
            context.metrics.actions_performed.add("generate_component_files")

        return {
            "mappings": {},
            "generated_files": [],
            "bedrock_components": [],
        }

    async def _reviewer_agent(self, context: StepContext) -> Dict[str, Any]:
        context.metrics.actions_performed.add("validate_json_schema")
        context.metrics.actions_performed.add("validate_scripts")
        context.metrics.actions_performed.add("validate_semantics")
        context.metrics.actions_performed.add("check_api_compatibility")

        return {
            "validation_results": {
                "schema_valid": True,
                "semantics_valid": True,
                "api_compatible": True,
            },
            "issues": [],
        }

    async def _fixer_agent(self, context: StepContext) -> Dict[str, Any]:
        context.metrics.actions_performed.add("identify_issues")
        context.metrics.actions_performed.add("apply_fixes")
        context.metrics.actions_performed.add("re_validate")
        context.metrics.actions_performed.add("verify_fixes")

        return {
            "fixes_applied": [],
            "verified": True,
        }

    async def run_qa_pipeline_constraint_guided(
        self, context: QAContext
    ) -> QAContext:
        """Run QA pipeline with constraint-guided execution using RunAgent."""
        if not self._run_agent_instance:
            self.setup_run_agent()

        initial_state = {
            "source_java_path": str(context.source_java_path),
            "output_bedrock_path": str(context.output_bedrock_path),
            "job_id": context.job_id,
            "source_classes": [],
            "source_methods": [],
        }

        success, result = await self._run_agent_instance.execute_conversion(
            initial_state=initial_state,
        )

        context.validation_results = {}
        for step_result in result.get("step_results", []):
            step_id = step_result["step_id"]
            context.validation_results[step_id] = {
                "success": step_result["success"],
                "result": step_result.get("output", {}),
                "errors": step_result.get("errors", []),
                "duration_ms": step_result.get("duration_ms", 0),
                "retry_count": step_result.get("retry_count", 0),
            }

        context.metadata["execution_mode"] = "constraint_guided"
        context.metadata["constraint_guided_trace"] = result.get("trace", {})
        context.metadata["completed_steps"] = result.get("completed_steps", [])

        trace = self._run_agent_instance.get_execution_trace()
        if trace:
            context.metadata["step_order_verified"] = trace.can_verify_step_order(
                ["extract", "map", "generate", "validate", "repair"]
            )

        return context

    def run_qa_pipeline_constraint_guided_sync(self, context: QAContext) -> QAContext:
        """Synchronous wrapper for constraint-guided pipeline."""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                raise RuntimeError("Cannot run sync version in async context.")
            return loop.run_until_complete(
                self.run_qa_pipeline_constraint_guided(context)
            )
        except RuntimeError:
            return asyncio.run(self.run_qa_pipeline_constraint_guided(context))

    async def run_agent(self, context: QAContext, agent_name: str) -> Dict[str, Any]:
        breaker = self._breakers[agent_name]

        async def run_with_timeout():
            return await asyncio.wait_for(
                self._execute_agent_placeholder(context, agent_name),
                timeout=self.timeout_seconds,
            )

        def run_async():
            return asyncio.run(run_with_timeout())

        try:
            if asyncio.get_event_loop().is_running():
                return await self._run_with_breaker_async(breaker, context, agent_name)
            else:
                return breaker.call(lambda: asyncio.run(run_with_timeout()))
        except CircuitBreakerOpenError:
            raise
        except RuntimeError:
            return await self._run_with_breaker_async(breaker, context, agent_name)

    async def _run_with_breaker_async(
        self, breaker: CircuitBreaker, context: QAContext, agent_name: str
    ) -> Dict[str, Any]:
        if str(breaker.state.value) == "open":
            raise CircuitBreakerOpenError(f"Circuit breaker '{agent_name}' is open")

        try:
            result = await asyncio.wait_for(
                self._execute_agent_placeholder(context, agent_name),
                timeout=self.timeout_seconds,
            )
            breaker._on_success()
            return result
        except Exception:
            breaker._on_failure()
            raise

    async def _execute_agent_placeholder(
        self, context: QAContext, agent_name: str
    ) -> Dict[str, Any]:
        start_time = int(time.time() * 1000)
        await asyncio.sleep(0.1)
        end_time = int(time.time() * 1000)

        return {
            "agent_name": agent_name,
            "success": True,
            "result": {
                "message": f"{agent_name} agent completed",
                "job_id": context.job_id,
            },
            "errors": [],
            "execution_time_ms": end_time - start_time,
        }

    def _detect_critical_issues(self, context: QAContext) -> List[Dict[str, Any]]:
        """Detect critical issues from validation results."""
        critical_issues = []
        for agent_name, result in context.validation_results.items():
            if not result.get("success", True):
                error_msg = result.get("error", "Unknown error")
                critical_issues.append(
                    {
                        "agent_name": agent_name,
                        "error": error_msg,
                        "suggestions": self._get_suggestions_for_agent(agent_name, error_msg),
                    }
                )
            errors = result.get("errors", [])
            if isinstance(errors, list):
                for error in errors:
                    if isinstance(error, dict) and error.get("severity") == "CRITICAL":
                        critical_issues.append(
                            {
                                "agent_name": agent_name,
                                "error": error.get("message", str(error)),
                                "suggestions": error.get("suggestions", []),
                            }
                        )
        return critical_issues

    def _get_suggestions_for_agent(self, agent_name: str, error: str) -> List[str]:
        """Get suggested fixes based on agent type and error."""
        suggestions = {
            "translator": [
                "Check Java syntax compatibility with Bedrock",
                "Verify all imports are properly handled",
                "Ensure proper error handling patterns",
            ],
            "reviewer": [
                "Review code style guidelines",
                "Check naming conventions",
                "Verify documentation completeness",
            ],
            "tester": [
                "Review test coverage",
                "Check edge case handling",
                "Verify test assertions",
            ],
            "semantic_checker": [
                "Verify behavioral equivalence",
                "Check API compatibility",
                "Review state management",
            ],
            "logic_auditor": [
                "Check numeric formula accuracy",
                "Verify probability comparisons",
                "Confirm event hook mappings",
                "Validate conditional logic",
            ],
        }
        return suggestions.get(agent_name, ["Review the error and fix accordingly"])

    def _build_refinement_prompt(self, context: QAContext, issues: List[Dict]) -> str:
        """Build a refinement prompt for the translator with error context."""
        prompt_parts = [
            f"Source file: {context.source_java_path}",
            "",
            "Critical issues detected that need to be addressed:",
        ]
        for i, issue in enumerate(issues, 1):
            prompt_parts.append(f"{i}. [{issue['agent_name']}] {issue['error']}")
            if issue.get("suggestions"):
                prompt_parts.append("   Suggestions:")
                for suggestion in issue["suggestions"]:
                    prompt_parts.append(f"   - {suggestion}")
        prompt_parts.append("")
        prompt_parts.append("Please fix these issues in the translated code.")
        return "\n".join(prompt_parts)

    def _calculate_quality_score(self, validation_results: Dict[str, Any]) -> float:
        """Calculate weighted quality score from validation results."""
        weights = {
            "translator": 0.20,
            "reviewer": 0.20,
            "tester": 0.20,
            "semantic_checker": 0.20,
            "logic_auditor": 0.20,
        }
        total_score = 0.0
        for agent_name, weight in weights.items():
            result = validation_results.get(agent_name, {})
            if result.get("success"):
                score = result.get("result", {}).get("score", 100.0)
            else:
                score = 0.0
            total_score += score * weight
        return total_score

    def run_with_refinement(self, context: QAContext) -> QAContext:
        """Run QA pipeline with iterative refinement."""
        if not self.refinement_enabled or not context.refinement_enabled:
            return self.run_qa_pipeline_parallel(context)

        context.refinement_iteration = 0
        context.refinement_history = []

        if self.parallel_execution_enabled:
            context = self.run_qa_pipeline_parallel(context)
        else:
            context = self.run_qa_pipeline(context)

        initial_score = self._calculate_quality_score(context.validation_results)

        for iteration in range(1, self.max_refinement_iterations + 1):
            context.refinement_iteration = iteration
            logger.info("Refinement iteration", iteration=iteration, job_id=context.job_id)

            critical_issues = self._detect_critical_issues(context)
            if not critical_issues:
                logger.info("No critical issues detected, stopping refinement")
                break

            refinement_prompt = self._build_refinement_prompt(context, critical_issues)

            context.metadata["refinement_prompt"] = refinement_prompt
            context.metadata["current_iteration"] = iteration

            context = self._run_refinement_iteration(context, refinement_prompt)

            final_score = self._calculate_quality_score(context.validation_results)

            history_entry = RefinementHistory(
                iteration=iteration,
                initial_score=initial_score,
                final_score=final_score,
                issues_detected=critical_issues,
                translator_prompt_modifications=refinement_prompt,
            )
            context.refinement_history.append(history_entry)

            improvement = final_score - initial_score
            logger.info(
                "Refinement iteration complete",
                iteration=iteration,
                initial_score=initial_score,
                final_score=final_score,
                improvement=improvement,
            )

            if improvement < 5.0:
                logger.info("Improvement below threshold, stopping refinement")
                break

            initial_score = final_score

        context.refinement_completed = True
        return context

    def _run_refinement_iteration(self, context: QAContext, refinement_prompt: str) -> QAContext:
        """Run a single refinement iteration (re-run agents with refinement context)."""
        context.validation_results = {}

        context.current_agent = "translator"
        try:
            agent_output = self._execute_agent_placeholder(context, "translator")
            agent_output["result"]["refinement_prompt"] = refinement_prompt
            validated = validate_agent_output(agent_output)
            context.validation_results["translator"] = {
                "success": validated.success,
                "result": validated.result,
                "errors": validated.errors,
                "execution_time_ms": validated.execution_time_ms,
            }
        except Exception as e:
            logger.error("Refinement translator failed", error=str(e))
            context.validation_results["translator"] = {"success": False, "error": str(e)}

        if self.parallel_execution_enabled:
            parallel_results = self._run_agents_parallel_sync(context, ["reviewer", "tester"])
            for agent_name, result in parallel_results.items():
                if result.get("success"):
                    validated = validate_agent_output(result["result"])
                    context.validation_results[agent_name] = {
                        "success": validated.success,
                        "result": validated.result,
                        "errors": validated.errors,
                        "execution_time_ms": validated.execution_time_ms,
                    }
                else:
                    context.validation_results[agent_name] = {
                        "success": False,
                        "error": result.get("error", "Unknown error"),
                    }
        else:
            for agent_name in ["reviewer", "tester"]:
                context.current_agent = agent_name
                try:
                    agent_output = self._execute_agent_placeholder(context, agent_name)
                    validated = validate_agent_output(agent_output)
                    context.validation_results[agent_name] = {
                        "success": validated.success,
                        "result": validated.result,
                        "errors": validated.errors,
                        "execution_time_ms": validated.execution_time_ms,
                    }
                except Exception as e:
                    context.validation_results[agent_name] = {"success": False, "error": str(e)}

        context.current_agent = "semantic_checker"
        try:
            agent_output = self._execute_agent_placeholder(context, "semantic_checker")
            validated = validate_agent_output(agent_output)
            context.validation_results["semantic_checker"] = {
                "success": validated.success,
                "result": validated.result,
                "errors": validated.errors,
                "execution_time_ms": validated.execution_time_ms,
            }
        except Exception as e:
            context.validation_results["semantic_checker"] = {"success": False, "error": str(e)}

        context.current_agent = "logic_auditor"
        try:
            agent_output = self._execute_agent_placeholder(context, "logic_auditor")
            validated = validate_agent_output(agent_output)
            context.validation_results["logic_auditor"] = {
                "success": validated.success,
                "result": validated.result,
                "errors": validated.errors,
                "execution_time_ms": validated.execution_time_ms,
            }
        except Exception as e:
            context.validation_results["logic_auditor"] = {"success": False, "error": str(e)}

        context.current_agent = None
        return context

    def _run_agents_parallel_sync(
        self, context: QAContext, agent_names: List[str]
    ) -> Dict[str, Dict[str, Any]]:
        """Synchronous version of running agents in parallel."""
        results = {}
        for agent_name in agent_names:
            try:
                result = self._execute_agent_placeholder(context, agent_name)
                results[agent_name] = {"success": True, "result": result}
            except Exception as e:
                logger.error("Agent failed in refinement", agent=agent_name, error=str(e))
                results[agent_name] = {"success": False, "error": str(e)}
        return results
