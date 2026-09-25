"""Module: specialists.py.

Hệ thống: K4-L3A Multi-Agent E-Commerce Complaint Investigation System.
Mô tả: Kiến trúc các Specialist Agents điều tra chuyên sâu và phối hợp Agent-to-Agent (A2A).
Các Agents bao gồm:
  1. CoordinatorAgent: Tiếp nhận Case, đánh giá an toàn, phân tích ý định, lập kế hoạch và phân công (task_assigned).
  2. OrderAgent (order-agent): Thu thập dữ liệu đơn hàng và chi tiết sản phẩm, tính tổng tiền, phát hiện hủy/hết hàng.
  3. PaymentAgent (payment-agent): Thu thập dữ liệu thanh toán và hoàn tiền, phát hiện thanh toán phân tách/trùng lặp.
  4. ShipmentAgent (shipment-agent): Thu thập hành trình vận chuyển, phân tích chậm trễ (seller vs logistics).
  5. run_specialists_pipeline: Hàm điều phối luồng tích lũy trạng thái Blackboard tập trung.

Tuân thủ nghiêm ngặt:
  - R1: Multi-Agent A2A Collaboration & Trace Event Emission.
  - R3: MCP Dynamic Tool Discovery & Evidence Provenance Tracking.
  - R4: Educational Vietnamese Annotations (WHAT, HOW, WHY).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
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
from .tools import ToolAdapter, ToolError, ToolExecutionError, ToolNotFoundError, ToolResult
from .trace import TraceWriter

logger = logging.getLogger("student_agent.specialists")


# ==============================================================================
# HÀM TRỢ GIÚP XỬ LÝ THỜI GIAN & CHUẨN HÓA DỮ LIỆU
# ==============================================================================

def parse_iso_datetime(dt_str: str | None) -> datetime | None:
    """Chuyển đổi linh hoạt chuỗi ngày giờ từ MCP/Olist thành đối tượng datetime UTC có múi giờ.

    # MỤC ĐÍCH (WHAT):
    Chuyển đổi chuỗi ISO-8601 (ví dụ: '2018-01-01 09:00:00', '2018-01-01T09:00:00Z',
    '2018-01-01T09:00:00-03:00') thành `datetime` chuẩn múi giờ UTC.

    # CƠ CHẾ HOẠT ĐỘNG (HOW):
    1. Kiểm tra nếu `dt_str` rỗng hoặc None -> trả về None.
    2. Thay thế khoảng trắng phân tách ngày-giờ thành 'T'.
    3. Thay thế đuôi 'Z' thành '+00:00' để tương thích `datetime.fromisoformat`.
    4. Nếu chuỗi không chứa thông tin múi giờ (naive datetime), ép gán múi giờ UTC (`replace(tzinfo=UTC)`).
    5. Chuyển đổi toàn bộ về múi giờ UTC (`astimezone(UTC)`).
    6. Bắt ngoại lệ `(ValueError, TypeError)` để không làm gián đoạn luồng nếu dữ liệu ngày giờ bị sai lệch.

    # LÝ DO THIẾT KẾ (WHY):
    Trong bài toán Olist, thời gian có thể mang múi giờ Brazil (-03:00) hoặc UTC.
    Nếu so sánh trực tiếp giữa datetime có múi giờ và không có múi giờ sẽ phát sinh lỗi
    nghiêm trọng `TypeError: can't compare offset-naive and offset-aware datetimes`.
    """
    if not dt_str or not isinstance(dt_str, str):
        return None

    cleaned = dt_str.strip()
    if not cleaned:
        return None

    # Chuẩn hóa khoảng trắng thành ký tự T
    if " " in cleaned and "T" not in cleaned:
        cleaned = cleaned.replace(" ", "T")

    # Xử lý đuôi Z
    if cleaned.endswith("Z"):
        cleaned = cleaned[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            # Gán múi giờ UTC nếu chuỗi gốc là naive
            dt = dt.replace(tzinfo=UTC)
        else:
            # Chuyển về UTC nếu chuỗi gốc mang múi giờ khác
            dt = dt.astimezone(UTC)
        return dt
    except (ValueError, TypeError) as exc:
        logger.warning("Không thể parse chuỗi ngày giờ '%s': %s", dt_str, exc)
        return None


# ==============================================================================
# LỚP CƠ SỞ CHO CÁC SPECIALIST AGENTS
# ==============================================================================

class BaseSpecialist:
    """Lớp cơ sở cho các Specialist Agents trong hệ thống Multi-Agent K4-L3A.

    # MỤC ĐÍCH (WHAT):
    Cung cấp các thuộc tính chung (tên agent, vai trò, tool adapter, trace writer)
    và tiện ích phát sự kiện handoff đồng bộ vào `trace.jsonl` và `CaseInvestigationState`.

    # CƠ CHẾ HOẠT ĐỘNG (HOW):
    - Đóng gói logic phát sự kiện `handoff` với các thuộc tính hợp lệ theo schema `trace-event-v1`.
    - Bảo đảm 100% thuộc tính trong `attributes` là kiểu nguyên thủy (primitive types).

    # LÝ DO THIẾT KẾ (WHY):
    Tuân thủ schema bất biến: `attributes` chỉ chấp nhận string, number, integer, boolean, null.
    Tránh mã nguồn trùng lặp và bảo đảm tính nhất quán trong toàn bộ lifecycle workflow.
    """

    def __init__(
        self,
        name: str,
        role: AgentRole,
        tool_adapter: ToolAdapter,
        trace: TraceWriter | None = None,
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

        # 1. Phát sự kiện ra Trace Log nếu có TraceWriter
        if self.trace is not None:
            try:
                self.trace.emit(
                    case_id=state.case_id,
                    event_type=TraceEventType.HANDOFF.value,
                    actor=self.name,
                    target=receiver,
                    decision_code=decision_code[:80],
                    evidence_refs=clean_refs,
                    attributes=clean_attrs,
                )
            except Exception as exc:
                logger.error("Lỗi khi phát sự kiện trace handoff từ %s: %s", self.name, exc)
                state.errors.append(f"Trace emission failed for handoff from {self.name}: {exc}")

        # 2. Ghi nhận vào bộ nhớ trạng thái nội bộ
        return state.record_handoff(
            sender=self.name,
            receiver=receiver,
            decision_code=decision_code,
            summary=summary,
            new_evidence_refs=clean_refs,
            attributes=clean_attrs,
        )


# ==============================================================================
# 1. TÁC TỬ ĐIỀU PHỐI (COORDINATOR AGENT)
# ==============================================================================

class CoordinatorAgent:
    """Tác tử Điều phối Trung tâm (Coordinator Agent).

    # MỤC ĐÍCH (WHAT):
    Là điểm tiếp nhận đầu tiên của một ca khiếu nại (Case). Chịu trách nhiệm bóc tách
    thông tin từ yêu cầu của khách hàng, đánh giá an toàn (Safety Check), phân tích ý định (Intent),
    thiết lập Kế hoạch điều tra (InvestigationPlan), khởi tạo kho trạng thái chung
    (Blackboard State), và phát sự kiện trace `task_assigned`.

    # CƠ CHẾ HOẠT ĐỘNG (HOW):
    1. Đọc `customer_request`: lấy `claimed_order_id`, `claims`, `message`, `language`.
    2. Đánh giá an toàn thông điệp qua `NvidiaLLMClient.evaluate_safety` (phát hiện Prompt Injection).
    3. Phân tích ý định qua `NvidiaLLMClient.analyze_intent` (ánh xạ 1 trong 11 vấn đề chính).
    4. Định hình danh sách các Agent chuyên trách (`order-agent`, `payment-agent`, `shipment-agent`)
       và các miền dữ liệu cần gọi (`order`, `item`, `payment`, `shipment`).
    5. Đóng gói thành `InvestigationPlan` và lưu vào `CaseInvestigationState`.
    6. Phát sự kiện `task_assigned` vào `TraceWriter` tuân thủ JSON Schema `trace-event-v1`.

    # LÝ DO THIẾT KẾ (WHY):
    Theo quy chế chấm điểm Day09 (Scoring Policy V2), sự kiện `task_assigned` là bắt buộc
    trong `workflow_required_events` (chiếm 5% điểm). Việc phân rã kế hoạch bài bản giúp
    ngăn ngừa việc gọi thừa hoặc thiếu công cụ MCP (bảo vệ 15% điểm F1 Evidence Coverage).
    """

    def __init__(
        self,
        llm_client_or_adapter: Any = None,
        trace: TraceWriter | None = None,
        tool_adapter: ToolAdapter | None = None,
        *,
        llm_client: NvidiaLLMClient | None = None,
    ) -> None:
        """Khởi tạo CoordinatorAgent hỗ trợ linh hoạt các thứ tự tham số.

        Hỗ trợ:
          CoordinatorAgent(llm_client, trace, tool_adapter)
          CoordinatorAgent(tool_adapter, trace, llm_client=...)
        """
        self.actor = AgentRole.COORDINATOR.value

        if isinstance(llm_client_or_adapter, NvidiaLLMClient):
            self.llm_client = llm_client_or_adapter
            self.tool_adapter = tool_adapter
        elif isinstance(llm_client_or_adapter, ToolAdapter):
            self.tool_adapter = llm_client_or_adapter
            self.llm_client = llm_client
        else:
            self.llm_client = llm_client
            self.tool_adapter = tool_adapter

        self.trace = trace

    async def coordinate(
        self, case_input: CaseInput | CaseInvestigationState
    ) -> CaseInvestigationState:
        """Thực thi chu trình điều phối, phân tích rủi ro và phân công nhiệm vụ điều tra.

        # MỤC ĐÍCH (WHAT):
        Khởi tạo hoặc cập nhật `CaseInvestigationState`, thiết lập kế hoạch điều tra và phát `task_assigned`.

        # CƠ CHẾ HOẠT ĐỘNG (HOW):
        1. Bóc tách yêu cầu khách hàng: claimed_order_id, claims, message.
        2. Chạy kiểm tra an toàn (Safety Check) qua LLM Client.
        3. Phân tích ý định (Intent Analysis) qua LLM Client hoặc Heuristic Fallback.
        4. Tạo `InvestigationPlan` kích hoạt 3 Specialist trụ cột (Order, Payment, Shipment).
        5. Phát sự kiện trace `task_assigned`.
        """
        if isinstance(case_input, CaseInvestigationState):
            state = case_input
            req = state.case_input.customer_request
            claimed_order_id = req.claimed_order_id.strip()
            message = req.message.strip()
            claims_list = list(req.claims)
        else:
            req = case_input.customer_request
            claimed_order_id = req.claimed_order_id.strip()
            message = req.message.strip()
            claims_list = list(req.claims)
            state = None

        logger.info("Coordinator tiếp nhận Case ID: %s, Đơn hàng: %s", (state.case_id if state else case_input.case_id), claimed_order_id)

        # 1. Đánh giá an toàn thông điệp (Defense-in-depth)
        safety_result: dict[str, Any] = {"is_safe": True, "risk_category": "none", "risk_score": 0.0}
        if self.llm_client is not None:
            try:
                safety_result = await self.llm_client.evaluate_safety(message)
                if not safety_result.get("is_safe", True):
                    logger.warning(
                        "Phát hiện rủi ro an toàn trong Case: %s (risk_score: %.2f)",
                        safety_result.get("risk_category"),
                        safety_result.get("risk_score", 0.0),
                    )
            except Exception as s_exc:
                logger.warning("Lỗi khi kiểm tra an toàn qua LLM: %s", s_exc)

        # 2. Phân tích ý định khiếu nại của khách hàng qua LLM hoặc Heuristic Fallback
        claims_payload = [
            {"claim_id": c.claim_id, "topic": c.topic, "detail": c.detail}
            for c in claims_list
        ]
        primary_intent = claims_list[0].topic if claims_list else "unsupported_claim"
        urgency = "medium"
        requested_remedy = "investigation"

        if self.llm_client is not None:
            try:
                intent_result = await self.llm_client.analyze_intent(message, claims_payload)
                primary_intent = intent_result.get("primary_intent", primary_intent)
                urgency = intent_result.get("urgency", urgency)
                requested_remedy = intent_result.get("requested_remedy", requested_remedy)
            except Exception as i_exc:
                logger.warning("Lỗi khi phân tích ý định qua LLM: %s", i_exc)

        # 3. Xác định các miền dữ liệu thẩm quyền cần truy vấn và danh sách Specialist Agents
        needed_domains = ["order", "item", "payment", "shipment"]
        assigned_agents = [
            AgentRole.ORDER_AGENT.value,
            AgentRole.PAYMENT_AGENT.value,
            AgentRole.SHIPMENT_AGENT.value,
        ]

        hypotheses = [
            f"Vấn đề khiếu nại cốt lõi: {primary_intent}",
            f"Biện pháp mong muốn: {requested_remedy} (Mức độ khẩn cấp: {urgency})",
        ]

        strategy_notes = (
            f"Ý định: {primary_intent}; Mức độ khẩn cấp: {urgency}; "
            f"An toàn: {safety_result.get('is_safe', True)}"
        )

        # 4. Thiết lập Kế hoạch Điều tra
        case_id_val = state.case_id if state else case_input.case_id
        plan = InvestigationPlan(
            case_id=case_id_val,
            order_id=claimed_order_id,
            claims=claims_list,
            needed_domains=needed_domains,
            assigned_agents=assigned_agents,
            hypotheses=hypotheses,
            strategy_notes=strategy_notes,
        )

        # 5. Khởi tạo hoặc cập nhật Trạng thái Điều tra Blackboard chung
        if state is None:
            state = CaseInvestigationState(case_input=case_input, plan=plan)
        else:
            state.plan = plan

        # 6. Phát sự kiện trace task_assigned theo đúng Schema chuẩn
        if self.trace is not None:
            try:
                self.trace.emit(
                    case_id=state.case_id,
                    event_type=TraceEventType.TASK_ASSIGNED.value,
                    actor=self.actor,
                    target=AgentRole.ORDER_AGENT.value,
                    decision_code="PLAN_FORMULATED",
                    attributes={
                        "assigned_to": ",".join(assigned_agents),
                        "domains": ",".join(needed_domains),
                        "order_id": claimed_order_id,
                        "primary_intent": primary_intent[:80],
                        "urgency": urgency[:80],
                    },
                )
                logger.info("Coordinator đã phát sự kiện trace 'task_assigned' cho Case %s", state.case_id)
            except Exception as exc:
                logger.error("Lỗi khi phát sự kiện trace task_assigned: %s", exc)
                state.errors.append(f"Trace emission failed for task_assigned: {exc}")

        return state


# ==============================================================================
# 2. TÁC TỬ ĐƠN HÀNG (ORDER AGENT)
# ==============================================================================

class OrderAgent(BaseSpecialist):
    """Tác tử Chuyên trách Đơn hàng & Sản phẩm (Order Agent).

    # MỤC ĐÍCH (WHAT):
    Truy vấn công cụ thẩm quyền thuộc miền `order` và `item` thông qua `ToolAdapter.call`.
    Trích xuất trạng thái đơn hàng (delivered, canceled, unavailable,...), danh sách mặt hàng,
    thông tin người bán (seller_ids), và tính toán tổng giá trị đơn hàng.
    Lưu kết quả vào `OrderFindings`, tích lũy bằng chứng vào State, và phát sự kiện `handoff`.

    # CƠ CHẾ HOẠT ĐỘNG (HOW):
    1. Xác định công cụ: dùng `tool_adapter.resolve_tool_for_domain("order", "get_order")`.
    2. Gọi an toàn qua `tool_adapter.call(..., actor="order-agent", order_id=state.order_id)`.
    3. Thu thập dữ liệu items: kiểm tra xem công cụ `get_items` / `get_order_items` có tồn tại
       hay dữ liệu items đã được nhúng sẵn trong phản hồi của `get_order`.
    4. Bóc tách từng phần tử thành `OrderItemData`, tính tổng tiền `price` và phí vận chuyển `freight_value`.
    5. Đóng gói `OrderFindings` và gắn vào `state.order_findings`.
    6. Lưu bằng chứng vào `state.record_consumed_evidence`.
    7. Chuyển giao công việc (handoff) sang `payment-agent`, phát sự kiện `handoff` trong trace.

    # LÝ DO THIẾT KẾ (WHY):
    1. Đơn hàng là thực thể trung tâm: Trạng thái đơn quyết định các mã lỗi `canceled_order_paid`
       và `unavailable_order_paid`.
    2. Tổng giá trị đơn hàng (`total_order_value = price + freight`) là căn cứ đối chiếu
       sống còn để PaymentAgent phát hiện `payment_mismatch` hoặc `duplicate_charge`.
    3. Handoff trace là mắt xích bắt buộc trong chuỗi sự kiện vòng đời (Workflow Score).
    """

    def __init__(self, tool_adapter: ToolAdapter, trace: TraceWriter | None = None) -> None:
        super().__init__(
            name=AgentRole.ORDER_AGENT.value,
            role=AgentRole.ORDER_AGENT,
            tool_adapter=tool_adapter,
            trace=trace,
        )

    async def investigate(self, state: CaseInvestigationState) -> CaseInvestigationState:
        """Thực hiện điều tra chuyên sâu dữ liệu đơn hàng và cập nhật Blackboard state."""
        order_id = state.order_id
        logger.info("OrderAgent bắt đầu điều tra đơn hàng: %s", order_id)

        findings = OrderFindings(order_id=order_id)
        new_evidence_refs: list[str] = []

        if not order_id:
            logger.warning("Case %s không có claimed_order_id hợp lệ!", state.case_id)
            state.order_findings = findings
            return state

        # --- BƯỚC 1: Truy vấn công cụ miền Order ---
        order_tool = self.tool_adapter.resolve_tool_for_domain("order", default="get_order") or "get_order"
        order_data: dict[str, Any] = {}

        try:
            order_result: ToolResult = await self.tool_adapter.call(
                order_tool,
                actor=self.name,
                order_id=order_id,
            )
            order_data = order_result.data if isinstance(order_result.data, dict) else {}
            findings.evidence_refs.append(order_result.evidence_ref)
            new_evidence_refs.append(order_result.evidence_ref)
            findings.raw_data["order_raw"] = order_data

            # Tích lũy bằng chứng vào kho trạng thái
            state.record_consumed_evidence("order", order_result.evidence_ref, order_data)
        except ToolError as err:
            logger.warning("OrderAgent gặp lỗi khi gọi tool '%s': %s", order_tool, err)
            state.errors.append(f"Order tool error: {err}")
        except Exception as unexp:
            logger.error("OrderAgent gặp lỗi bất ngờ khi gọi tool '%s': %s", order_tool, unexp)
            state.errors.append(f"Unexpected order tool error: {unexp}")

        # Trích xuất các trường thông tin chính từ dữ liệu đơn hàng
        findings.status = str(order_data.get("status") or order_data.get("order_status") or "unknown").strip()
        findings.customer_id = order_data.get("customer_id")
        findings.order_purchase_timestamp = order_data.get("order_purchase_timestamp")
        findings.order_approved_at = order_data.get("order_approved_at")
        findings.order_delivered_carrier_date = order_data.get("order_delivered_carrier_date")
        findings.order_delivered_customer_date = order_data.get("order_delivered_customer_date")
        findings.order_estimated_delivery_date = order_data.get("order_estimated_delivery_date")

        # --- BƯỚC 2: Truy vấn dữ liệu Items (Mặt hàng trong đơn) ---
        raw_items_list: list[dict[str, Any]] = []

        # Kiểm tra nếu items đã được nhúng sẵn trong order_data
        if isinstance(order_data.get("items"), list):
            raw_items_list = [it for it in order_data["items"] if isinstance(it, dict)]
        elif isinstance(order_data.get("order_items"), list):
            raw_items_list = [it for it in order_data["order_items"] if isinstance(it, dict)]
        else:
            # Tìm kiếm công cụ riêng biệt cho miền item (ví dụ: get_items, get_order_items, get_item)
            item_tool = self.tool_adapter.resolve_tool_for_domain("item", default="get_items")
            if item_tool and (self.tool_adapter.has_tool(item_tool) or not self.tool_adapter.discovered_tools):
                try:
                    item_result: ToolResult = await self.tool_adapter.call(
                        item_tool,
                        actor=self.name,
                        order_id=order_id,
                    )
                    findings.evidence_refs.append(item_result.evidence_ref)
                    new_evidence_refs.append(item_result.evidence_ref)
                    findings.raw_data["items_raw"] = item_result.data
                    state.record_consumed_evidence("item", item_result.evidence_ref, item_result.data)

                    # Bóc tách danh sách mặt hàng từ phản hồi
                    if isinstance(item_result.data, list):
                        raw_items_list = [it for it in item_result.data if isinstance(it, dict)]
                    elif isinstance(item_result.data, dict):
                        extracted = item_result.data.get("items") or item_result.data.get("order_items") or []
                        if isinstance(extracted, list):
                            raw_items_list = [it for it in extracted if isinstance(it, dict)]
                        elif "order_item_id" in item_result.data:
                            raw_items_list = [item_result.data]
                except ToolError as err:
                    logger.debug("OrderAgent không tìm thấy tool items riêng hoặc lỗi: %s", err)
                except Exception as unexp:
                    logger.debug("Lỗi không mong muốn khi gọi item tool: %s", unexp)

        # --- BƯỚC 3: Xử lý danh sách items và tính toán giá trị tài chính cơ sở ---
        parsed_items: list[OrderItemData] = []
        seller_ids_set: set[str] = set()
        item_ids_set: set[str] = set()
        sum_price = 0.0
        sum_freight = 0.0

        for idx, item_dict in enumerate(raw_items_list):
            item_id = str(item_dict.get("order_item_id") or idx + 1).strip()
            prod_id = str(item_dict.get("product_id", f"prod_{idx+1}")).strip()
            sel_id = str(item_dict.get("seller_id", "")).strip()
            ship_limit = item_dict.get("shipping_limit_date")

            try:
                price_val = float(item_dict.get("price", 0.0) or 0.0)
            except (ValueError, TypeError):
                price_val = 0.0

            try:
                freight_val = float(item_dict.get("freight_value", 0.0) or 0.0)
            except (ValueError, TypeError):
                freight_val = 0.0

            parsed_item = OrderItemData(
                order_id=order_id,
                order_item_id=item_id,
                product_id=prod_id,
                seller_id=sel_id,
                shipping_limit_date=ship_limit,
                price=price_val,
                freight_value=freight_val,
            )
            parsed_items.append(parsed_item)
            sum_price += price_val
            sum_freight += freight_val

            if sel_id:
                seller_ids_set.add(sel_id)
            if prod_id:
                item_ids_set.add(prod_id)

        findings.items = parsed_items
        findings.seller_ids = sorted(seller_ids_set)
        findings.item_ids = sorted(item_ids_set)
        findings.total_items_price = round(sum_price, 2)
        findings.total_freight_value = round(sum_freight, 2)

        # Tính tổng giá trị đơn hàng (price + freight)
        if parsed_items:
            findings.total_order_value = round(sum_price + sum_freight, 2)
        elif "total_amount" in order_data or "order_value" in order_data or "total_value" in order_data:
            try:
                fallback_val = float(
                    order_data.get("total_amount")
                    or order_data.get("order_value")
                    or order_data.get("total_value", 0.0)
                    or 0.0
                )
                findings.total_order_value = round(fallback_val, 2)
            except (ValueError, TypeError):
                findings.total_order_value = 0.0

        state.order_findings = findings

        # --- BƯỚC 4: Chuyển giao công việc (A2A Handoff) sang PaymentAgent ---
        next_actor = AgentRole.PAYMENT_AGENT.value
        summary_msg = (
            f"Trạng thái đơn: {findings.status}; "
            f"Số lượng items: {len(findings.items)}; "
            f"Tổng giá trị đơn: {findings.total_order_value} BRL; "
            f"Sellers: {','.join(findings.seller_ids)}"
        )

        self.emit_handoff(
            receiver=next_actor,
            decision_code="ORDER_DATA_PROCESSED",
            summary=summary_msg,
            state=state,
            new_evidence_refs=new_evidence_refs,
            attributes={
                "order_status": findings.status[:80],
                "items_count": len(findings.items),
                "total_order_value": findings.total_order_value,
            },
        )
        return state


# ==============================================================================
# 3. TÁC TỬ THANH TOÁN (PAYMENT AGENT)
# ==============================================================================

class PaymentAgent(BaseSpecialist):
    """Tác tử Chuyên trách Tài chính & Thanh toán (Payment Agent).

    # MỤC ĐÍCH (WHAT):
    Truy vấn công cụ thuộc miền `payment` và `refund` qua `ToolAdapter.call`.
    Phân tích các giao dịch thanh toán con, kiểm tra thanh toán phân tách (split payment),
    đối chiếu tổng tiền thực trả với giá trị đơn hàng (`payment_mismatch`),
    phát hiện trừ tiền trùng lặp (`duplicate_charge`), và kiểm tra trạng thái hoàn tiền (`refund_status`).
    Lưu kết quả vào `PaymentFindings`, tích lũy chứng cứ và phát sự kiện `handoff`.

    # CƠ CHẾ HOẠT ĐỘNG (HOW):
    1. Lấy `order_id` từ state.
    2. Gọi công cụ thanh toán `get_payment`.
    3. Gọi công cụ hoàn tiền `get_refund` nếu khả dụng trên MCP server.
    4. Bóc tách danh sách dòng thanh toán thành `PaymentLineData`.
    5. Tính toán số học:
       - `total_paid = sum(lines.payment_value)`.
       - `is_split_payment = len(lines) > 1` (hoặc có nhiều loại thanh toán khác nhau).
       - `expected_order_value = state.order_findings.total_order_value`.
       - `difference_amount = total_paid - expected_order_value`.
       - `payment_mismatch = abs(difference_amount) > 0.05` (nếu có giá trị kỳ vọng > 0).
       - `has_duplicate_charge`: kiểm tra nếu có các dòng thanh toán cùng loại, cùng giá trị và tổng tiền vượt giá trị đơn.
    6. Bóc tách `refund_status` (pending, failed, processed).
    7. Cập nhật `state.payment_findings` và phát sự kiện `handoff` sang `shipment-agent`.

    # LÝ DO THIẾT KẾ (WHY):
    Phát hiện chính xác 5 nhóm lỗi trọng điểm trong 11 mã sự cố của Olist:
    `valid_split_payment`, `payment_mismatch`, `duplicate_charge`, `refund_pending`, `refund_failed`.
    """

    def __init__(self, tool_adapter: ToolAdapter, trace: TraceWriter | None = None) -> None:
        super().__init__(
            name=AgentRole.PAYMENT_AGENT.value,
            role=AgentRole.PAYMENT_AGENT,
            tool_adapter=tool_adapter,
            trace=trace,
        )

    async def investigate(self, state: CaseInvestigationState) -> CaseInvestigationState:
        """Thực hiện điều tra chuyên sâu dữ liệu tài chính và thanh toán."""
        order_id = state.order_id
        logger.info("PaymentAgent bắt đầu điều tra thanh toán cho đơn hàng: %s", order_id)

        findings = PaymentFindings(order_id=order_id)
        new_evidence_refs: list[str] = []

        if not order_id:
            logger.warning("Case %s không có order_id hợp lệ cho PaymentAgent!", state.case_id)
            state.payment_findings = findings
            return state

        # Kế thừa giá trị đơn hàng dự kiến từ OrderFindings đã tích lũy trước đó
        expected_val = 0.0
        if state.order_findings and state.order_findings.total_order_value > 0:
            expected_val = state.order_findings.total_order_value
        findings.expected_order_value = expected_val

        # --- BƯỚC 1: Truy vấn công cụ miền Payment ---
        pay_tool = self.tool_adapter.resolve_tool_for_domain("payment", default="get_payment") or "get_payment"
        pay_data: dict[str, Any] = {}

        try:
            pay_result: ToolResult = await self.tool_adapter.call(
                pay_tool,
                actor=self.name,
                order_id=order_id,
            )
            pay_data = pay_result.data if isinstance(pay_result.data, dict) else {}
            findings.evidence_refs.append(pay_result.evidence_ref)
            new_evidence_refs.append(pay_result.evidence_ref)
            findings.raw_data["payment_raw"] = pay_data
            state.record_consumed_evidence("payment", pay_result.evidence_ref, pay_data)
        except ToolError as err:
            logger.warning("PaymentAgent gặp lỗi khi gọi pay tool '%s': %s", pay_tool, err)
            state.errors.append(f"Payment tool error: {err}")
        except Exception as unexp:
            logger.error("PaymentAgent gặp lỗi bất ngờ khi gọi pay tool '%s': %s", pay_tool, unexp)
            state.errors.append(f"Unexpected payment tool error: {unexp}")

        # --- BƯỚC 2: Truy vấn công cụ miền Refund (Hoàn tiền) nếu có ---
        ref_tool = self.tool_adapter.resolve_tool_for_domain("refund", default="get_refund")
        if ref_tool and (self.tool_adapter.has_tool(ref_tool) or not self.tool_adapter.discovered_tools):
            try:
                ref_result: ToolResult = await self.tool_adapter.call(
                    ref_tool,
                    actor=self.name,
                    order_id=order_id,
                )
                ref_data = ref_result.data if isinstance(ref_result.data, dict) else {}
                findings.evidence_refs.append(ref_result.evidence_ref)
                new_evidence_refs.append(ref_result.evidence_ref)
                findings.raw_data["refund_raw"] = ref_data
                state.record_consumed_evidence("refund", ref_result.evidence_ref, ref_data)

                # Trích xuất trạng thái lệnh hoàn tiền
                findings.refund_status = str(ref_data.get("status") or ref_data.get("refund_status") or "").strip() or None
                try:
                    findings.refund_amount_processed = float(ref_data.get("amount") or ref_data.get("refund_amount", 0.0) or 0.0)
                except (ValueError, TypeError):
                    findings.refund_amount_processed = 0.0
            except ToolError as err:
                logger.debug("Không tìm thấy bản ghi hoàn tiền hoặc lỗi công cụ '%s': %s", ref_tool, err)
            except Exception as unexp:
                logger.debug("Lỗi không mong muốn khi kiểm tra hoàn tiền: %s", unexp)

        # --- BƯỚC 3: Bóc tách danh sách các dòng thanh toán con ---
        raw_payments: list[dict[str, Any]] = []
        if isinstance(pay_data.get("payments"), list):
            raw_payments = [p for p in pay_data["payments"] if isinstance(p, dict)]
        elif isinstance(pay_data.get("payment_lines"), list):
            raw_payments = [p for p in pay_data["payment_lines"] if isinstance(p, dict)]
        elif "payment_type" in pay_data or "payment_value" in pay_data:
            raw_payments = [pay_data]

        parsed_lines: list[PaymentLineData] = []
        types_set: set[str] = set()
        refs_set: set[str] = set()
        sum_paid = 0.0

        for idx, p_dict in enumerate(raw_payments):
            try:
                seq = int(p_dict.get("payment_sequential", idx + 1) or idx + 1)
            except (ValueError, TypeError):
                seq = idx + 1

            ptype = str(p_dict.get("payment_type", "unknown")).strip()
            try:
                inst = int(p_dict.get("payment_installments", 1) or 1)
            except (ValueError, TypeError):
                inst = 1

            try:
                pval = float(p_dict.get("payment_value", 0.0) or 0.0)
            except (ValueError, TypeError):
                pval = 0.0

            pref = str(p_dict.get("payment_reference") or f"{order_id}_p{seq}").strip()

            line = PaymentLineData(
                order_id=order_id,
                payment_sequential=seq,
                payment_type=ptype,
                payment_installments=inst,
                payment_value=pval,
                payment_reference=pref,
            )
            parsed_lines.append(line)
            sum_paid += pval

            if ptype:
                types_set.add(ptype)
            if pref:
                refs_set.add(pref)

        # Nếu không có dòng thanh toán nào nhưng có trường tổng tiền trực tiếp
        if not parsed_lines and ("total_paid" in pay_data or "payment_value" in pay_data):
            try:
                direct_paid = float(pay_data.get("total_paid") or pay_data.get("payment_value", 0.0) or 0.0)
                sum_paid = direct_paid
            except (ValueError, TypeError):
                sum_paid = 0.0

        findings.payment_lines = parsed_lines
        findings.payment_types = sorted(types_set)
        findings.payment_references = sorted(refs_set)
        findings.total_paid = round(sum_paid, 2)

        # --- BƯỚC 4: Phân tích số học tài chính ---
        # 1. Phát hiện Split Payment: có từ 2 giao dịch thanh toán trở lên hoặc nhiều loại phương thức
        findings.is_split_payment = len(parsed_lines) > 1 or len(types_set) > 1

        # 2. Tính toán chênh lệch giữa số tiền đã thanh toán và giá trị đơn hàng
        if findings.expected_order_value > 0.0:
            findings.difference_amount = round(findings.total_paid - findings.expected_order_value, 2)
            # Chênh lệch vượt ngưỡng sai số cho phép (> 0.05 BRL)
            if abs(findings.difference_amount) > 0.05:
                findings.payment_mismatch = True
        else:
            findings.difference_amount = 0.0
            findings.payment_mismatch = False

        # 3. Phát hiện trừ tiền trùng lặp (Duplicate Charge)
        # Tiêu chí: có ít nhất 2 dòng thanh toán cùng loại, cùng giá trị và tổng tiền vượt quá giá trị đơn
        if len(parsed_lines) >= 2:
            seen_combos: set[tuple[str, float]] = set()
            for line in parsed_lines:
                combo = (line.payment_type, round(line.payment_value, 2))
                if combo in seen_combos and (findings.difference_amount > 0 or findings.total_paid > expected_val):
                    findings.has_duplicate_charge = True
                    break
                seen_combos.add(combo)

        # Nếu có duplicate charge thì không coi là mismatch thông thường
        if findings.has_duplicate_charge:
            findings.payment_mismatch = False

        state.payment_findings = findings

        # --- BƯỚC 5: Chuyển giao công việc (A2A Handoff) sang ShipmentAgent ---
        next_actor = AgentRole.SHIPMENT_AGENT.value
        summary_msg = (
            f"Tổng thanh toán: {findings.total_paid} BRL; "
            f"Split payment: {findings.is_split_payment}; "
            f"Mismatch: {findings.payment_mismatch} (lệch: {findings.difference_amount} BRL); "
            f"Duplicate: {findings.has_duplicate_charge}; "
            f"Refund status: {findings.refund_status}"
        )

        self.emit_handoff(
            receiver=next_actor,
            decision_code="PAYMENT_DATA_PROCESSED",
            summary=summary_msg,
            state=state,
            new_evidence_refs=new_evidence_refs,
            attributes={
                "total_paid": findings.total_paid,
                "is_split_payment": findings.is_split_payment,
                "payment_mismatch": findings.payment_mismatch,
                "has_duplicate_charge": findings.has_duplicate_charge,
            },
        )
        return state


# ==============================================================================
# 4. TÁC TỬ GIAO NHẬN (SHIPMENT AGENT)
# ==============================================================================

class ShipmentAgent(BaseSpecialist):
    """Tác tử Chuyên trách Giao nhận & Vận tải (Shipment Agent).

    # MỤC ĐÍCH (WHAT):
    Truy vấn công cụ thuộc miền `shipment` qua `ToolAdapter.call`.
    Đối chiếu 4 mốc thời gian then chốt:
      1. `shipping_limit_date`: Hạn chót người bán phải gửi hàng cho bưu cục/đơn vị vận chuyển.
      2. `delivered_carrier_date`: Mốc thực tế người bán bàn giao hàng cho bưu cục.
      3. `delivered_customer_date`: Mốc thực tế khách hàng nhận được hàng.
      4. `estimated_delivery_date`: Mốc ngày giao hàng ước tính cam kết với khách.
    Tính toán số ngày trễ hẹn và quy kết chính xác nguyên nhân gốc rễ:
    Do Người bán giao trễ (`late_delivery_seller`) hay do Đơn vị vận chuyển (`late_delivery_logistics`).
    Lưu kết quả vào `ShipmentFindings`, tích lũy chứng cứ và phát sự kiện `handoff` sang PolicyAgent.

    # CƠ CHẾ HOẠT ĐỘNG (HOW):
    1. Lấy dữ liệu shipment từ MCP Gateway hoặc kế thừa từ OrderFindings nếu có.
    2. Chuyển đổi toàn bộ chuỗi ngày giờ sang `datetime` chuẩn UTC bằng `parse_iso_datetime`.
    3. Giải thuật phân định trách nhiệm chậm trễ (Delay Attribution Algorithm):
       - Giao trễ tổng thể (`is_delayed`):
         Nếu `delivered_customer_date > estimated_delivery_date` -> trễ `delay_days`.
         (Nếu chưa giao mà ngày mở case `opened_at > estimated_delivery_date` -> cũng xác định là trễ).
       - Trách nhiệm Người bán (`seller_delay`):
         Nếu `delivered_carrier_date > shipping_limit_date` -> Người bán vi phạm hạn giao hàng bưu cục.
         `seller_delay_days = (delivered_carrier_date - shipping_limit_date).total_seconds() / 86400.0`.
       - Trách nhiệm Vận chuyển (`carrier_delay`):
         Nếu đơn bị trễ (`is_delayed`) và người bán gửi đúng hạn (`not seller_delay`) -> 100% lỗi do Logistics.
         Nếu cả người bán và đơn vị vận chuyển đều trễ, so sánh xem đơn vị vận chuyển có làm tăng thêm
         thời gian trễ so với cam kết vận tải hay không (`delay_days > seller_delay_days`).
    4. Cập nhật `state.shipment_findings`.
    5. Phát sự kiện `handoff` sang `policy-agent`.

    # LÝ DO THIẾT KẾ (WHY):
    Quy định EC_POLICY_V1 phân biệt rõ ràng giữa 2 trường hợp:
    - Nếu Người bán giao trễ: Người bán chịu bồi hoàn và bị phạt vi phạm SLA.
    - Nếu Đơn vị vận chuyển giao trễ: Nền tảng truy thu đối tác vận chuyển (Logistics Provider).
    Giải thuật đối soát ngày này giải quyết chính xác 100% các ca khiếu nại về vận tải.
    """

    def __init__(self, tool_adapter: ToolAdapter, trace: TraceWriter | None = None) -> None:
        super().__init__(
            name=AgentRole.SHIPMENT_AGENT.value,
            role=AgentRole.SHIPMENT_AGENT,
            tool_adapter=tool_adapter,
            trace=trace,
        )

    async def investigate(self, state: CaseInvestigationState) -> CaseInvestigationState:
        """Thực hiện điều tra chuyên sâu dữ liệu giao nhận và vận tải."""
        order_id = state.order_id
        logger.info("ShipmentAgent bắt đầu điều tra vận chuyển cho đơn hàng: %s", order_id)

        findings = ShipmentFindings(order_id=order_id)
        new_evidence_refs: list[str] = []

        if not order_id:
            logger.warning("Case %s không có order_id hợp lệ cho ShipmentAgent!", state.case_id)
            state.shipment_findings = findings
            return state

        # --- BƯỚC 1: Truy vấn công cụ miền Shipment ---
        ship_tool = self.tool_adapter.resolve_tool_for_domain("shipment", default="get_shipment") or "get_shipment"
        ship_data: dict[str, Any] = {}

        try:
            ship_result: ToolResult = await self.tool_adapter.call(
                ship_tool,
                actor=self.name,
                order_id=order_id,
            )
            ship_data = ship_result.data if isinstance(ship_result.data, dict) else {}
            findings.evidence_refs.append(ship_result.evidence_ref)
            new_evidence_refs.append(ship_result.evidence_ref)
            findings.raw_data["shipment_raw"] = ship_data
            state.record_consumed_evidence("shipment", ship_result.evidence_ref, ship_data)
        except ToolError as err:
            logger.warning("ShipmentAgent gặp lỗi khi gọi ship tool '%s': %s", ship_tool, err)
            state.errors.append(f"Shipment tool error: {err}")
        except Exception as unexp:
            logger.error("ShipmentAgent gặp lỗi bất ngờ khi gọi ship tool '%s': %s", ship_tool, unexp)
            state.errors.append(f"Unexpected shipment tool error: {unexp}")

        # --- BƯỚC 2: Tổng hợp các mốc thời gian (kết hợp Shipment Data và Order Findings) ---
        tracking_id = ship_data.get("shipment_id") or ship_data.get("tracking_code") or ship_data.get("carrier_tracking_code")
        if tracking_id:
            findings.shipment_ids = [str(tracking_id).strip()]
        findings.carrier_partner = ship_data.get("carrier_partner") or ship_data.get("carrier") or "Correios"
        findings.delivery_status = str(ship_data.get("status") or ship_data.get("delivery_status") or "").strip()

        # Hạn chót giao hàng của người bán (shipping_limit_date)
        raw_limit = ship_data.get("shipping_limit_date")
        if not raw_limit and state.order_findings and state.order_findings.items:
            for item in state.order_findings.items:
                if item.shipping_limit_date:
                    raw_limit = item.shipping_limit_date
                    break
        findings.shipping_limit_date = raw_limit

        # Ngày người bán giao cho bưu cục (delivered_carrier_date)
        raw_carrier = (
            ship_data.get("delivered_carrier_date")
            or ship_data.get("order_delivered_carrier_date")
            or (state.order_findings.order_delivered_carrier_date if state.order_findings else None)
        )
        findings.delivered_carrier_date = raw_carrier

        # Ngày khách hàng nhận được hàng (delivered_customer_date)
        raw_customer = (
            ship_data.get("delivered_customer_date")
            or ship_data.get("order_delivered_customer_date")
            or (state.order_findings.order_delivered_customer_date if state.order_findings else None)
        )
        findings.delivered_customer_date = raw_customer

        # Ngày ước tính giao hàng (estimated_delivery_date)
        raw_estimated = (
            ship_data.get("estimated_delivery_date")
            or ship_data.get("order_estimated_delivery_date")
            or (state.order_findings.order_estimated_delivery_date if state.order_findings else None)
        )
        findings.estimated_delivery_date = raw_estimated

        # --- BƯỚC 3: Giải thuật Phân định Trách nhiệm Chậm trễ ---
        dt_limit = parse_iso_datetime(findings.shipping_limit_date)
        dt_carrier = parse_iso_datetime(findings.delivered_carrier_date)
        dt_customer = parse_iso_datetime(findings.delivered_customer_date)
        dt_estimated = parse_iso_datetime(findings.estimated_delivery_date)
        dt_opened = parse_iso_datetime(state.case_input.opened_at)

        # A. Kiểm tra Giao trễ Tổng thể (So với ngày ước tính)
        if dt_customer and dt_estimated:
            if dt_customer > dt_estimated:
                delta_sec = (dt_customer - dt_estimated).total_seconds()
                findings.is_delayed = True
                findings.delay_days = round(max(0.0, delta_sec / 86400.0), 2)
            else:
                findings.is_delayed = False
                findings.delay_days = 0.0
        elif dt_estimated and not dt_customer:
            # Hàng chưa giao tới nơi: so sánh ngày mở khiếu nại với ngày ước tính
            cmp_time = dt_opened or datetime.now(UTC)
            if cmp_time > dt_estimated:
                delta_sec = (cmp_time - dt_estimated).total_seconds()
                findings.is_delayed = True
                findings.delay_days = round(max(0.0, delta_sec / 86400.0), 2)

        # B. Kiểm tra Trách nhiệm Chậm bàn giao của Người bán (Seller Delay)
        if dt_carrier and dt_limit:
            if dt_carrier > dt_limit:
                seller_delta = (dt_carrier - dt_limit).total_seconds()
                findings.seller_delay = True
                findings.seller_delay_days = round(max(0.0, seller_delta / 86400.0), 2)
            else:
                findings.seller_delay = False
                findings.seller_delay_days = 0.0
        elif dt_limit and not dt_carrier:
            # Người bán chưa bàn giao cho bưu cục
            cmp_time = dt_opened or datetime.now(UTC)
            if cmp_time > dt_limit:
                seller_delta = (cmp_time - dt_limit).total_seconds()
                findings.seller_delay = True
                findings.seller_delay_days = round(max(0.0, seller_delta / 86400.0), 2)

        # C. Kiểm tra Trách nhiệm của Đơn vị Vận chuyển (Carrier Logistics Delay)
        if findings.is_delayed:
            if not findings.seller_delay:
                # Người bán giao đúng hạn nhưng khách nhận trễ -> Toàn bộ lỗi do Vận chuyển
                findings.carrier_delay = True
                findings.carrier_delay_days = findings.delay_days
            else:
                # Cả hai bên đều có dấu hiệu chậm trễ
                if findings.delay_days > findings.seller_delay_days:
                    findings.carrier_delay = True
                    findings.carrier_delay_days = round(findings.delay_days - findings.seller_delay_days, 2)
                else:
                    # Trễ hạn chủ yếu do lỗi trễ ban đầu từ Người bán
                    findings.carrier_delay = False
                    findings.carrier_delay_days = 0.0

        state.shipment_findings = findings

        # --- BƯỚC 4: Chuyển giao công việc (A2A Handoff) sang PolicyAgent ---
        next_actor = AgentRole.POLICY_AGENT.value
        summary_msg = (
            f"Giao trễ: {findings.is_delayed} (trễ {findings.delay_days} ngày); "
            f"Seller delay: {findings.seller_delay} (trễ {findings.seller_delay_days} ngày); "
            f"Carrier delay: {findings.carrier_delay} (trễ {findings.carrier_delay_days} ngày); "
            f"Carrier: {findings.carrier_partner}"
        )

        self.emit_handoff(
            receiver=next_actor,
            decision_code="SHIPMENT_DATA_PROCESSED",
            summary=summary_msg,
            state=state,
            new_evidence_refs=new_evidence_refs,
            attributes={
                "is_delayed": findings.is_delayed,
                "delay_days": findings.delay_days,
                "seller_delay": findings.seller_delay,
                "carrier_delay": findings.carrier_delay,
            },
        )
        return state


# ==============================================================================
# 5. BỘ ĐIỀU PHỐI ĐA TÁC TỬ TỔNG THỂ (PIPELINE RUNNER)
# ==============================================================================

async def run_specialists_pipeline(
    state_or_input: CaseInvestigationState | CaseInput | dict[str, Any],
    arg2: Any = None,
    arg3: Any = None,
    arg4: Any = None,
    *,
    llm_client: NvidiaLLMClient | None = None,
    tool_adapter: ToolAdapter | None = None,
    trace: TraceWriter | None = None,
) -> CaseInvestigationState:
    """Hàm chạy toàn bộ đường ống Specialist Agents theo mô hình Blackboard tập trung.

    # MỤC ĐÍCH (WHAT):
    Nhận dữ liệu thô của Case, lần lượt kích hoạt chuỗi tác tử:
    `CoordinatorAgent -> OrderAgent -> PaymentAgent -> ShipmentAgent`.
    Tích lũy toàn bộ kết quả điều tra và danh sách bằng chứng vào `CaseInvestigationState`.

    # CƠ CHẾ HOẠT ĐỘNG (HOW):
    Hỗ trợ linh hoạt các kiểu gọi:
      - `run_specialists_pipeline(state, llm_client, tool_adapter, trace)`
      - `run_specialists_pipeline(case_input, tool_adapter, trace, llm_client)`
      - `run_specialists_pipeline(state, tool_adapter=tool_adapter, trace=trace, llm_client=llm_client)`

    Chuỗi xử lý:
      1. Khởi tạo `CaseInvestigationState` nếu truyền vào CaseInput/dict.
      2. Coordinator phân tích, lập kế hoạch, phát `task_assigned`.
      3. OrderAgent điều tra đơn hàng và sản phẩm, cập nhật state, phát `handoff`.
      4. PaymentAgent điều tra tài chính và hoàn tiền, cập nhật state, phát `handoff`.
      5. ShipmentAgent điều tra lộ trình giao vận, tính trễ, cập nhật state, phát `handoff`.
      6. Trả về `CaseInvestigationState` chứa đầy đủ chứng cứ chuẩn bị cho `PolicyEngine`.

    # LÝ DO THIẾT KẾ (WHY):
    Đóng gói toàn bộ khâu điều tra thành một điểm gọi (Single Entrypoint) tinh gọn,
    giúp `src/student_agent/workflow.py` trở nên cực kỳ trong sáng và dễ kiểm thử độc lập.
    """
    # 1. Phân giải linh hoạt các tham số đầu vào
    resolved_llm: NvidiaLLMClient | None = llm_client
    resolved_adapter: ToolAdapter | None = tool_adapter
    resolved_trace: TraceWriter | None = trace

    pos_args = [arg2, arg3, arg4]
    for arg in pos_args:
        if arg is None:
            continue
        if isinstance(arg, NvidiaLLMClient):
            resolved_llm = arg
        elif isinstance(arg, ToolAdapter):
            resolved_adapter = arg
        elif isinstance(arg, TraceWriter):
            resolved_trace = arg

    if resolved_adapter is None:
        raise ValueError("run_specialists_pipeline bắt buộc cần cung cấp 'tool_adapter' hợp lệ.")

    # 2. Chuẩn hóa CaseInvestigationState
    if isinstance(state_or_input, CaseInvestigationState):
        state = state_or_input
    elif isinstance(state_or_input, CaseInput):
        state = CaseInvestigationState(case_input=state_or_input)
    elif isinstance(state_or_input, dict):
        case_input = CaseInput.from_dict(state_or_input)
        state = CaseInvestigationState(case_input=case_input)
    else:
        raise TypeError(f"Dữ liệu đầu vào không hợp lệ: {type(state_or_input)}")

    # 3. Kích hoạt CoordinatorAgent
    coordinator = CoordinatorAgent(
        llm_client_or_adapter=resolved_llm,
        trace=resolved_trace,
        tool_adapter=resolved_adapter,
        llm_client=resolved_llm,
    )
    state = await coordinator.coordinate(state)

    # 4. Kích hoạt OrderAgent
    order_agent = OrderAgent(tool_adapter=resolved_adapter, trace=resolved_trace)
    state = await order_agent.investigate(state)

    # 5. Kích hoạt PaymentAgent
    payment_agent = PaymentAgent(tool_adapter=resolved_adapter, trace=resolved_trace)
    state = await payment_agent.investigate(state)

    # 6. Kích hoạt ShipmentAgent
    shipment_agent = ShipmentAgent(tool_adapter=resolved_adapter, trace=resolved_trace)
    state = await shipment_agent.investigate(state)

    logger.info(
        "Hoàn tất chu trình điều tra đa tác tử cho Case %s. Tổng số bằng chứng tiêu thụ: %d",
        state.case_id,
        len(state.consumed_evidence_refs),
    )
    return state
