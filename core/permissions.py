"""Who may do what. One can() check runs before every action, and the gateway logs every answer."""

from __future__ import annotations

from dataclasses import dataclass, field

from .model import (
    AGENT, APPROVED, COLLECTIONS_REFERRAL, COMPLIANCE, COUNSELOR, DIRECTOR, DISCOUNT,
    FREE_CARE, GATEWAY, MERGE_ACCOUNTS, NEW_RULE, PAYMENT_PLAN, REVERSAL, SAFE_KINDS,
    STAFF_ROLES, SYNC,
)

READ = "read"
OPEN_WORK_ITEM = "open_work_item"
MOVE_WORK_ITEM = "move_work_item"
PROPOSE = "propose"
ASK = "ask"
ANSWER = "answer"
ACT_SAFE = "act_safe"
APPROVE = "approve"
REJECT = "reject"
POST = "post"

COUNSELOR_LIMIT_CENTS = 5_000_00

ADJUSTMENTS = frozenset({FREE_CARE, DISCOUNT, PAYMENT_PLAN, MERGE_ACCOUNTS})
DECIDES = {
    COUNSELOR: ADJUSTMENTS,
    DIRECTOR: ADJUSTMENTS | {COLLECTIONS_REFERRAL, NEW_RULE},
    COMPLIANCE: frozenset({REVERSAL}),
}


@dataclass(frozen=True)
class Actor:
    id: str
    role: str
    name: str = ""
    patient_ids: frozenset[str] = field(default_factory=frozenset)  # patient records that are this person


@dataclass(frozen=True)
class Resource:
    kind: str | None = None             # proposal kind, when there is one
    account_id: str | None = None
    patient_id: str | None = None
    amount_cents: int = 0
    proposed_by: str | None = None
    legal_question: bool = False        # about how the law applies: compliance decides
    status: str | None = None


@dataclass(frozen=True)
class Decision:
    allowed: bool
    reason: str

    def __bool__(self) -> bool:
        return self.allowed


def allow(reason: str) -> Decision:
    return Decision(True, reason)


def deny(reason: str) -> Decision:
    return Decision(False, reason)


def can(actor: Actor, action: str, resource: Resource = Resource()) -> Decision:
    role = actor.role

    if action == READ:
        return allow("Everyone can read.")

    if action == OPEN_WORK_ITEM:
        return allow("The sync job opens work items.") if role == SYNC else deny("Only the sync job opens work items.")

    if action == MOVE_WORK_ITEM:
        if role in (SYNC, AGENT):
            return allow(f"The {role} moves work items while working them.")
        return deny("Only the sync job and the agent move work items.")

    if action in (PROPOSE, ASK):
        if role in (AGENT, *STAFF_ROLES):
            return allow(f"The {role} can {action}.")
        return deny(f"A {role} can't {action}.")

    if action == ANSWER:
        return allow("Staff answer questions.") if role in STAFF_ROLES else deny("Only staff answer questions.")

    if action == ACT_SAFE:
        if resource.kind not in SAFE_KINDS:
            return deny(f"{resource.kind} is not a safe action; it needs an approval.")
        if role in (AGENT, *STAFF_ROLES):
            return allow("Stopping a collection is always safe, so it needs no approval.")
        return deny(f"A {role} can't stop collections.")

    if action in (APPROVE, REJECT):
        return _can_decide(actor, action, resource)

    if action == POST:
        if role != GATEWAY:
            return deny("Only the gateway posts changes.")
        if resource.status != APPROVED:
            return deny(f"Only approved proposals are posted; this one is {resource.status}.")
        return allow("Approved, so the gateway posts it.")

    return deny(f"Unknown action {action}.")


def _can_decide(actor: Actor, action: str, resource: Resource) -> Decision:
    role = actor.role
    if role not in STAFF_ROLES:
        return deny(f"The AI proposes and never approves. A {role} can't {action}.")
    if resource.proposed_by == actor.id:
        return deny(f"Whoever proposes something can never {action} it.")
    if resource.patient_id and resource.patient_id in actor.patient_ids:
        return deny(f"Nobody can {action} their own account.")
    if resource.legal_question:
        if role != COMPLIANCE:
            return deny("This is about how the law applies, so only the compliance officer decides it.")
        return allow("The compliance officer decides how the law applies.")
    if resource.kind not in DECIDES[role]:
        return deny(f"A {role} can't {action} {resource.kind}.")
    if role == COUNSELOR and resource.amount_cents > COUNSELOR_LIMIT_CENTS:
        return deny(f"Over the counselor's ${COUNSELOR_LIMIT_CENTS // 100:,} limit; the director decides.")
    return allow(f"Within the {role}'s limits.")
