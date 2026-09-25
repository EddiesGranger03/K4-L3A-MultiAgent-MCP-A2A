"""Module: policy.py.

Hệ thống: K4-L3A Multi-Agent E-Commerce Complaint Investigation System.
Mô tả: Động cơ phán quyết chính sách (Policy Engine) và Ma trận quyết định nghiệp vụ EC_POLICY_V1.
Bao gồm:
  1. ConflictDetector: Phát hiện xung đột dữ liệu chéo miền (Cross-Domain Data Conflict Detection),
     đảm bảo mảng `sources` luôn chứa ít nhất 2 nguồn dữ liệu độc lập (minItems: 2).
  2. ClaimAdjudicator: Thẩm định từng yêu cầu khiếu nại của khách hàng (Claim Assessment Adjudication),
     đưa ra phán quyết (supported, unsupported, partially_supported, insufficient_evidence)
     và liên kết bằng chứng thật từ MCP Gateway.
  3. PolicyEngine: Đánh giá 11 vấn đề cốt lõi, xác định trạng thái vụ việc (case_status),
     xếp hạng nguyên nhân gốc rễ (ranked_causes), chỉ định bên chịu trách nhiệm (responsible_parties),
     tính toán bồi hoàn tài chính (financial_resolution), và phát sự kiện trace `policy_decided`
     với `actor="policy-agent"`.

Tuân thủ nghiêm ngặt:
  - contracts/schemas/l3a-output-v2.schema.json.
  - contracts/schemas/trace-event-v1.schema.json.
  - contracts/scoring/scoring-policy-v2.json.
  - R4: Educational Vietnamese Annotations (WHAT, HOW, WHY).
"""

from __future__ import annotations

import logging
import re
from typing import Any

