# Handoff Report: Verification & Evaluation Suite Survey (Day09 L3A)

## Features Discovered

| # | Category | Feature | Description | Inputs | Outputs | Error Behavior | Discovered Via |
|---|----------|---------|-------------|--------|---------|----------------|----------------|
| 1 | CLI Command | `day09 run` | Executes multi-agent investigation workflow for all cases, writes outputs and traces | `--root <path>` (optional, default `.`): path to repository root | Files `outputs/<case_id>.json`, `traces/trace.jsonl` | Raises `ValueError`, `RuntimeError`, or `ContractError` and exits with code 1 | `src/student_agent/cli.py:30-61` |
| 2 | CLI Command | `day09 validate` | Validates completeness and schema compliance of all 100 outputs and trace log | `--root <path>` (optional, default `.`) | Prints `OK: 100 outputs / N trace events` to stdout | Exits 1 with detailed message on missing files, schema error, duplicate events, or key leak | `src/student_agent/cli.py:90-94`, `src/student_agent/submission.py:42-86` |
| 3 | CLI Command | `day09 validate-inputs` | Validates inventory and syntax of `case-set.json` and 100 input files | `--root <path>` (optional, default `.`) | Prints `OK: l3a / <version> / 100 cases` | Exits 1 if count != 100, variant != l3a, or files mismatch | `src/student_agent/cli.py:80-85`, `src/student_agent/cases.py:32-60` |
| 4 | CLI Command | `day09 mcp-tools` | Connects to MCP Gateway, authenticates with Team API Key, lists tools | `--root <path>` (optional, default `.`) | Prints list of available tool names to stdout | Exits 1 if credentials invalid, network fails, or tool list empty | `src/student_agent/cli.py:22-27`, `src/student_agent/mcp_gateway.py:20-23` |
| 5 | CLI Command | `day09 package` | Validates artifacts and generates submission ZIP archive for competition upload | `--root <path>`, `--output <zip_path>` (default `dist/submission.zip`) | ZIP containing `manifest.json`, `trace.jsonl`, `outputs/*.json` | Exits 1 if validation fails, file > 1MB, or uncompressed > 12MB | `src/student_agent/cli.py:95-97`, `src/student_agent/submission.py:89-121` |
| 6 | Gateway Client | `EvidenceGateway.call` | Calls tool on remote MCP Gateway, validates envelope and returns data + evidence_ref | `tool_name`, `case_id`, `**arguments` | Dict containing `schema_version`, `evidence_ref`, `result_hash`, `domain`, `data`, `warnings` | Raises `RuntimeError` on MCP error, `ContractError` on schema violation | `src/student_agent/mcp_gateway.py:24-41` |
| 7 | Trace Logging | `TraceWriter.emit` | Appends validated event to `traces/trace.jsonl` | `case_id`, `event_type`, `actor`, optional `target`, `decision_code`, `tool_name`, `evidence_refs`, `attributes` | Validated JSON dict appended as a single JSONL line | Raises `ContractError` if event violates `trace-event-v1.schema.json` | `src/student_agent/trace.py:20-51` |
| 8 | Contract Validation | `Contracts.validate_output` | Validates case output against draft 2020-12 schema | Output dict, label string | None (passes silently) | Raises `ContractError` indicating exact JSON path of failure | `src/student_agent/contracts.py:43-44` |
| 9 | Scoring Engine | Scoring Policy V2 | Computes weighted average score across public (20%) and private (80%) cases | 100 case outputs and trace log | Final score in [0, 100] | 0 score triggered by hard gates (schema violation, invalid/unknown/cross-case evidence_ref) | `contracts/scoring/scoring-policy-v2.json` |

## Edge Cases

