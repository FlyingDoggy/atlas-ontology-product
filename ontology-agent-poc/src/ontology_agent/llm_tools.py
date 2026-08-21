from __future__ import annotations

from .contracts import PublicationError, VerifiedSnapshot
from .llm_contracts import (
    SafeComparisonResult,
    SafeContributorResult,
    SafeDecompositionResult,
    SafePeriodResult,
)
from .runtime import _comparison, _driver_facts, _period_facts
from .runtime_snapshot import verify_snapshot_handle
from .sql_compiler import DuckDBContext, compile_trading_days, compile_turnover


class ADTToolError(RuntimeError):
    """A closed ADT tool request could not be bound or executed safely."""


class ADTAnalyticTools:
    def __init__(self, snapshot: VerifiedSnapshot, *, role: str):
        try:
            verify_snapshot_handle(snapshot)
        except PublicationError as exc:
            raise ADTToolError("Snapshot verification failed") from exc
        policy = snapshot.package.policies[0]
        if role in policy.denied_roles or role not in policy.allowed_roles:
            raise ADTToolError("Role is not allowed to use aggregate ADT tools")
        self.snapshot = snapshot
        self.role = role

    def _scope(
        self,
        *,
        metric_id: str,
        previous_period_id: str,
        current_period_id: str,
        population_id: str,
    ) -> tuple[str, str]:
        package = self.snapshot.package
        expected_population = f"{package.scenario.id}:{package.scenario.market_id}"
        available = {period.id for period in package.scenario.periods}
        if metric_id != "metric.average_daily_turnover":
            raise ADTToolError("Metric is outside the ADT tool capability")
        if population_id != expected_population:
            raise ADTToolError("Population is outside the active ADT scenario")
        if (
            previous_period_id not in available
            or current_period_id not in available
            or previous_period_id == current_period_id
        ):
            raise ADTToolError("Exactly two distinct governed periods are required")
        ordered = tuple(
            period.id
            for period in sorted(package.scenario.periods, key=lambda item: item.start)
            if period.id in {previous_period_id, current_period_id}
        )
        if ordered != (previous_period_id, current_period_id):
            raise ADTToolError("Comparison periods must follow governed time order")
        return ordered

    def compare_periods(
        self,
        *,
        metric_id: str,
        previous_period_id: str,
        current_period_id: str,
        population_id: str,
    ) -> SafeComparisonResult:
        periods = self._scope(
            metric_id=metric_id,
            previous_period_id=previous_period_id,
            current_period_id=current_period_id,
            population_id=population_id,
        )
        package = self.snapshot.package
        turnover_query = compile_turnover(package, periods)
        days_query = compile_trading_days(package, periods)
        with DuckDBContext(package, self.snapshot.resource_paths) as context:
            turnover_rows = context.execute(turnover_query)
            day_rows = context.execute(days_query)
        period_facts = _period_facts(package, turnover_rows, day_rows)
        if set(period_facts) != set(periods):
            raise ADTToolError("Not every governed period produced a result")
        comparison = _comparison(periods, period_facts)

        def period_result(period_id: str) -> SafePeriodResult:
            fact = period_facts[period_id]
            return SafePeriodResult(
                period_id=period_id,
                adt_hkd_mn_per_trading_day=fact["adt_hkd_mn_per_trading_day"],
                eligible_turnover_hkd_mn=fact["eligible_turnover_hkd_mn"],
                trading_day_count=fact["trading_day_count"],
            )

        return SafeComparisonResult(
            previous=period_result(previous_period_id),
            current=period_result(current_period_id),
            adt_direction=comparison["adt_direction"],
            adt_delta_hkd_mn_per_trading_day=comparison[
                "adt_delta_hkd_mn_per_trading_day"
            ],
            adt_delta_pct=comparison["adt_delta_pct"],
        )

    def rank_contributors(
        self,
        *,
        previous_period_id: str,
        current_period_id: str,
        dimension_id: str,
        population_id: str,
    ) -> SafeContributorResult:
        if dimension_id != "dimension.segment":
            raise ADTToolError("Dimension is outside the contributor capability")
        periods = self._scope(
            metric_id="metric.average_daily_turnover",
            previous_period_id=previous_period_id,
            current_period_id=current_period_id,
            population_id=population_id,
        )
        driver = self._driver_facts(periods)
        leading = driver["leading_segment"]
        return SafeContributorResult(
            segment_id=leading["segment_id"],
            segment_name=leading["segment_name"],
            rank=leading["rank"],
            delta_hkd_mn=leading["delta_hkd_mn"],
            net_change_contribution_pct=leading["net_change_contribution_pct"],
        )

    def _driver_facts(self, periods: tuple[str, str]) -> dict[str, object]:
        package = self.snapshot.package
        turnover_query = compile_turnover(package, periods)
        days_query = compile_trading_days(package, periods)
        segment_query = compile_turnover(package, periods, by_segment=True)
        with DuckDBContext(package, self.snapshot.resource_paths) as context:
            turnover_rows = context.execute(turnover_query)
            day_rows = context.execute(days_query)
            segment_rows = context.execute(segment_query)
        period_facts = _period_facts(package, turnover_rows, day_rows)
        if set(period_facts) != set(periods):
            raise ADTToolError("Not every governed period produced a driver result")
        return _driver_facts(package, periods, period_facts, segment_rows)

    def decompose_change(
        self,
        *,
        previous_period_id: str,
        current_period_id: str,
        method_id: str,
        population_id: str,
    ) -> SafeDecompositionResult:
        if method_id != "sequential_calendar_first":
            raise ADTToolError("Decomposition method is outside the ADT capability")
        periods = self._scope(
            metric_id="metric.average_daily_turnover",
            previous_period_id=previous_period_id,
            current_period_id=current_period_id,
            population_id=population_id,
        )
        decomposition = self._driver_facts(periods)["decomposition"]
        return SafeDecompositionResult(
            method=decomposition["method"],
            calendar_effect_hkd_mn=decomposition["calendar_effect_hkd_mn"],
            activity_effect_hkd_mn=decomposition["activity_effect_hkd_mn"],
            residual_hkd_mn=decomposition["residual_hkd_mn"],
            causal_claim=decomposition["causal_claim"],
            order_dependent=decomposition["order_dependent"],
        )
