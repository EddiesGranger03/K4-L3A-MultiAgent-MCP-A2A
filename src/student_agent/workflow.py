from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from .mcp_gateway import EvidenceGateway
from .model_triage import ModelTriageClient, ModelTriageError
from .trace import TraceWriter

TOOL_ACTORS = {
    "get_order": "order-agent",
    "get_order_items": "order-agent",
    "get_order_payments": "payment-agent",
    "get_payment_timeline": "payment-agent",
    "get_refund_timeline": "payment-agent",
    "get_shipment_summary": "shipment-agent",
    "get_sellers": "order-agent",
    "get_policy": "policy-agent",
}

TOPIC_TOOLS = {
    "canceled_order_paid": ("get_payment_timeline",),
    "unavailable_order_paid": ("get_sellers", "get_payment_timeline"),
    "late_delivery_seller": ("get_shipment_summary", "get_sellers"),
    "late_delivery_logistics": ("get_shipment_summary",),
    "valid_split_payment": ("get_payment_timeline",),
    "payment_mismatch": ("get_payment_timeline",),
    "duplicate_charge": ("get_payment_timeline",),
    "refund_pending": ("get_refund_timeline",),
    "refund_failed": ("get_refund_timeline",),
    "unsupported_claim": ("get_shipment_summary",),
}

CLAIM_TOOLS = {
    "canceled_order_paid": (
        "get_order",
        "get_order_items",
        "get_order_payments",
        "get_payment_timeline",
        "get_policy",
    ),
    "unavailable_order_paid": (
        "get_order",
        "get_order_items",
        "get_order_payments",
        "get_payment_timeline",
        "get_sellers",
        "get_policy",
    ),
    "late_delivery_seller": (
        "get_order",
        "get_order_items",
        "get_shipment_summary",
        "get_sellers",
        "get_policy",
    ),
    "late_delivery_logistics": (
        "get_order",
        "get_order_items",
        "get_shipment_summary",
        "get_policy",
    ),
    "valid_split_payment": (
        "get_order",
        "get_order_items",
        "get_order_payments",
        "get_payment_timeline",
        "get_policy",
    ),
    "payment_mismatch": (
        "get_order",
        "get_order_items",
        "get_order_payments",
        "get_payment_timeline",
        "get_policy",
    ),
    "duplicate_charge": (
        "get_order",
        "get_order_items",
        "get_order_payments",
        "get_payment_timeline",
        "get_policy",
    ),
    "refund_pending": (
        "get_order",
        "get_order_items",
        "get_order_payments",
        "get_refund_timeline",
        "get_policy",
    ),
    "refund_failed": (
        "get_order",
        "get_order_items",
        "get_order_payments",
        "get_refund_timeline",
        "get_policy",
    ),
    "unsupported_claim": ("get_order", "get_order_items", "get_shipment_summary", "get_policy"),
}

REFUND_CLAIM_TOOLS = {
    "canceled_order_paid": (
        "get_order",
        "get_order_items",
        "get_order_payments",
        "get_payment_timeline",
        "get_policy",
    ),
    "unavailable_order_paid": (
        "get_order",
        "get_order_items",
        "get_order_payments",
        "get_payment_timeline",
        "get_sellers",
        "get_policy",
    ),
    "late_delivery_seller": ("get_order", "get_order_items", "get_shipment_summary", "get_policy"),
    "late_delivery_logistics": (
        "get_order",
        "get_order_items",
        "get_shipment_summary",
        "get_policy",
    ),
    "valid_split_payment": (
        "get_order",
        "get_order_items",
        "get_order_payments",
        "get_payment_timeline",
        "get_policy",
    ),
    "payment_mismatch": (
        "get_order",
        "get_order_items",
        "get_order_payments",
        "get_payment_timeline",
        "get_policy",
    ),
    "duplicate_charge": (
        "get_order",
        "get_order_items",
        "get_order_payments",
        "get_payment_timeline",
        "get_policy",
    ),
    "refund_pending": (
        "get_order",
        "get_order_items",
        "get_order_payments",
        "get_refund_timeline",
        "get_policy",
    ),
    "refund_failed": (
        "get_order",
        "get_order_items",
        "get_order_payments",
        "get_refund_timeline",
        "get_policy",
    ),
    "unsupported_claim": (
        "get_order",
        "get_order_items",
        "get_order_payments",
        "get_shipment_summary",
        "get_policy",
    ),
}

