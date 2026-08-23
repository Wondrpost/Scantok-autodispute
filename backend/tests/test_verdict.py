"""Truth-table tests. Pure logic - no model, no GPU, no media files."""

import pytest

from app.agent_vision import (
    DAMAGE_MIN_HITS,
    DAMAGE_MIN_RATIO,
    STATUS_DAMAGED,
    STATUS_INVALID,
    STATUS_NOT_OBSERVED,
    STATUS_SAFE,
    _is_damaged,
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


def test_damage_needs_both_floor_and_ratio():
    """1 of 4 frames clears no bar; 6 of 15 clears both."""
    assert _is_damaged(1, 4) is False        # ratio 0.25, and below the floor
    assert _is_damaged(2, 15) is False       # meets floor, ratio only 0.13
    assert _is_damaged(6, 15) is True        # floor met, ratio 0.40
    assert _is_damaged(3, 90) is False       # sparse noise in a long clip


def test_damage_verdict_is_scale_invariant():
    """The same proportion decides the same way at any window length."""
    for total in (10, 20, 60):
        hits = int(total * (DAMAGE_MIN_RATIO + 0.1))
        assert _is_damaged(hits, total) is True
        assert _is_damaged(int(total * (DAMAGE_MIN_RATIO - 0.1)), total) is False


def test_single_frame_photo_can_still_be_damaged():
    """A still has one observation: ratio 1.0, and min_hits is passed as 1."""
    assert _is_damaged(1, 1, min_hits=1) is True
    assert _is_damaged(0, 1, min_hits=1) is False


def test_damage_on_empty_window_is_never_true():
    assert _is_damaged(0, 0) is False
    assert _is_damaged(DAMAGE_MIN_HITS, 0) is False


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
