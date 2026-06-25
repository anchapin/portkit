"""
LLM Cost Monitoring and Budget Guardrails

Provides per-conversion cost tracking and budget enforcement to prevent
runaway LLM costs from large mods.

Issue: #1205 - Pre-beta: LLM cost monitoring, per-conversion cost tracking, and budget guardrails
"""

import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

from agent_metrics.llm_usage_tracker import track_llm_call, llm_tracker

logger = logging.getLogger(__name__)


class BudgetAction(Enum):
    """Actions to take when budget is exceeded"""

    ALLOW = "allow"
    WARN = "warn"
    BLOCK = "block"
    FAIL_CONVERSION = "fail_conversion"


@dataclass
class BudgetConfig:
    """Configuration for budget guardrails"""

    per_conversion_budget: float = 5.0
    daily_budget: float = 50.0
    monthly_budget: float = 500.0
    warn_threshold: float = 0.8
    block_threshold: float = 1.0
    enable_per_conversion_limit: bool = True
    enable_daily_limit: bool = True
    enable_monthly_limit: bool = False


@dataclass
class ConversionCost:
    """Cost tracking for a single conversion"""

    conversion_id: str
    started_at: datetime
    completed_at: Optional[datetime] = None
    total_cost: float = 0.0
    llm_calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    budget_action: BudgetAction = BudgetAction.ALLOW
    blocked: bool = False
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "conversion_id": self.conversion_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "total_cost": round(self.total_cost, 6),
            "llm_calls": self.llm_calls,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "budget_action": self.budget_action.value,
            "blocked": self.blocked,
            "error": self.error,
        }


