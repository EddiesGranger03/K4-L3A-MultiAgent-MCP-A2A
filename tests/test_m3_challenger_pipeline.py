"""Empirical Challenger Test Suite for Milestone 3.2: Workflow Pipeline & Fallback.

Adversarially challenges the end-to-end `solve_case` workflow in `src/student_agent/workflow.py`:
1. Corrupted/malformed input cases (missing fields, wrong types, boundary values).
2. Failing EvidenceGateway (ConnectionResetError, TimeoutError, RuntimeError).
3. Empty/unregistered tool discovery (list_tools -> [], or unexpected tool catalog).
4. Trace event emission sequence and schema validity across normal and disaster recovery flows.
5. Zero exception escape guarantee under extreme/hostile inputs.
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from typing import Any

import pytest

from student_agent.contracts import Contracts
from student_agent.llm_client import NvidiaLLMClient
from student_agent.trace import TraceWriter
from student_agent.workflow import create_fallback_output, solve_case


# ==============================================================================
# FIXTURES & MOCK CLIENTS / GATEWAYS
# ==============================================================================

class FastMockLLMClient(NvidiaLLMClient):
    """Subclass of NvidiaLLMClient that instantly uses deterministic offline fallback."""

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.0,
        max_tokens: int = 1024,
    ) -> str | None:
        return None


@pytest.fixture
def fast_llm_client() -> FastMockLLMClient:
    return FastMockLLMClient()


@pytest.fixture
def contracts_fixture() -> Contracts:
    schema_dir = Path(__file__).resolve().parents[1] / "contracts" / "schemas"
    return Contracts(schema_dir)


@pytest.fixture
def temp_trace_writer(tmp_path: Path, contracts_fixture: Contracts) -> TraceWriter:
    trace_path = tmp_path / "traces" / "challenger_trace.jsonl"
    return TraceWriter(trace_path, contracts_fixture)


class HealthyMockGateway:
    """Mock gateway providing realistic responses across all domains."""

    async def list_tools(self) -> list[str]:
        return ["get_order", "get_payment", "get_shipment", "get_refund"]

    async def call(self, tool_name: str, *, case_id: str, **arguments: str) -> dict[str, Any]:
        if tool_name == "get_order":
            return {
                "evidence_ref": "ev_order_test_record_00000000000001",
                "domain": "order",
                "result_hash": "hash_order_111",
                "data": {
                    "order_id": arguments.get("order_id", "ord_normal_001"),
                    "status": "delivered",
                    "customer_id": "cust_001",
                    "order_purchase_timestamp": "2026-09-01T10:00:00Z",
                    "items": [
                        {
                            "item_id": "item_001",
                            "seller_id": "seller_001",
                            "price": 100.0,
                            "freight_value": 20.0,
                            "shipping_limit_date": "2026-09-05T10:00:00Z",
                        }
                    ],
                },
                "warnings": [],
            }
        elif tool_name == "get_payment":
            return {
                "evidence_ref": "ev_payment_test_record_00000000002",
                "domain": "payment",
                "result_hash": "hash_pay_222",
                "data": {
                    "order_id": arguments.get("order_id", "ord_normal_001"),
                    "total_paid": 120.0,
                    "payments": [
                        {
                            "payment_sequential": 1,
                            "payment_type": "credit_card",
                            "payment_installments": 1,
                            "payment_value": 120.0,
                        }
                    ],
                },
                "warnings": [],
            }
        elif tool_name == "get_shipment":
            return {
                "evidence_ref": "ev_shipment_test_record_0000000003",
                "domain": "shipment",
                "result_hash": "hash_ship_333",
                "data": {
                    "order_id": arguments.get("order_id", "ord_normal_001"),
                    "shipment_id": "ship_001",
                    "carrier_partner": "correios",
                    "delivered_carrier_date": "2026-09-04T10:00:00Z",
                    "delivered_customer_date": "2026-09-08T10:00:00Z",
                    "estimated_delivery_date": "2026-09-10T10:00:00Z",
                },
                "warnings": [],
            }
        elif tool_name == "get_refund":
            return {
                "evidence_ref": "ev_refund_test_record_00000000004",
                "domain": "refund",
                "result_hash": "hash_ref_444",
                "data": {
                    "order_id": arguments.get("order_id", "ord_normal_001"),
                    "refund_status": "none",
                    "refunded_amount": 0.0,
                },
                "warnings": [],
            }
        return {
            "evidence_ref": "ev_unknown_test_record_0000000005",
            "domain": "unknown",
            "result_hash": "hash_unk",
            "data": {},
            "warnings": [],
        }


# ==============================================================================
# 1. CHALLENGE WITH CORRUPTED / MALFORMED INPUT CASES
# ==============================================================================

def test_corrupted_empty_dict(
    contracts_fixture: Contracts, temp_trace_writer: TraceWriter, fast_llm_client: FastMockLLMClient
) -> None:
    """Empty dict {} should not crash solve_case and must yield a schema-valid fallback."""
    gateway = HealthyMockGateway()
    output = asyncio.run(
        solve_case({}, gateway, temp_trace_writer, llm_client=fast_llm_client, contracts=contracts_fixture)
    )  # type: ignore[arg-type]
    assert isinstance(output, dict)
    assert output["schema_version"] == "day09-l3a-output-v2"
    assert output["assessment"]["primary_issue"] == "insufficient_evidence"
    assert output["assessment"]["case_status"] == "needs_investigation"
    assert output["financial_resolution"]["recommended_refund_brl"] == 0.0
    contracts_fixture.validate_output(output, "test_corrupted_empty_dict")


def test_corrupted_missing_customer_request(
    contracts_fixture: Contracts, temp_trace_writer: TraceWriter, fast_llm_client: FastMockLLMClient
) -> None:
    """Case with case_id but no customer_request field should fall back gracefully."""
    gateway = HealthyMockGateway()
    case = {"case_id": "CASE_CORRUPT_001", "opened_at": "2026-09-25T00:00:00Z"}
    output = asyncio.run(
        solve_case(case, gateway, temp_trace_writer, llm_client=fast_llm_client, contracts=contracts_fixture)
    )
    assert output["case_id"] == "CASE_CORRUPT_001"
    contracts_fixture.validate_output(output, "test_corrupted_missing_customer_request")


def test_corrupted_invalid_types_in_fields(
    contracts_fixture: Contracts, temp_trace_writer: TraceWriter, fast_llm_client: FastMockLLMClient
) -> None:
    """Case with invalid types (ints, lists where dicts expected) must survive without crash."""
    gateway = HealthyMockGateway()
    case = {
        "case_id": "CASE_BAD_TYPES_001",
        "opened_at": 123456789,  # Int instead of string
        "customer_request": "This is a string not a dict",
        "policy_version": None,
    }
    output = asyncio.run(
        solve_case(case, gateway, temp_trace_writer, llm_client=fast_llm_client, contracts=contracts_fixture)
    )  # type: ignore[arg-type]
    assert output["case_id"] == "CASE_BAD_TYPES_001"
    contracts_fixture.validate_output(output, "test_corrupted_invalid_types_in_fields")


def test_corrupted_malformed_claims_list(
    contracts_fixture: Contracts, temp_trace_writer: TraceWriter, fast_llm_client: FastMockLLMClient
) -> None:
    """Claims containing non-dict elements, None, ints, or empty claim_ids."""
    gateway = HealthyMockGateway()
    case = {
        "case_id": "CASE_BAD_CLAIMS_001",
        "opened_at": "2026-09-25T00:00:00Z",
        "customer_request": {
            "claimed_order_id": "ord_bad_claims_001",
            "claims": [
                None,
                12345,
                "string_claim",
                {"claim_id": "valid_claim_1", "topic": "delivery"},
            ],
        },
    }
    output = asyncio.run(
        solve_case(case, gateway, temp_trace_writer, llm_client=fast_llm_client, contracts=contracts_fixture)
    )
    assert output["case_id"] == "CASE_BAD_CLAIMS_001"
    contracts_fixture.validate_output(output, "test_corrupted_malformed_claims_list")


def test_corrupted_empty_string_claim_id(
    contracts_fixture: Contracts, temp_trace_writer: TraceWriter, fast_llm_client: FastMockLLMClient
) -> None:
    """Stress test: claim_id is an empty string, which violates minLength: 1 if not sanitized."""
    gateway = HealthyMockGateway()
    case = {
        "case_id": "CASE_EMPTY_CLAIM_ID_001",
        "opened_at": "2026-09-25T00:00:00Z",
        "customer_request": {
            "claimed_order_id": "ord_empty_claim_001",
            "claims": [
                {"claim_id": "", "topic": "delivery"},  # Empty claim_id!
            ],
        },
    }
    output = asyncio.run(
        solve_case(case, gateway, temp_trace_writer, llm_client=fast_llm_client, contracts=contracts_fixture)
    )
    contracts_fixture.validate_output(output, "test_corrupted_empty_string_claim_id")


def test_corrupted_oversized_claimed_order_id(
    contracts_fixture: Contracts, temp_trace_writer: TraceWriter, fast_llm_client: FastMockLLMClient
) -> None:
    """Stress test: claimed_order_id is > 128 characters, which violates idSet maxLength: 128 if not truncated."""
    gateway = HealthyMockGateway()
    oversized_id = "ord_" + "A" * 150  # 154 characters
    case = {
        "case_id": "CASE_OVERSIZED_ORD_001",
        "opened_at": "2026-09-25T00:00:00Z",
        "customer_request": {
            "claimed_order_id": oversized_id,
            "claims": [{"claim_id": "c1", "topic": "delivery"}],
        },
    }
    output = asyncio.run(
        solve_case(case, gateway, temp_trace_writer, llm_client=fast_llm_client, contracts=contracts_fixture)
    )
    contracts_fixture.validate_output(output, "test_corrupted_oversized_claimed_order_id")


# ==============================================================================
# 2. CHALLENGE WITH FAILING EVIDENCE GATEWAY (ConnectionResetError, TimeoutError)
# ==============================================================================

class ConnectionResetGateway:
    async def list_tools(self) -> list[str]:
        raise ConnectionResetError("TCP connection reset by peer (MCP gateway down)")

    async def call(self, tool_name: str, *, case_id: str, **arguments: str) -> dict[str, Any]:
        raise ConnectionResetError("TCP connection reset by peer")


class TimeoutGateway:
    async def list_tools(self) -> list[str]:
        raise TimeoutError("Gateway request timed out after 30000ms")

    async def call(self, tool_name: str, *, case_id: str, **arguments: str) -> dict[str, Any]:
        raise TimeoutError("Gateway request timed out")


class CallOnlyFailingGateway:
    """Gateway that discovers tools successfully, but fails on call()."""

    async def list_tools(self) -> list[str]:
        return ["get_order", "get_payment", "get_shipment", "get_refund"]

    async def call(self, tool_name: str, *, case_id: str, **arguments: str) -> dict[str, Any]:
        if tool_name == "get_order":
            raise ConnectionResetError("Connection lost while fetching order")
        elif tool_name == "get_payment":
            raise TimeoutError("Timeout while fetching payment")
        raise RuntimeError(f"Unexpected call failure on {tool_name}")


def test_failing_gateway_connection_reset(
    contracts_fixture: Contracts, temp_trace_writer: TraceWriter, fast_llm_client: FastMockLLMClient
) -> None:
    """ConnectionResetError on list_tools must be caught and return valid fallback."""
    case = {
        "case_id": "CASE_CONN_RESET_001",
        "opened_at": "2026-09-25T00:00:00Z",
        "customer_request": {"claimed_order_id": "ord_cr_001"},
    }
    output = asyncio.run(
        solve_case(case, ConnectionResetGateway(), temp_trace_writer, llm_client=fast_llm_client, contracts=contracts_fixture)
    )  # type: ignore[arg-type]
    assert output["case_id"] == "CASE_CONN_RESET_001"
    assert output["assessment"]["primary_issue"] == "insufficient_evidence"
    assert output["assessment"]["case_status"] == "needs_investigation"
    assert output["financial_resolution"]["recommended_refund_brl"] == 0.0
    contracts_fixture.validate_output(output, "test_failing_gateway_connection_reset")


def test_failing_gateway_timeout(
    contracts_fixture: Contracts, temp_trace_writer: TraceWriter, fast_llm_client: FastMockLLMClient
) -> None:
    """TimeoutError on list_tools must be caught and return valid fallback."""
    case = {
        "case_id": "CASE_TIMEOUT_001",
        "opened_at": "2026-09-25T00:00:00Z",
        "customer_request": {"claimed_order_id": "ord_to_001"},
    }
    output = asyncio.run(
        solve_case(case, TimeoutGateway(), temp_trace_writer, llm_client=fast_llm_client, contracts=contracts_fixture)
    )  # type: ignore[arg-type]
    assert output["case_id"] == "CASE_TIMEOUT_001"
    assert output["assessment"]["primary_issue"] == "insufficient_evidence"
    assert output["assessment"]["case_status"] == "needs_investigation"
    contracts_fixture.validate_output(output, "test_failing_gateway_timeout")


def test_failing_gateway_calls_fail_after_successful_discovery(
    contracts_fixture: Contracts, temp_trace_writer: TraceWriter, fast_llm_client: FastMockLLMClient
) -> None:
    """Discovery succeeds, but all individual tool calls fail with network errors."""
    case = {
        "case_id": "CASE_CALL_FAIL_001",
        "opened_at": "2026-09-25T00:00:00Z",
        "customer_request": {
            "claimed_order_id": "ord_cf_001",
            "claims": [{"claim_id": "c1", "topic": "canceled_order_paid"}],
        },
    }
    output = asyncio.run(
        solve_case(case, CallOnlyFailingGateway(), temp_trace_writer, llm_client=fast_llm_client, contracts=contracts_fixture)
    )  # type: ignore[arg-type]
    assert output["case_id"] == "CASE_CALL_FAIL_001"
    assert output["assessment"]["primary_issue"] == "insufficient_evidence"
    assert output["assessment"]["case_status"] == "needs_investigation"
    assert output["financial_resolution"]["recommended_refund_brl"] == 0.0
    # Must contain zero hallucinated refs
    assert len(output["evidence_refs"]) == 0
    contracts_fixture.validate_output(output, "test_failing_gateway_calls_fail_after_successful_discovery")


# ==============================================================================
# 3. CHALLENGE WITH EMPTY TOOL DISCOVERY
# ==============================================================================

class EmptyToolsGateway:
    async def list_tools(self) -> list[str]:
        return []

    async def call(self, tool_name: str, *, case_id: str, **arguments: str) -> dict[str, Any]:
        raise RuntimeError("No tools available")


class MismatchedToolsGateway:
    async def list_tools(self) -> list[str]:
        return ["unrelated_tool_foo", "unrelated_tool_bar"]

    async def call(self, tool_name: str, *, case_id: str, **arguments: str) -> dict[str, Any]:
        raise RuntimeError(f"Tool {tool_name} not available")


def test_empty_tool_discovery_graceful_fallback(
    contracts_fixture: Contracts, temp_trace_writer: TraceWriter, fast_llm_client: FastMockLLMClient
) -> None:
    """Gateway returns empty tool catalog []. Must fall back without crash."""
    case = {
        "case_id": "CASE_EMPTY_TOOLS_001",
        "opened_at": "2026-09-25T00:00:00Z",
        "customer_request": {"claimed_order_id": "ord_et_001"},
    }
    output = asyncio.run(
        solve_case(case, EmptyToolsGateway(), temp_trace_writer, llm_client=fast_llm_client, contracts=contracts_fixture)
    )  # type: ignore[arg-type]
    assert output["case_id"] == "CASE_EMPTY_TOOLS_001"
    assert output["assessment"]["primary_issue"] == "insufficient_evidence"
    assert output["assessment"]["case_status"] == "needs_investigation"
    contracts_fixture.validate_output(output, "test_empty_tool_discovery_graceful_fallback")


def test_mismatched_tool_discovery_graceful_fallback(
    contracts_fixture: Contracts, temp_trace_writer: TraceWriter, fast_llm_client: FastMockLLMClient
) -> None:
    """Gateway returns tools that don't match any required domains."""
    case = {
        "case_id": "CASE_MISMATCHED_TOOLS_001",
        "opened_at": "2026-09-25T00:00:00Z",
        "customer_request": {"claimed_order_id": "ord_mt_001"},
    }
    output = asyncio.run(
        solve_case(case, MismatchedToolsGateway(), temp_trace_writer, llm_client=fast_llm_client, contracts=contracts_fixture)
    )  # type: ignore[arg-type]
    assert output["case_id"] == "CASE_MISMATCHED_TOOLS_001"
    assert output["assessment"]["primary_issue"] == "insufficient_evidence"
    assert output["assessment"]["case_status"] == "needs_investigation"
    contracts_fixture.validate_output(output, "test_mismatched_tool_discovery_graceful_fallback")


