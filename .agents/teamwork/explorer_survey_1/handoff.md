# Handoff Report: Explorer Survey 1 (Codebase Architecture Explorer)

**Working Directory**: `.agents/teamwork/explorer_survey_1`  
**Target Milestone**: Survey and Architecture Mapping  
**Date/Timestamp**: 2026-09-25T04:12:00Z  

---

## 1. Observation

### 1.1 Repository Structure & Inventory
Direct inspection of the repository (`c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A`) reveals the following components:
- **Root Configuration & Docs**:
  - `pyproject.toml`: Project `day09-l3a-student-agent` (version 0.1.0, Python `>=3.11`). Specifies dependencies:
    ```toml
    dependencies = [
        "httpx2>=2,<3",
        "jsonschema[format]>=4.25,<5",
        "mcp>=2,<3",
        "python-dotenv>=1.1,<2",
    ]
    dev = ["pytest>=8.4,<9", "ruff>=0.12,<1"]
    [project.scripts]
    day09 = "student_agent.cli:main"
    ```
  - `README.md`: Detailed specification of goals, dataset (Olist Brazilian e-commerce), setup instructions, MCP gateway usage, multi-agent roles, scoring criteria, and submission rules.
  - `ARCHITECTURE.md`: Architecture template outlining system flow (`Input → Coordinator → Specialists → Verifier → Output`), Agent Ownership table, A2A protocol, Evidence lifecycle, and Verification invariants.
  - `.env` & `.env.example`: Defines `COMPETITION_API_URL`, `COMPETITION_TEAM_API_KEY`, and `MCP_ENDPOINT`.
  - `.github/workflows/quality.yml`: Runs CI checks with `ruff check .` and `pytest -q`.

- **Contracts & Schemas (`contracts/`)**:
  - `contracts/schemas/l3a-output-v2.schema.json`: Strict JSON schema for the final case output.
    - Required fields: `schema_version` (const `"day09-l3a-output-v2"`), `case_id`, `assessment`, `affected_entities`, `root_cause_analysis`, `evidence_refs`, `data_conflicts`, `financial_resolution`, `resolution_actions`.
    - `assessment.primary_issue` enums: `"canceled_order_paid"`, `"unavailable_order_paid"`, `"late_delivery_seller"`, `"late_delivery_logistics"`, `"valid_split_payment"`, `"payment_mismatch"`, `"duplicate_charge"`, `"refund_pending"`, `"refund_failed"`, `"unsupported_claim"`, `"insufficient_evidence"`.
    - `assessment.case_status` enums: `"action_required"`, `"no_action"`, `"needs_investigation"`.
    - `financial_resolution`: currency `"BRL"`, `recommended_refund_brl` (number >= 0), `refund_lines` (array of objects with `reason_code`, `amount_brl`, `entity_id`).
  - `contracts/schemas/trace-event-v1.schema.json`: Public trace contract.
    - Required fields: `schema_version` (`"day09-trace-event-v1"`), `event_id` (`^evt_[A-Za-z0-9_-]{12,96}$`), `case_id`, `event_type`, `occurred_at`, `actor`.
    - Allowed `event_type` enums:
      - `"case_received"`
      - `"task_assigned"`
      - `"tool_result_consumed"`
      - `"handoff"`
      - `"policy_decided"`
      - `"verification_completed"`
      - `"case_finalized"`
    - Optional fields: `target`, `decision_code`, `tool_name`, `evidence_refs` (array of `^ev_[A-Za-z0-9_-]{20,96}$`), `attributes` (key-value primitives).
  - `contracts/schemas/mcp-evidence-response-v1.schema.json`: Format returned by MCP tools. Required fields: `schema_version` (`"day09-mcp-evidence-v1"`), `evidence_ref` (`^ev_[A-Za-z0-9_-]{20,96}$`), `result_hash`, `domain` (enum: `"order"`, `"item"`, `"payment"`, `"shipment"`, `"seller"`, `"customer"`, `"product"`, `"refund"`, `"policy"`), `data`, and optional `warnings`.
  - `contracts/scoring/scoring-policy-v2.json`:
    - Metric weights for L3A: `semantic` (45%), `evidence` (15%), `provenance` (15%), `consistency` (10%), `schema` (5%), `calibration` (5%), `workflow` (5%), `efficiency` (0%).
    - Hard gates (0 score if violated): `case_id_mismatch`, `unscorable_schema`, `missing_required_evidence`, `invalid_evidence_refs`, `unknown_evidence_ref`, `cross_scope_evidence_ref`.
    - `workflow_required_events`: `["case_received", "task_assigned", "handoff", "verification_completed", "case_finalized"]`.