class BudgetGuardrails:
    """
    Budget guardrails for LLM cost monitoring and control.

    Features:
    - Per-conversion budget limits
    - Daily/monthly budget tracking
    - Automatic blocking or warning when budgets exceeded
    - Integration with LLMUsageTracker for call tracking
    """

    def __init__(self, config: Optional[BudgetConfig] = None):
        self.config = config or BudgetConfig()
        self._lock = threading.Lock()
        self._active_conversions: Dict[str, ConversionCost] = {}
        self._daily_costs: Dict[str, float] = {}
        self._monthly_costs: Dict[str, float] = {}
        self._llm_tracker = llm_tracker
        self._callbacks: List[Callable] = []

    def start_conversion_tracking(
        self, conversion_id: str, options: Optional[Dict[str, Any]] = None
    ) -> ConversionCost:
        """
        Start tracking costs for a new conversion.

        Args:
            conversion_id: Unique conversion identifier
            options: Optional settings (can include custom budget override)

        Returns:
            ConversionCost object for tracking
        """
        with self._lock:
            if conversion_id in self._active_conversions:
                logger.warning(f"Conversion {conversion_id} already being tracked")
                return self._active_conversions[conversion_id]

            cost = ConversionCost(
                conversion_id=conversion_id,
                started_at=datetime.now(timezone.utc),
            )

            self._active_conversions[conversion_id] = cost

            per_conversion_budget = self.config.per_conversion_budget
            if options and "budget" in options:
                per_conversion_budget = options["budget"]

            budget_status = self._check_budgets(
                conversion_id, cost.total_cost, per_conversion_budget
            )
            if budget_status["action"] != BudgetAction.ALLOW:
                cost.budget_action = budget_status["action"]
                if budget_status["action"] == BudgetAction.BLOCK:
                    cost.blocked = True
                    cost.error = budget_status["reason"]
                    logger.warning(f"Conversion {conversion_id} blocked: {budget_status['reason']}")

            logger.info(f"Started cost tracking for conversion {conversion_id}")
            return cost

    def record_llm_call(
        self,
        conversion_id: str,
        model: str,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        duration: float,
        cost: float,
        success: bool = True,
        error: Optional[str] = None,
    ) -> ConversionCost:
        """
        Record an LLM call and update conversion cost tracking.

        Args:
            conversion_id: Conversion identifier
            model: LLM model name
            provider: LLM provider
            input_tokens: Input token count
            output_tokens: Output token count
            duration: Call duration in seconds
            cost: Calculated cost
            success: Whether call succeeded
            error: Error message if failed

        Returns:
            Updated ConversionCost
        """
        with self._lock:
            if conversion_id not in self._active_conversions:
                logger.warning(f"Conversion {conversion_id} not being tracked, creating tracking")
                self.start_conversion_tracking(conversion_id)

            cost_record = self._active_conversions[conversion_id]

            track_llm_call(
                model=model,
                provider=provider,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                duration=duration,
                success=success,
                error=error,
                metadata={"conversion_id": conversion_id},
            )

            cost_record.llm_calls += 1
            cost_record.input_tokens += input_tokens
            cost_record.output_tokens += output_tokens
            cost_record.total_cost += cost

            budget_status = self._check_budgets(
                conversion_id, cost_record.total_cost, self.config.per_conversion_budget
            )

            if budget_status["action"] == BudgetAction.BLOCK and not cost_record.blocked:
                cost_record.blocked = True
                cost_record.budget_action = BudgetAction.BLOCK
                cost_record.error = budget_status["reason"]
                self._trigger_callbacks("budget_exceeded", budget_status)

            elif (
                budget_status["action"] == BudgetAction.WARN
                and cost_record.budget_action == BudgetAction.ALLOW
            ):
                cost_record.budget_action = BudgetAction.WARN
                self._trigger_callbacks("budget_warning", budget_status)

            self._update_daily_costs(cost_record)

            return cost_record

    def _check_budgets(
        self,
        conversion_id: str,
        current_cost: float,
        per_conversion_budget: float,
    ) -> Dict[str, Any]:
        """Check if current costs exceed any budget limits"""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        month_key = datetime.now(timezone.utc).strftime("%Y-%m")

        daily_cost = self._daily_costs.get(today, 0.0)
        monthly_cost = self._monthly_costs.get(month_key, 0.0)

        if self.config.enable_per_conversion_limit:
            warn_threshold = per_conversion_budget * self.config.warn_threshold
            block_threshold = per_conversion_budget * self.config.block_threshold

            if current_cost >= block_threshold:
                return {
                    "action": BudgetAction.BLOCK,
                    "reason": (
                        f"Per-conversion budget exceeded: "
                        f"${current_cost:.2f} >= ${block_threshold:.2f}"
                    ),
                    "budget_type": "per_conversion",
                }
            elif current_cost >= warn_threshold:
                return {
                    "action": BudgetAction.WARN,
                    "reason": (
                        f"Per-conversion budget warning: "
                        f"${current_cost:.2f} >= ${warn_threshold:.2f}"
                    ),
                    "budget_type": "per_conversion",
                }

        if self.config.enable_daily_limit:
            daily_warn = self.config.daily_budget * self.config.warn_threshold
            daily_block = self.config.daily_budget * self.config.block_threshold

            if daily_cost >= daily_block:
                return {
                    "action": BudgetAction.BLOCK,
                    "reason": f"Daily budget exceeded: ${daily_cost:.2f} >= ${daily_block:.2f}",
                    "budget_type": "daily",
                }
            elif daily_cost >= daily_warn:
                return {
                    "action": BudgetAction.WARN,
                    "reason": (f"Daily budget warning: ${daily_cost:.2f} >= ${daily_warn:.2f}"),
                    "budget_type": "daily",
                }

        if self.config.enable_monthly_limit:
            monthly_warn = self.config.monthly_budget * self.config.warn_threshold
            monthly_block = self.config.monthly_budget * self.config.block_threshold

            if monthly_cost >= monthly_block:
                return {
                    "action": BudgetAction.BLOCK,
                    "reason": (
                        f"Monthly budget exceeded: ${monthly_cost:.2f} >= ${monthly_block:.2f}"
                    ),
                    "budget_type": "monthly",
                }
            elif monthly_cost >= monthly_warn:
                return {
                    "action": BudgetAction.WARN,
                    "reason": (
                        f"Monthly budget warning: ${monthly_cost:.2f} >= ${monthly_warn:.2f}"
                    ),
                    "budget_type": "monthly",
                }

        return {"action": BudgetAction.ALLOW, "reason": "Within budget", "budget_type": None}

    def _update_daily_costs(self, cost_record: ConversionCost) -> None:
        """Update daily and monthly cost totals"""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        month_key = datetime.now(timezone.utc).strftime("%Y-%m")

        if today not in self._daily_costs:
            self._daily_costs[today] = 0.0
        self._daily_costs[today] += cost_record.total_cost

        if month_key not in self._monthly_costs:
            self._monthly_costs[month_key] = 0.0
        self._monthly_costs[month_key] += cost_record.total_cost

    def end_conversion_tracking(self, conversion_id: str) -> Optional[ConversionCost]:
        """
        End tracking for a conversion and return final cost.

        Args:
            conversion_id: Conversion identifier

        Returns:
            Final ConversionCost or None if not found
        """
        with self._lock:
            if conversion_id not in self._active_conversions:
                logger.warning(f"Conversion {conversion_id} not being tracked")
                return None

            cost_record = self._active_conversions[conversion_id]
            cost_record.completed_at = datetime.now(timezone.utc)

            logger.info(
                f"Completed cost tracking for conversion {conversion_id}: "
                f"${cost_record.total_cost:.4f} ({cost_record.llm_calls} calls)"
            )

            return cost_record

    def get_conversion_cost(self, conversion_id: str) -> Optional[ConversionCost]:
        """Get current cost tracking for a conversion"""
        with self._lock:
            return self._active_conversions.get(conversion_id)

    def get_active_conversions(self) -> List[ConversionCost]:
        """Get all active conversion cost records"""
        with self._lock:
            return list(self._active_conversions.values())

    def get_budget_status(self) -> Dict[str, Any]:
        """Get current budget status across all limits"""
        with self._lock:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            month_key = datetime.now(timezone.utc).strftime("%Y-%m")
            daily_cost = self._daily_costs.get(today, 0.0)
            monthly_cost = self._monthly_costs.get(month_key, 0.0)

            active_count = len(self._active_conversions)

            return {
                "daily": {
                    "cost": round(daily_cost, 4),
                    "budget": self.config.daily_budget,
                    "percent_used": round((daily_cost / self.config.daily_budget) * 100, 2)
                    if self.config.daily_budget > 0
                    else 0,
                },
                "monthly": {
                    "cost": round(monthly_cost, 4),
                    "budget": self.config.monthly_budget,
                    "percent_used": round((monthly_cost / self.config.monthly_budget) * 100, 2)
                    if self.config.monthly_budget > 0
                    else 0,
                },
                "active_conversions": active_count,
            }

    def check_budget_available(self, conversion_id: str, estimated_cost: float) -> Dict[str, Any]:
        """
        Check if budget is available for a new conversion.

        Args:
            conversion_id: New conversion ID
            estimated_cost: Estimated cost for the conversion

        Returns:
            Dict with allowed status and reason
        """
        with self._lock:
            if conversion_id in self._active_conversions:
                return {"allowed": True, "reason": "Conversion already tracked"}

            budget_status = self._check_budgets(
                conversion_id, estimated_cost, self.config.per_conversion_budget
            )

            return {
                "allowed": budget_status["action"] != BudgetAction.BLOCK,
                "reason": budget_status["reason"],
                "action": budget_status["action"].value,
            }

    def add_callback(self, callback: Callable) -> None:
        """Add a callback for budget events"""
        self._callbacks.append(callback)

    def _trigger_callbacks(self, event_type: str, data: Dict) -> None:
        """Trigger all registered callbacks"""
        for callback in self._callbacks:
            try:
                callback(event_type, data)
            except Exception as e:
                logger.error(f"Error in budget callback: {e}")

    def reset_daily(self) -> None:
        """Reset daily cost tracking (called by scheduler)"""
        with self._lock:
            today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
            self._daily_costs = {today: 0.0}
            logger.info("Reset daily cost tracking")

    def reset_all(self) -> None:
        """Reset all cost tracking"""
        with self._lock:
            self._active_conversions.clear()
            self._daily_costs.clear()
            self._monthly_costs.clear()
            logger.info("Reset all cost tracking")


