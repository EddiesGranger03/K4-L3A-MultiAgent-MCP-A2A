"""Module mô hình dữ liệu và kiến trúc trạng thái hệ thống Multi-Agent (K4-L3A).

Tài liệu giáo dục & đặc tả kỹ thuật:
- WHAT: Định nghĩa toàn bộ cấu trúc dữ liệu nội bộ (Single Source of Truth),
  các đối tượng trao đổi Agent-to-Agent (A2A handoff), kết quả điều tra của
  từng Specialist Agent, và mô hình đầu ra cuối cùng tuân thủ tuyệt đối
  `contracts/schemas/l3a-output-v2.schema.json`.
- HOW: Sử dụng Python dataclasses với type annotations chặt chẽ, các Enums chuẩn hóa,
  hàm chuyển đổi hai chiều (serialization/deserialization), và bộ kiểm tra tính
  nhất quán nghiệp vụ (invariant validation).
- WHY:
  1. Ngăn chặn triệt để lỗi vi phạm schema (Hard Gate: unscorable_schema).
  2. Đảm bảo kiểm soát nguồn gốc bằng chứng (Evidence Provenance: 15% tổng điểm).
  3. Cung cấp giao thức A2A mạch lạc, cho phép tích lũy trạng thái (State Accumulation)
     mà không làm mất mát thông tin giữa các bước chuyển giao (Handoff).
  4. Hỗ trợ học tập: Giúp học viên nắm vững cách xây dựng hệ thống Multi-Agent
     chuẩn công nghiệp với kiểm chứng chặt chẽ.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import Enum
from typing import Any

# ==============================================================================
# 1. BIỂU THỨC CHÍNH QUY (REGEX) VÀ HẰNG SỐ HỆ THỐNG
# ==============================================================================

# WHAT: Regex kiểm tra định dạng mã case ID.
# HOW: Bắt đầu bằng ký tự chữ in hoa hoặc số, tiếp theo là 2-63 ký tự chữ/số/gạch dưới/gạch ngang.
# WHY: Đảm bảo case_id khớp hoàn toàn với quy định của cuộc thi và tên file inputs.
CASE_ID_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_-]{2,63}$")

# WHAT: Regex kiểm tra định dạng tham chiếu bằng chứng (evidence_ref) từ MCP Gateway.
# HOW: Phải bắt đầu bằng tiền tố 'ev_' theo sau là 20 đến 96 ký tự chữ, số, gạch ngang, gạch dưới.
# WHY: Hard Gate: invalid_evidence_refs sẽ bị 0 điểm nếu chuỗi không khớp mẫu này.
EVIDENCE_REF_PATTERN = re.compile(r"^ev_[A-Za-z0-9_-]{20,96}$")

# WHAT: Regex kiểm tra mã nguyên nhân gốc rễ (cause_code).
# HOW: Bắt đầu bằng chữ in hoa, theo sau là chữ in hoa, số hoặc gạch dưới (độ dài 3-80 ký tự).
# WHY: Tuân thủ trường root_cause_analysis.ranked_causes[].cause_code trong JSON Schema.
CAUSE_CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{2,79}$")

# WHAT: Regex kiểm tra định dạng ID sự kiện trace (event_id).
# HOW: Bắt đầu bằng 'evt_' theo sau là 12-96 ký tự an toàn URL.
# WHY: Đảm bảo tính hợp lệ khi TraceWriter ghi log sự kiện kiểm toán.
EVENT_ID_PATTERN = re.compile(r"^evt_[A-Za-z0-9_-]{12,96}$")

# WHAT: Tên phiên bản schema đầu ra chuẩn của L3A.
OUTPUT_SCHEMA_VERSION = "day09-l3a-output-v2"

# WHAT: Đơn vị tiền tệ chuẩn được quy định trong hợp đồng bảo hiểm/bồi hoàn Olist.
CURRENCY_BRL = "BRL"


# ==============================================================================
# 2. ENUMS CHUẨN HÓA NGHIỆP VỤ & HỢP ĐỒNG (CONTRACT ENUMS)
# ==============================================================================

class PrimaryIssue(str, Enum):
    """WHAT: 11 loại khiếu nại / vấn đề chính được hệ thống EC_POLICY_V1 hỗ trợ.

    HOW: Kế thừa từ `str` và `Enum` để tự động tuần tự hóa thành chuỗi JSON tương thích.
    WHY: Đây là trường phân loại cốt lõi quyết định 45% điểm semantic và xác định
    nhánh xử lý tài chính (Financial Resolution) tiếp theo.
    """

    CANCELED_ORDER_PAID = "canceled_order_paid"          # Đơn bị hủy nhưng tiền đã trừ thành công
    UNAVAILABLE_ORDER_PAID = "unavailable_order_paid"    # Hàng hết/không khả dụng nhưng đã thanh toán
    LATE_DELIVERY_SELLER = "late_delivery_seller"        # Giao trễ do người bán chậm bàn giao cho bưu cục
    LATE_DELIVERY_LOGISTICS = "late_delivery_logistics"  # Giao trễ do đơn vị vận chuyển giao chậm
    VALID_SPLIT_PAYMENT = "valid_split_payment"          # Thanh toán chia nhiều phương thức hợp lệ
    PAYMENT_MISMATCH = "payment_mismatch"                # Số tiền thanh toán không khớp giá trị đơn
    DUPLICATE_CHARGE = "duplicate_charge"                # Bị trừ tiền trùng lặp cho cùng một đơn
    REFUND_PENDING = "refund_pending"                    # Yêu cầu hoàn tiền đang chờ ngân hàng/cổng xử lý
    REFUND_FAILED = "refund_failed"                      # Giao dịch hoàn tiền bị lỗi/thất bại kỹ thuật
    UNSUPPORTED_CLAIM = "unsupported_claim"              # Khiếu nại của khách hàng không có cơ sở thực tế
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"      # Thiếu dữ liệu/bằng chứng MCP để kết luận chắc chắn


class CaseStatus(str, Enum):
    """WHAT: Trạng thái hành động tổng thể của Case.

    HOW: Ba mức độ hành động được quy định trong schema:
    - action_required: Cần bồi hoàn, phạt người bán hoặc mở lại khiếu nại.
    - no_action: Khiếu nại sai hoặc đã xử lý xong hoàn tất, không cần làm gì thêm.
    - needs_investigation: Cần chuyển cấp giám sát hoặc xác minh bổ sung từ ngân hàng.
    WHY: Ràng buộc tính nhất quán: Nếu no_action thì recommended_refund_brl BẮT BUỘC bằng 0.
    """

    ACTION_REQUIRED = "action_required"
    NO_ACTION = "no_action"
    NEEDS_INVESTIGATION = "needs_investigation"


class ClaimVerdict(str, Enum):
    """WHAT: Phán quyết cho từng yêu cầu cụ thể của khách hàng (Claim).

    HOW: Gồm 4 mức: supported, unsupported, partially_supported, insufficient_evidence.
    WHY: Giúp giải thích minh bạch cho khách hàng biết lý do chấp thuận hoặc từ chối từng phần.
    """

    SUPPORTED = "supported"
    UNSUPPORTED = "unsupported"
    PARTIALLY_SUPPORTED = "partially_supported"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class PartyType(str, Enum):
    """WHAT: Loại chủ thể chịu trách nhiệm cho sự cố đơn hàng.

    HOW: 6 đối tượng theo quy định schema.
    WHY: Định tuyến trách nhiệm pháp lý và truy thu tài chính (VD: phạt seller hay đòi logistics).
    """

    SELLER = "seller"
    PLATFORM = "platform"
    LOGISTICS_PROVIDER = "logistics_provider"
    PAYMENT_PROVIDER = "payment_provider"
    CUSTOMER = "customer"
    UNKNOWN = "unknown"


class EvidenceDomain(str, Enum):
    """WHAT: 9 miền dữ liệu có thẩm quyền được cung cấp bởi MCP Gateway.

    HOW: Khớp với thuộc tính `domain` trong `mcp-evidence-response-v1.schema.json`.
    WHY: Kiểm soát phạm vi truy vấn của từng Agent, ngăn gọi sai miền dẫn đến phạt Precision.
    """

    ORDER = "order"
    ITEM = "item"
    PAYMENT = "payment"
    SHIPMENT = "shipment"
    SELLER = "seller"
    CUSTOMER = "customer"
    PRODUCT = "product"
    REFUND = "refund"
    POLICY = "policy"


class TraceEventType(str, Enum):
    """WHAT: 7 loại sự kiện vòng đời bắt buộc phải xuất hiện trong `trace.jsonl`.

    HOW: Định nghĩa các mốc chuyển trạng thái từ khi nhận case đến khi đóng hồ sơ.
    WHY: Đạt điểm tối đa thành phần Workflow (5%) và đáp ứng điều kiện tiên quyết của Scorer.
    """

    CASE_RECEIVED = "case_received"                  # Ghi nhận tiếp nhận case từ cli.py
    TASK_ASSIGNED = "task_assigned"                  # Coordinator phân công nhiệm vụ cho Specialist
    TOOL_RESULT_CONSUMED = "tool_result_consumed"    # Specialist tiêu thụ evidence từ MCP Gateway
    HANDOFF = "handoff"                              # Chuyển giao ngữ cảnh giữa các Agent (A2A)
    POLICY_DECIDED = "policy_decided"                # Policy Agent đưa ra phán quyết nghiệp vụ
    VERIFICATION_COMPLETED = "verification_completed"  # Verifier hoàn tất kiểm tra tính nhất quán
    CASE_FINALIZED = "case_finalized"                # Đóng hồ sơ và xuất kết quả file json


class AgentRole(str, Enum):
    """WHAT: Định danh các tác nhân (Actors) tham gia trong hệ thống Multi-Agent.

    HOW: Chuỗi định danh ngắn gọn dùng cho trường `actor` và `target` trong Trace Event.
    WHY: Giúp hệ thống giám sát và người chấm điểm theo dõi sự phối hợp phân tán rõ ràng.
    """

    COORDINATOR = "coordinator"
    ORDER_AGENT = "order-agent"
    PAYMENT_AGENT = "payment-agent"
    SHIPMENT_AGENT = "shipment-agent"
    POLICY_AGENT = "policy-agent"
    VERIFIER = "verifier"


# ==============================================================================
# 3. MÔ HÌNH DỮ LIỆU ĐẦU VÀO (INPUT MODELS)
# ==============================================================================

@dataclass(frozen=True)
class CustomerClaim:
    """WHAT: Đại diện cho một yêu cầu / tuyên bố đơn lẻ của khách hàng trong đơn khiếu nại.

    HOW: Chứa mã `claim_id` duy nhất và chủ đề `topic` (ví dụ: late_delivery_seller, requested_full_refund).
    WHY: Đảm bảo phân rã bài toán lớn thành các tiểu mục kiểm chứng độc lập.
    """

    claim_id: str
    topic: str
    detail: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CustomerClaim:
        """HOW: Chuyển đổi an toàn từ dictionary JSON đầu vào sang CustomerClaim."""
        return cls(
            claim_id=str(data.get("claim_id", "")),
            topic=str(data.get("topic", "")),
            detail=data.get("detail"),
        )


@dataclass(frozen=True)
class CustomerRequest:
    """WHAT: Phần nội dung chi tiết phản ánh của khách hàng kèm thông tin ngữ cảnh.

    HOW: Lưu trữ ngôn ngữ giao tiếp, tin nhắn thô, mã đơn hàng được khách khiếu nại
    và danh sách các claims cần thẩm định.
    WHY: Là điểm xuất phát để Coordinator phân tích ngữ nghĩa và lập kế hoạch điều tra.
    """

    language: str
    message: str
    claimed_order_id: str
    claims: tuple[CustomerClaim, ...] = field(default_factory=tuple)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CustomerRequest:
        """HOW: Parse các claims con và tạo cấu trúc immutable tuple."""
        raw_claims = data.get("claims", [])
        parsed_claims = tuple(CustomerClaim.from_dict(c) for c in raw_claims if isinstance(c, dict))
        return cls(
            language=str(data.get("language", "vi")),
            message=str(data.get("message", "")),
            claimed_order_id=str(data.get("claimed_order_id", "")).strip(),
            claims=parsed_claims,
        )


@dataclass(frozen=True)
class CaseInput:
    """WHAT: Mô hình đóng gói toàn bộ dữ liệu đầu vào của một Case (`inputs/<case_id>.json`).

    HOW: Đọc từ dictionary case do `load_case_set` nạp lên.
    WHY: Đảm bảo dữ liệu đầu vào bất biến (frozen), tránh tình trạng Agent sửa đổi nhầm.
    """

    case_id: str
    opened_at: str
    customer_request: CustomerRequest
    policy_version: str = "EC_POLICY_V1"

    @property
    def order_id(self) -> str:
        """WHAT: Truy xuất nhanh mã đơn hàng cần điều tra từ request của khách hàng."""
        return self.customer_request.claimed_order_id

    @property
    def claim_topics(self) -> list[str]:
        """WHAT: Danh sách các chủ đề claim của case để Coordinator định tuyến nhiệm vụ."""
        return [c.topic for c in self.customer_request.claims]

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CaseInput:
        """HOW: Khởi tạo CaseInput với xác thực hợp lệ case_id."""
        case_id = str(data.get("case_id", "")).strip()
        if not CASE_ID_PATTERN.match(case_id):
            raise ValueError(f"Dữ liệu đầu vào chứa case_id không hợp lệ: {case_id}")
        return cls(
            case_id=case_id,
            opened_at=str(data.get("opened_at", "")),
            customer_request=CustomerRequest.from_dict(data.get("customer_request", {})),
            policy_version=str(data.get("policy_version", "EC_POLICY_V1")),
        )


# ==============================================================================
# 4. KẾ HOẠCH ĐIỀU TRA & GIAO THỨC CHUYỂN GIAO A2A (COORDINATION & HANDOFF)
# ==============================================================================

@dataclass
class InvestigationPlan:
    """WHAT: Bản kế hoạch hành động do CoordinatorAgent thiết lập sau khi phân tích khiếu nại.

    HOW: Xác định các miền dữ liệu cần gọi (needed_domains), các Specialist Agents
    được kích hoạt (assigned_agents), và giả thuyết sơ bộ (hypotheses).
    WHY: Thể hiện tư duy phối hợp có hệ thống (Workflow Score), tránh gọi bừa bãi các công cụ
    không liên quan làm lãng phí token và tài nguyên hệ thống.
    """

    case_id: str
    order_id: str
    claims: list[CustomerClaim] = field(default_factory=list)
    needed_domains: list[str] = field(default_factory=list)
    assigned_agents: list[str] = field(default_factory=list)
    hypotheses: list[str] = field(default_factory=list)
    strategy_notes: str = ""


@dataclass
class AgentHandoffMessage:
    """WHAT: Bản tin chuyển giao ngữ cảnh trực tiếp giữa các Agent (Agent-to-Agent Handoff).

    HOW: Mỗi khi Agent A hoàn thành một phần việc và chuyển giao cho Agent B,
    một Handoff Message được tạo ra, lưu lại lý do (decision_code), tóm tắt phát hiện (summary),
    bằng chứng vừa thu thập (new_evidence_refs) và các thông số bổ sung (attributes).
    WHY: Phục vụ trực tiếp cho việc phát sự kiện `handoff` trong trace log, giúp Scorer kiểm chứng
    chuỗi suy luận và sự cộng tác đa tác nhân thực sự.
    """

    sender: str
    receiver: str
    decision_code: str
    summary: str
    new_evidence_refs: list[str] = field(default_factory=list)
    attributes: dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat().replace("+00:00", "Z")
    )


# ==============================================================================
# 5. KẾT QUẢ ĐIỀU TRA CỦA CÁC SPECIALIST AGENTS (SPECIALIST FINDINGS)
# ==============================================================================

@dataclass
class OrderItemData:
    """WHAT: Dữ liệu chi tiết của từng mặt hàng nằm trong đơn hàng.

    HOW: Trích xuất từ kết quả trả về của công cụ `get_order_items` hoặc `get_items`.
    WHY: Cần thiết để xác định seller_id chịu trách nhiệm và tính toán tổng tiền hàng/phí ship.
    """

    order_id: str
    order_item_id: int | str
    product_id: str
    seller_id: str
    shipping_limit_date: str | None = None
    price: float = 0.0
    freight_value: float = 0.0

    @property
    def total_value(self) -> float:
        """WHAT: Tổng giá trị của item bao gồm giá gốc và phí vận chuyển."""
        return round(self.price + self.freight_value, 2)


@dataclass
class OrderFindings:
    """WHAT: Báo cáo phát hiện chuyên sâu về Đơn hàng do OrderAgent thu thập.

    HOW: Gọi các công cụ MCP thuộc domain `order` và `item`. Phân tích trạng thái đơn
    (delivered, canceled, unavailable,...), ngày mua, và danh sách các sản phẩm/người bán.
    WHY: Là dữ liệu nền tảng xác thực xem đơn hàng có bị hủy, không khả dụng hay không.
    """

    order_id: str
    status: str = "unknown"
    customer_id: str | None = None
    order_purchase_timestamp: str | None = None
    order_approved_at: str | None = None
    order_delivered_carrier_date: str | None = None
    order_delivered_customer_date: str | None = None
    order_estimated_delivery_date: str | None = None
    items: list[OrderItemData] = field(default_factory=list)
    seller_ids: list[str] = field(default_factory=list)
    item_ids: list[str] = field(default_factory=list)
    total_items_price: float = 0.0
    total_freight_value: float = 0.0
    total_order_value: float = 0.0
    evidence_refs: list[str] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict)

    @property
    def is_canceled(self) -> bool:
        """WHAT: Kiểm tra đơn hàng có rơi vào trạng thái hủy bỏ không."""
        return self.status.lower() == "canceled"

    @property
    def is_unavailable(self) -> bool:
        """WHAT: Kiểm tra đơn hàng có bị thông báo hết hàng/không cung ứng được không."""
        return self.status.lower() == "unavailable"

    @property
    def is_delivered(self) -> bool:
        """WHAT: Kiểm tra đơn hàng đã được giao thành công tới tay khách chưa."""
        return self.status.lower() == "delivered"


@dataclass
class PaymentLineData:
    """WHAT: Chi tiết từng giao dịch thanh toán con cấu thành nên đơn hàng.

    HOW: Chứa hình thức thanh toán (credit_card, boleto, voucher,...), số kỳ trả góp và số tiền.
    WHY: Cần thiết để phát hiện split payment hợp lệ hoặc giao dịch trùng lặp (duplicate charge).
    """

    order_id: str
    payment_sequential: int = 1
    payment_type: str = ""
    payment_installments: int = 1
    payment_value: float = 0.0
    payment_reference: str | None = None


@dataclass
class PaymentFindings:
    """WHAT: Báo cáo phát hiện chuyên sâu về Tài chính & Thanh toán do PaymentAgent thực hiện.

    HOW: Gọi các công cụ domain `payment` và `refund`. Tổng hợp toàn bộ số tiền khách đã trả,
    so sánh với giá trị đơn hàng, kiểm tra trạng thái lệnh hoàn tiền trong hệ thống.
    WHY: Giúp PolicyAgent xác định chính xác các mã lỗi: valid_split_payment, payment_mismatch,
    duplicate_charge, refund_pending, refund_failed.
    """

    order_id: str
    payment_lines: list[PaymentLineData] = field(default_factory=list)
    payment_types: list[str] = field(default_factory=list)
    payment_references: list[str] = field(default_factory=list)
    total_paid: float = 0.0
    is_split_payment: bool = False
    has_duplicate_charge: bool = False
    payment_mismatch: bool = False
    expected_order_value: float = 0.0
    difference_amount: float = 0.0
    refund_status: str | None = None
    refund_amount_processed: float = 0.0
    evidence_refs: list[str] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class ShipmentFindings:
    """WHAT: Báo cáo phát hiện chuyên sâu về Giao nhận & Vận tải do ShipmentAgent thực hiện.

    HOW: Gọi các công cụ domain `shipment`. Đối chiếu mốc thời gian giao bưu cục
    với `shipping_limit_date` của người bán, và mốc nhận hàng của khách với `estimated_delivery_date`.
    WHY: Phân định rạch ròi trách nhiệm giao trễ là do người bán (late_delivery_seller)
    hay do công ty vận chuyển (late_delivery_logistics).
    """

    order_id: str
    shipment_ids: list[str] = field(default_factory=list)
    carrier_partner: str | None = None
    shipping_limit_date: str | None = None
    delivered_carrier_date: str | None = None
    delivered_customer_date: str | None = None
    estimated_delivery_date: str | None = None
    is_delayed: bool = False
    delay_days: float = 0.0
    seller_delay: bool = False
    seller_delay_days: float = 0.0
    carrier_delay: bool = False
    carrier_delay_days: float = 0.0
    delivery_status: str = ""
    evidence_refs: list[str] = field(default_factory=list)
    raw_data: dict[str, Any] = field(default_factory=dict)


@dataclass
class SellerFindings:
    """WHAT: Thông tin người bán được trích xuất khi cần quy trách nhiệm."""

    seller_id: str
    city: str | None = None
    state: str | None = None
    zip_code_prefix: str | None = None
    evidence_refs: list[str] = field(default_factory=list)


@dataclass
class CustomerFindings:
    """WHAT: Thông tin khách hàng được trích xuất phục vụ kiểm tra danh tính và địa chỉ."""

    customer_id: str
    city: str | None = None
    state: str | None = None
    zip_code_prefix: str | None = None
    evidence_refs: list[str] = field(default_factory=list)


# ==============================================================================
# 6. MÔ HÌNH PHÁN QUYẾT CHÍNH SÁCH (POLICY DECISION MODELS)
# ==============================================================================

@dataclass
class Assessment:
    """WHAT: Kết quả phân loại cấp cao nhất của vụ việc.

    HOW: Gồm mã lỗi chính (primary_issue), trạng thái xử lý (case_status) và độ tin cậy (confidence).
    WHY: Khớp chính xác với khối `assessment` trong schema đầu ra.
    """

    primary_issue: PrimaryIssue | str
    case_status: CaseStatus | str
    confidence: float

    def __post_init__(self) -> None:
        """HOW: Ép kiểu sang Enum nếu truyền string và chặn khoảng tin cậy [0.0, 1.0]."""
        if isinstance(self.primary_issue, str):
            self.primary_issue = PrimaryIssue(self.primary_issue)
        if isinstance(self.case_status, str):
            self.case_status = CaseStatus(self.case_status)
        self.confidence = max(0.0, min(1.0, float(self.confidence)))

    def to_dict(self) -> dict[str, Any]:
        """HOW: Chuyển đổi sang dict nguyên thủy với string value cho JSON serialization."""
        return {
            "primary_issue": (
                self.primary_issue.value
                if isinstance(self.primary_issue, PrimaryIssue)
                else str(self.primary_issue)
            ),
            "case_status": (
                self.case_status.value
                if isinstance(self.case_status, CaseStatus)
                else str(self.case_status)
            ),
            "confidence": round(self.confidence, 4),
        }


@dataclass
class AffectedEntities:
    """WHAT: Danh sách các thực thể liên quan trực tiếp đến vụ việc.

    HOW: Mỗi trường là một tập hợp các mã định danh không trùng lặp (tối đa 20 phần tử).
    WHY: Khớp với khối `affected_entities` trong schema, phục vụ truy vết phạm vi ảnh hưởng.
    """

    order_ids: list[str] = field(default_factory=list)
    item_ids: list[str] = field(default_factory=list)
    seller_ids: list[str] = field(default_factory=list)
    payment_references: list[str] = field(default_factory=list)
    shipment_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """HOW: Khử trùng lặp và giới hạn tối đa 20 phần tử mỗi mảng theo quy định schema."""
        def clean_list(items: list[str]) -> list[str]:
            seen: set[str] = set()
            res: list[str] = []
            for item in items:
                val = str(item).strip()
                if val and val not in seen:
                    seen.add(val)
                    res.append(val[:128])
            return res[:20]

        return {
            "order_ids": clean_list(self.order_ids),
            "item_ids": clean_list(self.item_ids),
            "seller_ids": clean_list(self.seller_ids),
            "payment_references": clean_list(self.payment_references),
            "shipment_ids": clean_list(self.shipment_ids),
        }


@dataclass
class ClaimAssessment:
    """WHAT: Thẩm định chi tiết từng claim trong khiếu nại của khách hàng.

    HOW: Xác định verdict, confidence và đính kèm danh sách evidence_refs chứng minh.
    WHY: Thể hiện tính minh bạch, đáp ứng schema `claim_assessments` (tối đa 5 phần tử).
    """

    claim_id: str
    verdict: ClaimVerdict | str
    confidence: float
    evidence_refs: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        """HOW: Chuẩn hóa kiểu dữ liệu verdict và chặn khoảng confidence."""
        if isinstance(self.verdict, str):
            self.verdict = ClaimVerdict(self.verdict)
        self.confidence = max(0.0, min(1.0, float(self.confidence)))

    def to_dict(self) -> dict[str, Any]:
        """HOW: Lọc trùng evidence_refs, đảm bảo tối đa 30 phần tử theo quy định schema."""
        seen_refs: set[str] = set()
        clean_refs: list[str] = []
        for ref in self.evidence_refs:
            val = str(ref).strip()
            if val and val not in seen_refs:
                seen_refs.add(val)
                clean_refs.append(val)
        return {
            "claim_id": str(self.claim_id)[:64],
            "verdict": self.verdict.value if isinstance(self.verdict, ClaimVerdict) else str(self.verdict),
            "confidence": round(self.confidence, 4),
            "evidence_refs": clean_refs[:30],
        }


@dataclass
class RankedCause:
    """WHAT: Một nguyên nhân gốc rễ được xếp hạng theo thứ tự ưu tiên tác động."""

    cause_code: str
    rank: int

    def __post_init__(self) -> None:
        """HOW: Đảm bảo rank nằm trong khoảng từ 1 đến 5 theo schema."""
        self.rank = max(1, min(5, int(self.rank)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "cause_code": str(self.cause_code),
            "rank": self.rank,
        }


@dataclass
class ResponsibleParty:
    """WHAT: Chủ thể chịu trách nhiệm cho nguyên nhân gốc rễ."""

    party_type: PartyType | str
    party_id: str | None = None

    def __post_init__(self) -> None:
        if isinstance(self.party_type, str):
            self.party_type = PartyType(self.party_type)

    def to_dict(self) -> dict[str, Any]:
        return {
            "party_type": self.party_type.value if isinstance(self.party_type, PartyType) else str(self.party_type),
            "party_id": str(self.party_id)[:128] if self.party_id is not None else None,
        }


@dataclass
class RootCauseAnalysis:
    """WHAT: Kết quả phân tích nguyên nhân gốc rễ tổng hợp."""

    ranked_causes: list[RankedCause] = field(default_factory=list)
    responsible_parties: list[ResponsibleParty] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "ranked_causes": [c.to_dict() for c in self.ranked_causes[:5]],
            "responsible_parties": [p.to_dict() for p in self.responsible_parties[:5]],
        }


@dataclass
class RefundLine:
    """WHAT: Chi tiết từng khoản tiền cần bồi hoàn cho khách hàng hoặc khấu trừ đối tác."""

    reason_code: str
    amount_brl: float
    entity_id: str | None = None

    def __post_init__(self) -> None:
        self.amount_brl = max(0.0, round(float(self.amount_brl), 2))

    def to_dict(self) -> dict[str, Any]:
        return {
            "reason_code": str(self.reason_code)[:80],
            "amount_brl": self.amount_brl,
            "entity_id": str(self.entity_id)[:128] if self.entity_id is not None else None,
        }


@dataclass
class FinancialResolution:
    """WHAT: Nghị quyết tài chính chính thức của hồ sơ bồi hoàn.

    HOW: Chứa đơn vị tiền tệ 'BRL', tổng số tiền hoàn, và các dòng hoàn tiền chi tiết.
    WHY: Ràng buộc tính nhất quán sống còn: recommended_refund_brl BẮT BUỘC bằng tổng
    các dòng refund_lines (sai số = 0).
    """

    currency: str = CURRENCY_BRL
    recommended_refund_brl: float = 0.0
    refund_lines: list[RefundLine] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.recommended_refund_brl = max(0.0, round(float(self.recommended_refund_brl), 2))

    def verify_arithmetic_consistency(self) -> bool:
        """WHAT: Kiểm tra tính đúng đắn số học giữa tổng tiền và các dòng chi tiết."""
        calculated_sum = round(sum(line.amount_brl for line in self.refund_lines), 2)
        return abs(self.recommended_refund_brl - calculated_sum) < 0.001

    def to_dict(self) -> dict[str, Any]:
        return {
            "currency": CURRENCY_BRL,
            "recommended_refund_brl": self.recommended_refund_brl,
            "refund_lines": [line.to_dict() for line in self.refund_lines[:10]],
        }


@dataclass
class DataConflict:
    """WHAT: Ghi nhận sự mâu thuẫn giữa các nguồn dữ liệu và cách giải quyết."""

    field: str
    sources: list[str]
    selected_source: str | None
    resolution_code: str

    def to_dict(self) -> dict[str, Any]:
        """HOW: Lọc trùng danh sách nguồn sources (tối thiểu 2, tối đa 5 theo schema)."""
        seen_src: set[str] = set()
        clean_sources: list[str] = []
        for s in self.sources:
            val = str(s).strip()
            if val and val not in seen_src:
                seen_src.add(val)
                clean_sources.append(val[:80])
        return {
            "field": str(self.field)[:100],
            "sources": clean_sources[:5],
            "selected_source": str(self.selected_source)[:80] if self.selected_source is not None else None,
            "resolution_code": str(self.resolution_code)[:80],
        }


@dataclass
class PolicyDecision:
    """WHAT: Toàn bộ phán quyết nghiệp vụ do PolicyAgent tổng hợp sau khi đánh giá các phát hiện.

    HOW: Gồm assessment, thực thể ảnh hưởng, phân tích nguyên nhân, thẩm định claim,
    nghị quyết tài chính, danh sách hành động khắc phục, và các bằng chứng hỗ trợ.
    WHY: Là đối tượng trung gian chuyển giao từ PolicyAgent sang VerifierAgent để kiểm toán
    tính nhất quán và đóng gói thành JSON schema cuối cùng.
    """

    assessment: Assessment
    affected_entities: AffectedEntities
    root_cause_analysis: RootCauseAnalysis
    financial_resolution: FinancialResolution
    claim_assessments: list[ClaimAssessment] = field(default_factory=list)
    evidence_refs: list[str] = field(default_factory=list)
    data_conflicts: list[DataConflict] = field(default_factory=list)
    resolution_actions: list[str] = field(default_factory=list)


# ==============================================================================
# 7. TRẠNG THÁI ĐIỀU TRA TOÀN CỤC CỦA CASE (CASE INVESTIGATION STATE)
# ==============================================================================

@dataclass
class CaseInvestigationState:
    """WHAT: Kho lưu trữ trạng thái điều tra tập trung xuyên suốt vòng đời của Case.

    HOW:
    - Bắt đầu từ CoordinatorAgent (nhận CaseInput, lập Kế hoạch).
    - Được chuyển giao tuần tự hoặc song song qua các Specialist Agents để điền
      OrderFindings, PaymentFindings, ShipmentFindings.
    - Đi qua PolicyAgent để tính toán PolicyDecision.
    - Kết thúc tại VerifierAgent để đóng gói L3AOutputV2.
    WHY: Triển khai mô hình Blackboard/State-Accumulation cho phép các Agent đọc dữ liệu
    của nhau một cách minh bạch mà không bị ghi đè, bảo toàn 100% bằng chứng đã gọi.
    """

    case_input: CaseInput
    plan: InvestigationPlan | None = None
    order_findings: OrderFindings | None = None
    payment_findings: PaymentFindings | None = None
    shipment_findings: ShipmentFindings | None = None
    seller_findings: dict[str, SellerFindings] = field(default_factory=dict)
    customer_findings: CustomerFindings | None = None
    policy_decision: PolicyDecision | None = None
    final_output: dict[str, Any] | None = None

    # Quản lý nguồn gốc bằng chứng (Evidence Provenance Management)
    consumed_evidence_refs: set[str] = field(default_factory=set)
    evidence_by_domain: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    discovered_tools: list[str] = field(default_factory=list)
    handoff_history: list[AgentHandoffMessage] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def case_id(self) -> str:
        """WHAT: Mã case ID duy nhất của hồ sơ điều tra."""
        return self.case_input.case_id

    @property
    def order_id(self) -> str:
        """WHAT: Mã đơn hàng được khách hàng khiếu nại."""
        return self.case_input.order_id

    def record_consumed_evidence(
        self,
        domain: str,
        evidence_ref: str,
        data: dict[str, Any],
    ) -> None:
        """WHAT: Ghi nhận một bằng chứng thật thu được từ MCP Gateway vào kho trạng thái.

        HOW: Lưu ref vào tập hợp `consumed_evidence_refs` và lưu payload vào `evidence_by_domain`.
        WHY: Đảm bảo Verifier kiểm tra được 100% evidence xuất ra trong output đều là thật,
        không bao giờ bị lỗi 'unknown_evidence_ref' hay 'cross_scope_evidence_ref'.
        """
        if not evidence_ref or not EVIDENCE_REF_PATTERN.match(evidence_ref):
            raise ValueError(f"evidence_ref không đúng định dạng hợp lệ: {evidence_ref}")
        self.consumed_evidence_refs.add(evidence_ref)
        self.evidence_by_domain.setdefault(domain, []).append({
            "evidence_ref": evidence_ref,
            "data": data,
        })

    def record_handoff(
        self,
        sender: str,
        receiver: str,
        decision_code: str,
        summary: str,
        new_evidence_refs: list[str] | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> AgentHandoffMessage:
        """WHAT: Ghi nhận một bước chuyển giao công việc giữa hai Agent (A2A Handoff).

        HOW: Tạo một `AgentHandoffMessage` và thêm vào danh sách `handoff_history`.
        WHY: Giúp quy trình có thể kiểm toán lại toàn bộ đường đi của dữ liệu (Audit Trail).
        """
        msg = AgentHandoffMessage(
            sender=sender,
            receiver=receiver,
            decision_code=decision_code,
            summary=summary,
            new_evidence_refs=list(new_evidence_refs or []),
            attributes=dict(attributes or {}),
        )
        self.handoff_history.append(msg)
        return msg

    def extract_affected_entities(self) -> AffectedEntities:
        """WHAT: Tự động tổng hợp danh sách tất cả thực thể liên quan từ các phát hiện.

        HOW: Gom order_id, item_ids, seller_ids, payment_references, shipment_ids
        từ OrderFindings, PaymentFindings, ShipmentFindings.
        WHY: Tiết kiệm công sức lặp lại code ở các Agent và đảm bảo không bỏ sót thực thể nào.
        """
        orders: list[str] = [self.order_id] if self.order_id else []
        items: list[str] = []
        sellers: list[str] = []
        payments: list[str] = []
        shipments: list[str] = []

        if self.order_findings:
            items.extend(self.order_findings.item_ids)
            sellers.extend(self.order_findings.seller_ids)
        if self.payment_findings:
            payments.extend(self.payment_findings.payment_references)
        if self.shipment_findings:
            shipments.extend(self.shipment_findings.shipment_ids)

        return AffectedEntities(
            order_ids=orders,
            item_ids=items,
            seller_ids=sellers,
            payment_references=payments,
            shipment_ids=shipments,
        )

    def is_evidence_provenanced(self, refs: list[str]) -> bool:
        """WHAT: Kiểm tra xem toàn bộ các ref được trích dẫn có thực sự đã được gọi và lưu không.

        HOW: So khớp tập hợp con `set(refs).issubset(self.consumed_evidence_refs)`.
        WHY: Chống ảo giác (Anti-Hallucination) tuyệt đối trước khi đóng gói output.
        """
        return set(refs).issubset(self.consumed_evidence_refs)


# ==============================================================================
# 8. MÔ HÌNH ĐẦU RA CHUẨN CỦA HỆ THỐNG (FINAL OUTPUT MODEL - L3A V2)
# ==============================================================================

@dataclass
class L3AOutputV2:
    """WHAT: Đối tượng dữ liệu đầu ra chính thức của bài toán K4-L3A.

    HOW: Tuân thủ cấu trúc 100% theo JSON Schema Draft 2020-12 trong file
    `contracts/schemas/l3a-output-v2.schema.json`.
    WHY: Mọi sai khác (thừa trường, thiếu trường, sai kiểu) sẽ kích hoạt Hard Gate
    `unscorable_schema` khiến toàn bộ case bị 0 điểm. Lớp này đảm bảo tính an toàn tối đa.
    """

    case_id: str
    assessment: Assessment
    affected_entities: AffectedEntities
    root_cause_analysis: RootCauseAnalysis
    evidence_refs: list[str]
    data_conflicts: list[DataConflict]
    financial_resolution: FinancialResolution
    resolution_actions: list[str]
    claim_assessments: list[ClaimAssessment] | None = None
    schema_version: str = OUTPUT_SCHEMA_VERSION

    @classmethod
    def from_decision(cls, case_id: str, decision: PolicyDecision) -> L3AOutputV2:
        """WHAT: Hàm chuyển đổi nhà máy (Factory Method) từ PolicyDecision sang L3AOutputV2.

        HOW: Đóng gói các thuộc tính tương ứng và gán schema_version chuẩn.
        WHY: Tạo điểm chuyển đổi sạch sẽ giữa logic nghiệp vụ (Policy) và định dạng xuất bản (Verifier).
        """
        return cls(
            case_id=case_id,
            assessment=decision.assessment,
            affected_entities=decision.affected_entities,
            claim_assessments=decision.claim_assessments if decision.claim_assessments else None,
            root_cause_analysis=decision.root_cause_analysis,
            evidence_refs=decision.evidence_refs,
            data_conflicts=decision.data_conflicts,
            financial_resolution=decision.financial_resolution,
            resolution_actions=decision.resolution_actions,
            schema_version=OUTPUT_SCHEMA_VERSION,
        )

    def validate_invariants(self, consumed_refs: set[str] | None = None) -> list[str]:
        """WHAT: Bộ kiểm tra bất biến nghiệp vụ và tính toàn vẹn trước khi xuất JSON.

        HOW: Kiểm tra các quy tắc:
        1. case_status == no_action => recommended_refund_brl == 0 và refund_lines rỗng.
        2. case_status == action_required => recommended_refund_brl == sum(lines.amount_brl).
        3. evidence_refs phải là tập con của consumed_refs từ MCP Gateway.
        4. Không trùng lặp hành động trong resolution_actions.
        5. Độ dài mảng tuân thủ giới hạn schema.
        WHY: Bắt lỗi sớm ngay tại VerifierAgent để tự sửa chữa (Self-Correction) trước khi
        lưu file ra đĩa.
        """
        violations: list[str] = []

        # 1. Kiểm tra case_id
        if not CASE_ID_PATTERN.match(self.case_id):
            violations.append(f"case_id không khớp định dạng chuẩn: {self.case_id}")

        # 2. Kiểm tra tính nhất quán số tiền và trạng thái
        status = self.assessment.case_status
        status_val = status.value if isinstance(status, CaseStatus) else str(status)
        refund_amount = self.financial_resolution.recommended_refund_brl
        lines = self.financial_resolution.refund_lines

        if status_val == CaseStatus.NO_ACTION.value:
            if refund_amount != 0.0:
                violations.append(f"case_status là no_action nhưng recommended_refund_brl = {refund_amount} (phải bằng 0)")
            if len(lines) > 0:
                violations.append(f"case_status là no_action nhưng refund_lines không rỗng (len={len(lines)})")
        elif status_val == CaseStatus.ACTION_REQUIRED.value:
            lines_sum = round(sum(l.amount_brl for l in lines), 2)
            if abs(refund_amount - lines_sum) > 0.001:
                violations.append(f"Tổng tiền hoàn ({refund_amount}) không khớp tổng refund_lines ({lines_sum})")

        # 3. Kiểm tra kiểm toán nguồn gốc bằng chứng (Evidence Provenance)
        if consumed_refs is not None:
            unprovenanced = set(self.evidence_refs) - consumed_refs
            if unprovenanced:
                violations.append(f"Phát hiện evidence_refs không có nguồn gốc trong MCP Gateway: {unprovenanced}")

        # 4. Kiểm tra độ dài và tính duy nhất của resolution_actions
        if len(self.resolution_actions) > 8:
            violations.append(f"resolution_actions vượt quá giới hạn 8 phần tử: {len(self.resolution_actions)}")
        if len(self.resolution_actions) != len(set(self.resolution_actions)):
            violations.append("resolution_actions chứa phần tử trùng lặp")

        return violations

    def to_dict(self) -> dict[str, Any]:
        """WHAT: Chuyển đổi toàn bộ đối tượng thành dictionary thuần chuẩn JSON Schema.

        HOW:
        - Sử dụng các hàm to_dict() con đã được khử trùng lặp và giới hạn số lượng.
        - Khử trùng lặp `evidence_refs` và giới hạn tối đa 30 phần tử.
        - Khử trùng lặp `resolution_actions` và giới hạn tối đa 8 phần tử.
        - Xử lý `claim_assessments` (bỏ qua nếu rỗng hoặc None).
        - Đảm bảo `schema_version` và `case_id` luôn đứng đầu.
        WHY: Đảm bảo `contracts.validate_output(output)` luôn vượt qua 100% không có ngoại lệ.
        """
        # Làm sạch evidence_refs: khử trùng lặp, giữ thứ tự, tối đa 30 phần tử
        seen_refs: set[str] = set()
        clean_evidence_refs: list[str] = []
        for ref in self.evidence_refs:
            r = str(ref).strip()
            if r and EVIDENCE_REF_PATTERN.match(r) and r not in seen_refs:
                seen_refs.add(r)
                clean_evidence_refs.append(r)
        clean_evidence_refs = clean_evidence_refs[:30]

        # Làm sạch resolution_actions: khử trùng lặp, giữ thứ tự, tối đa 8 phần tử
        seen_actions: set[str] = set()
        clean_actions: list[str] = []
        for action in self.resolution_actions:
            act = str(action).strip()
            if act and act not in seen_actions:
                seen_actions.add(act)
                clean_actions.append(act[:80])
        clean_actions = clean_actions[:8]

        # Lọc data_conflicts hợp lệ (tối thiểu 2 nguồn theo schema)
        valid_conflicts = [
            dc.to_dict()
            for dc in self.data_conflicts[:5]
            if len(dc.sources) >= 2
        ]

        result: dict[str, Any] = {
            "schema_version": OUTPUT_SCHEMA_VERSION,
            "case_id": self.case_id,
            "assessment": self.assessment.to_dict(),
            "affected_entities": self.affected_entities.to_dict(),
            "root_cause_analysis": self.root_cause_analysis.to_dict(),
            "evidence_refs": clean_evidence_refs,
            "data_conflicts": valid_conflicts,
            "financial_resolution": self.financial_resolution.to_dict(),
            "resolution_actions": clean_actions,
        }

        # claim_assessments là trường tùy chọn nhưng nếu có phải tuân thủ schema (tối đa 5)
        if self.claim_assessments is not None and len(self.claim_assessments) > 0:
            result["claim_assessments"] = [ca.to_dict() for ca in self.claim_assessments[:5]]

        return result
