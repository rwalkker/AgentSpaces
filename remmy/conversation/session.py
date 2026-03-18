"""Session state tracking for conversational context."""

from dataclasses import dataclass, field
from remmy.engine.hc import HCResult


@dataclass
class SessionState:
    # Plan inputs
    planning_om: str = ""
    shift_type: str = ""  # "Day" / "Night"
    date: str = ""
    big_gulp_volume: float = 0
    shift_duration: float = 0
    show_rate_day: float = 0
    show_rate_night: float = 0
    seed_hc_day: float = 0
    seed_hc_night: float = 0
    ns_pct: float = 0
    new_hire_pct: float = 0
    new_hire_count: int = 0
    backlog_current: float = 0
    backlog_target: float = 0
    prior_shift_hit: str = ""  # "hit" / "miss" / "exceed"
    quarter: int = 1

    # Computed
    plan_result: HCResult | None = None
    plan_id: int | None = None
    status: str = "draft"
    locked_by: str = ""
    locked_at: str = ""

    # Tracking
    flags: list = field(default_factory=list)
    acknowledged_warnings: set = field(default_factory=set)
    overrides: dict = field(default_factory=dict)  # role_code -> value
    locks: set = field(default_factory=set)  # locked role codes
    new_hire_prompted: bool = False
    conversation_history: list = field(default_factory=list)

    # Required inputs for plan creation
    REQUIRED_INPUTS = [
        ("planning_om", "What's your name (Planning OM)?"),
        ("shift_type", "Day or Night shift?"),
        ("date", "What date is this plan for?"),
        ("big_gulp_volume", "What's the Big Gulp volume?"),
        ("shift_duration", "Shift duration in hours?"),
    ]

    def get_missing_inputs(self) -> list[tuple[str, str]]:
        missing = []
        for attr, prompt in self.REQUIRED_INPUTS:
            val = getattr(self, attr)
            if not val:
                missing.append((attr, prompt))
        return missing

    def has_plan(self) -> bool:
        return self.plan_result is not None

    def is_locked(self) -> bool:
        return self.status == "locked"