class CostBudgetMiddleware:
    """
    Middleware that wraps LLM calls to automatically track costs
    and enforce budget limits per conversion.
    """

    def __init__(self, guardrails: BudgetGuardrails):
        self.guardrails = guardrails
        self._conversion_id: Optional[str] = None

    def set_conversion(self, conversion_id: str) -> None:
        """Set the current conversion ID for tracking"""
        self._conversion_id = conversion_id

    def clear_conversion(self) -> None:
        """Clear the current conversion ID"""
        self._conversion_id = None

    def wrap_llm_call(
        self,
        model: str,
        provider: str,
        input_tokens: int,
        output_tokens: int,
        duration: float,
        cost: float,
        success: bool = True,
        error: Optional[str] = None,
    ) -> bool:
        """
        Wrap an LLM call to track costs.

        Returns:
            True if call was allowed, False if blocked
        """
        if self._conversion_id is None:
            logger.debug("No conversion ID set, not tracking cost")
            return True

        conversion_cost = self.guardrails.record_llm_call(
            conversion_id=self._conversion_id,
            model=model,
            provider=provider,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            duration=duration,
            cost=cost,
            success=success,
            error=error,
        )

        return not conversion_cost.blocked


def estimate_call_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """
    Estimate the cost of an LLM call.

    Args:
        model: Model name
        input_tokens: Input token count
        output_tokens: Output token count

    Returns:
        Estimated cost in USD
    """
    return llm_tracker.estimate_cost(model, input_tokens, output_tokens)


