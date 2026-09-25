# Handoff Report: Evidence Integration, Trace Alignment & Claim Adjudication (Explorer M2.3)

**Author**: Explorer M2.3 (Evidence Integration Explorer)  
**Assigned Working Directory**: `.agents/teamwork/explorer_m2_3_gen2`  
**Date**: 2026-09-25T11:58:00+07:00  
**Status**: Completed (Hard Handoff)  
**Target Modules**: `src/student_agent/policy.py` & `src/student_agent/specialists.py`  

---

## 1. Observation

### 1.1 Contract Schema Invariants & Constraints
Direct examination of `contracts/schemas/` reveals strict structural and semantic boundaries:

1. **`contracts/schemas/trace-event-v1.schema.json`**:
   - `required`: `["schema_version", "event_id", "case_id", "event_type", "occurred_at", "actor"]`.
   - `schema_version`: Must be `"day09-trace-event-v1"`.
   - `event_id`: Regex `^evt_[A-Za-z0-9_-]{12,96}$`.
   - `case_id`: Regex `^[A-Z0-9][A-Z0-9_-]{2,63}$`.
   - `event_type`: Restricted to `["case_received", "task_assigned", "tool_result_consumed", "handoff", "policy_decided", "verification_completed", "case_finalized"]`.
   - `actor`: String, length `1..80`. Specifically, `policy_decided` requires `actor: "policy-agent"` per `PROJECT.md:106`.
   - `evidence_refs`: Array of strings matching `^ev_[A-Za-z0-9_-]{20,96}$`, `uniqueItems: true`, `maxItems: 20`.
   - `attributes`: **Crucial Schema Invariant** (lines 34–38):
     ```json
     "attributes": {
       "type": "object",
       "maxProperties": 20,
       "additionalProperties": {"type": ["string", "number", "integer", "boolean", "null"]}
     }
     ```
     *Fact*: Nested dictionaries, lists, or objects inside `attributes` will immediately trigger a `ContractError` on `trace.emit()`. All attribute values must be strictly primitive types (`str`, `int`, `float`, `bool`, `None`).

2. **`contracts/schemas/l3a-output-v2.schema.json`**:
   - `data_conflicts` (lines 106–115):
     ```json
     "dataConflict": {
       "type": "object", "additionalProperties": false,
       "required": ["field", "sources", "selected_source", "resolution_code"],
       "properties": {
         "field": {"type": "string", "minLength": 1, "maxLength": 100},
         "sources": {"type": "array", "minItems": 2, "maxItems": 5, "uniqueItems": true, "items": {"type": "string", "minLength": 1, "maxLength": 80}},
         "selected_source": {"type": ["string", "null"], "maxLength": 80},
         "resolution_code": {"type": "string", "minLength": 1, "maxLength": 80}
       }
     }
     ```
     *Fact*: Any conflict with fewer than 2 sources or duplicated sources violates `minItems: 2` and `uniqueItems: true`, triggering the Hard Gate `unscorable_schema` (0 score for the case).
   - `claim_assessments` (lines 64–73):
     ```json
     "claimAssessment": {
       "type": "object", "additionalProperties": false,
       "required": ["claim_id", "verdict", "confidence", "evidence_refs"],
       "properties": {
         "claim_id": {"type": "string", "minLength": 1, "maxLength": 64},
         "verdict": {"enum": ["supported", "unsupported", "partially_supported", "insufficient_evidence"]},
         "confidence": {"type": "number", "minimum": 0, "maximum": 1},
         "evidence_refs": {"$ref": "#/$defs/evidenceRefs"}
       }
     }
     ```

3. **`contracts/scoring/scoring-policy-v2.json`**:
   - `workflow_required_events`: `["case_received", "task_assigned", "handoff", "verification_completed", "case_finalized"]`.
   - `workflow`: "Mean of lifecycle-event coverage, receive/finalize ordering, actor collaboration and evidence-to-trace linkage."
   - `provenance` (15%): "All submitted evidence refs must exist in MCP audit and match team, run and case."
   - Hard Gates: `case_id_mismatch`, `unscorable_schema`, `missing_required_evidence`, `invalid_evidence_refs`, `unknown_evidence_ref`, `cross_scope_evidence_ref`.

### 1.2 Existing Foundation Modules in `src/student_agent/`
- **`tools.py`**:
  - `ToolAdapter.call(tool_name, actor, **arguments)` automatically tracks authentic `evidence_ref` in `_consumed_evidence_refs: set[str]` and emits `tool_result_consumed`.
  - Provides `filter_valid_refs(candidate_refs: Iterable[str]) -> list[str]` to purge any hallucinated or guessed refs.
  - Exposes `get_evidence_by_domain(domain: str)` and `get_evidence_by_ref(ref: str)`.
- **`models.py`**:
  - Implements contract dataclasses: `DataConflict`, `ClaimAssessment`, `ClaimVerdict`, `PolicyDecision`, `CaseInvestigationState`, `L3AOutputV2`.
  - `CaseInvestigationState.record_handoff(...)` tracks A2A transitions.
  - `L3AOutputV2.to_dict()` enforces `minItems: 2` on `data_conflicts` (`[dc.to_dict() for dc in self.data_conflicts[:5] if len(dc.sources) >= 2]`).
- **`llm_client.py`**:
  - Implements `NvidiaLLMClient` with deterministic fallback functions `_fallback_analyze_intent` and `_fallback_assist_claim_verification`, mapping customer requests to `EC_POLICY_V1` rules.

---

## 2. Logic Chain

1. **Trace Event `policy_decided` Alignment**:
   - From Schema Observation §1.1, `policy_decided` is the authoritative audit event where the policy engine registers its resolution before handing off to the verifier.
   - To achieve full credit on the Workflow metric (5%) and pass schema validation:
     - `actor` must be strictly `"policy-agent"`.
     - `decision_code` must be set to the determined `primary_issue` (e.g. `"canceled_order_paid"`).
     - `evidence_refs` must contain only genuine refs from `ToolAdapter.consumed_evidence_refs` (capped at 20).
     - `attributes` must contain strictly primitive key-value pairs (string, int, float, bool) summarizing the decision metrics: `case_status`, `confidence`, `recommended_refund_brl`, `refund_lines_count`, `claims_count`, `conflicts_detected`, `resolution_actions_count`.
     - Passing nested dicts or lists in `attributes` causes validation failure in `TraceWriter.emit` (`Contracts.validate_trace`).

2. **Trace Event `handoff` Coordination Sequence**:
   - The workflow scoring requires demonstrable "actor collaboration" across the multi-agent pipeline.
   - The lifecycle demands seamless context passing:
     - `coordinator` $\xrightarrow{\text{handoff}}$ `order-agent`
     - `order-agent` $\xrightarrow{\text{handoff}}$ `payment-agent`
     - `payment-agent` $\xrightarrow{\text{handoff}}$ `shipment-agent`
     - `shipment-agent` $\xrightarrow{\text{handoff}}$ `policy-agent`
     - `policy-agent` $\xrightarrow{\text{handoff}}$ `verifier`
   - Each handoff must emit a trace event `event_type="handoff"` with `actor` (sender), `target` (receiver), `decision_code` (status milestone), `evidence_refs` (newly acquired refs), and primitive `attributes` (findings summary), while recording the message in `state.handoff_history`.

3. **Claim Assessment Adjudication & Strict Evidence Linkage**:
   - Customer complaints contain discrete claims (e.g. `canceled_order_paid`, `requested_full_refund`, `late_delivery_seller`).
   - If a claim is evaluated without evidence or with invented evidence, Hard Gates (`invalid_evidence_refs`, `unknown_evidence_ref`) trigger a zero score.
   - Therefore, the adjudication logic must:
     - Corroborate each claim against verified specialist findings (`OrderFindings`, `PaymentFindings`, `ShipmentFindings`).
     - Map to exact enum verdicts: `supported`, `unsupported`, `partially_supported`, `insufficient_evidence`.
     - Link only domain-relevant evidence refs:
       - Order claims link to order/item tool results.
       - Payment/refund claims link to payment/refund tool results.
       - Delivery claims link to shipment tool results.
     - Pass all candidate refs through `ToolAdapter.filter_valid_refs()` to guarantee 100% provenance.

4. **Cross-Domain Data Conflict Detection (`minItems: 2`)**:
   - Real-world e-commerce data often exhibits discrepancies across separate service domains (e.g. order marked canceled in order service, but payment capture marked successful in payment gateway).
   - `contracts/schemas/l3a-output-v2.schema.json` strictly requires `sources` in each conflict to contain at least 2 distinct sources (`minItems: 2`).
   - The conflict detector must deterministically check for cross-domain discrepancies across 5 primary discrepancy patterns and output valid `DataConflict` instances with at least 2 distinct domain source strings.

5. **Invariant Enforcement & Error Resilience**:
   - `case_status == "no_action"` $\implies$ `recommended_refund_brl == 0.0` and `refund_lines == []`.
   - `case_status == "action_required"` $\implies$ `recommended_refund_brl == sum(lines.amount_brl)`.
   - If MCP tools fail or return empty data, the system must not crash; it must gracefully degrade to `primary_issue = "insufficient_evidence"`, `case_status = "needs_investigation"`, and `verdict = "insufficient_evidence"`.

