# Forensic Audit Report: Milestone 1.1 Foundation Modules

**Work Product**: `src/student_agent/models.py`, `src/student_agent/llm_client.py`, `src/student_agent/tools.py`  
**Profile**: General Project (Integrity Forensics)  
**Integrity Mode**: Benchmark Mode (Ground truth: `ORIGINAL_REQUEST.md` line 14)  
**Verdict**: **CLEAN**

---

## 1. Observation

Direct empirical observations made across the audited codebase and relevant specification files:

### Check 1: Anti-Hardcoding
- Exact paths checked:
  - `src/student_agent/models.py` (1003 lines)
  - `src/student_agent/llm_client.py` (840 lines)
  - `src/student_agent/tools.py` (446 lines)
- Ripgrep scan for test case identifiers (`L3A_CASE_`, `CASE_001` through `CASE_100`):
  - Result: 0 matches found in `src/student_agent/`. All case IDs are dynamically injected from runtime inputs (`CaseInput.from_dict` in `models.py:255`, `ToolAdapter(gateway, trace, case_id)` in `tools.py:130`).
- Ripgrep scan for 32-character hexadecimal IDs (order/item IDs):
  - Result: 0 matches found in `src/student_agent/`.
- Financial computations in `models.py` and `llm_client.py`:
  - `models.py:670`: `calculated_sum = round(sum(line.amount_brl for line in self.refund_lines), 2)` dynamically aggregates refund lines.
  - `models.py:930`: `lines_sum = round(sum(l.amount_brl for l in lines), 2)` verifies dynamic arithmetic equality.
  - `llm_client.py:727-832`: `_fallback_assist_claim_verification` computes verdicts based on real parameters (`order_status`, `total_paid`, `is_seller_late`, `is_carrier_late`) rather than static lookup tables.

### Check 2: Anti-Dummy / Anti-Facade
- `src/student_agent/models.py`:
  - Enums (lines 63–174): 11 `PrimaryIssue`, 3 `CaseStatus`, 4 `ClaimVerdict`, 6 `PartyType`, 9 `EvidenceDomain`, 7 `TraceEventType`, 6 `AgentRole`.
  - Data sanitization and bounds enforcement: `clean_list` (lines 528–536) deduplicates and bounds lists to 20 elements; `ClaimAssessment.to_dict` (lines 567–580) deduplicates `evidence_refs` and caps to 30 elements; `RankedCause.__post_init__` (line 592) bounds rank between 1 and 5; `DataConflict.to_dict` (lines 690–705) enforces minItems: 2.
  - Invariant validator: `L3AOutputV2.validate_invariants` (lines 900–946) actively checks `CASE_ID_PATTERN`, `case_status == no_action` vs `recommended_refund_brl == 0`, `action_required` vs refund sum, and provenance membership.
- `src/student_agent/llm_client.py`:
  - Genuine HTTP client implementation: `_get_client` (lines 182–210) provisions `httpx2.AsyncClient` with connection pooling (`max_connections=20, max_keepalive_connections=10`), timeouts (`httpx2.Timeout`), and `Bearer` headers.
  - `chat_completion` (lines 228–321): implements complete HTTP POST invocation, exponential backoff retry loop on HTTP 429 and 503 with `Retry-After` header extraction, and network error handling.
  - Dual-layer resilience: `_fallback_evaluate_safety` (lines 423–462), `_fallback_analyze_intent` (lines 536–621), and `_fallback_assist_claim_verification` (lines 684–839) provide complete, robust heuristics.
- `src/student_agent/tools.py`:
  - `ToolAdapter.discover_tools` (lines 191–210): authentic asynchronous call `await self._gateway.list_tools()` with caching.
  - `ToolAdapter.call` (lines 240–387): genuine call wrapper that sanitizes arguments, retries on `httpx2.TransportError` and `httpx2.TimeoutException`, validates response envelopes, checks regex `EVIDENCE_REF_PATTERN`, synchronizes `trace.emit(event_type="tool_result_consumed")`, updates domain indexes, and constructs `ToolResult`.

