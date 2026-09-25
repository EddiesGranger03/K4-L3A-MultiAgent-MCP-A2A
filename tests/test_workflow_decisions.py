from __future__ import annotations

import asyncio

from student_agent.workflow import (
    _claim_refs,
    _confidence,
    _normalize_parties,
    _verified_topic,
    solve_case,
)


def test_unsupported_shipping_claim_ignores_event_after_case_opened() -> None:
    case = {"opened_at": "2018-01-10T09:00:00-03:00"}
    evidence = {
        "get_order": {
            "data": {
                "order_status": "delivered",
                "order_delivered_customer_date": "2018-01-07T09:00:00-03:00",
                "order_estimated_delivery_date": "2018-01-08T09:00:00-03:00",
            }
        },
        "get_order_items": {"data": []},
        "get_shipment_summary": {
            "data": {
                "delivered_customer_at": "2018-01-07T09:00:00-03:00",
                "estimated_delivery_at": "2018-01-08T09:00:00-03:00",
                "events": [
                    {
                        "event_at": "2018-05-17T09:00:00-03:00",
                        "event_type": "delivered_late",
                        "actor": "logistics_provider",
                        "status": "confirmed",
                    }
                ],
            }
        },
        "get_policy": {"data": {}},
    }
    assert _verified_topic("unsupported_claim", case, evidence) == "unsupported"
    del evidence["get_shipment_summary"]
    assert _verified_topic("unsupported_claim", case, evidence) == "insufficient_evidence"


def test_claim_refs_include_only_requested_evidence() -> None:
    evidence = {
        "get_order": {"evidence_ref": "ev_order"},
        "get_order_payments": {"evidence_ref": "ev_payment"},
        "get_shipment_summary": {"evidence_ref": "ev_shipment"},
    }
    assert _claim_refs(("get_order", "get_shipment_summary"), evidence) == [
        "ev_order",
        "ev_shipment",
    ]


def test_shipping_claim_rejects_conflicting_confirmed_shipment_event() -> None:
    case = {"opened_at": "2018-01-10T09:00:00-03:00"}
    evidence = {
        "get_order": {
            "data": {
                "order_delivered_customer_date": "2018-01-07T09:00:00-03:00",
                "order_estimated_delivery_date": "2018-01-08T09:00:00-03:00",
            }
        },
        "get_order_items": {"data": []},
        "get_shipment_summary": {
            "data": {
                "delivered_customer_at": "2018-01-07T09:00:00-03:00",
                "estimated_delivery_at": "2018-01-08T09:00:00-03:00",
                "events": [
                    {
                        "event_at": "2018-01-08T09:00:00-03:00",
                        "event_type": "delivered_late",
                        "status": "confirmed",
                    }
                ],
            }
        },
        "get_policy": {"data": {}},
    }
    assert _verified_topic("unsupported_claim", case, evidence) == "insufficient_evidence"


def test_shipping_claim_ignores_event_before_order_purchase() -> None:
    case = {"opened_at": "2018-04-13T09:00:00-03:00"}
    evidence = {
        "get_order": {
            "data": {
                "order_purchase_timestamp": "2018-04-01T09:00:00-03:00",
                "order_delivered_customer_date": "2018-04-10T09:00:00-03:00",
                "order_estimated_delivery_date": "2018-04-11T09:00:00-03:00",
            }
        },
        "get_order_items": {"data": []},
        "get_shipment_summary": {
            "data": {
                "delivered_customer_at": "2018-04-10T09:00:00-03:00",
                "estimated_delivery_at": "2018-04-11T09:00:00-03:00",
                "events": [
                    {
                        "event_at": "2018-02-14T09:00:00-03:00",
                        "event_type": "delivered_late",
                        "status": "confirmed",
                    }
                ],
            }
        },
        "get_policy": {"data": {}},
    }
    assert _verified_topic("unsupported_claim", case, evidence) == "unsupported"


def test_shipping_claim_ignores_delivery_event_before_actual_delivery() -> None:
    case = {"opened_at": "2018-08-26T09:00:00-03:00"}
    evidence = {
        "get_order": {
            "data": {
                "order_purchase_timestamp": "2018-08-14T09:00:00-03:00",
                "order_delivered_customer_date": "2018-08-23T09:00:00-03:00",
                "order_estimated_delivery_date": "2018-08-24T09:00:00-03:00",
            }
        },
        "get_order_items": {"data": []},
        "get_shipment_summary": {
            "data": {
                "delivered_customer_at": "2018-08-23T09:00:00-03:00",
                "estimated_delivery_at": "2018-08-24T09:00:00-03:00",
                "events": [
                    {
                        "event_at": "2018-08-20T09:00:00-03:00",
                        "event_type": "delivered_late",
                        "status": "confirmed",
                    }
                ],
            }
        },
        "get_policy": {"data": {}},
    }
    assert _verified_topic("unsupported_claim", case, evidence) == "unsupported"


