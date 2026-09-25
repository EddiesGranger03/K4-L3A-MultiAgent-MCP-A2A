from __future__ import annotations

from copy import deepcopy
from typing import Any

import pytest

from student_agent.workflow import CLAIM_TOOLS, _verified_topic

CASE = {"opened_at": "2024-01-10T12:00:00+00:00"}


def _evidence(topic: str) -> dict[str, dict[str, Any]]:
    evidence = {tool: {"data": {}} for tool in CLAIM_TOOLS[topic]}
    evidence["get_order"] = {
        "data": {
            "order_status": "delivered",
            "order_purchase_timestamp": "2024-01-01T09:00:00+00:00",
            "order_delivered_carrier_date": "2024-01-02T09:00:00+00:00",
            "order_estimated_delivery_date": "2024-01-05T09:00:00+00:00",
            "order_delivered_customer_date": "2024-01-04T09:00:00+00:00",
        }
    }
    evidence["get_order_items"] = {
        "data": [{"order_item_id": "item-1", "price": 90, "freight_value": 10}]
    }
    evidence["get_order_payments"] = {
        "data": [
            {"payment_sequential": 1, "payment_type": "credit_card", "payment_value": 60},
            {"payment_sequential": 2, "payment_type": "voucher", "payment_value": 40},
        ]
    }
    return evidence


def _capture(identity: str, amount: int) -> dict[str, Any]:
    return {
        "event_id": identity,
        "capture_id": identity,
        "event_type": "captured",
        "status": "confirmed",
        "event_at": "2024-01-01T10:00:00+00:00",
        "amount_brl": amount,
    }


def _refund(status: str, day: int) -> dict[str, Any]:
    return {
        "event_id": f"refund-event-{day}",
        "refund_id": "refund-1",
        "event_type": "refund_status_changed",
        "status": status,
        "event_at": f"2024-01-{day:02}T10:00:00+00:00",
        "amount_brl": 100,
    }


@pytest.mark.parametrize(
    ("topic", "events", "expected"),
    [
        ("refund_pending", [_refund("pending", 2), _refund("completed", 3)], "unsupported"),
        ("refund_failed", [_refund("failed", 2), _refund("pending", 3)], "unsupported"),
        ("refund_pending", [_refund("failed", 2), _refund("pending", 3)], "supported"),
    ],
)
def test_refund_verdict_uses_latest_status_before_case_opened(
    topic: str, events: list[dict[str, Any]], expected: str
) -> None:
    evidence = _evidence(topic)
    # Responses need not be sorted, and future events must not replace the visible state.
    evidence["get_refund_timeline"] = {
        "data": {"events": [_refund("failed", 12), *reversed(events)]}
    }

    assert _verified_topic(topic, CASE, evidence) == expected


@pytest.mark.parametrize("second_amount", [30, 50])
def test_split_payment_requires_captured_total_to_match_items(second_amount: int) -> None:
    evidence = _evidence("valid_split_payment")
    evidence["get_payment_timeline"] = {
        "data": {"events": [_capture("capture-1", 60), _capture("capture-2", second_amount)]}
    }

    assert _verified_topic("valid_split_payment", CASE, evidence) == "unsupported"


def test_split_payment_accepts_two_distinct_captures_covering_order_total() -> None:
    evidence = _evidence("valid_split_payment")
    evidence["get_payment_timeline"] = {
        "data": {"events": [_capture("capture-1", 60), _capture("capture-2", 40)]}
    }

    assert _verified_topic("valid_split_payment", CASE, evidence) == "supported"


def test_replayed_capture_is_not_a_second_charge() -> None:
    evidence = _evidence("duplicate_charge")
    capture = _capture("capture-1", 100)
    evidence["get_payment_timeline"] = {
        "data": {"events": [capture, deepcopy(capture)]}
    }

    assert _verified_topic("duplicate_charge", CASE, evidence) == "unsupported"


def test_conflicting_item_totals_cannot_be_resolved_by_choosing_maximum() -> None:
    evidence = _evidence("duplicate_charge")
    evidence["get_order_items"]["data"].append(
        {"order_item_id": "item-1", "price": 190, "freight_value": 10}
    )
    evidence["get_payment_timeline"] = {
        "data": {"events": [_capture("capture-1", 100), _capture("capture-2", 50)]}
    }

    # Captured 150 is excessive if the total is 100, but not if it is 200.
    assert _verified_topic("duplicate_charge", CASE, evidence) == "insufficient_evidence"


def test_late_logistics_delivery_is_supported_after_delivery_completed() -> None:
    evidence = _evidence("late_delivery_logistics")
    evidence["get_order"]["data"]["order_delivered_customer_date"] = (
        "2024-01-07T09:00:00+00:00"
    )
    evidence["get_shipment_summary"] = {
        "data": {
            "shipping_limits": [
                {"order_item_id": "item-1", "shipping_limit_at": "2024-01-03T09:00:00+00:00"}
            ],
            "events": [],
        }
    }

    assert _verified_topic("late_delivery_logistics", CASE, evidence) == "supported"