# Global guardrails instance
_guardrails: Optional[BudgetGuardrails] = None
_middleware: Optional[CostBudgetMiddleware] = None


def get_budget_guardrails(config: Optional[BudgetConfig] = None) -> BudgetGuardrails:
    """Get or create the global budget guardrails instance"""
    global _guardrails
    if _guardrails is None:
        _guardrails = BudgetGuardrails(config)
    return _guardrails


def get_cost_middleware() -> CostBudgetMiddleware:
    """Get or create the global cost middleware instance"""
    global _middleware
    if _middleware is None:
        guardrails = get_budget_guardrails()
        _middleware = CostBudgetMiddleware(guardrails)
    return _middleware


def start_conversion_cost_tracking(conversion_id: str, **options) -> ConversionCost:
    """Start tracking costs for a conversion"""
    guardrails = get_budget_guardrails()
    return guardrails.start_conversion_tracking(conversion_id, options)


def record_conversion_llm_call(
    conversion_id: str,
    model: str,
    provider: str,
    input_tokens: int,
    output_tokens: int,
    duration: float,
    **kwargs,
) -> ConversionCost:
    """Record an LLM call for a conversion"""
    cost = estimate_call_cost(model, input_tokens, output_tokens)
    guardrails = get_budget_guardrails()
    return guardrails.record_llm_call(
        conversion_id=conversion_id,
        model=model,
        provider=provider,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        duration=duration,
        cost=cost,
        **kwargs,
    )


def end_conversion_cost_tracking(conversion_id: str) -> Optional[ConversionCost]:
    """End cost tracking for a conversion"""
    guardrails = get_budget_guardrails()
    return guardrails.end_conversion_tracking(conversion_id)


def get_conversion_cost_report(conversion_id: str) -> Optional[Dict[str, Any]]:
    """Get cost report for a conversion"""
    guardrails = get_budget_guardrails()
    cost = guardrails.get_conversion_cost(conversion_id)
    if cost:
        return cost.to_dict()

    tracker_report = llm_tracker.get_recent_calls(limit=100)
    conversion_calls = [
        c for c in tracker_report if c.get("metadata", {}).get("conversion_id") == conversion_id
    ]

    if conversion_calls:
        total_cost = sum(c.get("cost", 0) for c in conversion_calls)
        total_tokens = sum(c.get("total_tokens", 0) for c in conversion_calls)
        return {
            "conversion_id": conversion_id,
            "total_cost": round(total_cost, 6),
            "llm_calls": len(conversion_calls),
            "total_tokens": total_tokens,
            "calls": conversion_calls,
        }

    return None


def get_budget_status_report() -> Dict[str, Any]:
    """Get overall budget status"""
    guardrails = get_budget_guardrails()
    return guardrails.get_budget_status()


def check_conversion_budget(conversion_id: str, estimated_cost: float = 0.0) -> Dict[str, Any]:
    """Check if budget is available for a new conversion"""
    guardrails = get_budget_guardrails()
    return guardrails.check_budget_available(conversion_id, estimated_cost)
