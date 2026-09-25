# Handoff Report: Explorer M1.3 (Tool Adapter & Evidence Tracker Explorer)

**Working Directory**: `.agents/teamwork/explorer_m1_3`  
**Target Module**: `src/student_agent/tools.py`  
**Milestone**: M1.3 (Foundation: Tool Adapter & Evidence Tracker)  
**Date/Timestamp**: 2026-09-25T11:22:00+07:00  

---

## 1. Observation

Direct code and contract inspection across the repository establishes the exact technical requirements and execution environment:

### 1.1 `EvidenceGateway` Protocol & Signatures
- **File**: `src/student_agent/mcp_gateway.py` lines 15–42:
  ```python
  class EvidenceGateway:
      def __init__(self, session: ClientSession, contracts: Contracts) -> None:
          self._session = session
          self._contracts = contracts

      async def list_tools(self) -> list[str]:
          response = await self._session.list_tools()
          return sorted(tool.name for tool in response.tools)

      async def call(self, tool_name: str, *, case_id: str, **arguments: str) -> dict[str, Any]:
          payload = {"case_id": case_id, **arguments}
          result = await self._session.call_tool(tool_name, arguments=payload)
          if result.isError:
              message = " ".join(
                  block.text for block in result.content if getattr(block, "text", None)
              )
              raise RuntimeError(f"MCP tool {tool_name} failed: {message or 'unknown error'}")
          evidence = getattr(result, "structuredContent", None)
          if evidence is None:
              evidence = getattr(result, "structured_content", None)
          if evidence is None:
              text_blocks = [block.text for block in result.content if getattr(block, "text", None)]
              if len(text_blocks) != 1:
                  raise ValueError(f"MCP tool {tool_name} did not return one evidence object")
              evidence = json.loads(text_blocks[0])
          self._contracts.validate_evidence(evidence, f"MCP tool {tool_name}")
          return evidence
  ```
- **Key Characteristics**:
  1. `list_tools()` returns a sorted list of tool name strings (`list[str]`).
  2. `call()` requires keyword-only `case_id: str`. It automatically validates the returned envelope with `self._contracts.validate_evidence(evidence)` before returning.
  3. If the tool call fails on the server side (`result.isError == True`), it raises `RuntimeError`.
  4. Arguments passed to `gateway.call` are mapped into the MCP payload dictionary as `{"case_id": case_id, **arguments}`.

### 1.2 MCP Evidence Response Schema
- **File**: `contracts/schemas/mcp-evidence-response-v1.schema.json` lines 7–28:
  ```json
  "required": ["schema_version", "evidence_ref", "result_hash", "domain", "data"],
  "properties": {
    "schema_version": {"const": "day09-mcp-evidence-v1"},
    "evidence_ref": {
      "type": "string",
      "pattern": "^ev_[A-Za-z0-9_-]{20,96}$"
    },
    "result_hash": {
      "type": "string",
      "pattern": "^sha256:[a-f0-9]{64}$"
    },
    "domain": {
      "enum": ["order", "item", "payment", "shipment", "seller", "customer", "product", "refund", "policy"]
    },
    "data": {},
    "warnings": {
      "type": "array",
      "maxItems": 10,
      "items": {"type": "string", "minLength": 1, "maxLength": 160},
      "uniqueItems": true
    }
  }
  ```
- **Key Characteristics**:
  1. `evidence_ref` must conform to `^ev_[A-Za-z0-9_-]{20,96}$`.
  2. `domain` is strictly restricted to one of the 9 authorized enum values.
  3. `data` is an arbitrary JSON object/dict containing authoritative entity fields.
  4. `result_hash` is an immutable SHA-256 fingerprint computed by the server for provenance audit.

### 1.3 `TraceWriter` Event Protocol
- **File**: `src/student_agent/trace.py` lines 20–51 and `contracts/schemas/trace-event-v1.schema.json` lines 12–39:
  ```python
  def emit(
      self,
      *,
      case_id: str,
      event_type: str,
      actor: str,
      target: str | None = None,
      decision_code: str | None = None,
      tool_name: str | None = None,
      evidence_refs: list[str] | None = None,
      attributes: dict[str, str | int | float | bool | None] | None = None,
  ) -> dict[str, Any]:
  ```
