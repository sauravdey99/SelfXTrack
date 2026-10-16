"""Subscription plans (Phase 4). Limits are enforced on the server.
SOS to family + Call 112 + school always works, even if a payment fails."""
from datetime import datetime, timedelta, timezone

from .config import settings
from .models import User

PLAN_RANK = {"basic": 0, "smart": 1, "guardian": 2}

PLANS = {
    "basic": {"name": "Basic", "monthly": 199, "yearly": 1999, "history_days": 7, "family": 2,
              "features": ["Live location, safe zones, offline alert, live link", "SOS → family + Call 112",
                           "7-day history", "2 family members"]},
    "smart": {"name": "Smart", "monthly": 299, "yearly": 2999, "history_days": 30, "family": 5,
              "features": ["Everything in Basic", "Emergency – School + Emergency – Group (helpers nearby)",
                           "AI: usual routes, unusual route / stop alerts, ETA, daily summary, assistant",
                           "30-day history calendar", "5 family members"]},
    "guardian": {"name": "Guardian", "monthly": 499, "yearly": 4999, "history_days": 30, "family": 8,
                 "features": ["Everything in Smart",
                              "Emergency risk prompt (fast + off-route + late)", "Incident report for police / school",
                              "8 family members"]},
}

FEATURE_MIN_PLAN = {"school": "smart", "group": "smart", "ai": "smart", "risk": "guardian", "report": "guardian"}


def effective_plan(user: User) -> str:
    """Paid plan while active; after expiry + grace period the account falls back to Basic."""
    plan = user.plan or "basic"
    exp = user.plan_expires_at
    if exp is not None:
        if exp.tzinfo is None:
            exp = exp.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) > exp + timedelta(days=settings.grace_days):
            return "basic"
    return plan


def rank(plan: str) -> int:
    return PLAN_RANK.get(plan, 0)


def allows(plan: str, feature: str) -> bool:
    return rank(plan) >= rank(FEATURE_MIN_PLAN[feature])