| # | Feature | Input | Observed Behavior |
|---|---------|-------|-------------------|
| 1 | `load_case_set` | `variant_id` set to `"l3b"` in `case-set.json` | Raises `ValueError("expected variant 'l3a', got 'l3b'")` |
| 2 | `load_case_set` | Case count != 100 or duplicated case IDs | Raises `ValueError("case-set must contain exactly 100 unique case IDs")` |
| 3 | `load_case_set` | Files in `inputs/` don't match `case_ids` exactly | Raises `ValueError("inputs do not match case-set; missing=..., extra=...")` |
| 4 | `validate_artifacts` | Missing or extra files in `outputs/` | Raises `ValueError("outputs do not match case-set; missing=..., extra=...")` |
| 5 | `validate_artifacts` | Duplicate `event_id` in `traces/trace.jsonl` | Raises `ValueError("traces/trace.jsonl:<line>: duplicate event_id")` |
| 6 | `validate_artifacts` | Trace event containing foreign `case_id` | Raises `ValueError("traces/trace.jsonl:<line>: case is outside this case-set")` |
| 7 | `validate_artifacts` | Any output or trace line contains `sk-team-...` | Raises `ValueError("a Team API Key appears in output or trace")` |
| 8 | `package_submission` | Single file in ZIP exceeds 1 MB | Raises `ValueError("submission files exceed 1 MB: [...]")` |
| 9 | `package_submission` | Uncompressed total size of ZIP exceeds 12 MB | Raises `ValueError("submission exceeds the 12 MB uncompressed limit")` |
| 10 | `test_release_safety` | Repository root contains `case-set.json` or `inputs/*.json` | Test fails assertion: `test_repository_contains_no_competition_payload` |

---

## 1. Observation

Direct examination of codebase files reveals the following facts and structures:

### 1.1 CLI Entry Point & Configuration
- **Entry Point**: `pyproject.toml` lines 20-21:
  ```toml
  [project.scripts]
  day09 = "student_agent.cli:main"
  ```
- **CLI Definition**: `src/student_agent/cli.py` lines 63-73 defines the argument parser with global argument `--root` (default `.`):
  ```python
  def parser() -> argparse.ArgumentParser:
      result = argparse.ArgumentParser(description="Day09 L3A student workflow")
      result.add_argument("--root", default=".", help="repository root (default: current directory)")
      commands = result.add_subparsers(dest="command", required=True)
      commands.add_parser("validate-inputs", help="validate case-set.json and all 100 inputs")
      commands.add_parser("mcp-tools", help="authenticate and list discovered MCP tools")
      commands.add_parser("run", help="run the implemented workflow for all cases")
      commands.add_parser("validate", help="validate outputs and observable trace")
      package = commands.add_parser("package", help="validate and build the submission ZIP")
      package.add_argument("--output", default="dist/submission.zip")
      return result
  ```
- **Settings & Environment**: `src/student_agent/config.py` lines 10-36:
  - Requires `.env` in `root`.
  - Required variables: `COMPETITION_API_URL` (must start with `http://` or `https://`), `COMPETITION_TEAM_API_KEY` (must match `^sk-team-[A-Za-z0-9_-]{16,128}$`), `MCP_ENDPOINT` (must start with `http://` or `https://`).
- **`day09 run` Execution**: Lines 30-61 in `cli.py`:
  - Resolves `root`.
  - Loads `Settings`, `CaseSet`, and `Contracts`.
  - Clears `outputs/*.json` and `traces/trace.jsonl`.
  - Connects to MCP Gateway via `connect_gateway`.
  - Discovers tools; if empty, raises `RuntimeError("MCP Gateway returned no tools")`.
  - Loops over each `case_id` in `case_set.case_ids`:
    1. `trace.emit(case_id=case_id, event_type="case_received", actor="coordinator")`
    2. `output = await solve_case(case, gateway, trace)`
    3. `contracts.validate_output(output, f"outputs/{case_id}.json")`
    4. Asserts `output.get("case_id") == case_id`
    5. Writes formatted output atomically via `.json.tmp` rename to `outputs/{case_id}.json`
    6. `trace.emit(case_id=case_id, event_type="case_finalized", actor="coordinator")`