def test_case_refs_exclude_unused_payment_evidence() -> None:
    called_tools = []
    trace_events = []

    class Gateway:
        async def call(self, tool_name: str, **_: str) -> dict:
            called_tools.append(tool_name)
            data = {
                "get_order": {
                    "order_status": "delivered",
                    "order_purchase_timestamp": "2018-01-01T09:00:00-03:00",
                    "order_delivered_carrier_date": "2018-01-02T09:00:00-03:00",
                    "order_estimated_delivery_date": "2018-01-05T09:00:00-03:00",
                    "order_delivered_customer_date": "2018-01-07T09:00:00-03:00",
                },
                "get_order_items": [
                    {"order_item_id": "item-1", "seller_id": "seller-1", "price": 90}
                ],
                "get_order_payments": [
                    {"payment_sequential": 1, "payment_value": 100},
                    {"payment_sequential": 1, "payment_value": 150},
                ],
                "get_shipment_summary": {
                    "shipping_limits": [{"shipping_limit_at": "2018-01-03T09:00:00-03:00"}],
                    "events": [],
                },
                "get_policy": {
                    "rules": {
                        "late_delivery_logistics": {
                            "case_status": "resolved",
                            "refund_brl": 0,
                            "recommended_action": "no_refund",
                            "responsible_parties": [
                                {"party_type": "logistics_provider", "party_id": None}
                            ],
                        }
                    }
                },
            }
            return {"evidence_ref": f"ev_{tool_name}", "data": data[tool_name]}

    class Trace:
        def emit(self, **event: object) -> None:
            trace_events.append(event)

    case = {
        "case_id": "L3A_CASE_TEST",
        "opened_at": "2018-01-10T09:00:00-03:00",
        "policy_version": "EC_POLICY_V1",
        "customer_request": {
            "claimed_order_id": "order-1",
            "claims": [{"claim_id": "claim-a", "topic": "late_delivery_logistics"}],
        },
    }
    output = asyncio.run(solve_case(case, Gateway(), Trace()))
    assert "get_order_payments" not in called_tools
    assert "ev_get_order_payments" not in output["evidence_refs"]
    assert not any(
        conflict["field"].endswith("payment_value") for conflict in output["data_conflicts"]
    )
    assert set(output["claim_assessments"][0]["evidence_refs"]).issubset(output["evidence_refs"])
    positions = {
        (event["event_type"], event.get("actor"), event.get("target")): index
        for index, event in enumerate(trace_events)
    }
    assert (
        positions[("handoff", "shipment-agent", "coordinator")]
        < positions[("policy_decided", "policy-agent", None)]
    )
    assert (
        positions[("policy_decided", "policy-agent", None)]
        < positions[("handoff", "coordinator", "verifier")]
    )
    assert (
        positions[("verification_completed", "verifier", None)]
        < positions[("handoff", "verifier", "coordinator")]
    )
    assert all(
        event.get("tool_name") in called_tools
        for event in trace_events
        if event["event_type"] == "task_assigned"
    )


def test_seller_id_must_come_from_order_and_seller_evidence() -> None:
    evidence = {
        "get_order_items": {"data": [{"seller_id": "seller-for-this-order"}]},
        "get_sellers": {"data": [{"seller_id": "seller-for-this-order"}]},
    }
    parties, conflicts = _normalize_parties(
        [{"party_type": "seller", "party_id": "seller-from-another-order"}], evidence
    )
    assert parties == [{"party_type": "seller", "party_id": "seller-for-this-order"}]
    assert conflicts[0]["resolution_code"] == "POLICY_SELLER_ID_MISMATCH"


def test_confidence_changes_only_for_relevant_conflicts() -> None:
    conflicts = [
        {"field": "item-1.freight_value"},
        {"field": "1.payment_value"},
    ]
    assert _confidence("payment_mismatch", conflicts) == 0.93
    assert _confidence("unsupported_claim", conflicts) == 0.95