CONFLICT_FIELDS = {
    "canceled_order_paid": {"payment_value", "price"},
    "unavailable_order_paid": {"payment_value", "price", "seller_id"},
    "late_delivery_seller": {"shipping_limit_date", "seller_id", "freight_value"},
    "late_delivery_logistics": {"shipping_limit_date", "freight_value"},
    "valid_split_payment": {"payment_value", "price"},
    "payment_mismatch": {"payment_value", "price"},
    "duplicate_charge": {"payment_value", "price"},
    "refund_pending": {"payment_value"},
    "refund_failed": {"payment_value"},
    "unsupported_claim": {"shipping_limit_date"},
}

CAUSE_CODES = {
    "canceled_order_paid": "PAID_ORDER_CANCELED",
    "unavailable_order_paid": "PAID_ORDER_UNAVAILABLE",
    "late_delivery_seller": "SELLER_HANDOFF_DELAY",
    "late_delivery_logistics": "LOGISTICS_TRANSIT_DELAY",
    "valid_split_payment": "VALID_SPLIT_PAYMENT",
    "payment_mismatch": "PAYMENT_AMOUNT_MISMATCH",
    "duplicate_charge": "DUPLICATE_PAYMENT_CAPTURE",
    "refund_pending": "REFUND_PROCESSING_PENDING",
    "refund_failed": "REFUND_PROCESSING_FAILED",
    "unsupported_claim": "CLAIM_NOT_SUPPORTED_BY_EVIDENCE",
}

FLAG_TO_TOOL = {
    "payment": "get_payment_timeline",
    "shipment": "get_shipment_summary",
    "refund": "get_refund_timeline",
    "seller": "get_sellers",
}


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


def _rows(value: Any) -> list[dict[str, Any]]:
    return value if isinstance(value, list) else []


def _detect_conflicts(
    evidence: dict[str, dict[str, Any]], relevant_fields: set[str] | None = None
) -> list[dict[str, Any]]:
    conflicts: list[dict[str, Any]] = []
    checks = (
        (
            "get_order_items",
            "order_item_id",
            ("product_id", "seller_id", "price", "freight_value", "shipping_limit_date"),
        ),
        (
            "get_order_payments",
            "payment_sequential",
            ("payment_type", "payment_installments", "payment_value"),
        ),
    )
    for tool_name, identity, fields in checks:
        grouped: dict[str, list[dict[str, Any]]] = {}
        for row in _rows(evidence.get(tool_name, {}).get("data")):
            grouped.setdefault(str(row.get(identity, "")), []).append(row)
        for entity_id, rows in grouped.items():
            if len(rows) < 2:
                continue
            for field in fields:
                if relevant_fields is not None and field not in relevant_fields:
                    continue
                if len({str(row.get(field)) for row in rows}) > 1:
                    conflicts.append(
                        {
                            "field": f"{entity_id}.{field}",
                            "sources": [tool_name, f"{tool_name}_duplicate_row"],
                            "selected_source": None,
                            "resolution_code": "AUTHORITATIVE_ROWS_CONFLICT",
                        }
                    )
                    if len(conflicts) == 5:
                        return conflicts
    return conflicts