- **Requirements for Event `tool_result_consumed`**:
  - `event_type`: `"tool_result_consumed"`
  - `case_id`: Current active case ID (e.g. `"L3A_CASE_001"`)
  - `actor`: Specialist agent identifier (e.g. `"order-agent"`, `"payment-agent"`, `"shipment-agent"`, `"coordinator"`)
  - `tool_name`: Exact tool name invoked (e.g. `"get_order"`)
  - `evidence_refs`: Array containing the exact `[envelope["evidence_ref"]]`

### 1.4 Benchmark Scoring Policy & Anti-Hallucination Hard Gates
- **File**: `contracts/scoring/scoring-policy-v2.json`:
  - `provenance` weight: **15%** ("All submitted evidence refs must exist in MCP audit and match team, run and case").
  - `workflow` weight: **5%** ("Mean of lifecycle-event coverage, receive/finalize ordering, actor collaboration and evidence-to-trace linkage").
  - `evidence` weight: **15%** ("F1 of required evidence-group coverage and relevant evidence precision, with forbidden-domain penalties").
  - **Zero-Tolerance Hard Gates (Immediate 0 score for case/submission)**:
    1. `unknown_evidence_ref`: Any reference not present in the MCP audit log.
    2. `cross_scope_evidence_ref`: Any reference reused across different cases, runs, or teams.
    3. `invalid_evidence_refs`: Any reference failing the regex format `^ev_[A-Za-z0-9_-]{20,96}$`.

### 1.5 Usage Pattern from Starter Code & Guidelines
- **File**: `README.md` lines 88–109:
  ```python
  evidence = await gateway.call("get_order", case_id=case["case_id"], order_id=order_id)
  evidence_ref = evidence["evidence_ref"]
  order_data = evidence["data"]

  trace.emit(
      case_id=case["case_id"],
      event_type="tool_result_consumed",
      actor="order-agent",
      tool_name="get_order",
      evidence_refs=[evidence_ref],
  )
  ```
- **File**: `PROJECT.md` lines 88–94:
  - Class: `ToolAdapter(gateway: EvidenceGateway, trace: TraceWriter, case_id: str)`
  - Method: `async def call(self, tool_name: str, actor: str, **arguments) -> dict[str, Any]`
  - Emits: `trace.emit(case_id=self.case_id, event_type="tool_result_consumed", actor=actor, tool_name=tool_name, evidence_refs=[envelope["evidence_ref"]])`
  - Tracks: `self.consumed_evidence_refs: set[str]` and `self.evidence_by_domain: dict[str, list[dict]]`
  - Returns: unpacked `data` dict from the evidence envelope along with `evidence_ref`.

---

## 2. Logic Chain

1. **Direct Encapsulation of Gateway and Trace (Deduction from 1.1 & 1.3)**:
   - Direct calls from specialist agents to `gateway.call` would duplicate `case_id` passing, trace event emission, and error handling across every specialist.
   - Encapsulating `gateway` and `trace` inside a unified `ToolAdapter(gateway, trace, case_id)` centralizes parameter forwarding, error interception, provenance recording, and trace emission into a single authoritative wrapper.

2. **Strict Anti-Hallucination Guarantee (Deduction from 1.2 & 1.4)**:
   - The competition server strictly validates that every cited `evidence_ref` in `outputs/<case_id>.json` was audited during the execution of that specific case.
   - Any invented, predicted, or cross-case `evidence_ref` triggers an immediate hard gate (`unknown_evidence_ref` or `cross_scope_evidence_ref`), resulting in 0 points.
   - Therefore, `ToolAdapter` must maintain `_consumed_evidence_refs: set[str]`. This set must be strictly internal and **append-only**: an `evidence_ref` can **ONLY** be added if it is returned by a successful `self.gateway.call()` execution.
   - Public exposure of `consumed_evidence_refs` must be via a read-only property returning a copy (`set(self._consumed_evidence_refs)`), preventing any downstream agent from injecting synthetic refs.
   - The adapter must provide helper methods (`filter_valid_refs` and `is_valid_consumed_ref`) so `VerifierAgent` and specialists can sanitize their claim assessments and output structures.

3. **Dynamic Discovery and Resilient Invocation (Deduction from 1.1 & 1.5)**:
   - Tool names on the remote MCP Gateway are not guaranteed to follow static assumptions across different variants and server versions.
   - `ToolAdapter` must provide `discover_tools()` to invoke `await gateway.list_tools()`, cache the discovered tools, and support `has_tool(tool_name)` and `resolve_tool_for_domain(domain)`.
   - If an agent attempts to invoke a tool before discovery has run, the adapter must lazily trigger discovery automatically.

