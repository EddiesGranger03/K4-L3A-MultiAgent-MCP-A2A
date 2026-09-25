# Handoff Report: Explorer Survey 2 (MCP Gateway & Evidence Ref Explorer)

**Working Directory**: `.agents/teamwork/explorer_survey_2`  
**Target Milestone**: MCP Gateway, Tool Discovery & Evidence Ref Mechanics  
**Date/Timestamp**: 2026-09-25T04:15:00Z  

---

## 1. Observation

Direct inspection of the repository files, public contracts, schemas, and source code yields the following exact findings:

### 1.1 MCP Client Architecture & Connection Mechanism
- **File**: `src/student_agent/mcp_gateway.py` (lines 8–18, 44–57)
  ```python
  import httpx2
  from mcp import ClientSession
  from mcp.client.streamable_http import streamable_http_client
  from .contracts import Contracts

  class EvidenceGateway:
      def __init__(self, session: ClientSession, contracts: Contracts) -> None:
          self._session = session
          self._contracts = contracts

  @asynccontextmanager
  async def connect_gateway(
      endpoint: str, team_api_key: str, contracts: Contracts
  ) -> AsyncIterator[EvidenceGateway]:
      headers = {"Authorization": f"Bearer {team_api_key}"}
      timeout = httpx2.Timeout(300.0, connect=30.0, write=30.0, pool=30.0)
      async with (
          httpx2.AsyncClient(headers=headers, timeout=timeout) as http_client,
          streamable_http_client(endpoint, http_client=http_client) as (read_stream, write_stream),
          ClientSession(read_stream, write_stream) as session,
      ):
          await session.initialize()
          yield EvidenceGateway(session, contracts)
  ```
  - **Transport**: `mcp.client.streamable_http.streamable_http_client` over `httpx2.AsyncClient`.
  - **Authentication**: HTTP Header `Authorization: Bearer <COMPETITION_TEAM_API_KEY>`.
  - **Endpoint Configuration**: Loaded from `.env` via `src/student_agent/config.py`:
    - `MCP_ENDPOINT`: e.g. `https://day09-competition.34-142-201-239.sslip.io/mcp` or `http://127.0.0.1:8001/mcp`.
    - `COMPETITION_TEAM_API_KEY`: format `^sk-team-[A-Za-z0-9_-]{16,128}$`.
  - **Timeout Settings**: `300.0`s read/write timeout, `30.0`s connect/pool timeout.

### 1.2 Tool Discovery Mechanism
- **File**: `src/student_agent/mcp_gateway.py` (lines 20–22)
  ```python
  async def list_tools(self) -> list[str]:
      response = await self._session.list_tools()
      return sorted(tool.name for tool in response.tools)
  ```
  - `response` is an instance of `mcp.types.ListToolsResult`.
  - Each item in `response.tools` is an `mcp.types.Tool` object containing:
    - `tool.name`: Name of the tool (e.g., `"get_order"`).
    - `tool.description`: Description of what the tool queries.
    - `tool.input_schema` / `tool.inputSchema`: JSON Schema object detailing parameter types and required fields.
- **CLI Discovery Command**:
  - `day09 mcp-tools` executes `_show_tools(root)` in `src/student_agent/cli.py:22-28`:
    ```python
    async def _show_tools(root: Path) -> None:
        settings = Settings.load(root)
        contracts = Contracts(root / "contracts" / "schemas")
        async with connect_gateway(settings.mcp_endpoint, settings.team_api_key, contracts) as gateway:
            for tool in await gateway.list_tools():
                print(tool)
    ```
- **Runtime Discovery Check**:
  - In `src/student_agent/cli.py` (lines 43–46):
    ```python
    async with connect_gateway(settings.mcp_endpoint, settings.team_api_key, contracts) as gateway:
        discovered_tools = await gateway.list_tools()
        if not discovered_tools:
            raise RuntimeError("MCP Gateway returned no tools")
    ```

