"""API contract: every request and response shape the frontend uses.

The sample responses in /fixtures validate against these models (tests/test_contract.py).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class Rail(str, Enum):
    """Payment rail. Indian rails first; the rest are the payment formats in IBM's AML dataset.

    Only CASH changes detector behaviour (it is treated as a deposit into the destination account); every other
    rail is an account-to-account transfer.
    """

    UPI = "UPI"
    IMPS = "IMPS"
    NEFT = "NEFT"
    RTGS = "RTGS"
    CASH = "CASH"
    ACH = "ACH"
    WIRE = "WIRE"
    CHEQUE = "CHEQUE"
    CARD = "CARD"
    CRYPTO = "CRYPTO"
    REINVESTMENT = "REINVESTMENT"


# IBM AML "Payment Format" values -> Rail
IBM_PAYMENT_FORMATS: dict[str, Rail] = {
    "ACH": Rail.ACH,
    "Wire": Rail.WIRE,
    "Cheque": Rail.CHEQUE,
    "Credit Card": Rail.CARD,
    "Cash": Rail.CASH,
    "Bitcoin": Rail.CRYPTO,
    "Reinvestment": Rail.REINVESTMENT,
}


class Tier(str, Enum):
    CRITICAL = "Critical"
    REVIEW = "Review"
    WATCH = "Watch"


class Layer(str, Enum):
    DETECTOR = "detector"
    BASELINE = "baseline"
    GRAPH = "graph"
    MODEL = "model"


class Transaction(BaseModel):
    txn_id: str
    ts: datetime
    src_account: str
    dst_account: str
    amount: float = Field(gt=0)
    currency: str = "INR"
    rail: Rail
    src_handle: str | None = None  # VPA, masked PAN or IFSC; may be missing
    device_id: str | None = None  # missing on purpose in some rows
    location: str | None = None
    channel: str | None = None


class Reason(BaseModel):
    """One evidence-backed reason. `text` is shown to the analyst as is."""

    layer: Layer
    code: str  # e.g. "pass_through", "fan_in_out", "baseline_amount"
    text: str
    strength: float = Field(ge=0, le=1)
    txn_ids: list[str] = Field(default_factory=list)
    counterfactual: str | None = None  # "Not flagged if ..."


class ShapValue(BaseModel):
    feature: str
    value: float  # feature value for this transaction
    contribution: float  # SHAP contribution in log-odds


class ScoredTransaction(Transaction):
    probability: float = Field(ge=0, le=1)
    confidence: float = Field(ge=0, le=1)
    layer_scores: dict[Layer, float]
    reasons: list[Reason] = Field(default_factory=list)
    is_alert: bool = False
    case_id: str | None = None


class CaseSummary(BaseModel):
    case_id: str
    tier: Tier
    probability: float = Field(ge=0, le=1)  # highest in the case
    amount_at_risk: float
    expected_loss: float  # probability x amount_at_risk; the queue sorts by tier, then this
    accounts: int
    transactions: int
    typologies: list[str]
    opened_at: datetime
    updated_at: datetime
    status: str = "open"  # open | confirmed | dismissed


class GraphNode(BaseModel):
    id: str
    label: str
    role: str  # source | mule | collector | victim | other
    risk: float = Field(ge=0, le=1)


class GraphEdge(BaseModel):
    txn_id: str
    source: str
    target: str
    amount: float
    ts: datetime


class AccountProfile(BaseModel):
    account_id: str
    persona: str | None = None
    opened_days_ago: int | None = None
    median_amount_30d: float | None = None
    txns_30d: int | None = None
    devices: list[str] = Field(default_factory=list)


class CaseDetail(CaseSummary):
    reasons: list[Reason]
    shap: list[ShapValue]
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    timeline: list[ScoredTransaction]
    profiles: list[AccountProfile]
    narrative: str | None = None  # AI-written, verified against the case facts; None if the LLM failed
    str_due: datetime | None = None  # STR deadline once confirmed (7 working days)


class BudgetPoint(BaseModel):
    alerts_per_day: int
    recall: float
    precision: float
    value_caught_share: float


class MetricRow(BaseModel):
    name: str  # model variant or typology
    precision: float
    recall: float
    pr_auc: float | None = None
    precision_at_50: float | None = None


class EvalReport(BaseModel):
    dataset: str
    split: str
    generated_at: datetime
    overall: MetricRow
    baseline: MetricRow  # single-transaction baseline
    ablation: list[MetricRow]
    per_typology: list[MetricRow]
    budget_curve: list[BudgetPoint]
    suggested_budget: int
    throughput_tps: float | None = None
    p95_latency_ms: float | None = None
    notes: list[str] = Field(default_factory=list)


class Feedback(BaseModel):
    verdict: str = Field(pattern="^(confirmed|dismissed)$")
    note: str | None = None


class FeedbackResult(BaseModel):
    case_id: str
    status: str
    weights_before: dict[Layer, float]
    weights_after: dict[Layer, float]
    requeued: int  # cases whose rank changed


class StreamEvent(BaseModel):
    """One WebSocket message on /ws/stream."""

    type: str  # "txn" | "case" | "stats"
    txn: ScoredTransaction | None = None
    case: CaseSummary | None = None
    stats: dict[str, float] | None = None


class TaintHolding(BaseModel):
    """Money an account in a case holds right now that traces back to the victims' payments."""

    account_id: str
    received: float  # total received within the case's money trail
    sent: float
    tainted: float  # still held, traceable to victims (haircut method)
    tainted_share: float = Field(ge=0, le=1)  # tainted / funds held


class FreezeAction(BaseModel):
    account_id: str
    recoverable: float  # tainted funds a freeze would hold now
    collateral_cost: float  # how disruptive a freeze is: higher for accounts with more ordinary activity
    reason: str


class RecoveryPoint(BaseModel):
    ts: datetime
    recoverable: float  # tainted money still inside the case's accounts at this time
    escaped: float  # tainted money that had left to accounts outside the trail


class InterdictionPlan(BaseModel):
    case_id: str
    as_of: datetime
    stolen: float  # money that entered the trail from outside (the victims' payments)
    victims: list[str]
    holdings: list[TaintHolding]
    freeze: list[FreezeAction]  # the recommended freeze set, a minimum cut between victims and exits
    recoverable_now: float  # tainted funds held by the freeze set
    escaped: float  # tainted funds already outside the trail
    first_alert_at: datetime | None = None
    recoverable_at_first_alert: float | None = None  # how much a freeze at Ripple's first alert would have held
    recoverable_share_at_first_alert: float | None = None  # that amount over the traced money that had entered by then
    timeline: list[RecoveryPoint]
    method: str