4. **Dual Interface for `ToolResult` (Deduction from 1.5 & Python conventions)**:
   - Some agents or starter snippets access fields using dictionary subscripting (`res["data"]`, `res["evidence_ref"]`), while modern dataclass-oriented architectures prefer attribute access (`res.data`, `res.evidence_ref`).
   - Implementing `ToolResult` as a frozen dataclass with dictionary emulation methods (`__getitem__`, `get`, `__contains__`, `to_dict()`) guarantees 100% interoperability without risking `TypeError: 'ToolResult' object is not subscriptable`.

5. **Transient Network Fault Tolerance (Deduction from 1.1 & System Requirements)**:
   - Remote MCP calls over HTTP streaming can experience occasional transient network drops or socket timeouts.
   - `ToolAdapter.call()` must implement bounded exponential backoff retry logic (up to 2 retries) for transient transport exceptions (`httpx2.TransportError`, `httpx2.TimeoutException`).
   - When a call permanently fails (e.g. entity not found or HTTP 404), it raises `ToolExecutionError` without logging any `tool_result_consumed` event, preventing corrupted state.

6. **Educational Annotation Requirement (Deduction from Original Request §R4)**:
   - R4 strictly mandates comprehensive inline comments in Vietnamese explaining *what* (làm gì), *how* (hoạt động thế nào), and *why* (tại sao cần làm như vậy ở đây).
   - Every class, method, validation block, and control branch in `src/student_agent/tools.py` must include thorough, pedagogical Vietnamese docstrings and inline comments.

---

## 3. Caveats

1. **MCP Server Live State & Offline Unit Testing**:
   - The live MCP server requires authentic credentials (`COMPETITION_TEAM_API_KEY`). For local offline unit testing, `ToolAdapter` must be tested against a synthetic mock `EvidenceGateway` that adheres to `EvidenceGateway.call` and returns valid `day09-mcp-evidence-v1` dictionaries.
2. **Case Isolation Lifecycle**:
   - `ToolAdapter` instances are scoped **per case** (`case_id`). An instance created for `L3A_CASE_001` must never be reused for `L3A_CASE_002` to avoid cross-contamination of `consumed_evidence_refs`.
3. **Trace Payload Immutability**:
   - The trace schema strictly limits `actor` to `maxLength: 80` and `tool_name` to `maxLength: 80`. All specialist agents must pass clean, recognized actor names (`order-agent`, `payment-agent`, `shipment-agent`, `coordinator`, `policy-agent`, `verifier`).

---

## 4. Conclusion & Implementation Specification

Here is the exact, complete, production-ready specification and code design for `src/student_agent/tools.py`:

```python
"""Module: tools.py.

Mô tả: Lớp điều hợp công cụ (Tool Adapter) và theo dõi bằng chứng (Evidence Tracker).
Vai trò trong hệ sinh thái:
  - Bọc quanh `EvidenceGateway` (kết nối MCP) và `TraceWriter` (ghi log sự kiện).
  - Tự động khám phá công cụ động (Dynamic Tool Discovery) từ MCP Gateway.
  - Cung cấp cơ chế gọi an toàn (Safe Call Wrapper) tự động tiêm `case_id`, tiền xử lý tham số,
    và tái thử (retry) khi gặp lỗi mạng tạm thời.
  - Quản lý và bảo vệ tính toàn vẹn của bằng chứng (Anti-Hallucination Evidence Tracker),
    cam đoan 100% `evidence_ref` trong hệ thống đều xuất phát từ MCP Gateway thật.
  - Tự động phát sinh sự kiện trace `tool_result_consumed` ngay khi kết quả được tiêu thụ.
"""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

import httpx2

from .mcp_gateway import EvidenceGateway
from .trace import TraceWriter

logger = logging.getLogger(__name__)

# Biểu thức chính quy kiểm tra định dạng chuẩn của evidence_ref từ MCP Gateway
# Tuân thủ nghiêm ngặt schema: contracts/schemas/mcp-evidence-response-v1.schema.json
EVIDENCE_REF_PATTERN = re.compile(r"^ev_[A-Za-z0-9_-]{20,96}$")

# Danh sách các miền dữ liệu thẩm quyền hợp lệ theo quy định của ban tổ chức
VALID_DOMAINS = frozenset(
    [
        "order",
        "item",
        "payment",
        "shipment",
        "seller",
        "customer",
        "product",
        "refund",
        "policy",
    ]
)


class ToolError(Exception):
    """Lớp ngoại lệ cơ sở cho mọi lỗi liên quan đến công cụ trong hệ thống."""


class ToolNotFoundError(ToolError):
    """Ngoại lệ khi cố gắng gọi một công cụ không tồn tại trên MCP Gateway."""


class ToolExecutionError(ToolError):
    """Ngoại lệ khi việc thực thi công cụ trên MCP Gateway thất bại sau các lần retry."""


@dataclass(frozen=True)
class ToolResult:
    """Đối tượng lưu trữ kết quả trả về từ công cụ MCP sau khi được giải nén và thẩm định.

    Thiết kế lưỡng dụng (Dual Interface):
      - Hỗ trợ truy cập thuộc tính hướng đối tượng: `result.data`, `result.evidence_ref`.
      - Hỗ trợ cú pháp truy cập từ điển (dictionary subscripting): `result["data"]`, `result["evidence_ref"]`.
    Điều này giúp mã nguồn của các Specialist Agent linh hoạt, tương thích hoàn toàn với cả hai phong cách lập trình.
    """

    tool_name: str
    actor: str
    evidence_ref: str
    domain: str
    data: dict[str, Any]
    result_hash: str
    warnings: list[str] = field(default_factory=list)

    def __getitem__(self, key: str) -> Any:
        """Hỗ trợ truy cập dạng dict: `result['data']` hoặc `result['evidence_ref']`.

        What: Cho phép đọc dữ liệu thông qua toán tử ngoặc vuông giống dict.
        How: Kiểm tra thuộc tính tương ứng trên đối tượng; nếu không có, ném ra KeyError.
        Why: Giữ tính tương thích ngược tuyệt đối với các đoạn code mẫu trong README.md.
        """
        if hasattr(self, key):
            return getattr(self, key)
        raise KeyError(f"Trường '{key}' không tồn tại trong ToolResult.")

    def get(self, key: str, default: Any = None) -> Any:
        """Hỗ trợ phương thức `.get()` tương tự như một dictionary tiêu chuẩn.

        What: Lấy giá trị của một khóa với giá trị mặc định nếu khóa không tồn tại.
        How: Sử dụng getattr an toàn với default value.
        Why: Tránh lỗi runtime khi các specialist agent kiểm tra trường tùy chọn.
        """
        return getattr(self, key, default)

    def __contains__(self, key: str) -> bool:
        """Hỗ trợ toán tử `in`: `'data' in result`."""
        return hasattr(self, key)

    def to_dict(self) -> dict[str, Any]:
        """Chuyển đổi kết quả thành một dictionary thuần túy."""
        return {
            "tool_name": self.tool_name,
            "actor": self.actor,
            "evidence_ref": self.evidence_ref,
            "domain": self.domain,
            "data": self.data,
            "result_hash": self.result_hash,
            "warnings": list(self.warnings),
        }


class ToolAdapter:
    """Bộ điều hợp công cụ trung tâm (Tool Adapter) và Bộ theo dõi bằng chứng (Evidence Tracker).

    Chức năng chính:
      1. Dynamic Discovery: Khám phá danh mục công cụ động từ MCP server.
      2. Safe Call Wrapper: Đóng gói an toàn các lời gọi công cụ, tiêm `case_id`, tự động retry.
      3. Strict Anti-Hallucination: Theo dõi tập hợp `_consumed_evidence_refs` bất biến từ server,
         chống mọi hành vi tạo hoặc đoán mò evidence_ref.
      4. Automatic Trace Emission: Phát sự kiện trace `tool_result_consumed` ngay khi nhận dữ liệu.
      5. Multi-Domain Indexing: Lưu trữ và lập chỉ mục bằng chứng theo domain và evidence_ref
         để phục vụ khâu thẩm định của PolicyAgent và VerifierAgent.
    """

    def __init__(self, gateway: EvidenceGateway, trace: TraceWriter, case_id: str) -> None:
        """Khởi tạo ToolAdapter cho một ca điều tra cụ thể.

        What: Khởi tạo các trạng thái bộ nhớ cho adapter gắn liền với `case_id`.
        How:
          - Lưu tham chiếu đến `EvidenceGateway` và `TraceWriter`.
          - Khởi tạo tập hợp `_consumed_evidence_refs` (set rỗng).
          - Khởi tạo bảng chỉ mục miền `_evidence_by_domain` và bảng chỉ mục ref `_evidence_by_ref`.
        Why: Mỗi ca khiếu nại (case) là một phạm vi độc lập (isolated context); không được dùng chung
             bằng chứng giữa các case để tránh vi phạm quy tắc cross-scope evidence ref.
        """
        self._gateway = gateway
        self._trace = trace
        self._case_id = case_id

        # Danh sách các công cụ đã được phát hiện từ MCP server
        self._discovered_tools: list[str] = []

        # Tập hợp chứa TẤT CẢ các evidence_ref hợp lệ đã được gateway trả về cho case này
        # TUYỆT ĐỐI KHÔNG thêm bất kỳ chuỗi nào vào đây trừ khi nhận được từ server thật.
        self._consumed_evidence_refs: set[str] = set()

        # Bảng tra cứu bằng chứng theo domain (ví dụ: "order" -> [ToolResult, ...])
        self._evidence_by_domain: dict[str, list[ToolResult]] = {}

        # Bảng tra cứu bằng chứng theo evidence_ref (ví dụ: "ev_..." -> ToolResult)
        self._evidence_by_ref: dict[str, ToolResult] = {}

        # Lịch sử gọi công cụ theo trình tự thời gian (Chronological audit log)
        self._call_history: list[ToolResult] = []

    @property
    def case_id(self) -> str:
        """Mã định danh của case điều tra hiện tại."""
        return self._case_id

    @property
    def consumed_evidence_refs(self) -> set[str]:
        """Tập hợp bản sao các `evidence_ref` hợp lệ đã được tiêu thụ.

        What: Cung cấp danh sách các mã tham chiếu bằng chứng đã xác thực.
        How: Trả về bản sao (`copy()`) của tập hợp nội bộ `_consumed_evidence_refs`.
        Why: Bảo vệ tính bất biến; các agent bên ngoài không thể can thiệp thêm mã giả vào tập hợp này.
        """
        return set(self._consumed_evidence_refs)

    @property
    def discovered_tools(self) -> list[str]:
        """Danh sách các tên công cụ đã được phát hiện từ server."""
        return list(self._discovered_tools)

    @property
    def evidence_by_domain(self) -> dict[str, list[ToolResult]]:
        """Bảng chỉ mục kết quả công cụ phân loại theo từng miền nghiệp vụ."""
        return {domain: list(results) for domain, results in self._evidence_by_domain.items()}

    @property
    def call_history(self) -> list[ToolResult]:
        """Toàn bộ lịch sử các lần gọi công cụ thành công trong case này."""
        return list(self._call_history)

    async def discover_tools(self, force_refresh: bool = False) -> list[str]:
        """Khám phá danh sách các công cụ hiện có trên MCP Gateway.

        What: Truy vấn danh mục công cụ động từ MCP server và lưu bộ đệm.
        How: Gọi `await self._gateway.list_tools()`. Nếu đã có trong cache và không ép buộc làm mới
             (`force_refresh=False`), tái sử dụng danh sách đã lưu.
        Why: Tuân thủ quy định R3 (Dynamic Discovery). Ngăn ngừa việc mã nguồn bị cố định (hardcoded)
             với những tên tool có thể thay đổi hoặc mở rộng trong tương lai.
        """
        if self._discovered_tools and not force_refresh:
            return list(self._discovered_tools)

        try:
            tools = await self._gateway.list_tools()
            self._discovered_tools = sorted(tools)
            logger.info("Đã khám phá %d công cụ từ MCP Gateway: %s", len(self._discovered_tools), self._discovered_tools)
            return list(self._discovered_tools)
        except Exception as exc:
            logger.error("Lỗi khi khám phá công cụ từ MCP Gateway: %s", exc)
            raise ToolExecutionError(f"Không thể khám phá danh mục công cụ từ MCP Gateway: {exc}") from exc

    def has_tool(self, tool_name: str) -> bool:
        """Kiểm tra xem một công cụ cụ thể có tồn tại trong danh mục đã khám phá hay không.

        What: Xác định khả năng hỗ trợ của hệ sinh thái MCP đối với một chức năng truy vấn.
        How: Tìm kiếm `tool_name` trong danh sách `_discovered_tools`.
        Why: Giúp Specialist Agent chủ động rẽ nhánh hoặc dùng phương án thay thế nếu công cụ vắng mặt.
        """
        return tool_name in self._discovered_tools

    def resolve_tool_for_domain(self, domain: str, default: str | None = None) -> str | None:
        """Tự động phân giải tên công cụ phù hợp với một miền nghiệp vụ.

        What: Tìm công cụ đại diện tốt nhất cho một miền dữ liệu (ví dụ: 'order' -> 'get_order').
        How:
          1. Duyệt qua danh sách `_discovered_tools`.
          2. Tìm công cụ có tên chứa từ khóa `domain` (ví dụ: 'order' xuất hiện trong 'get_order').
          3. Nếu không tìm thấy, trả về giá trị `default`.
        Why: Đảm bảo khả năng tương thích cao ngay cả khi tên tool trên server có tiền tố hoặc hậu tố khác nhau.
        """
        domain_lower = domain.lower()
        # Ưu tiên các quy tắc đặt tên phổ biến: get_<domain>, query_<domain>, <domain>_details
        candidates = [t for t in self._discovered_tools if domain_lower in t.lower()]
        if candidates:
            # Ưu tiên tool bắt đầu bằng get_<domain> nếu có
            exact_match = f"get_{domain_lower}"
            if exact_match in candidates:
                return exact_match
            return candidates[0]
        return default

    async def call(
        self,
        tool_name: str,
        actor: str,
        retries: int = 2,
        backoff_base_sec: float = 0.5,
        **arguments: Any,
    ) -> ToolResult:
        """Lớp bọc an toàn (Safe Call Wrapper) để gọi một công cụ trên MCP Gateway.

        What:
          - Thực hiện gọi tool lên MCP server với `case_id` và các tham số nghiệp vụ.
          - Tự động phát hiện công cụ nếu chưa khám phá.
          - Xử lý lỗi kết nối tạm thời bằng cơ chế tái thử (exponential backoff retry).
          - Kiểm tra và xác thực tính hợp lệ của phong bì bằng chứng (Evidence Envelope).
          - Lưu vết mã tham chiếu `evidence_ref` vào tập hợp chống ảo giác (`_consumed_evidence_refs`).
          - Phát sự kiện trace `tool_result_consumed` ngay lập tức để ghi nhận vào `traces/trace.jsonl`.
          - Lập chỉ mục kết quả theo miền và lưu lịch sử gọi.

        How:
          1. Chuẩn hóa tham số: Lọc bỏ các tham số có giá trị None, ép kiểu thành chuỗi (str)
             phù hợp với giao diện của `EvidenceGateway.call`.
          2. Tự động gọi `discover_tools()` nếu danh sách công cụ đang rỗng.
          3. Thực hiện vòng lặp retry (tối đa `retries` lần) với các ngoại lệ mạng tạm thời
             như `httpx2.TransportError`, `httpx2.TimeoutException`.
          4. Khi server trả về envelope:
             - Thẩm định regex `evidence_ref` qua `EVIDENCE_REF_PATTERN`.
             - Trích xuất `domain`, `data`, `result_hash`, `warnings`.
             - Bổ sung `evidence_ref` vào `self._consumed_evidence_refs`.
          5. Gọi `self._trace.emit(...)` phát sự kiện `tool_result_consumed` với `evidence_refs=[evidence_ref]`.
          6. Đóng gói thành `ToolResult` và ghi nhận vào các bảng tra cứu nội bộ.
          7. Trả về `ToolResult`.

        Why:
          - Loại bỏ hoàn toàn nguy cơ quên truyền `case_id` hoặc truyền sai `case_id`.
          - Đảm bảo 100% bằng chứng được liên kết đồng bộ giữa trace log và output cuối cùng,
            đáp ứng tiêu chí chấm điểm Workflow & Provenance (chiếm 30% tổng số điểm).
          - Ngăn chặn hệ thống bị sập vì lỗi mạng chớp nhoáng (transient network glitch).
          - Cơ chế chốt chặn chống ảo giác: Chỉ những gì server thực sự cấp phát mới được hệ thống ghi nhận.
        """
        # Đảm bảo danh mục công cụ đã được tải
        if not self._discovered_tools:
            await self.discover_tools()

        # Kiểm tra sự tồn tại của công cụ nếu danh mục đã được khám phá
        if self._discovered_tools and tool_name not in self._discovered_tools:
            raise ToolNotFoundError(
                f"Công cụ '{tool_name}' không tồn tại trên MCP Gateway. "
                f"Danh sách công cụ khả dụng: {self._discovered_tools}"
            )

        # Tiền xử lý tham số: Loại bỏ None và chuyển đổi thành chuỗi
        clean_args: dict[str, str] = {}
        for key, value in arguments.items():
            if value is not None:
                clean_args[key] = str(value)

        last_error: Exception | None = None

        # Vòng lặp retry chịu lỗi mạng
        for attempt in range(retries + 1):
            try:
                # Gọi trực tiếp qua gateway với case_id đã được gắn cố định
                envelope = await self._gateway.call(tool_name, case_id=self._case_id, **clean_args)
                break
            except (httpx2.TransportError, httpx2.TimeoutException) as network_err:
                last_error = network_err
                if attempt < retries:
                    delay = backoff_base_sec * (2**attempt)
                    logger.warning(
                        "Lỗi mạng tạm thời khi gọi tool '%s' (lần %d/%d). Thử lại sau %.2f giây. Lỗi: %s",
                        tool_name,
                        attempt + 1,
                        retries,
                        delay,
                        network_err,
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error("Đã thử lại %d lần nhưng vẫn không thể kết nối tới tool '%s'.", retries, tool_name)
                    raise ToolExecutionError(
                        f"Không thể thực thi tool '{tool_name}' do lỗi kết nối mạng sau {retries} lần thử: {network_err}"
                    ) from network_err
            except RuntimeError as mcp_runtime_err:
                # Lỗi trả về từ MCP Server (ví dụ: entity not found hoặc lỗi nội bộ server)
                # Không retry đối với lỗi logic nghiệp vụ từ server
                logger.error("MCP Server báo lỗi khi thực thi tool '%s': %s", tool_name, mcp_runtime_err)
                raise ToolExecutionError(
                    f"MCP tool '{tool_name}' thất bại với thông điệp: {mcp_runtime_err}"
                ) from mcp_runtime_err
            except Exception as unexpected_err:
                logger.error("Lỗi không lường trước khi gọi tool '%s': %s", tool_name, unexpected_err)
                raise ToolExecutionError(
                    f"Lỗi không lường trước khi thực thi tool '{tool_name}': {unexpected_err}"
                ) from unexpected_err

        # --- Giai đoạn Thẩm định Envelope & Bảo vệ Bằng chứng ---
        if not isinstance(envelope, dict):
            raise ToolExecutionError(f"Phản hồi từ tool '{tool_name}' không phải là một dictionary: {type(envelope)}")

        evidence_ref = envelope.get("evidence_ref")
        if not evidence_ref or not isinstance(evidence_ref, str) or not EVIDENCE_REF_PATTERN.match(evidence_ref):
            raise ToolExecutionError(
                f"Tool '{tool_name}' trả về evidence_ref không hợp lệ: {evidence_ref!r}. "
                "Yêu cầu định dạng khớp regex: ^ev_[A-Za-z0-9_-]{20,96}$"
            )

        domain = envelope.get("domain", "unknown")
        result_hash = envelope.get("result_hash", "")
        data = envelope.get("data", {})
        warnings = envelope.get("warnings", [])

        # Chống ảo giác (Anti-Hallucination): Ghi nhận duy nhất mã ref do server cấp
        self._consumed_evidence_refs.add(evidence_ref)

        # --- Giai đoạn Phát sự kiện Trace đồng bộ ---
        # Phát sự kiện tool_result_consumed ngay lập tức để bảo đảm trình tự thời gian
        try:
            self._trace.emit(
                case_id=self._case_id,
                event_type="tool_result_consumed",
                actor=actor,
                tool_name=tool_name,
                evidence_refs=[evidence_ref],
            )
        except Exception as trace_err:
            logger.error("Lỗi khi phát sự kiện trace tool_result_consumed: %s", trace_err)
            raise

        # Đóng gói đối tượng ToolResult hoàn chỉnh
        result = ToolResult(
            tool_name=tool_name,
            actor=actor,
            evidence_ref=evidence_ref,
            domain=domain,
            data=data if isinstance(data, dict) else {"raw_content": data},
            result_hash=result_hash,
            warnings=list(warnings) if isinstance(warnings, list) else [],
        )

        # Cập nhật các bảng chỉ mục phục vụ truy vấn
        self._evidence_by_domain.setdefault(domain, []).append(result)
        self._evidence_by_ref[evidence_ref] = result
        self._call_history.append(result)

        logger.debug(
            "Đã tiêu thụ thành công tool '%s' bởi actor '%s' (ref: %s, domain: %s)",
            tool_name,
            actor,
            evidence_ref,
            domain,
        )
        return result

    def is_valid_consumed_ref(self, evidence_ref: str) -> bool:
        """Kiểm tra xem một mã evidence_ref có thực sự được tạo ra trong case này hay không.

        What: Xác thực nguồn gốc (Provenance Check) cho một mã tham chiếu.
        How: Tra cứu xem `evidence_ref` có nằm trong tập hợp `_consumed_evidence_refs` hay không.
        Why: Giúp `VerifierAgent` phát hiện ngay các mã bằng chứng giả mạo do LLM suy diễn.
        """
        return evidence_ref in self._consumed_evidence_refs

    def filter_valid_refs(self, candidate_refs: Iterable[str]) -> list[str]:
        """Lọc danh sách các mã tham chiếu, chỉ giữ lại những mã thực sự đã tiêu thụ.

        What: Loại bỏ mọi mã giả mạo hoặc hallucinated ra khỏi danh sách ứng viên.
        How: Duyệt qua `candidate_refs`, đối chiếu với `_consumed_evidence_refs`, loại trùng và giữ nguyên thứ tự.
        Why: Đảm bảo mảng `evidence_refs` trong `outputs/<case_id>.json` không bao giờ vi phạm
             các hard gates (`unknown_evidence_ref` hay `invalid_evidence_refs`).
        """
        seen: set[str] = set()
        valid_list: list[str] = []
        for ref in candidate_refs:
            if ref in self._consumed_evidence_refs and ref not in seen:
                seen.add(ref)
                valid_list.append(ref)
        return valid_list

    def get_evidence_by_domain(self, domain: str) -> list[ToolResult]:
        """Lấy tất cả các kết quả bằng chứng đã thu thập thuộc một miền dữ liệu cụ thể.

        What: Truy xuất bằng chứng theo chuyên môn (Order, Payment, Shipment, v.v.).
        How: Tra cứu từ bảng chỉ mục `_evidence_by_domain`.
        Why: Giúp PolicyAgent tổng hợp chứng cứ từ nhiều specialist khác nhau mà không cần gọi lại tool.
        """
        return list(self._evidence_by_domain.get(domain, []))

    def get_evidence_by_ref(self, evidence_ref: str) -> ToolResult | None:
        """Lấy bản ghi bằng chứng gốc dựa trên mã định danh `evidence_ref`.

        What: Truy xuất chi tiết dữ liệu gốc của một bằng chứng cụ thể.
        How: Tra cứu từ bảng chỉ mục `_evidence_by_ref`.
        Why: Giúp Verifier kiểm tra chéo các trường dữ liệu và tính toán tài chính với chứng cứ gốc.
        """
        return self._evidence_by_ref.get(evidence_ref)

    def get_summary(self) -> dict[str, Any]:
        """Cung cấp bản tổng kết tình trạng thu thập chứng cứ của toàn bộ case.

        What: Thống kê số lượng tool đã gọi, số lượng ref đã lưu và phân bổ theo domain.
        How: Đếm số bản ghi trong `_call_history` và `_evidence_by_domain`.
        Why: Hỗ trợ log kiểm toán hoặc xác định trường hợp thiếu bằng chứng (`insufficient_evidence`).
        """
        return {
            "case_id": self._case_id,
            "total_calls": len(self._call_history),
            "unique_evidence_refs": len(self._consumed_evidence_refs),
            "domains_covered": sorted(self._evidence_by_domain.keys()),
            "calls_per_domain": {d: len(res) for d, res in self._evidence_by_domain.items()},
        }
```