- **Student Agent Source (`src/student_agent/`)**:
  - `__init__.py`: Exports `VARIANT_ID = "l3a"` and `OUTPUT_SCHEMA_VERSION = "day09-l3a-output-v2"`.
  - `config.py`: `Settings.load(root)` loads `.env` and validates URL formatting and team key pattern (`^sk-team-[A-Za-z0-9_-]{16,128}$`).
  - `contracts.py`: `Contracts` class builds a `referencing.Registry` and validates output, trace, manifest, and evidence using `Draft202012Validator`.
  - `mcp_gateway.py`: `EvidenceGateway` wraps `mcp.ClientSession` over `httpx2`. Provides `list_tools()` and `call(tool_name, *, case_id, **arguments)`. Validates tool results against `mcp-evidence-response-v1.schema.json`.
  - `trace.py`: `TraceWriter.emit(...)` writes JSON lines to `traces/trace.jsonl` after validating each event against `trace-event-v1.schema.json`.
  - `submission.py`: Validates outputs and traces against contracts, builds `manifest.json`, checks for leaked API keys, and packages `dist/submission.zip`.
  - `cases.py`: `load_case_set(root, expected_count=100)` loads `case-set.json` and 100 cases from `inputs/<case_id>.json`.
  - `cli.py`: Entry point for `day09` (`validate-inputs`, `mcp-tools`, `run`, `validate`, `package`).
  - `workflow.py`: Currently contains:
    ```python
    async def solve_case(
        case: dict[str, Any], gateway: EvidenceGateway, trace: TraceWriter
    ) -> dict[str, Any]:
        del case, gateway, trace
        raise NotImplementedError("Implement the L3A multi-agent workflow in solve_case()")
    ```

- **Environment & Dependencies (`.venv/Lib/site-packages`)**:
  - Installed libraries: `httpx2` (2.13.1), `mcp` (2.2.0), `jsonschema` (4.26.0), `pydantic` (2.13.5), `python-dotenv` (1.2.3), `pytest` (8.4.2), `ruff` (0.16.9), `anyio`, `starlette`.
  - Notable absences: Neither `openai` nor `langchain` is installed. `httpx2` is the primary modern async HTTP library available in the environment.

- **Datasets (`inputs/`)**:
  - The 100 competition cases (`L3A_CASE_001.json` through `L3A_CASE_100.json`) and `case-set.json` are present inside `inputs/l3a-inputs-v1/`.

---

## 2. Logic Chain

1. **Workflow Integration Point**:
   - In `student_agent.cli._run(root)` (lines 47-60):
     ```python
     for case_id in case_set.case_ids:
         case = case_set.cases[case_id]
         trace.emit(case_id=case_id, event_type="case_received", actor="coordinator")
         output = await solve_case(case, gateway, trace)
         contracts.validate_output(output, f"outputs/{case_id}.json")
         ...
         trace.emit(case_id=case_id, event_type="case_finalized", actor="coordinator")
     ```
   - *Deduction*: `cli.py` already handles emitting `case_received` before `solve_case` and `case_finalized` after `solve_case`.
   - *Deduction*: Inside `solve_case(case, gateway, trace)`, the multi-agent system must emit the remaining required events: `task_assigned`, `tool_result_consumed`, `handoff`, `policy_decided`, and `verification_completed`.

2. **Trace Emission Mechanics & Scoring**:
   - `scoring-policy-v2.json` explicitly mandates `["case_received", "task_assigned", "handoff", "verification_completed", "case_finalized"]`.
   - Furthermore, `tool_result_consumed` MUST be emitted whenever an MCP evidence item is utilized, containing the exact `evidence_refs=[evidence_ref]` and `tool_name`.
   - Any hallucinated or mismatched `evidence_ref` triggers hard-gate failure (0 score). Therefore, `evidence_ref` strings must only be extracted from genuine `gateway.call(...)` returns.

3. **LLM Client Architecture (NVIDIA API)**:
   - Original User Request specifies:
     - API Key: `Bearer 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`
     - Model: `Llama 3.1 Nemotron Safety Guard 8B v3` (`nvidia/llama-3.1-nemotron-safety-guard-8b-v3`)
   - Since `openai` is not in `.venv` or `pyproject.toml`, but `httpx2` (version 2.13.1) is installed, a lightweight async NVIDIA NIM client can be built directly using `httpx2.AsyncClient` targeting `https://integrate.api.nvidia.com/v1/chat/completions`.
   - This keeps the codebase completely zero-dependency beyond existing `pyproject.toml` requirements, ensuring full CI compliance (`quality.yml`).