### 1.3 Tool Invocation & Argument Protocol
- **File**: `src/student_agent/mcp_gateway.py` (lines 24–41)
  ```python
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
  - **Mandatory Argument**: Every tool call MUST supply `case_id` as a keyword argument.
  - **Error Handling**: When `result.isError` is true, extracts text error content and raises `RuntimeError`.
  - **Response Extraction**: Tries `result.structuredContent`, then `result.structured_content`, and finally parses JSON from `result.content[0].text`.
  - **Contract Validation**: Immediately executes `self._contracts.validate_evidence(evidence, f"MCP tool {tool_name}")` which verifies the response against `mcp-evidence-response-v1.schema.json`.

### 1.4 Authoritative Tool Domains & Schemas
- **Schema File**: `contracts/schemas/mcp-evidence-response-v1.schema.json`
  ```json
  {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "$id": "https://day09.vinaction.local/contracts/mcp-evidence-response-v1.schema.json",
    "title": "Day09 MCP evidence response V1",
    "type": "object",
    "additionalProperties": false,
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
  }
  ```
- **Authoritative Domains & Expected Tool Capabilities**:
  Based on `mcp-evidence-response-v1.schema.json`, `README.md:78`, `ARCHITECTURE.md:20-23`, and the Olist E-Commerce schema:
  1. **Domain `order`** (e.g. `get_order`):
     - Parameters: `case_id: str, order_id: str`
     - Returns: order status (`delivered`, `canceled`, `unavailable`, `shipped`, `invoiced`, `processing`), customer_id, timestamps (`order_purchase_timestamp`, `order_approved_at`, `order_delivered_carrier_date`, `order_delivered_customer_date`, `order_estimated_delivery_date`).
  2. **Domain `item`** (e.g. `get_order_items` / `get_item`):
     - Parameters: `case_id: str, order_id: str`
     - Returns: item list with `order_item_id`, `product_id`, `seller_id`, `shipping_limit_date`, `price`, `freight_value`.
  3. **Domain `payment`** (e.g. `get_order_payments` / `get_payment`):
     - Parameters: `case_id: str, order_id: str`
     - Returns: payment lines with `payment_sequential`, `payment_type` (`credit_card`, `boleto`, `voucher`, `debit_card`), `payment_installments`, `payment_value`.
  4. **Domain `shipment`** (e.g. `get_order_shipments` / `get_shipment`):
     - Parameters: `case_id: str, order_id: str`
     - Returns: carrier tracking, carrier partner name, delivery attempt timestamps, delay notifications.
  5. **Domain `seller`** (e.g. `get_seller`):
     - Parameters: `case_id: str, seller_id: str`
     - Returns: seller location (`zip_code_prefix`, `city`, `state`), seller fulfillment rating/history.
  6. **Domain `customer`** (e.g. `get_customer`):
     - Parameters: `case_id: str, customer_id: str`
     - Returns: customer unique ID, zip code, city, state.
  7. **Domain `product`** (e.g. `get_product`):
     - Parameters: `case_id: str, product_id: str`
     - Returns: product category, dimensions, weight.
  8. **Domain `refund`** (e.g. `get_refund` / `get_order_refunds`):
     - Parameters: `case_id: str, order_id: str`
     - Returns: refund status, refund reference, processed refund amount, refund timestamp.
  9. **Domain `policy`** (e.g. `get_policy`):
     - Parameters: `case_id: str, policy_id: str` (e.g., `policy_version: "EC_POLICY_V1"`)
     - Returns: authoritative policy terms, claim conditions, refund eligibility criteria, delay thresholds.

### 1.5 Evidence Ref Lifecycle, Trace Logging & Scoring Contracts
- **Format**: Regex `^ev_[A-Za-z0-9_-]{20,96}$`.
- **Trace Event Requirement**: `contracts/schemas/trace-event-v1.schema.json` lines 12–22, 28–33:
  - Event `tool_result_consumed`:
    ```json
    {
      "schema_version": "day09-trace-event-v1",
      "event_id": "evt_...",
      "case_id": "L3A_CASE_001",
      "event_type": "tool_result_consumed",
      "occurred_at": "2026-09-25T04:15:00Z",
      "actor": "order-agent",
      "tool_name": "get_order",
      "evidence_refs": ["ev_0123456789abcdef0123456789"]
    }
    ```
- **Output Schema Requirement**: `contracts/schemas/l3a-output-v2.schema.json`:
  - Output requires top-level `evidence_refs`: Array (max 30, unique) of `^ev_[A-Za-z0-9_-]{20,96}$`.
  - Claim assessments require `evidence_refs`: Array of `^ev_[A-Za-z0-9_-]{20,96}$` in each item of `claim_assessments`.
- **Scoring Invariants & Hard Gates**: `contracts/scoring/scoring-policy-v2.json`:
  - `provenance` (15%): "All submitted evidence refs must exist in MCP audit and match team, run and case."
  - `evidence` (15%): "F1 of required evidence-group coverage and relevant evidence precision, with forbidden-domain penalties."
  - `workflow` (5%): Requires evidence-to-trace linkage (every submitted evidence ref must appear in a `tool_result_consumed` event in `trace.jsonl`).
  - **Zero-Tolerance Hard Gates**:
    1. `invalid_evidence_refs`: Any non-matching regex.
    2. `unknown_evidence_ref`: Any ref not in the MCP server audit table.
    3. `cross_scope_evidence_ref`: Any ref generated for another case, run, or team.
    4. `missing_required_evidence`: Unsubstantiated claims.

### 1.6 Mock Servers, Fixtures & Testing State
- Direct examination of `tests/`:
  - `tests/test_starter.py`: Only unit tests `load_case_set` and `build_manifest` with in-memory temporary fixtures (`tmp_path`). Contains no mock MCP server.
  - `tests/test_release_safety.py`: Confirms no competition payloads, reference outputs, oracles, or `mcp-access.json` files are committed to the repo.
  - No existing mock MCP server is packaged in the starter repository.

---

## 2. Logic Chain

1. **Premise**: In `src/student_agent/mcp_gateway.py`, `EvidenceGateway.call` is the sole entry point for interacting with the MCP server.
2. **Premise**: Every tool call sends `{"case_id": case_id, **arguments}` and receives an evidence envelope conforming to `day09-mcp-evidence-v1`.
3. **Inference (Audit Provenance Binding)**:
   - Because the remote MCP Gateway logs each call with `case_id`, `team_api_key`, `timestamp`, and `result_hash`, any `evidence_ref` presented in `outputs/<case_id>.json` must have been returned by a live call made during that specific case execution.
   - Fabricating synthetic or static `evidence_ref` values (e.g. `ev_placeholder1234567890`) directly triggers the `unknown_evidence_ref` hard gate on the server scorer, resulting in a score of **0**.
4. **Inference (Cross-Case Isolation)**:
   - If two cases involve the same order or seller, an agent cannot cache and reuse an `evidence_ref` across cases. Reusing an evidence ref from Case A in Case B triggers the `cross_scope_evidence_ref` hard gate, yielding a score of **0**.
5. **Inference (Evidence-to-Trace Linkage)**:
   - `scoring-policy-v2.json` specifies: `"workflow": "Mean of lifecycle-event coverage, receive/finalize ordering, actor collaboration and evidence-to-trace linkage."`
   - Therefore, whenever an agent receives evidence, it must immediately emit `trace.emit(case_id=case_id, event_type="tool_result_consumed", actor=actor_name, tool_name=tool_name, evidence_refs=[evidence_ref])`.
   - The verifier must check that `set(output["evidence_refs"]).issubset(set(all_consumed_evidence_refs_for_case))`.
6. **Inference (Tool Discovery Dynamic Adaptation)**:
   - `cli.py` mandates `discovered_tools = await gateway.list_tools()`.
   - Tool names on the remote server may be `get_order` or `get_order_items`, etc. An intelligent specialist agent dispatcher should inspect `await gateway.list_tools()` or `await gateway._session.list_tools()` at initialization time and dynamically route domain queries to the matching tool names.
7. **Inference (Testing Strategy without Live MCP)**:
   - While official runs (`day09 run`) must use the live authenticated MCP Gateway, unit tests (`pytest -q`) must run offline without requiring external network or live team credentials.
   - A mock `EvidenceGateway` fixture implementing the same `.call()` interface and producing compliant synthetic envelopes (`ev_` + 24 chars, `sha256:`, domain, data) is needed for local component unit tests.

---

## 3. Caveats

1. **Live MCP Server Availability & Credentials**:
   - The current `.env` contains placeholder `COMPETITION_TEAM_API_KEY=sk-team-replace_me`. Live execution via `day09 mcp-tools` or `day09 run` requires a valid team registration key from the competition portal.
2. **Terminal Execution Constraints**:
   - In this environment, interactive shell commands timed out awaiting manual permission. All tool analysis was conducted through comprehensive static code, schema, and dependency inspection.
3. **Exact Server-Side Tool Schema Variations**:
   - While `get_order` is confirmed in `README.md`, exact parameter names for auxiliary tools (e.g., whether items are queried via `get_order_items(case_id, order_id)` or `get_item(case_id, item_id)`) are discovered at runtime via `gateway.list_tools()` / `gateway._session.list_tools()`. The workflow must use dynamic discovery rather than hardcoding static tool names.

---

## 4. Conclusion

1. **MCP Gateway Mechanics**:
   - Client is implemented in `src/student_agent/mcp_gateway.py` via `mcp.ClientSession` over `httpx2` streamable HTTP client.
   - Authentication is via `Authorization: Bearer <key>`.
   - `EvidenceGateway.call(tool_name, *, case_id, **arguments)` enforces strict payload construction and immediately validates every response against `mcp-evidence-response-v1.schema.json`.
2. **Authoritative Evidence Envelope**:
   - Must contain `schema_version: "day09-mcp-evidence-v1"`, `evidence_ref: "^ev_[A-Za-z0-9_-]{20,96}$"`, `result_hash: "^sha256:[a-f0-9]{64}$"`, `domain` (one of 9 enums), and `data`.
3. **Evidence Ref Rules & Anti-Hallucination**:
   - `evidence_ref` values are cryptographically generated and audited on the server.
   - Never generate fake evidence refs. Never reuse evidence refs across cases.
   - Every evidence ref in the output must be grounded in an MCP Gateway call and logged in a `tool_result_consumed` trace event.
4. **Tool Discovery Protocol**:
   - The workflow must query `await gateway.list_tools()` on startup and dynamically resolve available tools.
5. **Testing Architecture**:
   - Starter kit contains no mock MCP server. A lightweight mock gateway fixture should be added to `tests/` for unit tests, ensuring `pytest -q` runs cleanly in offline mode.

---

## 5. Verification Method

To independently verify these findings:
1. **Schema Verification**:
   - View `contracts/schemas/mcp-evidence-response-v1.schema.json` to verify envelope fields, `domain` enum, and regex patterns for `evidence_ref` and `result_hash`.
   - View `contracts/schemas/trace-event-v1.schema.json` to verify `tool_result_consumed` and `evidence_refs` field properties.
2. **Codebase Gateway Verification**:
   - Inspect `src/student_agent/mcp_gateway.py` lines 15–42 to verify `EvidenceGateway.call` implementation, parameter forwarding, and validation call.
   - Inspect `src/student_agent/cli.py` lines 43–46 to verify tool discovery requirement.
3. **Scoring Policy Verification**:
   - Inspect `contracts/scoring/scoring-policy-v2.json` lines 8–14 and lines 44–51 to confirm `provenance` (15%), `evidence` (15%), and hard gates (`unknown_evidence_ref`, `cross_scope_evidence_ref`, `invalid_evidence_refs`).