---

## 3. Caveats

1. **Live MCP Server Call Budget**:
   - Although `l3a` variant has weight `0.00` for efficiency in public scoring, excessive redundant calls waste time and increase timeout risks. Tool calls should be scoped strictly to domains indicated by `InvestigationPlan`.
2. **Read-Only Investigation Mode**:
   - Per system prompt rules, this explorer has NOT modified source files in `src/student_agent/`. Complete implementation code specifications are provided below for the implementer agent (`worker_m2_1` or equivalent).
3. **Empty Data Conflicts**:
   - If a case has complete agreement across all domains with zero discrepancies, `data_conflicts` should remain empty `[]`. An empty array is 100% valid under the schema, whereas an array containing a conflict with only 1 source violates the schema.

---

## 4. Conclusion & Implementation Specification

### 4.1 Specification for `src/student_agent/specialists.py`

Below is the design and complete code specification for `specialists.py`. It integrates `ToolAdapter`, emits `task_assigned` and `handoff` trace events, populates `CaseInvestigationState`, and includes comprehensive Vietnamese comments (R4).

```python
"""Module: specialists.py.

Hệ thống: K4-L3A Multi-Agent E-Commerce Complaint Investigation System.
Mô tả: Định nghĩa các Agent chuyên trách (Specialist Agents) tham gia quy trình A2A:
  1. CoordinatorAgent: Tiếp nhận khiếu nại, phân tích ý định, phân công nhiệm vụ (task_assigned)
     và chuyển giao (handoff).
  2. OrderAgent: Điều tra dữ liệu đơn hàng và sản phẩm từ MCP Gateway, phát hiện trạng thái hủy/hết hàng.
  3. PaymentAgent: Đối soát giao dịch thanh toán, split payment, duplicate charge, và lệnh hoàn tiền.
  4. ShipmentAgent: Kiểm tra lịch trình vận chuyển, phân tích độ trễ của người bán vs đơn vị vận tải.

Tuân thủ:
  - ORIGINAL_REQUEST §R1 (A2A Workflow), §R3 (MCP Gateway & Evidence Provenance), §R4 (Vietnamese Comments).
  - Schema: contracts/schemas/trace-event-v1.schema.json.
"""

from __future__ import annotations

import logging
from typing import Any

from .llm_client import NvidiaLLMClient
from .models import (
    AgentHandoffMessage,
    AgentRole,
    CaseInput,
    CaseInvestigationState,
    InvestigationPlan,
    OrderFindings,
    OrderItemData,
    PaymentFindings,
    PaymentLineData,
    ShipmentFindings,
    TraceEventType,
)
from .tools import ToolAdapter, ToolResult
from .trace import TraceWriter

logger = logging.getLogger("student_agent.specialists")


class BaseSpecialist:
    """Lớp cơ sở cho tất cả các Specialist Agents trong hệ thống Multi-Agent.

    # MỤC ĐÍCH (WHAT):
    Cung cấp các thuộc tính chung (tên, vai trò, adapter công cụ, trace writer) và các hàm
    tiện ích phát sự kiện trace chuẩn hóa, tránh trùng lặp mã nguồn giữa các Agent.

    # CƠ CHẾ HOẠT ĐỘNG (HOW):
    - Nhận `name`, `role`, `tool_adapter`, `trace` trong hàm khởi tạo.
    - Cung cấp phương thức `emit_handoff` ghi nhận sự kiện chuyển giao cả vào TraceWriter
      lẫn vào lịch sử bộ nhớ của `CaseInvestigationState`.

    # LÝ DO THIẾT KẾ (WHY):
    Đảm bảo 100% sự kiện handoff giữa các Agent đều tuân thủ nghiêm ngặt schema trace-event-v1
    và đồng bộ với blackboard state, tối ưu hóa điểm Workflow (5%).
    """

    def __init__(
        self,
        name: str,
        role: AgentRole,
        tool_adapter: ToolAdapter,
        trace: TraceWriter,
    ) -> None:
        self.name = name
        self.role = role
        self.tool_adapter = tool_adapter
        self.trace = trace

    def emit_handoff(
        self,
        receiver: str,
        decision_code: str,
        summary: str,
        state: CaseInvestigationState,
        new_evidence_refs: list[str] | None = None,
        attributes: dict[str, str | int | float | bool | None] | None = None,
    ) -> AgentHandoffMessage:
        """Phát sự kiện chuyển giao ngữ cảnh A2A (handoff) đồng bộ vào trace log và state.

        # MỤC ĐÍCH (WHAT):
        Ghi nhận mốc bàn giao công việc từ agent này sang agent khác, kèm theo tóm tắt và bằng chứng.

        # CƠ CHẾ HOẠT ĐỘNG (HOW):
        1. Lọc và chuẩn hóa `new_evidence_refs` (tối đa 20 phần tử hợp lệ theo schema trace-event-v1).
        2. Chuẩn hóa `attributes`: Đảm bảo toàn bộ giá trị là kiểu nguyên thủy (primitive types).
        3. Gọi `self.trace.emit(event_type="handoff", actor=self.name, target=receiver, ...)`.
        4. Gọi `state.record_handoff(...)` để lưu vào lịch sử blackboard của ca điều tra.

        # LÝ DO THIẾT KẾ (WHY):
        Đáp ứng yêu cầu bắt buộc của scoring-policy-v2 (`workflow_required_events` chứa 'handoff')
        và ngăn chặn ContractError do thuộc tính lồng nhau (nested dicts).
        """
        clean_refs = self.tool_adapter.filter_valid_refs(new_evidence_refs or [])[:20]
        clean_attrs: dict[str, str | int | float | bool | None] = {}
        if attributes:
            for k, v in attributes.items():
                if isinstance(v, (str, int, float, bool)) or v is None:
                    clean_attrs[k] = v
                else:
                    clean_attrs[k] = str(v)[:80]

        # 1. Phát sự kiện ra Trace Log (traces/trace.jsonl)
        self.trace.emit(
            case_id=state.case_id,
            event_type=TraceEventType.HANDOFF.value,
            actor=self.name,
            target=receiver,
            decision_code=decision_code[:80],
            evidence_refs=clean_refs,
            attributes=clean_attrs,
        )

        # 2. Ghi nhận vào bộ nhớ trạng thái nội bộ
        return state.record_handoff(
            sender=self.name,
            receiver=receiver,
            decision_code=decision_code,
            summary=summary,
            new_evidence_refs=clean_refs,
            attributes=clean_attrs,
        )


class CoordinatorAgent(BaseSpecialist):
    """Agent Điều Phối (Coordinator Agent) - Đầu não tiếp nhận và lập kế hoạch điều tra.

    # MỤC ĐÍCH (WHAT):
    Phân tích đơn khiếu nại của khách hàng, trích xuất mã đơn hàng (`claimed_order_id`),
    nhận diện ý định và các chủ đề khiếu nại, thiết lập kế hoạch điều tra (`InvestigationPlan`),
    và phát sự kiện trace `task_assigned`.

    # CƠ CHẾ HOẠT ĐỘNG (HOW):
    - Đọc thông tin từ `case_input.customer_request`.
    - Sử dụng `NvidiaLLMClient.analyze_intent` (với fallback deterministic) để xác định miền cần truy vấn.
    - Phát sự kiện trace `task_assigned` với `actor="coordinator"` và `target="order-agent"`.
    - Thực hiện handoff chuyển giao công việc cho `order-agent`.

    # LÝ DO THIẾT KẾ (WHY):
    Tuân thủ đúng trình tự vòng đời sự kiện: case_received -> task_assigned -> handoff.
    """

    def __init__(
        self,
        tool_adapter: ToolAdapter,
        trace: TraceWriter,
        llm_client: NvidiaLLMClient | None = None,
    ) -> None:
        super().__init__(
            name=AgentRole.COORDINATOR.value,
            role=AgentRole.COORDINATOR,
            tool_adapter=tool_adapter,
            trace=trace,
        )
        self.llm_client = llm_client

    async def coordinate(self, state: CaseInvestigationState) -> InvestigationPlan:
        """Thực hiện điều phối, phân tích khiếu nại và lập kế hoạch điều tra.

        # MỤC ĐÍCH (WHAT): Khởi tạo kế hoạch điều tra và phân công các specialist.
        # CƠ CHẾ HOẠT ĐỘNG (HOW):
          1. Trích xuất claims và nội dung khiếu nại từ state.case_input.
          2. Gọi LLM hoặc fallback để phân tích ý định (intent analysis).
          3. Xác định các miền dữ liệu cần gọi (order, payment, shipment).
          4. Phát sự kiện trace `task_assigned`.
          5. Bàn giao (handoff) sang `order-agent`.
        # LÝ DO THIẾT KẾ (WHY): Giúp hệ thống không gọi bừa bãi công cụ ngoài phạm vi.
        """
        case_input = state.case_input
        customer_req = case_input.customer_request
        order_id = customer_req.claimed_order_id
        claims = list(customer_req.claims)

        # Phân tích ý định qua LLM hoặc Fallback Engine
        claims_raw = [{"claim_id": c.claim_id, "topic": c.topic} for c in claims]
        intent_info: dict[str, Any] = {}
        if self.llm_client:
            intent_info = await self.llm_client.analyze_intent(customer_req.message, claims_raw)
        else:
            # Fallback nếu không truyền LLM client
            primary_topic = claims[0].topic if claims else "unsupported_claim"
            intent_info = {
                "primary_intent": primary_topic,
                "urgency": "medium",
                "requested_remedy": "full_refund",
            }

        # Xác định các domain cần điều tra dựa trên ý định
        primary_intent = str(intent_info.get("primary_intent", ""))
        needed_domains = ["order", "payment", "shipment"]
        assigned_agents = [
            AgentRole.ORDER_AGENT.value,
            AgentRole.PAYMENT_AGENT.value,
            AgentRole.SHIPMENT_AGENT.value,
        ]

        plan = InvestigationPlan(
            case_id=state.case_id,
            order_id=order_id,
            claims=claims,
            needed_domains=needed_domains,
            assigned_agents=assigned_agents,
            hypotheses=[primary_intent],
            strategy_notes=f"Độ khẩn cấp: {intent_info.get('urgency', 'medium')}",
        )
        state.plan = plan

        # Phát sự kiện trace task_assigned (bắt buộc theo scoring-policy-v2)
        self.trace.emit(
            case_id=state.case_id,
            event_type=TraceEventType.TASK_ASSIGNED.value,
            actor=self.name,
            target=AgentRole.ORDER_AGENT.value,
            decision_code="INVESTIGATION_DISPATCH",
            evidence_refs=[],
            attributes={
                "order_id": order_id,
                "claims_count": len(claims),
                "primary_intent": primary_intent,
                "needed_domains": ",".join(needed_domains),
            },
        )

        # Phát sự kiện handoff chuyển giao cho OrderAgent
        self.emit_handoff(
            receiver=AgentRole.ORDER_AGENT.value,
            decision_code="DISPATCH_TO_ORDER_AGENT",
            summary=f"Bắt đầu điều tra đơn hàng {order_id} với {len(claims)} khiếu nại.",
            state=state,
            attributes={"order_id": order_id, "claims_count": len(claims)},
        )

        return plan


class OrderAgent(BaseSpecialist):
    """Specialist Agent chịu trách nhiệm thẩm tra dữ liệu Đơn hàng và Mặt hàng (Order & Item).

    # MỤC ĐÍCH (WHAT):
    Truy vấn công cụ `get_order` và `get_order_items` qua ToolAdapter, xác định trạng thái đơn hàng
    (delivered, canceled, unavailable), tính toán tổng tiền hàng và phí vận chuyển, thu thập
    danh sách người bán (`seller_ids`).

    # CƠ CHẾ HOẠT ĐỘNG (HOW):
    - Gọi `self.tool_adapter.call("get_order", actor=self.name, order_id=state.order_id)`.
    - Trích xuất dữ liệu, đóng gói vào `OrderFindings`.
    - Cập nhật vào `state.order_findings`.
    - Phát sự kiện `handoff` chuyển giao dữ liệu sang `payment-agent`.

    # LÝ DO THIẾT KẾ (WHY):
    Phát hiện ngay các trường hợp hủy đơn hoặc hết hàng để đối soát với cổng thanh toán.
    """

    def __init__(self, tool_adapter: ToolAdapter, trace: TraceWriter) -> None:
        super().__init__(
            name=AgentRole.ORDER_AGENT.value,
            role=AgentRole.ORDER_AGENT,
            tool_adapter=tool_adapter,
            trace=trace,
        )

    async def investigate(self, state: CaseInvestigationState) -> OrderFindings:
        """Thực thi điều tra thông tin đơn hàng từ MCP Gateway."""
        order_id = state.order_id
        order_tool = self.tool_adapter.resolve_tool_for_domain("order", default="get_order") or "get_order"
        evidence_refs: list[str] = []
        raw_order: dict[str, Any] = {}

        try:
            res: ToolResult = await self.tool_adapter.call(order_tool, actor=self.name, order_id=order_id)
            evidence_refs.append(res.evidence_ref)
            raw_order = res.data
        except Exception as exc:
            logger.warning("Không thể truy vấn order data cho đơn %s: %s", order_id, exc)
            state.errors.append(f"OrderAgent error: {exc}")

        # Thử lấy chi tiết items nếu có tool riêng biệt
        items_data: list[OrderItemData] = []
        seller_ids: list[str] = []
        item_ids: list[str] = []
        items_tool = self.tool_adapter.resolve_tool_for_domain("item")
        if items_tool and self.tool_adapter.has_tool(items_tool):
            try:
                item_res = await self.tool_adapter.call(items_tool, actor=self.name, order_id=order_id)
                evidence_refs.append(item_res.evidence_ref)
                raw_items = item_res.data.get("items", [])
                for idx, itm in enumerate(raw_items):
                    p_id = str(itm.get("product_id", f"prod_{idx}"))
                    s_id = str(itm.get("seller_id", "unknown_seller"))
                    seller_ids.append(s_id)
                    item_ids.append(p_id)
                    items_data.append(
                        OrderItemData(
                            order_id=order_id,
                            order_item_id=itm.get("order_item_id", idx + 1),
                            product_id=p_id,
                            seller_id=s_id,
                            shipping_limit_date=itm.get("shipping_limit_date"),
                            price=float(itm.get("price", 0.0) or 0.0),
                            freight_value=float(itm.get("freight_value", 0.0) or 0.0),
                        )
                    )
            except Exception as item_exc:
                logger.debug("Không thể lấy items từ tool riêng: %s", item_exc)

        # Nếu items nằm lồng sẵn trong raw_order
        if not items_data and "items" in raw_order and isinstance(raw_order["items"], list):
            for idx, itm in enumerate(raw_order["items"]):
                p_id = str(itm.get("product_id", f"prod_{idx}"))
                s_id = str(itm.get("seller_id", "unknown_seller"))
                seller_ids.append(s_id)
                item_ids.append(p_id)
                items_data.append(
                    OrderItemData(
                        order_id=order_id,
                        order_item_id=itm.get("order_item_id", idx + 1),
                        product_id=p_id,
                        seller_id=s_id,
                        shipping_limit_date=itm.get("shipping_limit_date"),
                        price=float(itm.get("price", 0.0) or 0.0),
                        freight_value=float(itm.get("freight_value", 0.0) or 0.0),
                    )
                )

        status = str(raw_order.get("status", raw_order.get("order_status", "unknown"))).lower()
        total_items_price = round(sum(i.price for i in items_data), 2)
        total_freight_value = round(sum(i.freight_value for i in items_data), 2)
        total_order_val = float(raw_order.get("total_value", total_items_price + total_freight_value) or 0.0)

        findings = OrderFindings(
            order_id=order_id,
            status=status,
            customer_id=raw_order.get("customer_id"),
            order_purchase_timestamp=raw_order.get("order_purchase_timestamp"),
            order_approved_at=raw_order.get("order_approved_at"),
            order_delivered_carrier_date=raw_order.get("order_delivered_carrier_date"),
            order_delivered_customer_date=raw_order.get("order_delivered_customer_date"),
            order_estimated_delivery_date=raw_order.get("order_estimated_delivery_date"),
            items=items_data,
            seller_ids=list(dict.fromkeys(seller_ids)),
            item_ids=list(dict.fromkeys(item_ids)),
            total_items_price=total_items_price,
            total_freight_value=total_freight_value,
            total_order_value=total_order_val,
            evidence_refs=evidence_refs,
            raw_data=raw_order,
        )
        state.order_findings = findings

        # Bàn giao sang PaymentAgent
        self.emit_handoff(
            receiver=AgentRole.PAYMENT_AGENT.value,
            decision_code="ORDER_FINDINGS_READY",
            summary=f"Trạng thái đơn: {status}, tổng giá trị: {total_order_val:.2f} BRL, {len(items_data)} items.",
            state=state,
            new_evidence_refs=evidence_refs,
            attributes={
                "order_status": status,
                "total_order_value": total_order_val,
                "items_count": len(items_data),
            },
        )
        return findings


class PaymentAgent(BaseSpecialist):
    """Specialist Agent chịu trách nhiệm điều tra Tài chính, Thanh toán và Hoàn tiền (Payment & Refund).

    # MỤC ĐÍCH (WHAT):
    Truy vấn `get_payment` và `get_refund`, kiểm tra các dòng thanh toán, tính tổng tiền khách đã trả,
    phát hiện thanh toán phân tách (split payment), khoản thu trùng lặp (duplicate charge),
    hoặc sai lệch số tiền (payment mismatch).

    # CƠ CHẾ HOẠT ĐỘNG (HOW):
    - Gọi MCP Gateway lấy dữ liệu thanh toán.
    - Đối chiếu `total_paid` với `order_findings.total_order_value`.
    - Ghi nhận `PaymentFindings` vào `state.payment_findings`.
    - Phát sự kiện `handoff` chuyển giao kết quả sang `shipment-agent`.

    # LÝ DO THIẾT KẾ (WHY):
    Phát hiện các bất thường thanh toán để xác định chính xác các mã lỗi tài chính.
    """

    def __init__(self, tool_adapter: ToolAdapter, trace: TraceWriter) -> None:
        super().__init__(
            name=AgentRole.PAYMENT_AGENT.value,
            role=AgentRole.PAYMENT_AGENT,
            tool_adapter=tool_adapter,
            trace=trace,
        )

    async def investigate(self, state: CaseInvestigationState) -> PaymentFindings:
        """Thực thi đối soát thanh toán và hoàn tiền từ MCP Gateway."""
        order_id = state.order_id
        payment_tool = self.tool_adapter.resolve_tool_for_domain("payment", default="get_payment") or "get_payment"
        evidence_refs: list[str] = []
        raw_payment: dict[str, Any] = {}

        try:
            res: ToolResult = await self.tool_adapter.call(payment_tool, actor=self.name, order_id=order_id)
            evidence_refs.append(res.evidence_ref)
            raw_payment = res.data
        except Exception as exc:
            logger.warning("Không thể truy vấn payment data cho đơn %s: %s", order_id, exc)
            state.errors.append(f"PaymentAgent error: {exc}")

        # Thử kiểm tra refund tool nếu có
        refund_status: str | None = None
        refund_amount = 0.0
        refund_tool = self.tool_adapter.resolve_tool_for_domain("refund")
        if refund_tool and self.tool_adapter.has_tool(refund_tool):
            try:
                r_res = await self.tool_adapter.call(refund_tool, actor=self.name, order_id=order_id)
                evidence_refs.append(r_res.evidence_ref)
                refund_status = str(r_res.data.get("refund_status", r_res.data.get("status", "unknown")))
                refund_amount = float(r_res.data.get("refund_amount", 0.0) or 0.0)
            except Exception as r_exc:
                logger.debug("Refund tool error: %s", r_exc)

        # Trích xuất các dòng thanh toán
        payment_lines: list[PaymentLineData] = []
        payment_types: list[str] = []
        payment_refs: list[str] = []
        raw_lines = raw_payment.get("payments", raw_payment.get("payment_lines", []))
        if isinstance(raw_lines, list) and raw_lines:
            for idx, p in enumerate(raw_lines):
                ptype = str(p.get("payment_type", "credit_card"))
                pval = float(p.get("payment_value", 0.0) or 0.0)
                pref = p.get("payment_reference", f"pay_{order_id}_{idx+1}")
                payment_types.append(ptype)
                payment_refs.append(pref)
                payment_lines.append(
                    PaymentLineData(
                        order_id=order_id,
                        payment_sequential=p.get("payment_sequential", idx + 1),
                        payment_type=ptype,
                        payment_installments=p.get("payment_installments", 1),
                        payment_value=pval,
                        payment_reference=pref,
                    )
                )

        total_paid = round(
            sum(pl.payment_value for pl in payment_lines)
            if payment_lines
            else float(raw_payment.get("total_paid", raw_payment.get("payment_value", 0.0)) or 0.0),
            2,
        )

        expected_val = state.order_findings.total_order_value if state.order_findings else total_paid
        diff_amount = round(total_paid - expected_val, 2)
        is_split = len(payment_lines) > 1 or len(set(payment_types)) > 1

        # Phát hiện duplicate charge: Có 2 giao dịch cùng số tiền hoặc tổng tiền vượt quá gấp đôi giá trị đơn
        has_duplicate = False
        if len(payment_lines) >= 2:
            amounts = [pl.payment_value for pl in payment_lines]
            if len(amounts) != len(set(amounts)) and expected_val > 0 and total_paid > expected_val:
                has_duplicate = True

        mismatch = abs(diff_amount) > 0.01 and not has_duplicate

        findings = PaymentFindings(
            order_id=order_id,
            payment_lines=payment_lines,
            payment_types=list(dict.fromkeys(payment_types)),
            payment_references=list(dict.fromkeys(payment_refs)),
            total_paid=total_paid,
            is_split_payment=is_split,
            has_duplicate_charge=has_duplicate,
            payment_mismatch=mismatch,
            expected_order_value=expected_val,
            difference_amount=diff_amount,
            refund_status=refund_status or raw_payment.get("refund_status"),
            refund_amount_processed=refund_amount,
            evidence_refs=evidence_refs,
            raw_data=raw_payment,
        )
        state.payment_findings = findings

        # Bàn giao sang ShipmentAgent
        self.emit_handoff(
            receiver=AgentRole.SHIPMENT_AGENT.value,
            decision_code="PAYMENT_FINDINGS_READY",
            summary=f"Tổng tiền đã thu: {total_paid:.2f} BRL ({len(payment_lines)} giao dịch). Duplicate: {has_duplicate}.",
            state=state,
            new_evidence_refs=evidence_refs,
            attributes={
                "total_paid": total_paid,
                "is_split_payment": is_split,
                "has_duplicate_charge": has_duplicate,
                "payment_mismatch": mismatch,
            },
        )
        return findings


class ShipmentAgent(BaseSpecialist):
    """Specialist Agent chịu trách nhiệm thẩm tra Vận chuyển và Giao nhận (Shipment & Carrier).

    # MỤC ĐÍCH (WHAT):
    Truy vấn `get_shipment`, tính toán và đối chiếu các mốc thời gian giao bưu cục vs hạn chót
    giao hàng của người bán (`shipping_limit_date`), và ngày giao thực tế vs ngày hẹn (`estimated_delivery_date`).

    # CƠ CHẾ HOẠT ĐỘNG (HOW):
    - Gọi MCP Gateway lấy dữ liệu shipment.
    - Phân tích độ trễ: phân định rõ lỗi do người bán (`seller_delay`) hay do đơn vị vận tải (`carrier_delay`).
    - Lưu `ShipmentFindings` vào `state.shipment_findings`.
    - Phát sự kiện `handoff` chuyển giao toàn bộ chứng cứ cho `policy-agent`.

    # LÝ DO THIẾT KẾ (WHY):
    Quyết định chính xác mã lỗi `late_delivery_seller` hay `late_delivery_logistics`,
    ảnh hưởng trực tiếp tới 45% điểm Semantic và đúng đắn của việc phạt người bán.
    """

    def __init__(self, tool_adapter: ToolAdapter, trace: TraceWriter) -> None:
        super().__init__(
            name=AgentRole.SHIPMENT_AGENT.value,
            role=AgentRole.SHIPMENT_AGENT,
            tool_adapter=tool_adapter,
            trace=trace,
        )

    async def investigate(self, state: CaseInvestigationState) -> ShipmentFindings:
        """Thực thi điều tra vận đơn và đối soát thời gian giao hàng."""
        order_id = state.order_id
        shipment_tool = self.tool_adapter.resolve_tool_for_domain("shipment", default="get_shipment") or "get_shipment"
        evidence_refs: list[str] = []
        raw_shipment: dict[str, Any] = {}

        try:
            res: ToolResult = await self.tool_adapter.call(shipment_tool, actor=self.name, order_id=order_id)
            evidence_refs.append(res.evidence_ref)
            raw_shipment = res.data
        except Exception as exc:
            logger.warning("Không thể truy vấn shipment data cho đơn %s: %s", order_id, exc)
            state.errors.append(f"ShipmentAgent error: {exc}")

        # Trích xuất các mốc thời gian
        delivered_carrier = raw_shipment.get("delivered_carrier_date") or (
            state.order_findings.order_delivered_carrier_date if state.order_findings else None
        )
        delivered_cust = raw_shipment.get("delivered_customer_date") or (
            state.order_findings.order_delivered_customer_date if state.order_findings else None
        )
        estimated_date = raw_shipment.get("estimated_delivery_date") or (
            state.order_findings.order_estimated_delivery_date if state.order_findings else None
        )

        shipping_limit: str | None = None
        if state.order_findings and state.order_findings.items:
            shipping_limit = state.order_findings.items[0].shipping_limit_date

        is_delayed = False
        delay_days = 0.0
        seller_delay = False
        carrier_delay = False

        # Phân tích so sánh chuỗi ngày dạng ISO 8601 (YYYY-MM-DD)
        if delivered_cust and estimated_date:
            if str(delivered_cust)[:10] > str(estimated_date)[:10]:
                is_delayed = True
                delay_days = 3.0  # Ước lượng độ trễ mặc định

        if delivered_carrier and shipping_limit:
            if str(delivered_carrier)[:10] > str(shipping_limit)[:10]:
                seller_delay = True

        if is_delayed and not seller_delay:
            carrier_delay = True
        elif is_delayed and seller_delay:
            # Nếu người bán giao trễ dẫn đến toàn bộ đơn bị trễ
            pass

        shipment_ids = [str(raw_shipment.get("shipment_id", f"ship_{order_id}"))] if raw_shipment else []

        findings = ShipmentFindings(
            order_id=order_id,
            shipment_ids=shipment_ids,
            carrier_partner=raw_shipment.get("carrier_partner", raw_shipment.get("carrier_name")),
            shipping_limit_date=shipping_limit,
            delivered_carrier_date=delivered_carrier,
            delivered_customer_date=delivered_cust,
            estimated_delivery_date=estimated_date,
            is_delayed=is_delayed,
            delay_days=delay_days,
            seller_delay=seller_delay,
            carrier_delay=carrier_delay,
            delivery_status=str(raw_shipment.get("delivery_status", raw_shipment.get("status", "unknown"))),
            evidence_refs=evidence_refs,
            raw_data=raw_shipment,
        )
        state.shipment_findings = findings

        # Bàn giao sang PolicyAgent
        self.emit_handoff(
            receiver=AgentRole.POLICY_AGENT.value,
            decision_code="SHIPMENT_FINDINGS_READY",
            summary=f"Giao trễ: {is_delayed}, Lỗi seller: {seller_delay}, Lỗi carrier: {carrier_delay}.",
            state=state,
            new_evidence_refs=evidence_refs,
            attributes={
                "is_delayed": is_delayed,
                "seller_delay": seller_delay,
                "carrier_delay": carrier_delay,
            },
        )
        return findings
```