### 1.2 `day09 validate` & Validation Suite
- **`day09 validate`**: In `cli.py` lines 90-94 calls `validate_artifacts(root, case_set, contracts)` from `src/student_agent/submission.py`.
- **Validation Pipeline**:
  - `outputs/<case_id>.json`: Exactly 100 files matching `case-set.json`.
  - Schema check: Each output validated against `contracts/schemas/l3a-output-v2.schema.json`.
  - Trace check: `traces/trace.jsonl` validated line-by-line against `contracts/schemas/trace-event-v1.schema.json`. Unique `event_id` enforcement. No foreign `case_id`.
  - Secret scanning: Regex `sk-team-[A-Za-z0-9_-]{8,}` checked against all outputs and trace lines.

### 1.3 Scoring Policy & Acceptance Criteria
- Authoritative file: `contracts/scoring/scoring-policy-v2.json`.
- Score range: `[0, 100]`, aggregation: `arithmetic_mean`.
- **Weights for Variant `l3a`**:
  - `semantic`: **45%** (0.45)
  - `evidence`: **15%** (0.15)
  - `provenance`: **15%** (0.15)
  - `consistency`: **10%** (0.10)
  - `schema`: **5%** (0.05)
  - `calibration`: **5%** (0.05)
  - `workflow`: **5%** (0.05)
  - `efficiency`: **0%** (0.00)
- **Hard Gates (Resulting in 0 score)**:
  - `case_id_mismatch`
  - `unscorable_schema`
  - `missing_required_evidence`
  - `invalid_evidence_refs`
  - `unknown_evidence_ref`
  - `cross_scope_evidence_ref`
- **Workflow Required Events**:
  - `case_received`
  - `task_assigned`
  - `handoff`
  - `verification_completed`
  - `case_finalized`
- **Leaderboard Splits**:
  - 50 public cases (20% final score)
  - 50 private cases (80% final score)

### 1.4 Test Suite in `tests/`
- `tests/test_starter.py`:
  - `test_load_case_set_rejects_wrong_variant`: Confirms `load_case_set` rejects `variant_id != "l3a"`.
  - `test_load_case_set_accepts_exact_input_inventory`: Confirms loading 2 cases when manifest matches input directory.
  - `test_generated_manifest_matches_public_contract`: Confirms `build_manifest` generates valid `day09-submission-manifest-v2` with `output_schema_version == "day09-l3a-output-v2"`.
- `tests/test_release_safety.py`:
  - `test_repository_contains_no_competition_payload`: Asserts that `root / "case-set.json"` does not exist, `root / "inputs" / "*.json"` is empty, `root / "outputs" / "*.json"` is empty, and forbidden filenames (`oracles`, `reference-outputs`, `private-partitions.json`, `mcp-access.json`) are absent.
  - `test_example_environment_has_no_real_key`: Asserts `.env.example` contains `"sk-team-replace_me"`.

### 1.5 Input and Output Specifications
- **Input Location**: `inputs/l3a-inputs-v1/case-set.json` (defines 100 cases `L3A_CASE_001` through `L3A_CASE_100`) and `inputs/l3a-inputs-v1/inputs/L3A_CASE_*.json`.
- **Input Case Structure**:
  ```json
  {
    "case_id": "L3A_CASE_001",
    "opened_at": "2018-01-01T09:00:00-03:00",
    "customer_request": {
      "language": "vi",
      "message": "...",
      "claimed_order_id": "e2a03ccf5ea816036608b2d8c3ab8e60",
      "claims": [
        {"claim_id": "claim-001-a", "topic": "canceled_order_paid"},
        {"claim_id": "claim-001-b", "topic": "requested_full_refund"}
      ]
    },
    "policy_version": "EC_POLICY_V1"
  }
  ```