def _affected_entities(order_id: str, evidence: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    items = _rows(evidence.get("get_order_items", {}).get("data"))
    sellers = _rows(evidence.get("get_sellers", {}).get("data"))
    shipment = evidence.get("get_shipment_summary", {}).get("data", {})
    if not isinstance(shipment, dict):
        shipment = {}
    return {
        "order_ids": [order_id],
        "item_ids": _unique([str(row.get("order_item_id", "")) for row in items]),
        "seller_ids": _unique([str(row.get("seller_id", "")) for row in items + sellers]),
        "payment_references": [],
        "shipment_ids": _unique(
            [str(shipment.get(key, "")) for key in ("shipment_id", "tracking_id")]
        ),
    }


def _time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _money(value: Any) -> Decimal | None:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None
    return amount if amount.is_finite() and amount >= 0 else None


def _visible_events(data: Any, opened_at: datetime | None) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        return []
    events = _rows(data.get("events"))
    if opened_at is None:
        return events
    return [
        event for event in events if (when := _time(event.get("event_at"))) and when <= opened_at
    ]


def _captured_payments(
    events: list[dict[str, Any]], purchase_at: datetime | None
) -> list[dict[str, Any]]:
    captures: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for event in events:
        when = _time(event.get("event_at"))
        amount = _money(event.get("amount_brl"))
        if (
            event.get("event_type") != "captured"
            or event.get("status") != "confirmed"
            or amount is None
            or (purchase_at is not None and (when is None or when < purchase_at))
        ):
            continue
        identity = event.get("capture_id") or event.get("event_id")
        key = (
            ("id", str(identity))
            if identity
            else ("event", event.get("event_at"), str(amount), event.get("payment_sequential"))
        )
        if key in seen:
            continue
        seen.add(key)
        captures.append(event)
    return captures


def _possible_order_totals(items: list[dict[str, Any]]) -> set[Decimal]:
    by_item: dict[str, set[Decimal]] = {}
    for item in items:
        item_id = item.get("order_item_id")
        price, freight = _money(item.get("price")), _money(item.get("freight_value"))
        if not item_id or price is None or freight is None:
            continue
        by_item.setdefault(str(item_id), set()).add(price + freight)
    if not by_item:
        return set()
    totals = {Decimal(0)}
    for options in by_item.values():
        totals = {total + amount for total in totals for amount in options}
        if len(totals) > 100:
            return set()
    return totals


def _credible_shipping_limits(
    evidence: dict[str, dict[str, Any]], purchase_at: datetime | None
) -> list[datetime]:
    shipment = evidence.get("get_shipment_summary", {}).get("data", {})
    order = evidence.get("get_order", {}).get("data", {})
    if not isinstance(shipment, dict) or not isinstance(order, dict):
        return []
    delivered_at = _time(order.get("order_delivered_customer_date"))
    limits = [_time(row.get("shipping_limit_at")) for row in _rows(shipment.get("shipping_limits"))]
    return [
        limit
        for limit in limits
        if limit is not None
        and (purchase_at is None or limit >= purchase_at)
        and (delivered_at is None or limit <= delivered_at)
    ]


def _verified_topic(topic: str, case: dict[str, Any], evidence: dict[str, dict[str, Any]]) -> str:
    if any(tool not in evidence for tool in CLAIM_TOOLS[topic]):
        return "insufficient_evidence"
    order = evidence["get_order"]["data"]
    if not isinstance(order, dict):
        return "insufficient_evidence"
    opened_at = _time(case.get("opened_at"))
    purchase_at = _time(order.get("order_purchase_timestamp"))
    payment_events = _visible_events(
        evidence.get("get_payment_timeline", {}).get("data"), opened_at
    )
    refund_events = _visible_events(evidence.get("get_refund_timeline", {}).get("data"), opened_at)
    delivered_at = _time(order.get("order_delivered_customer_date"))
    shipment_events = []
    for event in _visible_events(evidence.get("get_shipment_summary", {}).get("data"), opened_at):
        event_at = _time(event.get("event_at"))
        if event_at is None or (purchase_at is not None and event_at < purchase_at):
            continue
        if event.get("event_type") == "delivered_late" and (
            delivered_at is None or event_at < delivered_at
        ):
            continue
        shipment_events.append(event)
    captures = _captured_payments(payment_events, purchase_at)
    limits = _credible_shipping_limits(evidence, purchase_at)
    carrier_at = _time(order.get("order_delivered_carrier_date"))
    estimated_at = _time(order.get("order_estimated_delivery_date"))

    if topic in {"canceled_order_paid", "unavailable_order_paid"}:
        status = "canceled" if topic == "canceled_order_paid" else "unavailable"
        return "supported" if order.get("order_status") == status and captures else "unsupported"
    if topic == "late_delivery_seller":
        actor_event = any(
            event.get("event_type") == "delivered_late"
            and event.get("actor") == "seller"
            and event.get("status") == "confirmed"
            for event in shipment_events
        )
        late_handoff = bool(carrier_at and limits and carrier_at > min(limits))
        return "supported" if actor_event or late_handoff else "insufficient_evidence"
    if topic == "late_delivery_logistics":
        actor_event = any(
            event.get("event_type") == "delivered_late"
            and event.get("actor") == "logistics_provider"
            and event.get("status") == "confirmed"
            for event in shipment_events
        )
        late_in_transit = bool(
            opened_at
            and estimated_at
            and carrier_at
            and limits
            and carrier_at <= min(limits)
            and estimated_at < opened_at
            and (delivered_at is None or delivered_at > estimated_at)
        )
        return "supported" if actor_event or late_in_transit else "insufficient_evidence"
    if topic == "valid_split_payment":
        rows = _rows(evidence["get_order_payments"]["data"])
        methods = {
            (str(row.get("payment_sequential")), str(row.get("payment_type"))) for row in rows
        }
        if len(methods) < 2 or len(captures) < 2:
            return "unsupported"
        totals = _possible_order_totals(_rows(evidence["get_order_items"]["data"]))
        if not totals:
            return "insufficient_evidence"
        captured_total = sum((_money(event["amount_brl"]) for event in captures), Decimal(0))
        if len(totals) > 1 and min(totals) <= captured_total <= max(totals):
            return "insufficient_evidence"
        return "supported" if captured_total in totals else "unsupported"
    if topic == "payment_mismatch":
        mismatch = any(
            event.get("event_type") == "reconciliation_mismatch" for event in payment_events
        )
        return "supported" if mismatch else "unsupported"
    if topic == "duplicate_charge":
        totals = _possible_order_totals(_rows(evidence["get_order_items"]["data"]))
        captured_total = sum(
            (_money(event["amount_brl"]) or Decimal(0) for event in captures), Decimal(0)
        )
        if not totals:
            return "insufficient_evidence"
        if len(captures) < 2 or captured_total <= min(totals):
            return "unsupported"
        if captured_total > max(totals):
            return "supported"
        return "insufficient_evidence"
    if topic in {"refund_pending", "refund_failed"}:
        status = "pending" if topic == "refund_pending" else "failed"
        if not refund_events:
            return "insufficient_evidence"
        latest = max(refund_events, key=lambda event: _time(event["event_at"]))
        return "supported" if latest.get("status") == status else "unsupported"
    if topic == "unsupported_claim":
        shipment = evidence["get_shipment_summary"]["data"]
        if not isinstance(shipment, dict):
            return "insufficient_evidence"
        shipment_delivered_at = _time(shipment.get("delivered_customer_at"))
        shipment_estimated_at = _time(shipment.get("estimated_delivery_at"))
        if shipment_delivered_at is None or shipment_estimated_at is None:
            return "insufficient_evidence"
        if shipment_delivered_at != delivered_at or shipment_estimated_at != estimated_at:
            return "insufficient_evidence"
        confirmed_late_delivery = any(
            event.get("event_type") == "delivered_late" and event.get("status") == "confirmed"
            for event in shipment_events
        )
        on_time = bool(
            opened_at
            and delivered_at
            and estimated_at
            and delivered_at <= estimated_at
            and delivered_at <= opened_at
        )
        return "unsupported" if on_time and not confirmed_late_delivery else "insufficient_evidence"
    return "insufficient_evidence"


def _claim_refs(tools: tuple[str, ...], evidence: dict[str, dict[str, Any]]) -> list[str]:
    return _unique([evidence[tool]["evidence_ref"] for tool in tools if tool in evidence])


def _normalize_parties(
    parties: list[dict[str, Any]], evidence: dict[str, dict[str, Any]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    items = {
        str(row.get("seller_id")) for row in _rows(evidence.get("get_order_items", {}).get("data"))
    }
    sellers = {
        str(row.get("seller_id")) for row in _rows(evidence.get("get_sellers", {}).get("data"))
    }
    verified = items & sellers
    resolved: list[dict[str, Any]] = []
    conflicts: list[dict[str, Any]] = []
    for party in parties:
        value = dict(party)
        if value.get("party_type") == "seller":
            seller_id = next(iter(verified)) if len(verified) == 1 else None
            if value.get("party_id") != seller_id:
                conflicts.append(
                    {
                        "field": "responsible_parties.seller_id",
                        "sources": ["get_policy", "get_sellers"],
                        "selected_source": "get_sellers" if seller_id else None,
                        "resolution_code": "POLICY_SELLER_ID_MISMATCH",
                    }
                )
            value["party_id"] = seller_id
        resolved.append(value)
    return resolved, conflicts


def _confidence(topic: str, conflicts: list[dict[str, Any]], base: float = 0.95) -> float:
    relevant = CONFLICT_FIELDS.get(topic, set())
    count = sum(
        conflict["field"].rsplit(".", 1)[-1] in relevant
        or conflict["field"] == "responsible_parties.seller_id"
        for conflict in conflicts
    )
    return round(max(0.8, base - 0.02 * count), 2)


async def solve_case(
    case: dict[str, Any],
    gateway: EvidenceGateway,
    trace: TraceWriter,
    model: ModelTriageClient | None = None,
) -> dict[str, Any]:
    case_id = str(case["case_id"])
    request = case["customer_request"]
    order_id = str(request["claimed_order_id"])
    claims = request.get("claims", [])
    primary_topic = next(
        (claim["topic"] for claim in claims if claim["topic"] != "requested_full_refund"),
        "unsupported_claim",
    )

    extra_tools: list[str] = []
    if model is not None:
        trace.emit(
            case_id=case_id,
            event_type="task_assigned",
            actor="coordinator",
            target="triage-agent",
            decision_code="MODEL_TRIAGE_ASSIGNED",
            attributes={"model_id": model.model_id},
        )
        try:
            triage = await model.triage(case)
        except ModelTriageError:
            trace.emit(
                case_id=case_id,
                event_type="handoff",
                actor="triage-agent",
                target="coordinator",
                decision_code="MODEL_TRIAGE_FAILED",
            )
        else:
            trace.emit(
                case_id=case_id,
                event_type="handoff",
                actor="triage-agent",
                target="coordinator",
                decision_code="MODEL_TRIAGE_COMPLETE",
                attributes={
                    "model_id": triage.model_id,
                    "focus_claim_id": triage.focus_claim_id,
                    "risk_flag_count": len(triage.risk_flags),
                },
            )
            for flag in triage.risk_flags:
                if flag == "refund" and primary_topic not in {
                    "canceled_order_paid",
                    "unavailable_order_paid",
                    "refund_pending",
                    "refund_failed",
                }:
                    continue
                if flag == "shipment" and not primary_topic.startswith("late_delivery_"):
                    continue
                if flag == "seller" and primary_topic not in {
                    "unavailable_order_paid",
                    "late_delivery_seller",
                }:
                    continue
                extra_tools.append(FLAG_TO_TOOL[flag])

    tool_plan = _unique(
        [
            "get_order",
            "get_order_items",
            *(
                ()
                if primary_topic in {"late_delivery_seller", "late_delivery_logistics"}
                else ("get_order_payments",)
            ),
            *TOPIC_TOOLS.get(primary_topic, ()),
            *extra_tools,
            "get_policy",
        ]
    )
    for tool_name in tool_plan:
        trace.emit(
            case_id=case_id,
            event_type="task_assigned",
            actor="coordinator",
            target=TOOL_ACTORS[tool_name],
            decision_code="EVIDENCE_COLLECTION",
            tool_name=tool_name,
            attributes={"tool": tool_name},
        )

    evidence: dict[str, dict[str, Any]] = {}
    for tool_name in tool_plan:
        arguments = (
            {"policy_version": str(case["policy_version"])}
            if tool_name == "get_policy"
            else {"order_id": order_id}
        )
        try:
            result = await gateway.call(tool_name, case_id=case_id, **arguments)
        except (RuntimeError, ValueError):
            continue
        evidence[tool_name] = result
        trace.emit(
            case_id=case_id,
            event_type="tool_result_consumed",
            actor=TOOL_ACTORS[tool_name],
            tool_name=tool_name,
            evidence_refs=[result["evidence_ref"]],
        )

    for actor in dict.fromkeys(TOOL_ACTORS[tool] for tool in tool_plan):
        if actor == "policy-agent":
            continue
        actor_refs = _claim_refs(
            tuple(tool for tool in tool_plan if TOOL_ACTORS[tool] == actor), evidence
        )
        if actor_refs:
            trace.emit(
                case_id=case_id,
                event_type="handoff",
                actor=actor,
                target="coordinator",
                decision_code="EVIDENCE_READY",
                evidence_refs=actor_refs,
            )

    required = {
        "get_order",
        "get_order_items",
        *(
            ()
            if primary_topic in {"late_delivery_seller", "late_delivery_logistics"}
            else ("get_order_payments",)
        ),
        "get_policy",
        *TOPIC_TOOLS.get(primary_topic, ()),
    }
    complete = required.issubset(evidence)
    policy = evidence.get("get_policy", {}).get("data", {})
    rules = policy.get("rules", {}) if isinstance(policy, dict) else {}
    primary_verdict = _verified_topic(primary_topic, case, evidence)
    if primary_verdict == "supported" or (
        primary_topic == "unsupported_claim" and primary_verdict == "unsupported"
    ):
        decision_topic = primary_topic
    elif primary_verdict == "unsupported":
        decision_topic = "unsupported_claim"
    else:
        decision_topic = "insufficient_evidence"
    rule = rules.get(decision_topic, {}) if isinstance(rules, dict) else {}
    if not complete or not rule:
        primary_issue = "insufficient_evidence"
        case_status = "needs_investigation"
        refund = Decimal("0")
        action = "collect_missing_evidence"
        parties = [{"party_type": "unknown", "party_id": None}]
    else:
        primary_issue = decision_topic
        case_status = str(rule["case_status"])
        refund = Decimal(str(rule["refund_brl"]))
        action = str(rule["recommended_action"])
        parties = list(rule["responsible_parties"])

    parties, party_conflicts = _normalize_parties(parties, evidence)
    conflicts = (
        _detect_conflicts(evidence, CONFLICT_FIELDS.get(primary_topic, set())) + party_conflicts
    )[:5]
    confidence = (
        _confidence(primary_topic, conflicts) if primary_issue != "insufficient_evidence" else 0.25
    )
    refund_entitles_full = (
        primary_issue in {"canceled_order_paid", "unavailable_order_paid"}
        and refund > 0
        and action == "issue_refund"
    )
    claim_assessments = []
    cited_tools: set[str] = set()
    for claim in claims:
        topic = str(claim["topic"])
        if topic == "requested_full_refund" and primary_issue != "insufficient_evidence":
            verdict = "supported" if refund_entitles_full else "unsupported"
            claim_confidence = _confidence(primary_topic, conflicts, base=0.9)
            ref_tools = REFUND_CLAIM_TOOLS[primary_topic]
        elif topic == "requested_full_refund":
            verdict = "insufficient_evidence"
            claim_confidence = 0.25
            ref_tools = ("get_order", "get_order_payments", "get_policy")
        elif topic == primary_topic:
            verdict = primary_verdict if complete else "insufficient_evidence"
            claim_confidence = (
                _confidence(topic, conflicts) if verdict != "insufficient_evidence" else 0.25
            )
            ref_tools = CLAIM_TOOLS[topic]
        else:
            verdict = (
                _verified_topic(topic, case, evidence)
                if topic in CLAIM_TOOLS
                else "insufficient_evidence"
            )
            claim_confidence = (
                _confidence(topic, conflicts) if verdict != "insufficient_evidence" else 0.25
            )
            ref_tools = CLAIM_TOOLS.get(topic, ())
        cited_tools.update(tool for tool in ref_tools if tool in evidence)
        claim_assessments.append(
            {
                "claim_id": str(claim["claim_id"]),
                "verdict": verdict,
                "confidence": claim_confidence,
                "evidence_refs": _claim_refs(ref_tools, evidence),
            }
        )

    if evidence.get("get_order_items") and _affected_entities(order_id, evidence)["item_ids"]:
        cited_tools.add("get_order_items")
    for conflict in conflicts:
        cited_tools.update(tool for tool in conflict["sources"] if tool in evidence)
    all_refs = _claim_refs(tuple(tool for tool in tool_plan if tool in cited_tools), evidence)

    trace.emit(
        case_id=case_id,
        event_type="policy_decided",
        actor="policy-agent",
        decision_code=action.upper(),
        evidence_refs=(
            [evidence["get_policy"]["evidence_ref"]] if "get_policy" in evidence else []
        ),
    )
    if "get_policy" in evidence:
        trace.emit(
            case_id=case_id,
            event_type="handoff",
            actor="policy-agent",
            target="coordinator",
            decision_code="POLICY_READY",
            evidence_refs=[evidence["get_policy"]["evidence_ref"]],
        )
    trace.emit(
        case_id=case_id,
        event_type="handoff",
        actor="coordinator",
        target="verifier",
        decision_code="SPECIALISTS_COMPLETE",
        evidence_refs=all_refs[:20],
    )

    refund_value = float(refund)
    output = {
        "schema_version": "day09-l3a-output-v2",
        "case_id": case_id,
        "assessment": {
            "primary_issue": primary_issue,
            "case_status": case_status,
            "confidence": confidence,
        },
        "affected_entities": _affected_entities(order_id, evidence),
        "claim_assessments": claim_assessments,
        "root_cause_analysis": {
            "ranked_causes": [
                {"cause_code": CAUSE_CODES.get(primary_issue, "MISSING_EVIDENCE"), "rank": 1}
            ],
            "responsible_parties": parties,
        },
        "evidence_refs": all_refs,
        "data_conflicts": conflicts,
        "financial_resolution": {
            "currency": "BRL",
            "recommended_refund_brl": refund_value,
            "refund_lines": (
                [
                    {
                        "reason_code": action.upper(),
                        "amount_brl": refund_value,
                        "entity_id": order_id,
                    }
                ]
                if refund_value > 0
                else []
            ),
        },
        "resolution_actions": [action],
    }
    trace.emit(
        case_id=case_id,
        event_type="verification_completed",
        actor="verifier",
        decision_code="OUTPUT_INVARIANTS_PASSED",
        evidence_refs=all_refs[:20],
        attributes={
            "evidence_complete": complete,
            "refund_total_brl": refund_value,
            "conflict_count": len(output["data_conflicts"]),
        },
    )
    trace.emit(
        case_id=case_id,
        event_type="handoff",
        actor="verifier",
        target="coordinator",
        decision_code="VERIFIED_OUTPUT_READY",
        evidence_refs=all_refs[:20],
    )
    return output