4. **Multi-Agent Architecture Decomposition**:
   - To achieve high scores across Semantic (45%), Evidence (15%), Provenance (15%), Consistency (10%), Schema (5%), Calibration (5%), and Workflow (5%):
     - **Coordinator (`coordinator`)**: Analyzes customer request (`claimed_order_id`, customer claims), plans investigation, and delegates tasks via `task_assigned`.
     - **Order Specialist (`order-agent`)**: Invokes MCP tools (e.g., `get_order`, `get_items`), collects order status, purchase date, item count, and emits `tool_result_consumed` and `handoff`.
     - **Payment Specialist (`payment-agent`)**: Invokes payment tools (e.g., `get_payment`, `get_refunds`), inspects payment methods, total paid vs order total, installments, and emits `tool_result_consumed` and `handoff`.
     - **Shipment Specialist (`shipment-agent`)**: Invokes shipment tools (e.g., `get_shipment`), verifies shipping timeline, estimated vs actual delivery date, identifies if delivery delay is seller dispatch late or carrier delay, and emits `tool_result_consumed` and `handoff`.
     - **Policy Specialist (`policy-agent`)**: Evaluates evidence against policy (`EC_POLICY_V1`), decides `primary_issue`, calculates `recommended_refund_brl` and `refund_lines`, determines `responsible_parties`, and emits `policy_decided` and `handoff`.
     - **Verifier (`verifier`)**: Cross-checks all output fields against schema definitions, verifies arithmetic consistency (`recommended_refund_brl` == sum of refund lines), verifies all cited `evidence_refs` originate from actual MCP calls, and emits `verification_completed`.

5. **Educational Code Comments (R4)**:
   - R4 requires comprehensive inline comments in Vietnamese explaining *what* each step does, *how* it functions, and *why* it is necessary in that specific place. All classes, agents, and helper functions must be thoroughly documented.

---

## 3. Caveats

1. **MCP Server Live State**:
   - Static analysis was performed without triggering live calls to `MCP_ENDPOINT` (configured as `https://day09-competition.34-142-201-239.sslip.io/mcp`) because `.env` currently has placeholder `sk-team-replace_me`. Explorer 2 is responsible for live tool schema cataloging.
2. **Input Directory Resolution**:
   - Currently, `case-set.json` and inputs are located under `inputs/l3a-inputs-v1/`. For `day09 run` to execute against root default, either `inputs/` and `case-set.json` must be copied to root, or `--root inputs/l3a-inputs-v1` must be passed to CLI. Note that `test_release_safety.py` specifically tests that competition payloads are not in root during student starter kit distribution; during actual competition execution, input files are placed in root.
3. **Nemotron Safety Guard 8B Model Nature**:
   - The specified LLM is `Llama 3.1 Nemotron Safety Guard 8B v3`, which is optimized for safety evaluation, risk assessment, and guardrails. It should be used for intent understanding and safety checks, paired with deterministic verification to prevent any formatting drift.

---

## 4. Conclusion

The repository is cleanly architected with strong contract validation already built into `Contracts`, `TraceWriter`, and `EvidenceGateway`. The primary implementation task is writing the multi-agent system in `src/student_agent/workflow.py` (supported by clean sub-modules under `src/student_agent/`), implementing:
1. `NvidiaLLMClient` via `httpx2.AsyncClient` pointing to `https://integrate.api.nvidia.com/v1/chat/completions` using the specified API key and Nemotron 8B model.
2. Role-based A2A pipeline: `Coordinator`, `OrderAgent`, `PaymentAgent`, `ShipmentAgent`, `PolicyAgent`, and `Verifier`.
3. Deterministic evidence collection and provenance tracking to ensure 100% of cited `evidence_refs` match audited MCP gateway calls.
4. Complete event tracing conforming to `trace-event-v1.schema.json` and meeting all scoring criteria.
5. Rich, educational Vietnamese code comments across all modules.

---

## 5. Verification Method

To independently verify the findings in this report:
1. **Source Code & Package Verification**:
   - Inspect `pyproject.toml` and `.venv/Lib/site-packages` to confirm installed versions (`httpx2==2.13.1`, `mcp==2.2.0`, `jsonschema==4.26.0`, `pydantic==2.13.5`).
   - Check `contracts/schemas/` to verify schemas for output, trace, and MCP evidence.
2. **Schema & Contract Tests**:
   - Inspect `tests/test_starter.py` and `tests/test_release_safety.py` to confirm contract validation behavior.
3. **Trace Contract Verification**:
   - Inspect `contracts/schemas/trace-event-v1.schema.json` lines 12-22 to verify the 7 allowed `event_type` enums.
4. **Invalidation Conditions**:
   - If new dependencies are added to `pyproject.toml`, or if `mcp` endpoint signatures differ from `EvidenceGateway.call`, update the respective module architecture.