- **Output Schema Requirements (`contracts/schemas/l3a-output-v2.schema.json`)**:
  - `schema_version`: `"day09-l3a-output-v2"`
  - `case_id`: `^[A-Z0-9][A-Z0-9_-]{2,63}$`
  - `assessment`:
    - `primary_issue`: Enum of 11 issues (`canceled_order_paid`, `unavailable_order_paid`, `late_delivery_seller`, `late_delivery_logistics`, `valid_split_payment`, `payment_mismatch`, `duplicate_charge`, `refund_pending`, `refund_failed`, `unsupported_claim`, `insufficient_evidence`)
    - `case_status`: Enum `["action_required", "no_action", "needs_investigation"]`
    - `confidence`: Number in `[0, 1]`
  - `affected_entities`:
    - `order_ids`, `item_ids`, `seller_ids`, `payment_references`, `shipment_ids`: Unique arrays of string IDs (max 20 each)
  - `claim_assessments` (Optional array, max 5):
    - `claim_id`: String
    - `verdict`: Enum `["supported", "unsupported", "partially_supported", "insufficient_evidence"]`
    - `confidence`: Float `[0, 1]`
    - `evidence_refs`: Array of evidence refs
  - `root_cause_analysis`:
    - `ranked_causes`: Array (max 5) of `{ "cause_code": "^[A-Z][A-Z0-9_]{2,79}$", "rank": 1..5 }`
    - `responsible_parties`: Array (max 5) of `{ "party_type": enum["seller", "platform", "logistics_provider", "payment_provider", "customer", "unknown"], "party_id": string | null }`
  - `evidence_refs`: Array of strings matching `^ev_[A-Za-z0-9_-]{20,96}$` (max 30, unique)
  - `data_conflicts`: Array (max 5) of `{ "field": str, "sources": [str], "selected_source": str | null, "resolution_code": str }`
  - `financial_resolution`:
    - `currency`: `"BRL"`
    - `recommended_refund_brl`: Number >= 0
    - `refund_lines`: Array (max 10) of `{ "reason_code": str, "amount_brl": number >= 0, "entity_id": str | null }`
  - `resolution_actions`: Array (max 8) of unique strings (1..80 chars)
  - `additionalProperties`: false

---

## 2. Logic Chain

1. **CLI Execution & Data Flow**:
   - `day09 run` requires a valid `case-set.json` and matching `inputs/` directory in `--root`.
   - Before running `solve_case`, `day09 run` wipes out all existing `outputs/*.json` and `traces/trace.jsonl`.
   - `day09 run` performs real-time schema validation on each case output as soon as `solve_case` finishes. If any case fails schema validation, execution halts immediately with error.
   - The coordinator emits `case_received` before calling `solve_case` and `case_finalized` after `solve_case` finishes.
2. **Multi-Agent Orchestration & Trace Requirements**:
   - The scoring policy explicitly evaluates `workflow` (5%): "Mean of lifecycle-event coverage, receive/finalize ordering, actor collaboration and evidence-to-trace linkage."
   - Required events: `case_received` (done by CLI), `task_assigned` (must be done in workflow), `handoff` (must be done in workflow), `verification_completed` (must be done in workflow), `case_finalized` (done by CLI).
   - In addition, whenever an agent consumes a tool result, it must emit `tool_result_consumed` with `evidence_refs=[evidence_ref]`. The scoring policy verifies "evidence-to-trace linkage", meaning every evidence ref submitted in `outputs/<case_id>.json` must be linked to a `tool_result_consumed` event in the trace.
3. **Evidence Integrity & Provenance**:
   - Evidence refs must match `^ev_[A-Za-z0-9_-]{20,96}$`.
   - The server performs provenance auditing (15% score weight + hard gate): any evidence ref not generated by the server for that specific case, team, and run will cause disqualification or 0 score. Hallucinated or cross-case evidence refs trigger hard gates.