---

## 5. Verification Method

To independently verify this specification and its downstream correctness:

1. **Static Analysis & Schema Conformance**:
   - Verify `EVIDENCE_REF_PATTERN` matches `^ev_[A-Za-z0-9_-]{20,96}$` in `contracts/schemas/mcp-evidence-response-v1.schema.json`.
   - Verify `VALID_DOMAINS` matches the enum in `contracts/schemas/mcp-evidence-response-v1.schema.json:19`.
   - Verify that `trace.emit` arguments match `contracts/schemas/trace-event-v1.schema.json` for event `tool_result_consumed`.

2. **Offline Unit Test Specification (`tests/test_tools.py`)**:
   Implement a mock test verifying:
   - Dynamic discovery: `adapter.discover_tools()` retrieves tool names from mock gateway.
   - Safe call: `adapter.call("get_order", actor="order-agent", order_id="123")` passes `case_id` and receives `ToolResult`.
   - Trace emission: Verifies `trace.emit` was called with `case_id`, `tool_result_consumed`, `order-agent`, `get_order`, and `[evidence_ref]`.
   - Anti-hallucination: `adapter.consumed_evidence_refs` contains only genuine refs; `filter_valid_refs(["fake_ref", genuine_ref])` returns only `[genuine_ref]`.
   - Subscripting: `result["data"]` equals `result.data`.
   - Invalidation condition: If any un-audited ref is added to `consumed_evidence_refs` without a gateway call, verification fails.