### Check 3: Anti-Hallucination & Provenance
- `src/student_agent/tools.py`:
  - Line 32: `EVIDENCE_REF_PATTERN = re.compile(r"^ev_[A-Za-z0-9_-]{20,96}$")`.
  - Line 150: `self._consumed_evidence_refs: set[str] = set()`.
  - Lines 167–174: Property `consumed_evidence_refs` returns `set(self._consumed_evidence_refs)` (defensive copy; external mutations do not affect internal state).
  - Lines 335–349: `evidence_ref` is extracted directly from the gateway's response envelope, strictly validated against `EVIDENCE_REF_PATTERN`, and added to `_consumed_evidence_refs` only after gateway verification.
  - Lines 353–359: `trace.emit` emits `tool_result_consumed` with `evidence_refs=[evidence_ref]` at consumption time.
  - Lines 389–396: `is_valid_consumed_ref` tests membership in `_consumed_evidence_refs`.
  - Lines 398–412: `filter_valid_refs` discards any unprovenanced or hallucinated reference not present in `_consumed_evidence_refs`.
  - Absence of backdoor: No public method exists on `ToolAdapter` allowing arbitrary or manual addition of `evidence_ref`.

### Check 4: Secret Leak Scan
- Scanned for competition team keys (`sk-team-...`):
  - `src/student_agent/submission.py:14`: `SECRET_PATTERN = re.compile(r"sk-team-[A-Za-z0-9_-]{8,}")` (regex to detect and scrub secrets before export).
  - `src/student_agent/config.py:10`: `TEAM_KEY_PATTERN = re.compile(r"^sk-team-[A-Za-z0-9_-]{16,128}$")` (regex validator).
  - `src/student_agent/llm_client.py:443`: `r"sk-team-[a-za-z0-9_-]{8,}"` (regex pattern inside prompt injection detector).
  - `.env.example:2`: `COMPETITION_TEAM_API_KEY=sk-team-replace_me` (placeholder verified by `tests/test_release_safety.py`).
  - Result: ZERO hardcoded competition team API keys exist in the repository.
- Scanned for NVIDIA API key:
  - `src/student_agent/llm_client.py:27`: `DEFAULT_NVIDIA_API_KEY: str = "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"`.
  - Ground truth check (`ORIGINAL_REQUEST.md` line 22): Explicitly mandates: *"Use the provided NVIDIA API key (`Bearer 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`) and model (`Llama 3.1 Nemotron Safety Guard 8B v3`) để cấp nguồn cho các agent trong workflow."*
  - Key containment check: `self._api_key` is private to `NvidiaLLMClient`, used solely in the `Authorization` HTTP header (`llm_client.py:193`), and never emitted to traces, logs, or JSON outputs.

### Check 5: Educational Comments (Requirement R4 Compliance)
- All three files contain extensive, high-quality Vietnamese documentation structured around `# WHAT:` (chức năng), `# HOW:` (cơ chế hoạt động), and `# WHY:` (lý do thiết kế/ràng buộc nghiệp vụ):
  - `models.py`: Module docstring (lines 1–18), Regex constants (lines 32–50), Enums (lines 63–174), Input models (lines 180–264), Coordination (lines 270–309), Specialist findings (lines 315–470), Policy models (lines 475–725), State container (lines 731–854), Final output & invariant checks (lines 859–1002).
  - `llm_client.py`: Module docstring (lines 1–7), DTOs (lines 52–131), Client lifecycle & HTTP methods (lines 137–369), Safety evaluation (lines 373–462), Intent analysis (lines 467–621), Claim verification (lines 626–839).
  - `tools.py`: Module docstring (lines 1–12), `ToolResult` (lines 62–115), `ToolAdapter` and all public/private methods (lines 117–445).

---

## 2. Logic Chain

1. **Benchmark Mode Constraints (`ORIGINAL_REQUEST.md` line 14)**:
   - Benchmark Mode strictly prohibits: (1) Hardcoded test results, (2) Facade implementations, (3) Fabricated verification outputs, (4) Copied core logic, (5) External tool execution delegation, and (6) Fake `evidence_ref` values.
2. **Analysis of Anti-Hardcoding (Check 1)**:
   - Observations show 0 instances of test case identifiers (`L3A_CASE_*`), specific order IDs, or static return values across `models.py`, `llm_client.py`, and `tools.py`.
   - All arithmetic and classification logic is computed dynamically from inputs and tool responses.
   - Therefore, Check 1 is **CLEAN**.
3. **Analysis of Anti-Dummy/Facade (Check 2)**:
   - Observations show that `models.py` implements complete dataclass models, cross-field validations, invariant checks, and JSON Schema serialization.
   - `llm_client.py` implements a full asynchronous REST client with connection pooling, retry with backoff, JSON extraction, and comprehensive rule-based fallback engines.
   - `tools.py` implements dynamic MCP discovery, safe execution, retry handling, and multi-domain evidence indexing.
   - No methods return static placeholder stubs or dummy facades.
   - Therefore, Check 2 is **CLEAN**.