4. **Consistency Verification**:
   - 10% of score is based on cross-field consistency:
     - If `case_status == "no_action"`, `recommended_refund_brl` must be 0 and `refund_lines` must be empty.
     - If `case_status == "action_required"`, `recommended_refund_brl` must equal the sum of `amount_brl` across `refund_lines`, and `resolution_actions` must contain corresponding actions.
     - Root cause responsible parties must align with seller/logistics actions.
5. **Test Safety Constraints**:
   - `test_release_safety.py` tests that `case-set.json` is not present in repository root during unit tests.
   - To keep `pytest` passing while allowing `day09 run` to execute, the test suite is designed for a clean repository state where inputs live in an unpacked subfolder or are supplied via `--root`.

---

## 3. Caveats

1. **Server-Side Scoring Oracle**:
   - The ground truth labels, private partition memberships (50 public / 50 private), exact numeric refund tolerances, and semantic keyword matching formulas are maintained exclusively on the server side (`contracts/README.md:16-17`).
2. **Terminal Execution Permissions**:
   - In this environment, interactive shell commands requiring elevated user confirmation timed out. All findings are derived directly from authoritative static files, schemas, and source code.
3. **Live MCP Server Availability**:
   - Live querying of `day09 mcp-tools` requires a valid team API key in `.env` and an active connection to `https://day09-competition.34-142-201-239.sslip.io/mcp`.

---

## 4. Conclusion

The evaluation suite has two distinct layers:
1. **Local Verification (`day09 validate` and `pytest`)**:
   - Enforces 100% adherence to JSON Schema Draft 2020-12 (`l3a-output-v2.schema.json` and `trace-event-v1.schema.json`).
   - Ensures exact inventory of 100 cases, unique trace event IDs, and absolute absence of leaked team API keys (`sk-team-...`).
2. **Remote Evaluation & Scoring (`contracts/scoring/scoring-policy-v2.json`)**:
   - Evaluates outputs across 8 distinct metrics: Semantic (45%), Evidence F1 (15%), Provenance Audit (15%), Consistency (10%), Schema (5%), Calibration (5%), Workflow (5%), and Efficiency (0%).
   - Instantly zeros out scores for cases that fail any of the 6 Hard Gates (`case_id_mismatch`, `unscorable_schema`, `missing_required_evidence`, `invalid_evidence_refs`, `unknown_evidence_ref`, `cross_scope_evidence_ref`).

---

## 5. Verification Method

To verify these findings independently:
1. **Schema Validation**:
   - Inspect `contracts/schemas/l3a-output-v2.schema.json` and `contracts/schemas/trace-event-v1.schema.json`.
   - Run python code using `jsonschema.Draft202012Validator` on any sample output.
2. **Unit Test Verification**:
   - Run `pytest -q` to verify the baseline unit tests (`test_load_case_set_rejects_wrong_variant`, `test_load_case_set_accepts_exact_input_inventory`, `test_generated_manifest_matches_public_contract`, `test_repository_contains_no_competition_payload`, `test_example_environment_has_no_real_key`).
3. **CLI Verification**:
   - Run `python -m student_agent.cli --help` to confirm all 5 commands (`validate-inputs`, `mcp-tools`, `run`, `validate`, `package`).
   - Verify input case structure by inspecting `inputs/l3a-inputs-v1/inputs/L3A_CASE_001.json`.

---

## Complete Acceptance Criteria Checklist for 100% / Near-Perfect Score

### A. Functional & CLI Execution
- [ ] `day09 run` completes all 100 cases sequentially without crashing or unhandled exceptions.
- [ ] Stale output and trace files are cleaned automatically at start of run.
- [ ] Output files `outputs/<case_id>.json` are written atomically for all 100 cases.
- [ ] `day09 validate` exits with code 0 and reports `OK: 100 outputs / N trace events`.
- [ ] `day09 package` builds `dist/submission.zip` containing only `manifest.json`, `trace.jsonl`, and `outputs/<case_id>.json`.
- [ ] No file exceeds 1 MB; total uncompressed zip size <= 12 MB.

