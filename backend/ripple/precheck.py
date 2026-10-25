"""Pre-payment check: score a payment before the bank executes it, and say what to do with it.

The bank calls POST /check at authorisation, before money moves. Ripple scores the payment with every layer, against
the accounts' current history, without recording it, and answers one of three decisions:

    allow           below the alert score: the payment goes through
    cooling_off     unusual enough to alert: hold it for COOLING_OFF_MINUTES and tell the customer, who can release it
    hold_and_call   Critical, or a customer being coached into draining their savings (coerced transfer): hold it
                    and call the customer or their trusted contact before it is released

A hold is a pause, not a refusal: the customer keeps control of their money, and an honest payment still goes.
"""

from __future__ import annotations

from ripple.fmt import money
from ripple.schema import ScoredTransaction, Tier

COOLING_OFF_MINUTES = 60


def decide(scored: ScoredTransaction, tiers: dict) -> tuple[str, str, Tier | None, int | None, str | None]:
    """Returns (decision, headline, tier, hold minutes, message to the customer)."""
    p = scored.probability
    tier = Tier.CRITICAL if p >= tiers["critical"] else Tier.REVIEW if p >= tiers["review"] else (
        Tier.WATCH if p >= tiers["alert"] else None)
    amount = money(scored.amount, scored.currency)
    coerced = any(r.code == "coerced_transfer" for r in scored.reasons)
    if coerced or tier == Tier.CRITICAL:
        why = ("This looks like a customer being coached to move their savings." if coerced
               else "This payment matches a known fraud pattern.")
        message = (f"We have paused your payment of {amount} to {scored.dst_account} and will call you before it goes. "
                   "Police, CBI, customs and courts never ask you to move money to a 'safe account'. "
                   "If someone is on a call telling you to pay, hang up and call 1930.")
        return "hold_and_call", f"Hold and call the customer. {why}", tier, None, message
    if tier is not None:
        message = (f"We have paused your payment of {amount} to {scored.dst_account} for {COOLING_OFF_MINUTES} minutes "
                   "because it is unusual for your account. Reply YES or call us to release it now.")
        return ("cooling_off", f"Pause it for {COOLING_OFF_MINUTES} minutes and let the customer confirm.", tier,
                COOLING_OFF_MINUTES, message)
    return "allow", "Let it through. Nothing here looks like fraud.", None, None, None