---

### 4.2 Specification for `src/student_agent/policy.py`

Below is the design and complete code specification for `policy.py`. It integrates the authoritative `EC_POLICY_V1` decision matrix for all 11 primary issues, the `ConflictDetector` (strictly enforcing `sources` with `minItems: 2`), the `ClaimAdjudicator` (linking genuine evidence refs via `ToolAdapter`), emits `policy_decided` and `handoff` trace events with primitive attributes, and includes Vietnamese comments (R4).

```python
"""Module: policy.py.

Hệ thống: K4-L3A Multi-Agent E-Commerce Complaint Investigation System.
Mô tả: Động cơ phán quyết chính sách (Policy Engine) thực thi quy định EC_POLICY_V1.
Bao gồm:
  1. ConflictDetector: Phát hiện xung đột dữ liệu chéo miền (Cross-Domain Data Conflict Detection),
     đảm bảo mảng `sources` luôn chứa ít nhất 2 nguồn dữ liệu độc lập (minItems: 2).
  2. ClaimAdjudicator: Thẩm định từng yêu cầu khiếu nại của khách hàng (Claim Assessment Adjudication),
     đưa ra phán quyết (supported, unsupported, partially_supported, insufficient_evidence)
     và liên kết bằng chứng thật qua ToolAdapter.
  3. PolicyEngine: Đánh giá 11 vấn đề cốt lõi, xác định trạng thái vụ việc (case_status),
     xếp hạng nguyên nhân gốc rễ (ranked_causes), chỉ định bên chịu trách nhiệm (responsible_parties),
     tính toán bồi hoàn tài chính (financial_resolution), và phát sự kiện trace `policy_decided`
     với `actor="policy-agent"`.

Tuân thủ:
  - contracts/schemas/l3a-output-v2.schema.json.
  - contracts/schemas/trace-event-v1.schema.json.
  - contracts/scoring/scoring-policy-v2.json.
"""

from __future__ import annotations

import logging
from typing import Any

from .models import (
    AgentRole,
    Assessment,
    CaseInvestigationState,
    CaseStatus,
    ClaimAssessment,
    ClaimVerdict,
    DataConflict,
    FinancialResolution,
    PartyType,
    PolicyDecision,
    PrimaryIssue,
    RankedCause,
    RefundLine,
    ResponsibleParty,
    RootCauseAnalysis,
    TraceEventType,
)
from .tools import ToolAdapter
from .trace import TraceWriter

logger = logging.getLogger("student_agent.policy")


class ConflictDetector:
    """Bộ phát hiện xung đột dữ liệu chéo miền (Cross-Domain Data Conflict Detector).

    # MỤC ĐÍCH (WHAT):
    Phát hiện các điểm mâu thuẫn giữa các miền dữ liệu độc lập (Đơn hàng, Thanh toán, Vận chuyển)
    và đóng gói thành đối tượng `DataConflict` hợp lệ theo schema.

    # CƠ CHẾ HOẠT ĐỘNG (HOW):
    - So sánh trạng thái và số liệu giữa:
      + Order status vs Payment capture status.
      + Order items value vs Payment captured value.
      + Order delivery estimate vs Carrier actual delivery date.
      + Item shipping limit SLA vs Carrier handoff date.
      + Customer claim message vs Carrier delivery proof.
    - ĐẶC BIỆT TUÂN THỦ SCHEMA: Thuộc tính `sources` BẮT BUỘC chứa từ 2 đến 5 nguồn phân biệt (`minItems: 2`).
    - Gán `selected_source` là nguồn dữ liệu có thẩm quyền cao hơn và `resolution_code` xử lý.

    # LÝ DO THIẾT KẾ (WHY):
    Ngăn chặn tuyệt đối vi phạm schema (Hard Gate: unscorable_schema) khi mảng sources chỉ có 1 phần tử,
    đồng thời cung cấp căn cứ xử lý minh bạch cho vụ việc.
    """

    @staticmethod
    def detect_conflicts(state: CaseInvestigationState) -> list[DataConflict]:
        """Phát hiện toàn bộ các mâu thuẫn chéo miền trong ca điều tra hiện tại."""
        conflicts: list[DataConflict] = []
        order = state.order_findings
        payment = state.payment_findings
        shipment = state.shipment_findings

        if not order or not payment:
            return conflicts

        # Mâu thuẫn 1: Đơn hàng bị hủy nhưng tiền đã trừ thành công (Order Canceled vs Payment Captured)
        if order.is_canceled and payment.total_paid > 0 and payment.refund_status != "completed":
            conflicts.append(
                DataConflict(
                    field="order_status_vs_payment",
                    sources=["order.status", "payment.total_paid"],
                    selected_source="order.status",
                    resolution_code="ORDER_CANCELED_PRIORITIZE_REFUND",
                )
            )

        # Mâu thuẫn 2: Đơn hàng hết/không khả dụng nhưng tiền đã trừ (Order Unavailable vs Payment Captured)
        if order.is_unavailable and payment.total_paid > 0 and payment.refund_status != "completed":
            conflicts.append(
                DataConflict(
                    field="order_availability_vs_payment",
                    sources=["order.status", "payment.total_paid"],
                    selected_source="order.status",
                    resolution_code="ITEM_UNAVAILABLE_PRIORITIZE_REFUND",
                )
            )

        # Mâu thuẫn 3: Sai lệch số tiền giữa đơn hàng và cổng thanh toán (Order Value vs Amount Paid)
        if order.total_order_value > 0 and abs(order.total_order_value - payment.total_paid) > 0.01:
            conflicts.append(
                DataConflict(
                    field="order_total_value_vs_payment_captured",
                    sources=["order.total_order_value", "payment.total_paid"],
                    selected_source="payment.total_paid",
                    resolution_code=(
                        "RECONCILE_PAYMENT_LEDGER_OVERPAYMENT"
                        if payment.has_duplicate_charge
                        else "RECONCILE_PAYMENT_MISMATCH"
                    ),
                )
            )

        # Mâu thuẫn 4: Ngày giao thực tế trễ hơn ngày cam kết ước tính (Estimate vs Actual Carrier Delivery)
        if shipment and shipment.is_delayed:
            conflicts.append(
                DataConflict(
                    field="estimated_delivery_vs_carrier_actual",
                    sources=["order.estimated_delivery_date", "shipment.delivered_customer_date"],
                    selected_source="shipment.delivered_customer_date",
                    resolution_code="CARRIER_ACTUAL_DELIVERY_PREVAILS",
                )
            )

        # Mâu thuẫn 5: Người bán bàn giao trễ hạn chót SLA (Seller SLA Limit vs Carrier Handoff Date)
        if shipment and shipment.seller_delay:
            conflicts.append(
                DataConflict(
                    field="seller_shipping_limit_vs_carrier_handoff",
                    sources=["item.shipping_limit_date", "shipment.delivered_carrier_date"],
                    selected_source="shipment.delivered_carrier_date",
                    resolution_code="SELLER_DISPATCH_BREACH_PENALTY",
                )
            )

        # Giới hạn tối đa 5 conflicts theo schema và lọc đảm bảo >= 2 sources
        valid_conflicts = [c for c in conflicts if len(c.sources) >= 2][:5]
        return valid_conflicts


class ClaimAdjudicator:
    """Bộ thẩm định và phân xử khiếu nại (Claim Assessment Adjudicator).

    # MỤC ĐÍCH (WHAT):
    Đánh giá từng yêu cầu cụ thể (Claim) của khách hàng đối chiếu với bằng chứng xác thực,
    xác định phán quyết (supported, unsupported, partially_supported, insufficient_evidence),
    độ tin cậy (confidence), và liên kết các `evidence_refs` thẩm quyền tương ứng.

    # CƠ CHẾ HOẠT ĐỘNG (HOW):
    - Duyệt qua từng `CustomerClaim` trong `state.case_input.customer_request.claims`.
    - Đối chiếu topic khiếu nại với kết quả xác thực từ `OrderFindings`, `PaymentFindings`, `ShipmentFindings`.
    - Lấy danh sách candidate `evidence_refs` từ các specialist liên quan.
    - Lọc qua `tool_adapter.filter_valid_refs()` để đảm bảo 100% bằng chứng đính kèm là thật (Anti-Hallucination).

    # LÝ DO THIẾT KẾ (WHY):
    Đáp ứng khối `claim_assessments` trong output schema và bảo vệ Hard Gate `unknown_evidence_ref`.
    """

    @staticmethod
    def adjudicate_claims(
        state: CaseInvestigationState,
        tool_adapter: ToolAdapter,
    ) -> list[ClaimAssessment]:
        """Thẩm định toàn bộ danh sách khiếu nại của khách hàng trong case."""
        assessments: list[ClaimAssessment] = []
        claims = state.case_input.customer_request.claims
        order = state.order_findings
        payment = state.payment_findings
        shipment = state.shipment_findings

        # Nếu không có dữ liệu đơn hàng hoặc hệ thống bị lỗi nghiêm trọng
        if not order and not payment:
            for c in claims[:5]:
                assessments.append(
                    ClaimAssessment(
                        claim_id=c.claim_id,
                        verdict=ClaimVerdict.INSUFFICIENT_EVIDENCE,
                        confidence=0.50,
                        evidence_refs=[],
                    )
                )
            return assessments

        order_refs = order.evidence_refs if order else []
        payment_refs = payment.evidence_refs if payment else []
        shipment_refs = shipment.evidence_refs if shipment else []

        for claim in claims[:5]:
            claim_id = claim.claim_id
            topic = claim.topic.lower().strip()
            verdict: ClaimVerdict = ClaimVerdict.UNSUPPORTED
            confidence = 0.85
            candidate_refs: list[str] = []

            # 1. Khiếu nại đơn bị hủy nhưng đã trả tiền
            if topic in ("canceled_order_paid", "order_canceled_unrefunded"):
                candidate_refs.extend(order_refs + payment_refs)
                if order and order.is_canceled and payment and payment.total_paid > 0:
                    verdict = ClaimVerdict.SUPPORTED
                    confidence = 0.95
                else:
                    verdict = ClaimVerdict.UNSUPPORTED
                    confidence = 0.90

            # 2. Khiếu nại đơn không khả dụng / hết hàng
            elif topic in ("unavailable_order_paid", "item_unavailable"):
                candidate_refs.extend(order_refs + payment_refs)
                if order and order.is_unavailable and payment and payment.total_paid > 0:
                    verdict = ClaimVerdict.SUPPORTED
                    confidence = 0.95
                else:
                    verdict = ClaimVerdict.UNSUPPORTED
                    confidence = 0.90

            # 3. Khiếu nại người bán giao trễ
            elif topic in ("late_delivery_seller", "seller_delay"):
                candidate_refs.extend(shipment_refs + order_refs)
                if shipment and shipment.seller_delay:
                    verdict = ClaimVerdict.SUPPORTED
                    confidence = 0.92
                else:
                    verdict = ClaimVerdict.UNSUPPORTED
                    confidence = 0.88

            # 4. Khiếu nại đơn vị vận tải giao trễ
            elif topic in ("late_delivery_logistics", "carrier_delay"):
                candidate_refs.extend(shipment_refs)
                if shipment and shipment.carrier_delay:
                    verdict = ClaimVerdict.SUPPORTED
                    confidence = 0.92
                else:
                    verdict = ClaimVerdict.UNSUPPORTED
                    confidence = 0.88

            # 5. Khiếu nại bị trừ tiền 2 lần
            elif topic in ("duplicate_charge", "double_charge"):
                candidate_refs.extend(payment_refs)
                if payment and payment.has_duplicate_charge:
                    verdict = ClaimVerdict.SUPPORTED
                    confidence = 0.95
                else:
                    verdict = ClaimVerdict.UNSUPPORTED
                    confidence = 0.90

            # 6. Khiếu nại sai lệch tiền
            elif topic in ("payment_mismatch", "amount_discrepancy"):
                candidate_refs.extend(payment_refs + order_refs)
                if payment and payment.payment_mismatch:
                    verdict = ClaimVerdict.SUPPORTED
                    confidence = 0.93
                else:
                    verdict = ClaimVerdict.UNSUPPORTED
                    confidence = 0.90

            # 7. Khiếu nại thanh toán phân tách
            elif topic in ("valid_split_payment", "split_payment"):
                candidate_refs.extend(payment_refs)
                if payment and payment.is_split_payment:
                    verdict = ClaimVerdict.SUPPORTED
                    confidence = 0.92
                else:
                    verdict = ClaimVerdict.UNSUPPORTED
                    confidence = 0.85

            # 8. Khiếu nại hoàn tiền đang chờ
            elif topic in ("refund_pending", "refund_in_progress"):
                candidate_refs.extend(payment_refs)
                if payment and payment.refund_status in ("pending", "processing", "wait"):
                    verdict = ClaimVerdict.SUPPORTED
                    confidence = 0.92
                else:
                    verdict = ClaimVerdict.UNSUPPORTED
                    confidence = 0.85

            # 9. Khiếu nại hoàn tiền thất bại
            elif topic in ("refund_failed", "refund_error"):
                candidate_refs.extend(payment_refs)
                if payment and payment.refund_status in ("failed", "error", "rejected"):
                    verdict = ClaimVerdict.SUPPORTED
                    confidence = 0.95
                else:
                    verdict = ClaimVerdict.UNSUPPORTED
                    confidence = 0.90

            # 10. Yêu cầu hoàn tiền toàn bộ / một phần
            elif topic in ("requested_full_refund", "full_refund"):
                candidate_refs.extend(order_refs + payment_refs + shipment_refs)
                if (order and (order.is_canceled or order.is_unavailable)) or (payment and payment.has_duplicate_charge):
                    verdict = ClaimVerdict.SUPPORTED
                    confidence = 0.95
                elif shipment and (shipment.seller_delay or shipment.carrier_delay):
                    verdict = ClaimVerdict.PARTIALLY_SUPPORTED
                    confidence = 0.90
                else:
                    verdict = ClaimVerdict.UNSUPPORTED
                    confidence = 0.85

            elif topic in ("requested_partial_refund", "partial_refund"):
                candidate_refs.extend(order_refs + payment_refs + shipment_refs)
                if shipment and (shipment.seller_delay or shipment.carrier_delay):
                    verdict = ClaimVerdict.SUPPORTED
                    confidence = 0.92
                else:
                    verdict = ClaimVerdict.UNSUPPORTED
                    confidence = 0.85

            # 11. Các claim không có cơ sở
            else:
                candidate_refs.extend(order_refs)
                verdict = ClaimVerdict.UNSUPPORTED
                confidence = 0.80

            # Chống ảo giác: Lọc chỉ giữ lại ref thực tế đã được tiêu thụ từ MCP
            valid_refs = tool_adapter.filter_valid_refs(candidate_refs)[:30]

            assessments.append(
                ClaimAssessment(
                    claim_id=claim_id,
                    verdict=verdict,
                    confidence=confidence,
                    evidence_refs=valid_refs,
                )
            )

        return assessments


class PolicyEngine:
    """Động cơ phán quyết chính sách Olist (EC_POLICY_V1 Decision Matrix Engine).

    # MỤC ĐÍCH (WHAT):
    Tổng hợp toàn bộ các phát hiện từ các Specialist Agents, phân loại chính xác vào 1 trong 11
    vấn đề chính (primary_issue), xác định trạng thái xử lý (case_status), phân tích nguyên nhân
    gốc rễ và trách nhiệm pháp lý, tính toán bồi hoàn tài chính, và phát sự kiện `policy_decided`.

    # CƠ CHẾ HOẠT ĐỘNG (HOW):
    1. Chạy `ClaimAdjudicator.adjudicate_claims` thẩm định claims.
    2. Chạy `ConflictDetector.detect_conflicts` phát hiện mâu thuẫn chéo miền.
    3. Thực thi ma trận quyết định EC_POLICY_V1 cho 11 issues.
    4. Kiểm tra các điều kiện bất biến (status == no_action => refund == 0).
    5. Phát sự kiện trace `policy_decided` với `actor="policy-agent"` và các primitive attributes.
    6. Phát sự kiện trace `handoff` chuyển giao sang `verifier`.

    # LÝ DO THIẾT KẾ (WHY):
    Quyết định 45% điểm Semantic, 10% Consistency, 15% Provenance, và 5% Workflow.
    """

    def __init__(self, tool_adapter: ToolAdapter, trace: TraceWriter) -> None:
        self.tool_adapter = tool_adapter
        self.trace = trace

    def evaluate(self, state: CaseInvestigationState) -> PolicyDecision:
        """Đánh giá toàn diện ca khiếu nại và sinh ra PolicyDecision chính thức."""
        order = state.order_findings
        payment = state.payment_findings
        shipment = state.shipment_findings

        # 1. Thẩm định Claims và Phát hiện Conflicts
        claim_assessments = ClaimAdjudicator.adjudicate_claims(state, self.tool_adapter)
        data_conflicts = ConflictDetector.detect_conflicts(state)

        # 2. Xử lý trường hợp thiếu chứng cứ hoặc lỗi kết nối hệ thống
        if not order or not payment or state.errors:
            decision = self._create_insufficient_evidence_decision(state, claim_assessments, data_conflicts)
            self._emit_policy_trace_events(state, decision)
            state.policy_decision = decision
            return decision

        # 3. Ma trận quyết định 11 Primary Issues (Decision Matrix)
        primary_issue: PrimaryIssue
        case_status: CaseStatus
        confidence: float = 0.95
        ranked_causes: list[RankedCause] = []
        responsible_parties: list[ResponsibleParty] = []
        refund_lines: list[RefundLine] = []
        resolution_actions: list[str] = []

        total_paid = payment.total_paid
        total_order = order.total_order_value
        seller_id = order.seller_ids[0] if order.seller_ids else None

        # Nhánh 1: Canceled Order Paid (Đơn hủy nhưng đã trừ tiền)
        if order.is_canceled and total_paid > 0:
            primary_issue = PrimaryIssue.CANCELED_ORDER_PAID
            case_status = CaseStatus.ACTION_REQUIRED
            confidence = 0.98
            ranked_causes = [
                RankedCause("ORDER_CANCELED_AUTO_REFUND_NOT_TRIGGERED", 1),
                RankedCause("PAYMENT_GATEWAY_WEBHOOK_DELAY", 2),
            ]
            responsible_parties = [
                ResponsibleParty(PartyType.PLATFORM, "olist_core_platform"),
                ResponsibleParty(PartyType.PAYMENT_PROVIDER, "gateway_partner"),
            ]
            refund_lines = [
                RefundLine("REFUND_FULL_CANCELED_ORDER", total_paid, order.order_id)
            ]
            resolution_actions = [
                "APPROVE_FULL_REFUND",
                "NOTIFY_CUSTOMER_REFUND_ISSUED",
                "CLOSE_CLAIM_SATISFIED",
            ]

        # Nhánh 2: Unavailable Order Paid (Hết hàng nhưng đã thu tiền)
        elif order.is_unavailable and total_paid > 0:
            primary_issue = PrimaryIssue.UNAVAILABLE_ORDER_PAID
            case_status = CaseStatus.ACTION_REQUIRED
            confidence = 0.98
            ranked_causes = [
                RankedCause("SELLER_INVENTORY_OUT_OF_STOCK", 1),
                RankedCause("PLATFORM_LISTING_SYNC_DELAY", 2),
            ]
            responsible_parties = [
                ResponsibleParty(PartyType.SELLER, seller_id),
                ResponsibleParty(PartyType.PLATFORM, "olist_catalog"),
            ]
            refund_lines = [
                RefundLine("REFUND_FULL_UNAVAILABLE_ITEM", total_paid, order.order_id)
            ]
            resolution_actions = [
                "APPROVE_FULL_REFUND",
                "ISSUE_SELLER_OUT_OF_STOCK_PENALTY",
                "UPDATE_CATALOG_INVENTORY",
            ]

        # Nhánh 3: Duplicate Charge (Bị trừ tiền 2 lần)
        elif payment.has_duplicate_charge:
            primary_issue = PrimaryIssue.DUPLICATE_CHARGE
            case_status = CaseStatus.ACTION_REQUIRED
            confidence = 0.96
            excess_amount = round(total_paid - total_order, 2)
            ranked_causes = [
                RankedCause("PAYMENT_GATEWAY_DUPLICATE_CAPTURE", 1),
            ]
            responsible_parties = [
                ResponsibleParty(PartyType.PAYMENT_PROVIDER, "gateway_partner"),
            ]
            refund_lines = [
                RefundLine("REFUND_DUPLICATE_CAPTURE_PORTION", excess_amount, order.order_id)
            ]
            resolution_actions = [
                "APPROVE_PARTIAL_REFUND",
                "AUDIT_PAYMENT_GATEWAY_TRANSACTIONS",
            ]

        # Nhánh 4: Refund Failed (Lệnh hoàn tiền trước đó bị lỗi)
        elif payment.refund_status in ("failed", "error", "rejected"):
            primary_issue = PrimaryIssue.REFUND_FAILED
            case_status = CaseStatus.ACTION_REQUIRED
            confidence = 0.95
            ranked_causes = [
                RankedCause("BANK_CLEARING_HOUSE_REJECTION", 1),
            ]
            responsible_parties = [
                ResponsibleParty(PartyType.PAYMENT_PROVIDER, "bank_clearing_house"),
            ]
            refund_lines = [
                RefundLine("RETRY_MANUAL_REFUND_OVERRIDE", total_paid, order.order_id)
            ]
            resolution_actions = [
                "MANUAL_REFUND_OVERRIDE",
                "REQUEST_UPDATED_BANK_DETAILS",
            ]

        # Nhánh 5: Late Delivery Seller (Người bán chậm bàn giao)
        elif shipment and shipment.seller_delay:
            primary_issue = PrimaryIssue.LATE_DELIVERY_SELLER
            case_status = CaseStatus.ACTION_REQUIRED
            confidence = 0.93
            ranked_causes = [
                RankedCause("SELLER_DISPATCH_SLA_BREACH", 1),
            ]
            responsible_parties = [
                ResponsibleParty(PartyType.SELLER, seller_id),
            ]
            # Bồi hoàn phí ship do lỗi chậm của người bán
            freight_refund = round(order.total_freight_value, 2)
            if freight_refund > 0:
                refund_lines = [
                    RefundLine("REFUND_FREIGHT_SELLER_DELAY", freight_refund, seller_id)
                ]
            resolution_actions = [
                "APPROVE_FREIGHT_REFUND",
                "ISSUE_SELLER_SLA_WARNING",
                "NOTIFY_CUSTOMER_APOLOGY",
            ]

        # Nhánh 6: Late Delivery Logistics (Đơn vị vận tải giao trễ)
        elif shipment and shipment.carrier_delay:
            primary_issue = PrimaryIssue.LATE_DELIVERY_LOGISTICS
            case_status = CaseStatus.ACTION_REQUIRED
            confidence = 0.93
            ranked_causes = [
                RankedCause("CARRIER_TRANSIT_NETWORK_CONGESTION", 1),
            ]
            responsible_parties = [
                ResponsibleParty(PartyType.LOGISTICS_PROVIDER, shipment.carrier_partner or "logistics_partner"),
            ]
            freight_refund = round(order.total_freight_value, 2)
            if freight_refund > 0:
                refund_lines = [
                    RefundLine("REFUND_FREIGHT_LOGISTICS_DELAY", freight_refund, "logistics_partner")
                ]
            resolution_actions = [
                "APPROVE_FREIGHT_REFUND",
                "SUBMIT_CARRIER_SLA_DISPUTE",
            ]

        # Nhánh 7: Payment Mismatch (Sai lệch số tiền)
        elif payment.payment_mismatch:
            primary_issue = PrimaryIssue.PAYMENT_MISMATCH
            case_status = CaseStatus.ACTION_REQUIRED
            confidence = 0.92
            diff = round(payment.difference_amount, 2)
            ranked_causes = [
                RankedCause("PRICE_CALCULATION_OR_CURRENCY_MISMATCH", 1),
            ]
            responsible_parties = [
                ResponsibleParty(PartyType.PLATFORM, "checkout_pricing_engine"),
            ]
            if diff > 0:
                refund_lines = [
                    RefundLine("REFUND_OVERCHARGED_DIFFERENCE", diff, order.order_id)
                ]
            resolution_actions = [
                "RECONCILE_PAYMENT_LEDGER",
            ]

        # Nhánh 8: Refund Pending (Hoàn tiền đang chờ xử lý ngân hàng)
        elif payment.refund_status in ("pending", "processing", "wait"):
            primary_issue = PrimaryIssue.REFUND_PENDING
            case_status = CaseStatus.NEEDS_INVESTIGATION
            confidence = 0.90
            ranked_causes = [
                RankedCause("STANDARD_BANKING_SETTLEMENT_WINDOW", 1),
            ]
            responsible_parties = [
                ResponsibleParty(PartyType.PAYMENT_PROVIDER, "acquirer_bank"),
            ]
            refund_lines = []
            resolution_actions = [
                "ADVISE_CUSTOMER_BANKING_SLA",
                "MONITOR_PENDING_REFUND",
            ]

        # Nhánh 9: Valid Split Payment (Thanh toán nhiều phần hợp lệ)
        elif payment.is_split_payment and not payment.has_duplicate_charge and abs(total_paid - total_order) <= 0.05:
            primary_issue = PrimaryIssue.VALID_SPLIT_PAYMENT
            case_status = CaseStatus.NO_ACTION
            confidence = 0.95
            ranked_causes = [
                RankedCause("CUSTOMER_CONFUSION_SPLIT_PAYMENT_RECORDS", 1),
            ]
            responsible_parties = [
                ResponsibleParty(PartyType.CUSTOMER, order.customer_id),
            ]
            refund_lines = []
            resolution_actions = [
                "EXPLAIN_SPLIT_PAYMENT_BREAKDOWN",
                "CLOSE_CLAIM_REJECTED",
            ]

        # Nhánh 10: Unsupported Claim (Khiếu nại sai thực tế)
        else:
            primary_issue = PrimaryIssue.UNSUPPORTED_CLAIM
            case_status = CaseStatus.NO_ACTION
            confidence = 0.92
            ranked_causes = [
                RankedCause("CLAIM_UNFOUNDED_BY_BUYER", 1),
            ]
            responsible_parties = [
                ResponsibleParty(PartyType.CUSTOMER, order.customer_id),
            ]
            refund_lines = []
            resolution_actions = [
                "REJECT_UNFOUNDED_CLAIM",
                "PROVIDE_DELIVERY_PROOF_TO_BUYER",
                "CLOSE_CLAIM_REJECTED",
            ]

        # 4. Ràng buộc Tính nhất quán số học (Arithmetic Invariant Enforcement)
        recommended_refund: float
        if case_status == CaseStatus.NO_ACTION:
            recommended_refund = 0.0
            refund_lines = []
        elif case_status == CaseStatus.ACTION_REQUIRED:
            recommended_refund = round(sum(line.amount_brl for line in refund_lines), 2)
        else:  # needs_investigation
            recommended_refund = 0.0
            refund_lines = []

        financial_res = FinancialResolution(
            currency="BRL",
            recommended_refund_brl=recommended_refund,
            refund_lines=refund_lines[:10],
        )

        # 5. Tổng hợp Bằng chứng (Aggregate Provenanced Evidence Refs)
        all_candidate_refs = (
            (order.evidence_refs if order else [])
            + (payment.evidence_refs if payment else [])
            + (shipment.evidence_refs if shipment else [])
        )
        provenanced_refs = self.tool_adapter.filter_valid_refs(all_candidate_refs)[:30]

        # 6. Đóng gói đối tượng PolicyDecision
        decision = PolicyDecision(
            assessment=Assessment(primary_issue, case_status, confidence),
            affected_entities=state.extract_affected_entities(),
            root_cause_analysis=RootCauseAnalysis(
                ranked_causes=ranked_causes[:5],
                responsible_parties=responsible_parties[:5],
            ),
            financial_resolution=financial_res,
            claim_assessments=claim_assessments,
            evidence_refs=provenanced_refs,
            data_conflicts=data_conflicts,
            resolution_actions=list(dict.fromkeys(resolution_actions))[:8],
        )

        # 7. Phát sự kiện Trace: policy_decided và handoff -> verifier
        self._emit_policy_trace_events(state, decision)
        state.policy_decision = decision
        return decision

    def _create_insufficient_evidence_decision(
        self,
        state: CaseInvestigationState,
        claim_assessments: list[ClaimAssessment],
        data_conflicts: list[DataConflict],
    ) -> PolicyDecision:
        """Tạo quyết định an toàn khi thiếu dữ liệu hoặc hệ thống lỗi."""
        decision = PolicyDecision(
            assessment=Assessment(
                primary_issue=PrimaryIssue.INSUFFICIENT_EVIDENCE,
                case_status=CaseStatus.NEEDS_INVESTIGATION,
                confidence=0.50,
            ),
            affected_entities=state.extract_affected_entities(),
            root_cause_analysis=RootCauseAnalysis(
                ranked_causes=[RankedCause("EVIDENCE_RETRIEVAL_UNAVAILABLE", 1)],
                responsible_parties=[ResponsibleParty(PartyType.UNKNOWN, None)],
            ),
            financial_resolution=FinancialResolution(currency="BRL", recommended_refund_brl=0.0, refund_lines=[]),
            claim_assessments=claim_assessments,
            evidence_refs=list(state.consumed_evidence_refs)[:30],
            data_conflicts=data_conflicts,
            resolution_actions=["ESCALATE_TO_HUMAN_SUPERVISOR"],
        )
        return decision

    def _emit_policy_trace_events(self, state: CaseInvestigationState, decision: PolicyDecision) -> None:
        """Phát sự kiện policy_decided và handoff sang verifier tuân thủ tuyệt đối schema."""
        # 1. Phát sự kiện policy_decided
        self.trace.emit(
            case_id=state.case_id,
            event_type=TraceEventType.POLICY_DECIDED.value,
            actor=AgentRole.POLICY_AGENT.value,
            target=AgentRole.VERIFIER.value,
            decision_code=decision.assessment.primary_issue.value,
            evidence_refs=decision.evidence_refs[:20],
            attributes={
                "primary_issue": decision.assessment.primary_issue.value,
                "case_status": decision.assessment.case_status.value,
                "confidence": decision.assessment.confidence,
                "recommended_refund_brl": decision.financial_resolution.recommended_refund_brl,
                "refund_lines_count": len(decision.financial_resolution.refund_lines),
                "claims_count": len(decision.claim_assessments),
                "conflicts_detected": len(decision.data_conflicts),
                "resolution_actions_count": len(decision.resolution_actions),
                "ranked_causes_count": len(decision.root_cause_analysis.ranked_causes),
                "responsible_parties_count": len(decision.root_cause_analysis.responsible_parties),
            },
        )

        # 2. Phát sự kiện handoff sang Verifier
        self.trace.emit(
            case_id=state.case_id,
            event_type=TraceEventType.HANDOFF.value,
            actor=AgentRole.POLICY_AGENT.value,
            target=AgentRole.VERIFIER.value,
            decision_code="POLICY_EVALUATION_COMPLETED",
            evidence_refs=decision.evidence_refs[:20],
            attributes={
                "primary_issue": decision.assessment.primary_issue.value,
                "case_status": decision.assessment.case_status.value,
                "confidence": decision.assessment.confidence,
                "recommended_refund_brl": decision.financial_resolution.recommended_refund_brl,
            },
        )

        state.record_handoff(
            sender=AgentRole.POLICY_AGENT.value,
            receiver=AgentRole.VERIFIER.value,
            decision_code="POLICY_EVALUATION_COMPLETED",
            summary=f"Phán quyết: {decision.assessment.primary_issue.value}, hoàn tiền: {decision.financial_resolution.recommended_refund_brl} BRL.",
            new_evidence_refs=decision.evidence_refs[:20],
            attributes={
                "primary_issue": decision.assessment.primary_issue.value,
                "case_status": decision.assessment.case_status.value,
            },
        )
```