### B. Hard Gates (Zero-Tolerance Failure Conditions)
- [ ] No `case_id_mismatch`: Every output has `"case_id"` exactly matching the input case ID and filename.
- [ ] No `unscorable_schema`: Strict adherence to `l3a-output-v2.schema.json` with no extra or missing properties.
- [ ] No `missing_required_evidence`: All critical claims must be grounded in valid MCP evidence.
- [ ] No `invalid_evidence_refs`: All evidence refs conform strictly to `^ev_[A-Za-z0-9_-]{20,96}$`.
- [ ] No `unknown_evidence_ref`: 0% hallucinated evidence refs; every ref must originate from MCP Gateway.
- [ ] No `cross_scope_evidence_ref`: Never reuse evidence refs from another case, run, or team.
- [ ] No `secret_leak`: Neither output JSON nor trace log contains any string matching `sk-team-[A-Za-z0-9_-]{8,}`.

### C. Semantic Accuracy (45% Weight)
- [ ] `primary_issue` correctly identified among the 11 valid enum choices.
- [ ] Claim verdicts (`supported`, `unsupported`, `partially_supported`, `insufficient_evidence`) correctly assigned to all claims.
- [ ] Financial resolution: `recommended_refund_brl` matches exact policy calculation rules for the issue.
- [ ] Root cause: `cause_code` (pattern `^[A-Z][A-Z0-9_]{2,79}$`) and ranking (1..5) accurately determined.
- [ ] Responsible parties: Correct assignment of `party_type` (`seller`, `platform`, `logistics_provider`, `payment_provider`, `customer`, `unknown`) and `party_id`.

### D. Evidence F1 & Provenance (30% Weight Combined)
- [ ] Evidence F1 (15%): Comprehensive coverage of relevant evidence domains without missing key facts.
- [ ] Relevance Precision: Include only evidence refs directly relevant to the issue; avoid query bloat into forbidden/unrelated domains.
- [ ] Provenance (15%): 100% of submitted evidence refs exist in the MCP Gateway server audit log for the current run and case.

### E. Consistency & Calibration (15% Weight Combined)
- [ ] Cross-Field Consistency (10%):
  - If `case_status == "no_action"`: `recommended_refund_brl == 0`, `refund_lines == []`.
  - If `case_status == "action_required"`: `recommended_refund_brl` equals sum of `amount_brl` in `refund_lines`.
  - `resolution_actions` match the issue, root cause, and status without contradiction.
  - Zero duplicate actions in `resolution_actions`.
- [ ] Confidence Calibration (5%):
  - Output confidence calibrated against certainty: high confidence (0.85-0.98) when evidence is unambiguous; moderate confidence (0.50-0.70) when evidence shows conflicts or missing data.

### F. Multi-Agent Workflow & Observable Trace (5% Weight)
- [ ] Complete lifecycle events emitted for every single case:
  1. `case_received` (emitted by coordinator)
  2. `task_assigned` (emitted when assigning subtasks to specialist agents)
  3. `tool_result_consumed` (emitted with `evidence_refs=[...]` whenever an agent consumes tool output)
  4. `handoff` (emitted during A2A handoffs between specialists)
  5. `verification_completed` (emitted when verifier validates the synthesis)
  6. `case_finalized` (emitted by coordinator upon completion)
- [ ] Correct temporal ordering of events.
- [ ] Evidence-to-trace linkage: 100% of evidence refs appearing in final output are referenced in `tool_result_consumed` events in `trace.jsonl`.
- [ ] Clear actor identification (e.g. `coordinator`, `order_agent`, `payment_agent`, `shipment_agent`, `policy_agent`, `verifier`).

### G. Code Quality & Educational Annotations (R4)
- [ ] Every major class, function, and agent reasoning step contains detailed Vietnamese annotations explaining *what* it does, *how* it works, and *why* it is designed that way.