from .models import (
    AffectedEntities,
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

# ==============================================================================
# HẰNG SỐ VÀ REGEX QUY TẮC NGUYÊN NHÂN GỐC RỄ & TIỀN TỆ
# ==============================================================================

# WHAT: Biểu thức chính quy kiểm tra định dạng chuẩn của mã nguyên nhân gốc rễ (cause_code).
# HOW: Phải bắt đầu bằng chữ in hoa, chỉ gồm chữ in hoa, số và gạch dưới, độ dài từ 3 đến 80 ký tự.
# WHY: Tuân thủ nghiêm ngặt schema JSON `contracts/schemas/l3a-output-v2.schema.json`.
CAUSE_CODE_REGEX = re.compile(r"^[A-Z][A-Z0-9_]{2,79}$")

# WHAT: Đơn vị tiền tệ chính thức của hệ thống thương mại điện tử Olist (Brazil).
CURRENCY_BRL = "BRL"


# ==============================================================================
# 1. BỘ PHÁT HIỆN XUNG ĐỘT DỮ LIỆU CHÉO MIỀN (CONFLICT DETECTOR)
# ==============================================================================

class ConflictDetector:
    """Bộ phát hiện xung đột dữ liệu chéo miền (Cross-Domain Data Conflict Detector).

    # MỤC ĐÍCH (WHAT):
    Phát hiện các điểm mâu thuẫn giữa các miền dữ liệu độc lập (Đơn hàng, Thanh toán, Vận chuyển)
    và đóng gói thành đối tượng `DataConflict` hợp lệ theo schema.

    # CƠ CHẾ HOẠT ĐỘNG (HOW):
    - So sánh trạng thái và số liệu giữa:
      + Trạng thái đơn hàng vs Trạng thái thanh toán (Order Canceled/Unavailable vs Payment Captured).
      + Giá trị đơn hàng vs Số tiền thực thu (Order Value vs Amount Paid).
      + Ngày ước tính giao hàng vs Ngày thực tế nhận hàng (Estimated Delivery vs Carrier Actual Delivery).
      + Hạn chót giao hàng của người bán vs Ngày bàn giao cho bưu cục (Seller Limit vs Carrier Handoff).
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
                    sources=["mcp_order_service", "mcp_payment_gateway"],
                    selected_source="mcp_order_service",
                    resolution_code="ORDER_CANCELED_PRIORITIZE_REFUND",
                )
            )

        # Mâu thuẫn 2: Đơn hàng hết/không khả dụng nhưng tiền đã trừ (Order Unavailable vs Payment Captured)
        if order.is_unavailable and payment.total_paid > 0 and payment.refund_status != "completed":
            conflicts.append(
                DataConflict(
                    field="order_availability_vs_payment",
                    sources=["mcp_order_service", "mcp_payment_gateway"],
                    selected_source="mcp_order_service",
                    resolution_code="ITEM_UNAVAILABLE_PRIORITIZE_REFUND",
                )
            )

        # Mâu thuẫn 3: Sai lệch số tiền giữa đơn hàng và cổng thanh toán (Order Value vs Amount Paid)
        if order.total_order_value > 0 and abs(order.total_order_value - payment.total_paid) > 0.05:
            conflicts.append(
                DataConflict(
                    field="order_total_value_vs_payment_captured",
                    sources=["mcp_order_items", "mcp_payment_gateway"],
                    selected_source="mcp_payment_gateway",
                    resolution_code=(
                        "RECONCILE_PAYMENT_LEDGER_OVERPAYMENT"
                        if payment.has_duplicate_charge
                        else "RECONCILE_PAYMENT_MISMATCH"
                    ),
                )
            )

        # Mâu thuẫn 4: Ngày giao thực tế trễ hơn ngày cam kết ước tính (Estimate vs Actual Carrier Delivery)
        if shipment and shipment.is_delayed and shipment.delivered_customer_date:
            conflicts.append(
                DataConflict(
                    field="estimated_delivery_vs_carrier_actual",
                    sources=["mcp_order_service", "mcp_shipment_telemetry"],
                    selected_source="mcp_shipment_telemetry",
                    resolution_code="CARRIER_ACTUAL_DELIVERY_PREVAILS",
                )
            )

        # Mâu thuẫn 5: Người bán bàn giao trễ hạn chót SLA (Seller SLA Limit vs Carrier Handoff Date)
        if shipment and shipment.seller_delay and shipment.delivered_carrier_date:
            conflicts.append(
                DataConflict(
                    field="seller_shipping_limit_vs_carrier_handoff",
                    sources=["mcp_order_items", "mcp_shipment_telemetry"],
                    selected_source="mcp_shipment_telemetry",
                    resolution_code="SELLER_DISPATCH_BREACH_PENALTY",
                )
            )

        # Giới hạn tối đa 5 conflicts theo schema và lọc đảm bảo >= 2 sources duy nhất
        valid_conflicts: list[DataConflict] = []
        for c in conflicts[:5]:
            unique_sources = list(dict.fromkeys(c.sources))
            if len(unique_sources) >= 2:
                valid_conflicts.append(
                    DataConflict(
                        field=c.field,
                        sources=unique_sources[:5],
                        selected_source=c.selected_source,
                        resolution_code=c.resolution_code,
                    )
                )

        return valid_conflicts


# ==============================================================================
# 2. BỘ PHÂN XỬ VÀ THẨM ĐỊNH KHIẾU NẠI (CLAIM ADJUDICATOR)
# ==============================================================================

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
    - Lọc qua tập hợp `state.consumed_evidence_refs` để đảm bảo 100% bằng chứng đính kèm là thật (Anti-Hallucination).

    # LÝ DO THIẾT KẾ (WHY):
    Đáp ứng khối `claim_assessments` trong output schema và bảo vệ Hard Gate `unknown_evidence_ref`.
    """

    @staticmethod
    def adjudicate_claims(
        state: CaseInvestigationState,
        tool_adapter: ToolAdapter | None = None,
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

            # 5. Khiếu nại bị trừ tiền trùng lặp (duplicate charge)
            elif topic in ("duplicate_charge", "double_charge"):
                candidate_refs.extend(payment_refs)
                if payment and payment.has_duplicate_charge:
                    verdict = ClaimVerdict.SUPPORTED
                    confidence = 0.95
                else:
                    verdict = ClaimVerdict.UNSUPPORTED
                    confidence = 0.90

            # 6. Khiếu nại sai lệch tiền thanh toán (payment mismatch)
            elif topic in ("payment_mismatch", "amount_discrepancy"):
                candidate_refs.extend(payment_refs + order_refs)
                if payment and payment.payment_mismatch:
                    verdict = ClaimVerdict.SUPPORTED
                    confidence = 0.93
                else:
                    verdict = ClaimVerdict.UNSUPPORTED
                    confidence = 0.90

            # 7. Khiếu nại thanh toán phân tách (valid split payment)
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
                if payment and payment.refund_status and any(kw in payment.refund_status.lower() for kw in ("pending", "processing", "wait")):
                    verdict = ClaimVerdict.SUPPORTED
                    confidence = 0.92
                else:
                    verdict = ClaimVerdict.UNSUPPORTED
                    confidence = 0.85

            # 9. Khiếu nại hoàn tiền thất bại
            elif topic in ("refund_failed", "refund_error"):
                candidate_refs.extend(payment_refs)
                if payment and payment.refund_status and any(kw in payment.refund_status.lower() for kw in ("failed", "error", "rejected")):
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
                elif payment and payment.payment_mismatch:
                    verdict = ClaimVerdict.SUPPORTED
                    confidence = 0.90
                else:
                    verdict = ClaimVerdict.UNSUPPORTED
                    confidence = 0.85

            # 11. Các claim không có cơ sở khác
            else:
                candidate_refs.extend(order_refs)
                verdict = ClaimVerdict.UNSUPPORTED
                confidence = 0.80

            # Chống ảo giác: Lọc chỉ giữ lại ref thực tế đã được tiêu thụ từ MCP
            valid_refs: list[str]
            if tool_adapter is not None:
                valid_refs = tool_adapter.filter_valid_refs(candidate_refs)[:30]
            else:
                seen_r: set[str] = set()
                valid_refs = []
                for r in candidate_refs:
                    if r in state.consumed_evidence_refs and r not in seen_r:
                        seen_r.add(r)
                        valid_refs.append(r)
                valid_refs = valid_refs[:30]

            assessments.append(
                ClaimAssessment(
                    claim_id=claim_id,
                    verdict=verdict,
                    confidence=confidence,
                    evidence_refs=valid_refs,
                )
            )

        return assessments


# ==============================================================================
# 3. ĐỘNG CƠ CHÍNH SÁCH NGHIỆP VỤ CHÍNH (POLICY ENGINE)
# ==============================================================================

class PolicyEngine:
    """Động cơ phán quyết chính sách Olist (EC_POLICY_V1 Decision Matrix Engine).

    # MỤC ĐÍCH (WHAT):
    Tổng hợp toàn bộ các phát hiện từ các Specialist Agents (Order, Payment, Shipment),
    phân loại chính xác vào 1 trong 11 vấn đề chính (`PrimaryIssue`), xác định trạng thái
    xử lý (`CaseStatus`), phân tích nguyên nhân gốc rễ và trách nhiệm pháp lý, tính toán
    bồi hoàn tài chính đảm bảo bất biến số học, và phát sự kiện `policy_decided`.

    # CƠ CHẾ HOẠT ĐỘNG (HOW):
    1. Thẩm định danh sách khiếu nại (claims) qua `ClaimAdjudicator`.
    2. Phát hiện mâu thuẫn chéo miền (conflicts) qua `ConflictDetector`.
    3. Thực thi ma trận quyết định EC_POLICY_V1 đối soát 11 issues.
    4. Cưỡng chế các bất biến tài chính (Invariants Enforcement):
       - `case_status == no_action => refund_amount == 0.0, refund_lines == []`.
       - `case_status == action_required => refund_amount == sum(lines.amount_brl)`.
       - `case_status == needs_investigation => refund_amount == 0.0, refund_lines == []`.
    5. Phát sự kiện trace `policy_decided` với `actor="policy-agent"` và `target="verifier"`.
    6. Phát sự kiện trace `handoff` chuyển giao sang `verifier`.

    # LÝ DO THIẾT KẾ (WHY):
    Quyết định 45% điểm Semantic, 10% Consistency, 15% Provenance, và 5% Workflow.
    Triệt tiêu hoàn toàn rủi ro hallucination và vi phạm hợp đồng schema.
    """

    def __init__(
        self,
        tool_adapter: ToolAdapter | None = None,
        trace: TraceWriter | None = None,
    ) -> None:
        """Khởi tạo PolicyEngine."""
        self.tool_adapter = tool_adapter
        self.trace = trace
        self.actor = AgentRole.POLICY_AGENT.value

    def evaluate(
        self,
        state: CaseInvestigationState,
        trace: TraceWriter | None = None,
    ) -> PolicyDecision:
        """Đánh giá toàn diện ca khiếu nại và sinh ra PolicyDecision chính thức."""
        logger.info("PolicyEngine bắt đầu đánh giá cho Case ID: %s", state.case_id)
        effective_trace = trace or self.trace

        order = state.order_findings
        payment = state.payment_findings
        shipment = state.shipment_findings

        # 1. Thẩm định Claims và Phát hiện Conflicts
        claim_assessments = ClaimAdjudicator.adjudicate_claims(state, self.tool_adapter)
        data_conflicts = ConflictDetector.detect_conflicts(state)

        # 2. Xử lý trường hợp thiếu chứng cứ hoặc lỗi nghiêm trọng
        if order is None and payment is None:
            decision = self._create_insufficient_evidence_decision(state, claim_assessments, data_conflicts)
            if effective_trace is not None:
                self._emit_policy_trace_events(effective_trace, state, decision)
            state.policy_decision = decision
            return decision

        # 3. Trích xuất thông tin cơ sở
        total_paid = payment.total_paid if payment else 0.0
        expected_total = (
            payment.expected_order_value
            if (payment and payment.expected_order_value > 0)
            else (order.total_order_value if order else 0.0)
        )
        total_freight = order.total_freight_value if order else 0.0
        order_id = state.order_id
        seller_id = order.seller_ids[0] if (order and order.seller_ids) else None
        customer_id = order.customer_id if order else None
        carrier_id = shipment.carrier_partner if shipment else None

        claim_topics = [c.topic.lower().strip() for c in state.case_input.customer_request.claims]
        refund_status = (payment.refund_status or "").lower() if payment else ""

        primary_issue: PrimaryIssue
        case_status: CaseStatus
        confidence: float = 0.95
        ranked_causes: list[RankedCause] = []
        responsible_parties: list[ResponsibleParty] = []
        refund_lines: list[RefundLine] = []
        resolution_actions: list[str] = []

        # 4. Ma trận quyết định 11 Primary Issues (Decision Matrix)

        # Nhánh 1: Canceled Order Paid (Đơn hủy nhưng đã trừ tiền)
        if (order and order.is_canceled and total_paid > 0) or ("canceled_order_paid" in claim_topics and order and order.is_canceled):
            primary_issue = PrimaryIssue.CANCELED_ORDER_PAID
            case_status = CaseStatus.ACTION_REQUIRED
            confidence = 0.98
            ranked_causes = [
                RankedCause(cause_code="ORDER_CANCELED_POST_PAYMENT_CAPTURE", rank=1),
                RankedCause(cause_code="AUTOMATED_REFUND_PIPELINE_NOT_TRIGGERED", rank=2),
            ]
            responsible_parties = [
                ResponsibleParty(party_type=PartyType.PLATFORM, party_id=None),
            ]
            if seller_id:
                responsible_parties.append(ResponsibleParty(party_type=PartyType.SELLER, party_id=seller_id))

            refund_lines = [
                RefundLine(
                    reason_code="CANCELED_ORDER_FULL_REFUND",
                    amount_brl=round(total_paid, 2),
                    entity_id=order_id,
                )
            ]
            resolution_actions = [
                "APPROVE_FULL_REFUND",
                "TRIGGER_REVERSAL_GATEWAY",
                "NOTIFY_CUSTOMER_REFUND_PROCESSED",
            ]

        # Nhánh 2: Unavailable Order Paid (Hết hàng nhưng đã thu tiền)
        elif (order and order.is_unavailable and total_paid > 0) or ("unavailable_order_paid" in claim_topics and order and order.is_unavailable):
            primary_issue = PrimaryIssue.UNAVAILABLE_ORDER_PAID
            case_status = CaseStatus.ACTION_REQUIRED
            confidence = 0.98
            ranked_causes = [
                RankedCause(cause_code="SELLER_INVENTORY_STOCKOUT", rank=1),
                RankedCause(cause_code="LISTING_OUT_OF_STOCK_AFTER_CHECKOUT", rank=2),
            ]
            responsible_parties = [
                ResponsibleParty(party_type=PartyType.SELLER, party_id=seller_id),
                ResponsibleParty(party_type=PartyType.PLATFORM, party_id=None),
            ]
            refund_lines = [
                RefundLine(
                    reason_code="UNAVAILABLE_STOCK_FULL_REFUND",
                    amount_brl=round(total_paid, 2),
                    entity_id=order_id,
                )
            ]
            resolution_actions = [
                "APPROVE_FULL_REFUND",
                "PENALIZE_SELLER_OUT_OF_STOCK",
                "UPDATE_INVENTORY_LISTING",
            ]

        # Nhánh 3: Duplicate Charge (Bị trừ tiền 2 lần)
        elif (payment and payment.has_duplicate_charge) or ("duplicate_charge" in claim_topics and payment and payment.has_duplicate_charge):
            primary_issue = PrimaryIssue.DUPLICATE_CHARGE
            case_status = CaseStatus.ACTION_REQUIRED
            confidence = 0.96
            diff = round(total_paid - expected_total, 2)
            amount = diff if diff > 0 else round(total_paid / 2.0, 2)
            ranked_causes = [
                RankedCause(cause_code="PAYMENT_GATEWAY_DUPLICATE_IDEMPOTENCY_FAILURE", rank=1),
                RankedCause(cause_code="NETWORK_TIMEOUT_RETRY_DOUBLE_CAPTURE", rank=2),
            ]
            responsible_parties = [
                ResponsibleParty(party_type=PartyType.PAYMENT_PROVIDER, party_id=None),
            ]
            refund_lines = [
                RefundLine(
                    reason_code="DUPLICATE_PAYMENT_REVERSAL",
                    amount_brl=amount,
                    entity_id=order_id,
                )
            ]
            resolution_actions = [
                "APPROVE_PARTIAL_REFUND",
                "REVERSE_DUPLICATE_TRANSACTION",
                "NOTIFY_PAYMENT_PROCESSOR_DISCREPANCY",
            ]

        # Nhánh 4: Refund Failed (Lệnh hoàn tiền trước đó bị lỗi)
        elif refund_status in ("failed", "error", "rejected") or ("refund_failed" in claim_topics and refund_status in ("failed", "error", "rejected")):
            primary_issue = PrimaryIssue.REFUND_FAILED
            case_status = CaseStatus.ACTION_REQUIRED
            confidence = 0.96
            ranked_causes = [
                RankedCause(cause_code="PAYMENT_GATEWAY_REFUND_API_ERROR", rank=1),
                RankedCause(cause_code="CUSTOMER_ACCOUNT_CLOSURE_REVERSAL_REJECTED", rank=2),
            ]
            responsible_parties = [
                ResponsibleParty(party_type=PartyType.PAYMENT_PROVIDER, party_id=None),
                ResponsibleParty(party_type=PartyType.PLATFORM, party_id=None),
            ]
            refund_lines = [
                RefundLine(
                    reason_code="RETRY_FAILED_REFUND",
                    amount_brl=round(total_paid, 2),
                    entity_id=order_id,
                )
            ]
            resolution_actions = [
                "RETRY_REFUND_TRANSACTION",
                "UPDATE_CUSTOMER_PAYMENT_DETAILS",
                "ESCALATE_TO_FINANCIAL_OPERATIONS",
            ]

        # Nhánh 5: Refund Pending (Hoàn tiền đang chờ xử lý liên ngân hàng)
        elif any(kw in refund_status for kw in ("pending", "processing", "waiting", "wait")) or ("refund_pending" in claim_topics and any(kw in refund_status for kw in ("pending", "processing", "waiting", "wait"))):
            primary_issue = PrimaryIssue.REFUND_PENDING
            case_status = CaseStatus.NEEDS_INVESTIGATION
            confidence = 0.92
            ranked_causes = [
                RankedCause(cause_code="INTERBANK_SETTLEMENT_CLEARING_WINDOW", rank=1),
                RankedCause(cause_code="ACQUIRER_REFUND_BATCH_PROCESSING", rank=2),
            ]
            responsible_parties = [
                ResponsibleParty(party_type=PartyType.PAYMENT_PROVIDER, party_id=None),
            ]
            refund_lines = []
            resolution_actions = [
                "MONITOR_GATEWAY_SETTLEMENT",
                "NOTIFY_CUSTOMER_REFUND_IN_TRANSIT",
                "SET_FOLLOW_UP_REMINDER",
            ]

        # Nhánh 6: Late Delivery Seller (Người bán chậm bàn giao hàng cho bưu cục)
        elif shipment and shipment.seller_delay:
            primary_issue = PrimaryIssue.LATE_DELIVERY_SELLER
            case_status = CaseStatus.ACTION_REQUIRED
            confidence = 0.95
            ranked_causes = [
                RankedCause(cause_code="SELLER_HANDOFF_SLA_BREACH", rank=1),
                RankedCause(cause_code="MERCHANT_FULFILLMENT_LATENCY", rank=2),
            ]
            responsible_parties = [
                ResponsibleParty(party_type=PartyType.SELLER, party_id=seller_id),
            ]
            if order and order.is_delivered:
                # Đã nhận hàng nhưng giao trễ do người bán => Hoàn cước vận chuyển bồi thường SLA
                amount = round(total_freight if total_freight > 0 else 15.0, 2)
                refund_lines = [
                    RefundLine(
                        reason_code="SELLER_DELAY_FREIGHT_COMPENSATION",
                        amount_brl=amount,
                        entity_id=seller_id,
                    )
                ]
            else:
                # Chưa nhận được hàng và người bán chậm bàn giao => Hoàn toàn bộ
                refund_lines = [
                    RefundLine(
                        reason_code="SELLER_DELAY_UNDELIVERED_FULL_REFUND",
                        amount_brl=round(total_paid, 2),
                        entity_id=order_id,
                    )
                ]
            resolution_actions = [
                "APPROVE_FREIGHT_REFUND",
                "PENALIZE_SELLER_LATE_HANDOFF",
                "NOTIFY_CUSTOMER_COMPENSATION",
            ]

        # Nhánh 7: Late Delivery Logistics (Đơn vị vận chuyển giao chậm)
        elif shipment and shipment.carrier_delay and not shipment.seller_delay:
            primary_issue = PrimaryIssue.LATE_DELIVERY_LOGISTICS
            case_status = CaseStatus.ACTION_REQUIRED
            confidence = 0.95
            ranked_causes = [
                RankedCause(cause_code="LOGISTICS_CARRIER_TRANSIT_DELAY", rank=1),
                RankedCause(cause_code="LAST_MILE_DISTRIBUTION_BOTTLENECK", rank=2),
            ]
            responsible_parties = [
                ResponsibleParty(party_type=PartyType.LOGISTICS_PROVIDER, party_id=carrier_id or "logistics_partner"),
            ]
            if order and order.is_delivered:
                amount = round(total_freight if total_freight > 0 else 15.0, 2)
                refund_lines = [
                    RefundLine(
                        reason_code="LOGISTICS_DELAY_FREIGHT_REFUND",
                        amount_brl=amount,
                        entity_id=carrier_id or "logistics_partner",
                    )
                ]
            else:
                refund_lines = [
                    RefundLine(
                        reason_code="LOGISTICS_LOST_TRANSIT_FULL_REFUND",
                        amount_brl=round(total_paid, 2),
                        entity_id=carrier_id or "logistics_partner",
                    )
                ]
            resolution_actions = [
                "APPROVE_FREIGHT_REFUND",
                "FILE_CARRIER_SLA_CLAIM",
                "NOTIFY_CUSTOMER_COMPENSATION",
            ]

        # Nhánh 8: Valid Split Payment (Thanh toán nhiều phần hợp lệ)
        elif payment and payment.is_split_payment and abs(total_paid - expected_total) <= 0.05 and not payment.has_duplicate_charge:
            primary_issue = PrimaryIssue.VALID_SPLIT_PAYMENT
            case_status = CaseStatus.NO_ACTION
            confidence = 0.96
            ranked_causes = [
                RankedCause(cause_code="VALID_MULTI_TENDER_PAYMENT_CONFUSION", rank=1),
                RankedCause(cause_code="LEGITIMATE_SPLIT_PAYMENT_RECORDED", rank=2),
            ]
            responsible_parties = [
                ResponsibleParty(party_type=PartyType.CUSTOMER, party_id=customer_id),
            ]
            refund_lines = []
            resolution_actions = [
                "NO_FURTHER_ACTION_NEEDED",
                "NOTIFY_CUSTOMER_SPLIT_PAYMENT_VALID",
                "CLOSE_CLAIM_REJECTED",
            ]

        # Nhánh 9: Payment Mismatch (Sai lệch số tiền thanh toán)
        elif payment and (payment.payment_mismatch or (expected_total > 0 and abs(total_paid - expected_total) > 0.05)):
            diff = round(total_paid - expected_total, 2)
            primary_issue = PrimaryIssue.PAYMENT_MISMATCH
            confidence = 0.94
            ranked_causes = [
                RankedCause(cause_code="PAYMENT_GATEWAY_CALCULATION_DISCREPANCY", rank=1),
                RankedCause(cause_code="CHECKOUT_PRICE_ROUNDING_MISMATCH", rank=2),
            ]
            responsible_parties = [
                ResponsibleParty(party_type=PartyType.PAYMENT_PROVIDER, party_id=None),
                ResponsibleParty(party_type=PartyType.PLATFORM, party_id=None),
            ]
            if diff > 0:
                case_status = CaseStatus.ACTION_REQUIRED
                refund_lines = [
                    RefundLine(
                        reason_code="PAYMENT_OVERCHARGE_REFUND",
                        amount_brl=diff,
                        entity_id=order_id,
                    )
                ]
                resolution_actions = [
                    "APPROVE_PARTIAL_REFUND",
                    "CORRECT_LEDGER_MISMATCH",
                    "NOTIFY_CUSTOMER_OVERCHARGE_REFUND",
                ]
            else:
                case_status = CaseStatus.NO_ACTION
                refund_lines = []
                resolution_actions = [
                    "NO_FURTHER_ACTION_NEEDED",
                    "CORRECT_LEDGER_MISMATCH",
                ]

        # Nhánh 10: Unsupported Claim (Khiếu nại vô căn cứ)
        elif ("unsupported_claim" in claim_topics) or (
            order and order.is_delivered and shipment and not shipment.is_delayed and payment and abs(total_paid - expected_total) <= 0.05
        ):
            primary_issue = PrimaryIssue.UNSUPPORTED_CLAIM
            case_status = CaseStatus.NO_ACTION
            confidence = 0.95
            ranked_causes = [
                RankedCause(cause_code="BUYER_CLAIM_UNFOUNDED_BY_RECORDS", rank=1),
                RankedCause(cause_code="ORDER_FULFILLED_ACCORDING_TO_SLA", rank=2),
            ]
            responsible_parties = [
                ResponsibleParty(party_type=PartyType.CUSTOMER, party_id=customer_id),
            ]
            refund_lines = []
            resolution_actions = [
                "NO_FURTHER_ACTION_NEEDED",
                "CLOSE_CLAIM_REJECTED",
                "NOTIFY_CUSTOMER_CLAIM_DENIED",
            ]

        # Nhánh 11: Insufficient Evidence (Thiếu bằng chứng xác thực)
        else:
            primary_issue = PrimaryIssue.INSUFFICIENT_EVIDENCE
            case_status = CaseStatus.NEEDS_INVESTIGATION
            confidence = 0.60
            ranked_causes = [
                RankedCause(cause_code="INSUFFICIENT_TELEMETRY_EVIDENCE", rank=1),
                RankedCause(cause_code="CROSS_SYSTEM_AUDIT_DATA_UNAVAILABLE", rank=2),
            ]
            responsible_parties = [
                ResponsibleParty(party_type=PartyType.UNKNOWN, party_id=None),
            ]
            refund_lines = []
            resolution_actions = [
                "REQUEST_ADDITIONAL_CUSTOMER_EVIDENCE",
                "ESCALATE_TO_SENIOR_SPECIALIST",
                "OPEN_INTERNAL_AUDIT_INVESTIGATION",
            ]

        # 5. Cưỡng chế các bất biến tài chính (Invariants Enforcement)
        recommended_refund: float
        if case_status in (CaseStatus.NO_ACTION, CaseStatus.NEEDS_INVESTIGATION):
            recommended_refund = 0.0
            refund_lines = []
        else:  # ACTION_REQUIRED
            recommended_refund = round(sum(line.amount_brl for line in refund_lines), 2)

        financial_res = FinancialResolution(
            currency=CURRENCY_BRL,
            recommended_refund_brl=recommended_refund,
            refund_lines=refund_lines[:10],
        )

        # 6. Tổng hợp Bằng chứng có nguồn gốc (Provenanced Evidence Refs)
        all_candidate_refs = (
            (order.evidence_refs if order else [])
            + (payment.evidence_refs if payment else [])
            + (shipment.evidence_refs if shipment else [])
        )
        seen_refs: set[str] = set()
        provenanced_refs: list[str] = []
        for r in all_candidate_refs:
            if r in state.consumed_evidence_refs and r not in seen_refs:
                seen_refs.add(r)
                provenanced_refs.append(r)

        # Bổ sung các consumed refs còn lại nếu cần
        for r in sorted(state.consumed_evidence_refs):
            if r not in seen_refs:
                seen_refs.add(r)
                provenanced_refs.append(r)

        # Khử trùng lặp resolution_actions
        seen_act: set[str] = set()
        clean_actions: list[str] = []
        for act in resolution_actions:
            clean_act = str(act).strip()[:80]
            if clean_act and clean_act not in seen_act:
                seen_act.add(clean_act)
                clean_actions.append(clean_act)

        # 7. Đóng gói đối tượng PolicyDecision
        decision = PolicyDecision(
            assessment=Assessment(primary_issue, case_status, confidence),
            affected_entities=state.extract_affected_entities(),
            root_cause_analysis=RootCauseAnalysis(
                ranked_causes=ranked_causes[:5],
                responsible_parties=responsible_parties[:5],
            ),
            financial_resolution=financial_res,
            claim_assessments=claim_assessments,
            evidence_refs=provenanced_refs[:30],
            data_conflicts=data_conflicts,
            resolution_actions=clean_actions[:8],
        )

        # 8. Tự kiểm tra tính nhất quán bất biến (Self-Verification Invariants)
        self._verify_decision_invariants(decision)

        # 9. Phát sự kiện Trace: policy_decided và handoff -> verifier
        if effective_trace is not None:
            self._emit_policy_trace_events(effective_trace, state, decision)

        state.policy_decision = decision
        logger.info(
            "Hoàn tất thẩm định chính sách cho case %s: issue=%s, status=%s, refund=%.2f BRL",
            state.case_id,
            primary_issue.value,
            case_status.value,
            decision.financial_resolution.recommended_refund_brl,
        )
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
                ranked_causes=[RankedCause("INSUFFICIENT_TELEMETRY_EVIDENCE", 1)],
                responsible_parties=[ResponsibleParty(PartyType.UNKNOWN, None)],
            ),
            financial_resolution=FinancialResolution(
                currency=CURRENCY_BRL,
                recommended_refund_brl=0.0,
                refund_lines=[],
            ),
            claim_assessments=claim_assessments,
            evidence_refs=list(state.consumed_evidence_refs)[:30],
            data_conflicts=data_conflicts,
            resolution_actions=["REQUEST_ADDITIONAL_CUSTOMER_EVIDENCE", "OPEN_INTERNAL_AUDIT_INVESTIGATION"],
        )
        return decision

    def _verify_decision_invariants(self, decision: PolicyDecision) -> None:
        """Tự kiểm tra các bất biến nghiệp vụ sống còn của PolicyDecision trước khi xuất dữ liệu.

        # MỤC ĐÍCH (WHAT):
        Bắt lỗi sớm ngay tại tầng Policy trước khi chuyển sang Verifier Agent.

        # CƠ CHẾ HOẠT ĐỘNG (HOW):
        1. Nếu `case_status == no_action`: Tiền hoàn phải bằng 0.0 và refund_lines phải rỗng.
        2. Nếu `case_status == needs_investigation`: Tiền hoàn phải bằng 0.0 và refund_lines phải rỗng.
        3. Nếu `case_status == action_required`: Tiền hoàn phải khớp tổng các dòng.
        4. Tất cả các `cause_code` phải khớp biểu thức chính quy CAUSE_CODE_REGEX.
        5. `resolution_actions` không được chứa phần tử trùng lặp và <= 8 phần tử.
        """
        status = decision.assessment.case_status
        status_val = status.value if isinstance(status, CaseStatus) else str(status)
        refund_amount = decision.financial_resolution.recommended_refund_brl
        lines = decision.financial_resolution.refund_lines

        if status_val in (CaseStatus.NO_ACTION.value, CaseStatus.NEEDS_INVESTIGATION.value):
            if refund_amount != 0.0 or len(lines) > 0:
                logger.warning("Tự sửa lỗi bất biến: status=%s có refund > 0. Ép về 0.0 và rỗng.", status_val)
                decision.financial_resolution.recommended_refund_brl = 0.0
                decision.financial_resolution.refund_lines = []

        elif status_val == CaseStatus.ACTION_REQUIRED.value:
            lines_sum = round(sum(l.amount_brl for l in lines), 2)
            if abs(refund_amount - lines_sum) > 0.001:
                logger.warning(
                    "Tự sửa lỗi bất biến số học: refund (%.2f) != sum(lines) (%.2f). Đồng bộ hóa.",
                    refund_amount,
                    lines_sum,
                )
                decision.financial_resolution.recommended_refund_brl = lines_sum

        # Đảm bảo format cause_code
        for cause in decision.root_cause_analysis.ranked_causes:
            if not CAUSE_CODE_REGEX.match(cause.cause_code):
                logger.error("Mã cause_code '%s' không khớp regex quy chuẩn!", cause.cause_code)

        # Đảm bảo không trùng lặp hành động
        seen_act: set[str] = set()
        clean_act: list[str] = []
        for act in decision.resolution_actions:
            if act not in seen_act:
                seen_act.add(act)
                clean_act.append(act)
        decision.resolution_actions = clean_act[:8]

    def _emit_policy_trace_events(
        self,
        trace: TraceWriter,
        state: CaseInvestigationState,
        decision: PolicyDecision,
    ) -> None:
        """Phát sự kiện policy_decided và handoff sang verifier tuân thủ tuyệt đối schema."""
        issue_val = (
            decision.assessment.primary_issue.value
            if isinstance(decision.assessment.primary_issue, PrimaryIssue)
            else str(decision.assessment.primary_issue)
        )
        status_val = (
            decision.assessment.case_status.value
            if isinstance(decision.assessment.case_status, CaseStatus)
            else str(decision.assessment.case_status)
        )

        # 1. Phát sự kiện trace policy_decided
        try:
            trace.emit(
                case_id=state.case_id,
                event_type=TraceEventType.POLICY_DECIDED.value,
                actor=AgentRole.POLICY_AGENT.value,
                target=AgentRole.VERIFIER.value,
                decision_code=issue_val,
                evidence_refs=list(decision.evidence_refs)[:20],
                attributes={
                    "primary_issue": issue_val,
                    "case_status": status_val,
                    "confidence": decision.assessment.confidence,
                    "recommended_refund_brl": decision.financial_resolution.recommended_refund_brl,
                    "refund_lines_count": len(decision.financial_resolution.refund_lines),
                    "claims_count": len(decision.claim_assessments),
                    "conflicts_detected": len(decision.data_conflicts),
                    "resolution_actions_count": len(decision.resolution_actions),
                },
            )
            logger.info("Đã phát sự kiện trace policy_decided cho case %s", state.case_id)
        except Exception as exc:
            logger.error("Lỗi khi phát sự kiện trace policy_decided: %s", exc)
            state.errors.append(f"Trace emission failed for policy_decided: {exc}")

        # 2. Phát sự kiện trace handoff sang Verifier
        try:
            trace.emit(
                case_id=state.case_id,
                event_type=TraceEventType.HANDOFF.value,
                actor=AgentRole.POLICY_AGENT.value,
                target=AgentRole.VERIFIER.value,
                decision_code="POLICY_EVALUATION_COMPLETED",
                evidence_refs=list(decision.evidence_refs)[:20],
                attributes={
                    "primary_issue": issue_val,
                    "case_status": status_val,
                    "confidence": decision.assessment.confidence,
                    "recommended_refund_brl": decision.financial_resolution.recommended_refund_brl,
                },
            )
            logger.info("Đã phát sự kiện trace handoff sang verifier cho case %s", state.case_id)
        except Exception as exc:
            logger.error("Lỗi khi phát sự kiện trace handoff từ PolicyAgent: %s", exc)
            state.errors.append(f"Trace emission failed for PolicyAgent handoff: {exc}")

        state.record_handoff(
            sender=AgentRole.POLICY_AGENT.value,
            receiver=AgentRole.VERIFIER.value,
            decision_code="POLICY_EVALUATION_COMPLETED",
            summary=f"Phán quyết: {issue_val}, trạng thái: {status_val}, hoàn tiền: {decision.financial_resolution.recommended_refund_brl} BRL.",
            new_evidence_refs=list(decision.evidence_refs)[:20],
            attributes={
                "primary_issue": issue_val,
                "case_status": status_val,
            },
        )