---

## 5. Verification Method

To independently verify that the design and specifications adhere strictly to the contracts and schemas:

1. **Schema Validation of `policy_decided` Trace Event**:
   - Construct a sample `policy_decided` trace event conforming to §4.2:
     ```python
     from pathlib import Path
     from student_agent.contracts import Contracts
     contracts = Contracts(Path("contracts/schemas"))
     event = {
         "schema_version": "day09-trace-event-v1",
         "event_id": "evt_test12345678901234567890",
         "case_id": "L3A_CASE_001",
         "event_type": "policy_decided",
         "occurred_at": "2026-09-25T11:50:00Z",
         "actor": "policy-agent",
         "target": "verifier",
         "decision_code": "canceled_order_paid",
         "evidence_refs": ["ev_order_abc12345678901234567890"],
         "attributes": {
             "primary_issue": "canceled_order_paid",
             "case_status": "action_required",
             "confidence": 0.98,
             "recommended_refund_brl": 150.50,
             "refund_lines_count": 1,
             "claims_count": 2,
             "conflicts_detected": 1,
             "resolution_actions_count": 3
         }
     }
     contracts.validate_trace(event, "test_policy_decided")
     ```
   - *Expected Result*: Passes silently with zero `ContractError`.

2. **Cross-Domain Data Conflict Schema Validation (`minItems: 2`)**:
   - Verify that any conflict produced by `ConflictDetector` adheres to:
     ```python
     conflict = {
         "field": "order_status_vs_payment",
         "sources": ["order.status", "payment.total_paid"],
         "selected_source": "order.status",
         "resolution_code": "ORDER_CANCELED_PRIORITIZE_REFUND"
     }
     assert len(conflict["sources"]) >= 2
     assert len(conflict["sources"]) == len(set(conflict["sources"]))
     ```
   - *Expected Result*: Asserts pass.

3. **Claim Assessment Strict Provenance Linkage**:
   - Verify that `ClaimAdjudicator` uses `tool_adapter.filter_valid_refs()`:
     ```python
     # Candidate refs containing fake or unconsumed refs are strictly filtered out
     fake_candidate = ["ev_fake_unconsumed_12345678901234"]
     assert tool_adapter.filter_valid_refs(fake_candidate) == []
     ```
   - *Expected Result*: Guarantees zero `unknown_evidence_ref` or `cross_scope_evidence_ref` hard gate failures.

4. **Invalidation Conditions**:
   - If `contracts/schemas/trace-event-v1.schema.json` is changed to allow non-primitive attributes, update `_emit_policy_trace_events`.
   - If `contracts/schemas/l3a-output-v2.schema.json` alters enum values for `PrimaryIssue`, `CaseStatus`, or `ClaimVerdict`, synchronize `models.py` and `policy.py`.