# ==============================================================================
# 4. VERIFY TRACE EVENT EMISSION SEQUENCE
# ==============================================================================

def test_trace_sequence_normal_flow(
    contracts_fixture: Contracts, tmp_path: Path, fast_llm_client: FastMockLLMClient
) -> None:
    """Normal execution trace sequence verification:
    Must emit case_received -> task_assigned -> tool_result_consumed -> handoff -> policy_decided -> verification_completed -> case_finalized.
    """
    trace_file = tmp_path / "normal_trace.jsonl"
    trace = TraceWriter(trace_file, contracts_fixture)
    case_id = "CASE_TRACE_NORM_001"

    case = {
        "case_id": case_id,
        "opened_at": "2026-09-25T00:00:00Z",
        "policy_version": "EC_POLICY_V1",
        "customer_request": {
            "language": "vi",
            "message": "Đơn hàng đã nhận đúng hạn, cảm ơn",
            "claimed_order_id": "ord_norm_001",
            "claims": [{"claim_id": "c1", "topic": "no_issue"}],
        },
    }

    # Simulate cli.py wrapper
    trace.emit(case_id=case_id, event_type="case_received", actor="coordinator")
    output = asyncio.run(
        solve_case(case, HealthyMockGateway(), trace, llm_client=fast_llm_client, contracts=contracts_fixture)
    )  # type: ignore[arg-type]
    trace.emit(case_id=case_id, event_type="case_finalized", actor="coordinator")

    contracts_fixture.validate_output(output, "test_trace_normal")

    # Read and inspect trace events
    events = [json.loads(line) for line in trace_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    event_types = [e["event_type"] for e in events]

    # Verify all events conform to trace-event-v1.schema.json
    for idx, e in enumerate(events):
        contracts_fixture.validate_trace(e, f"event_{idx}_{e['event_type']}")

    # Verify lifecycle ordering
    assert event_types[0] == "case_received"
    assert "task_assigned" in event_types
    assert "tool_result_consumed" in event_types
    assert "handoff" in event_types
    assert "policy_decided" in event_types
    assert "verification_completed" in event_types
    assert event_types[-1] == "case_finalized"

    # Verify relative order
    idx_rec = event_types.index("case_received")
    idx_task = event_types.index("task_assigned")
    idx_tool = event_types.index("tool_result_consumed")
    idx_handoff = event_types.index("handoff")
    idx_policy = event_types.index("policy_decided")
    idx_ver = event_types.index("verification_completed")
    idx_fin = event_types.index("case_finalized")

    assert idx_rec < idx_task < idx_tool < idx_ver < idx_fin
    assert idx_handoff < idx_ver
    assert idx_policy < idx_ver


def test_trace_sequence_disaster_recovery_flow(
    contracts_fixture: Contracts, tmp_path: Path, fast_llm_client: FastMockLLMClient
) -> None:
    """Disaster recovery trace sequence verification:
    When gateway fails catastrophically, create_fallback_output must emit:
    task_assigned -> handoff -> verification_completed.
    With cli wrapper: case_received -> task_assigned -> handoff -> verification_completed -> case_finalized.
    """
    trace_file = tmp_path / "disaster_trace.jsonl"
    trace = TraceWriter(trace_file, contracts_fixture)
    case_id = "CASE_TRACE_DISASTER_001"

    case = {
        "case_id": case_id,
        "opened_at": "2026-09-25T00:00:00Z",
        "customer_request": {"claimed_order_id": "ord_disaster_001"},
    }

    trace.emit(case_id=case_id, event_type="case_received", actor="coordinator")
    output = asyncio.run(
        solve_case(case, ConnectionResetGateway(), trace, llm_client=fast_llm_client, contracts=contracts_fixture)
    )  # type: ignore[arg-type]
    trace.emit(case_id=case_id, event_type="case_finalized", actor="coordinator")

    contracts_fixture.validate_output(output, "test_trace_disaster")

    events = [json.loads(line) for line in trace_file.read_text(encoding="utf-8").splitlines() if line.strip()]
    event_types = [e["event_type"] for e in events]

    # Verify all events conform to trace-event-v1.schema.json
    for idx, e in enumerate(events):
        contracts_fixture.validate_trace(e, f"disaster_event_{idx}_{e['event_type']}")

    # Check all 5 required workflow events from scoring-policy-v2 are present
    assert "case_received" in event_types
    assert "task_assigned" in event_types
    assert "handoff" in event_types
    assert "verification_completed" in event_types
    assert "case_finalized" in event_types

    # Verify order
    assert event_types.index("case_received") < event_types.index("task_assigned")
    assert event_types.index("task_assigned") < event_types.index("handoff")
    assert event_types.index("handoff") < event_types.index("verification_completed")
    assert event_types.index("verification_completed") < event_types.index("case_finalized")


# ==============================================================================
# 5. VERIFY THAT NO EXCEPTION ESCAPES solve_case
# ==============================================================================

@pytest.mark.parametrize(
    "malformed_payload",
    [
        None,
        {},
        {"case_id": ""},
        {"case_id": None},
        {"case_id": 123456},
        {"case_id": "invalid case with spaces"},
        {"case_id": "lower_case_id"},
        {"case_id": "CASE_OK_001", "customer_request": None},
        {"case_id": "CASE_OK_002", "customer_request": 9999},
        {"case_id": "CASE_OK_003", "customer_request": {"claims": None}},
        {"case_id": "CASE_OK_004", "customer_request": {"claims": [None, "str", 123]}},
        {"case_id": "CASE_OK_005", "policy_version": 999},
    ],
)
def test_zero_exception_escapes_solve_case(
    malformed_payload: Any,
    contracts_fixture: Contracts,
    temp_trace_writer: TraceWriter,
    fast_llm_client: FastMockLLMClient,
) -> None:
    """Ensure solve_case NEVER raises any exception for hostile/malformed inputs."""
    try:
        output = asyncio.run(
            solve_case(
                malformed_payload,  # type: ignore[arg-type]
                ConnectionResetGateway(),  # type: ignore[arg-type]
                temp_trace_writer,
                llm_client=fast_llm_client,
                contracts=contracts_fixture,
            )
        )
        assert isinstance(output, dict)
        assert "schema_version" in output
        assert "case_id" in output
        assert "assessment" in output
        assert "financial_resolution" in output
    except Exception as exc:
        pytest.fail(f"solve_case raised an unhandled exception on payload {malformed_payload!r}: {exc}")


def test_create_fallback_output_handles_none_trace_and_none_contracts() -> None:
    """create_fallback_output should survive when trace=None, adapter=None, contracts=None."""
    output = create_fallback_output(
        case={"case_id": "CASE_MINIMAL_001"},
        adapter=None,
        trace=None,
        error=RuntimeError("Test error"),
        contracts=None,
    )
    assert isinstance(output, dict)
    assert output["case_id"] == "CASE_MINIMAL_001"
    assert output["assessment"]["primary_issue"] == "insufficient_evidence"