4. **Analysis of Anti-Hallucination & Provenance (Check 3)**:
   - In `tools.py`, `_consumed_evidence_refs` is private and its getter returns a shallow copy, preventing external tampering.
   - Evidence references enter the set strictly after validation of genuine responses from `EvidenceGateway.call()`.
   - `ToolAdapter.call()` immediately emits `trace.emit(event_type="tool_result_consumed")` to guarantee audit trail synchronization.
   - `filter_valid_refs` and `is_evidence_provenanced` strictly enforce provenance.
   - Therefore, Check 3 is **CLEAN**.
5. **Analysis of Secret Leaks (Check 4)**:
   - No hardcoded team keys (`sk-team-...`) exist in the codebase.
   - The default NVIDIA API key in `llm_client.py` is explicitly required by user instruction in `ORIGINAL_REQUEST.md` line 22, can be overridden via `NVIDIA_API_KEY` or constructor argument, and is strictly confined to internal request headers without leaking into outputs or traces.
   - Therefore, Check 4 is **CLEAN**.
6. **Analysis of Educational Annotations (Check 5)**:
   - Requirement R4 demands detailed inline comments in Vietnamese explaining *what*, *how*, and *why*.
   - All classes, methods, and algorithmic blocks across all three modules contain thorough Vietnamese annotations adhering to the `# WHAT:`, `# HOW:`, `# WHY:` structure.
   - Therefore, Check 5 is **CLEAN**.

---

## 3. Caveats

- **Network Dependency of LLM API**: Live execution against `https://integrate.api.nvidia.com/v1/chat/completions` requires active outbound network access. When offline or under rate limits, the client safely falls back to deterministic rule-based heuristics (`_fallback_evaluate_safety`, `_fallback_analyze_intent`, `_fallback_assist_claim_verification`), which was verified to be fully functional and authentic.
- **Scope Limit**: This audit covers the Foundation modules (`models.py`, `llm_client.py`, `tools.py`). Downstream modules (`specialists.py`, `policy.py`, `verifier.py`, `workflow.py`) will be audited in Milestones 2 and 3.

---

## 4. Conclusion

**Verdict: CLEAN**

The work products submitted for Milestone 1.1 (`src/student_agent/models.py`, `src/student_agent/llm_client.py`, and `src/student_agent/tools.py`) pass all five forensic integrity checks with zero violations:
1. Anti-Hardcoding: **PASS** (Zero hardcoded case IDs, outputs, or pre-cooked answers).
2. Anti-Dummy/Facade: **PASS** (Full, authentic implementations of all models, clients, and adapters).
3. Anti-Hallucination & Provenance: **PASS** (Tamper-proof, append-only evidence tracking and synchronized trace emission).
4. Secret Leak Scan: **PASS** (Zero competition team API keys; authorized NVIDIA key properly contained).
5. Educational Comments: **PASS** (100% compliance with Requirement R4 using Vietnamese What/How/Why comments).

The work product is approved without reservation.

---

## 5. Verification Method

To independently verify these forensic observations:

1. **Verify No Hardcoded Case IDs**:
   Inspect search results for case IDs in `src/student_agent`:
   ```bash
   rg -i "L3A_CASE_" src/student_agent/
   ```
   *Expected result*: 0 matches.

2. **Verify No Leaked Competition Team API Keys**:
   ```bash
   rg -i "sk-team-[A-Za-z0-9_-]{8,}" src/student_agent/
   ```
   *Expected result*: Matches only regex validation patterns in `submission.py`, `config.py`, and `llm_client.py`. No actual keys.

3. **Verify Python Syntax and Imports**:
   ```bash
   python -m py_compile src/student_agent/models.py src/student_agent/llm_client.py src/student_agent/tools.py
   ```
   *Expected result*: Exit code 0.

4. **Verify Evidence Immutability in `ToolAdapter`**:
   ```python
   from student_agent.tools import ToolAdapter
   # Verify that consumed_evidence_refs returns a copy:
   adapter = ToolAdapter(gateway=None, trace=None, case_id="TEST_CASE")
   refs = adapter.consumed_evidence_refs
   refs.add("ev_fake12345678901234567890")
   assert "ev_fake12345678901234567890" not in adapter.consumed_evidence_refs
   ```
   *Expected result*: Assertion passes (mutating returned set does not alter internal state).
