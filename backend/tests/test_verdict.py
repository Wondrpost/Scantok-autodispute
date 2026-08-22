"""Truth-table tests. Pure logic - no model, no GPU, no media files."""

import pytest

from app.agent_vision import (
    STATUS_DAMAGED,
    STATUS_INVALID,
    STATUS_NOT_OBSERVED,
    STATUS_SAFE,
)
from app.main import (
    VERDICT_BUYER_FRAUD,
    VERDICT_COURIER_FAULT,
    VERDICT_INVALID_EVIDENCE,
    VERDICT_NO_DAMAGE,
    VERDICT_PRODUCT_ONLY,
    VERDICT_SELLER_FAULT,
    VERDICT_TAMPERING,
    resolve_verdict,
)


@pytest.mark.parametrize(
    "seller,courier,buyer_pkg,expected,liable",
    [
        (STATUS_DAMAGED, STATUS_SAFE, STATUS_SAFE, VERDICT_SELLER_FAULT, "seller"),
        (STATUS_DAMAGED, STATUS_DAMAGED, STATUS_DAMAGED, VERDICT_SELLER_FAULT, "seller"),
        (STATUS_SAFE, STATUS_DAMAGED, STATUS_SAFE, VERDICT_COURIER_FAULT, "courier"),
        (STATUS_SAFE, STATUS_SAFE, STATUS_DAMAGED, VERDICT_BUYER_FRAUD, "buyer"),
        (STATUS_SAFE, STATUS_SAFE, STATUS_SAFE, VERDICT_NO_DAMAGE, "none"),
    ],
)
def test_first_damaged_checkpoint_wins(seller, courier, buyer_pkg, expected, liable):
    decision = resolve_verdict(seller, courier, buyer_pkg)
    assert decision["verdict"] == expected
    assert decision["liable_party"] == liable


@pytest.mark.parametrize("role_index", [0, 1, 2])
def test_invalid_evidence_short_circuits(role_index):
    statuses = [STATUS_SAFE, STATUS_SAFE, STATUS_SAFE]
    statuses[role_index] = STATUS_INVALID
    decision = resolve_verdict(*statuses)
    assert decision["verdict"] == VERDICT_INVALID_EVIDENCE
    assert decision["requires_manual_review"] is True
    assert decision["claim_approved"] is False


def test_invalid_outranks_tampering():
    """Too few pre-open frames makes the tampering signal untrustworthy."""
    decision = resolve_verdict(
        STATUS_SAFE, STATUS_SAFE, STATUS_INVALID, tampering_suspected=True
    )
    assert decision["verdict"] == VERDICT_INVALID_EVIDENCE


def test_tampering_outranks_damage_waterfall():
    decision = resolve_verdict(
        STATUS_DAMAGED, STATUS_SAFE, STATUS_SAFE, tampering_suspected=True
    )
    assert decision["verdict"] == VERDICT_TAMPERING
    assert decision["requires_manual_review"] is True


def test_product_damage_alone_escalates_never_accuses():
    decision = resolve_verdict(
        STATUS_SAFE, STATUS_SAFE, STATUS_SAFE, buyer_product=STATUS_DAMAGED
    )
    assert decision["verdict"] == VERDICT_PRODUCT_ONLY
    assert decision["liable_party"] == "unknown"
    assert decision["requires_manual_review"] is True


def test_product_status_never_overrides_exterior_chain():
    """A damaged exterior at the buyer's point outranks the product axis."""
    decision = resolve_verdict(
        STATUS_SAFE, STATUS_SAFE, STATUS_DAMAGED, buyer_product=STATUS_DAMAGED
    )
    assert decision["verdict"] == VERDICT_BUYER_FRAUD


def test_unobserved_product_is_not_damage():
    decision = resolve_verdict(
        STATUS_SAFE, STATUS_SAFE, STATUS_SAFE, buyer_product=STATUS_NOT_OBSERVED
    )
    assert decision["verdict"] == VERDICT_NO_DAMAGE


def test_every_branch_sets_required_keys():
    required = {"verdict", "claim_approved", "liable_party", "requires_manual_review", "reasoning"}
    cases = [
        (STATUS_INVALID, STATUS_SAFE, STATUS_SAFE, STATUS_NOT_OBSERVED, False),
        (STATUS_SAFE, STATUS_SAFE, STATUS_SAFE, STATUS_NOT_OBSERVED, True),
        (STATUS_DAMAGED, STATUS_SAFE, STATUS_SAFE, STATUS_NOT_OBSERVED, False),
        (STATUS_SAFE, STATUS_DAMAGED, STATUS_SAFE, STATUS_NOT_OBSERVED, False),
        (STATUS_SAFE, STATUS_SAFE, STATUS_DAMAGED, STATUS_NOT_OBSERVED, False),
        (STATUS_SAFE, STATUS_SAFE, STATUS_SAFE, STATUS_DAMAGED, False),
        (STATUS_SAFE, STATUS_SAFE, STATUS_SAFE, STATUS_NOT_OBSERVED, False),
    ]
    for seller, courier, buyer_pkg, product, tampering in cases:
        assert required <= set(resolve_verdict(seller, courier, buyer_pkg, product, tampering))
