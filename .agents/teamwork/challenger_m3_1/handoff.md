# Handoff Report — Challenger M3.1: Verifier Invariants & Security Challenger

## Verdict: REQUEST_CHANGES

---

## 1. Observation

### Observation 1.1: Challenge 1 — Financial Reconciliation Floating Point Extremes
- **File**: `src/student_agent/verifier.py:172-228` (`_verify_and_reconcile_financials`)
- **Execution**: Tested via `tests/test_m3_challenger_adversarial.py` (`test_financial_reconciliation_floating_point_point_one_plus_two`, `test_financial_reconciliation_extreme_fractions_999_999_brl`, `test_financial_reconciliation_empty_lines_auto_creation`, `test_financial_reconciliation_more_than_ten_refund_lines_truncated`).
- **Results**:
  - `0.1 + 0.2` (= `0.30000000000000004`) with line items `0.1` and `0.2` reconciled cleanly to `0.30` BRL within `< 0.001` delta.
  - `999.999 BRL` rounded to `1000.00 BRL` across recommended refund and refund lines.
  - Submitting 15 lines of `10.0` was truncated to 10 lines (`clean_lines[:10]`), and `recommended_refund_brl` was automatically resynchronized from `150.0` to `100.0` (`abs(refund_amount - lines_sum) > 0.001`).
  - Total `250.75` with empty lines auto-generated a default refund line `APPROVED_CLAIM_REFUND` with amount `250.75`.

### Observation 1.2: Challenge 2 — `no_action` and `needs_investigation` Decision Self-Healing
- **File**: `src/student_agent/verifier.py:193-206, 378-392`
- **Execution**: Tested via `tests/test_m3_challenger_adversarial.py` (`test_no_action_enforces_zero_refund_and_empty_lines_and_safe_actions`, `test_needs_investigation_enforces_zero_refund_and_empty_lines_and_audit_actions`).
- **Results**:
  - `no_action` with `recommended_refund_brl: 888.88` and multiple refund lines was clamped to `0.0` BRL and `[]`. Disallowed actions (`APPROVE_FULL_REFUND`, `DISPATCH_REPLACEMENT_ITEM`) were purged, defaulting to `["NO_FURTHER_ACTION_NEEDED"]`.
  - `needs_investigation` with `recommended_refund_brl: 123.45` was clamped to `0.0` BRL and `[]`. Disallowed refund actions were purged, defaulting to `["REQUEST_ADDITIONAL_CUSTOMER_EVIDENCE", "OPEN_INTERNAL_AUDIT_INVESTIGATION"]`.

### Observation 1.3: Challenge 3 — Hallucinated Evidence Refs Drop and Empty Consumed Refs Leak
- **File**: `src/student_agent/verifier.py:265-274` (`_audit_evidence_provenance`):
  ```python
  265: if consumed_refs and ref_str not in consumed_refs:
  266:     logger.error(
  267:         "[%s] PHÁT HIỆN ẢO GIÁC: Ref '%s' không có trong consumed_refs của MCP! Loại bỏ ngay lập tức.",
  268:         case_id,
  269:         ref_str,
  270:     )
  271:     continue
  272:
  273: seen.add(ref_str)
  274: valid_refs.append(ref_str)
  ```
- **Execution**:
  - When `consumed_refs` is non-empty (`{"ev_genuine_..."}`), unconsumed refs are strictly dropped (`test_hallucinated_evidence_refs_strictly_dropped`).
  - When `consumed_refs` is empty (`set()`), `test_flaw_hallucinated_refs_leak_when_consumed_refs_is_empty` executed:
    ```
    Empty consumed_refs audit result: ['ev_hallucinated_fake_00000000000001']
    ```
    The hallucinated ref was NOT dropped and leaked into the output because `if consumed_refs` evaluates to `False`.

### Observation 1.4: Challenge 4 — Secret Injection Scrubbing (`sk-team-testkey12345` vs `nvapi-testkey12345`)
- **File**: `src/student_agent/verifier.py:60-65` (`SECRET_PATTERNS`):
  ```python
  60: SECRET_PATTERNS: tuple[re.Pattern[str], ...] = (
  61:     re.compile(r"sk-team-[A-Za-z0-9_-]{8,}", re.IGNORECASE),
  62:     re.compile(r"nvapi-[A-Za-z0-9_-]{16,}", re.IGNORECASE),
  63:     re.compile(r"bearer\s+[A-Za-z0-9_\-\.]{16,}", re.IGNORECASE),
  64:     re.compile(r"(?:api_key|token|secret)=([A-Za-z0-9_-]{16,})", re.IGNORECASE),
  65: )
  ```
- **Execution**:
  - `sk-team-testkey12345`: `len("testkey12345") == 12 >= 8`. Matched line 61, scrubbed to `[REDACTED]` (`test_secret_injection_sk_team_scrubbed`).
  - `nvapi-testkey12345`: `len("testkey12345") == 12 < 16`. Failed to match line 62.
  - Python execution result:
    ```
    1: nvapi-testkey12345
    2: [REDACTED]
    ```
    `nvapi-testkey12345` was NOT scrubbed and leaked verbatim in `resolution_actions`, `payment_references`, and `responsible_parties` (`test_flaw_secret_injection_nvapi_short_key_leaks`).

### Observation 1.5: Challenge 5 — Data Conflict Schema Compliance (`minItems: 2`, `uniqueItems: true`)
- **File**: `src/student_agent/verifier.py:493-507` and `contracts/schemas/l3a-output-v2.schema.json:111`
  - Schema specifies: `"sources": {"type": "array", "minItems": 2, "maxItems": 5, "uniqueItems": true}`
  - Code in `verifier.py:498`:
    ```python
    sources = dc_dict.get("sources", [])
    if isinstance(sources, list) and len(sources) >= 2:
        valid_conflicts.append(dc_dict)
    ```
- **Execution**:
  - For `DataConflict` dataclass instances, `.to_dict()` deduplicates sources, and single-source conflicts (`len(sources) < 2`) are dropped (`test_data_conflict_single_source_dropped_and_valid_retained`).
  - When `data_conflicts` contains raw dicts with duplicate sources (`["order_db", "order_db"]`), `len(sources) >= 2` passes, but `Contracts.validate_output` crashes:
    ```
    student_agent.contracts.ContractError: outputs/CASE_TEST_001.json:data_conflicts.0.sources: ['order_db', 'order_db'] has non-unique elements
    student_agent.verifier.InvariantViolationError: Output không hợp chuẩn schema: outputs/CASE_TEST_001.json:data_conflicts.0.sources: ['order_db', 'order_db'] has non-unique elements
    ```
    Demonstrated in `test_flaw_data_conflict_duplicate_sources_in_dict_causes_schema_crash`.

---

## 2. Logic Chain

1. **Financial Reconciliation**: Observations 1.1 show that `_verify_and_reconcile_financials` rounds to 2 decimal places, handles IEEE 754 precision drifts via `< 0.001` tolerance, clamps line items to 10, and resynchronizes total refund to the sum of lines.
2. **Decision Self-Healing**: Observations 1.2 demonstrate that `no_action` and `needs_investigation` decisions with rogue refund amounts and refund actions are strictly normalized to `0.0` BRL, empty lines `[]`, and sanitized non-financial action lists.
3. **Evidence Provenance Hole**: Observation 1.3 proves that line 265 (`if consumed_refs and ref_str not in consumed_refs:`) skips validation when `consumed_refs` is empty. Under conditions where tool discovery or specialist execution fails to populate `consumed_refs`, hallucinated refs pass through into the output, violating PROJECT.md §5 ("all evidence_refs in output must be a subset of state.tool_adapter.consumed_evidence_refs").
4. **Secret Leak Vulnerability**: Observation 1.4 proves that line 62 (`r"nvapi-[A-Za-z0-9_-]{16,}"`) sets a threshold of 16 characters after `nvapi-`. Since `nvapi-testkey12345` has only 12 characters after the prefix, it evades regex matching and leaks unredacted into output JSON files.
5. **Data Conflict Uniqueness Hole**: Observation 1.5 proves that `VerifierAgent` relies on `len(sources) >= 2` without deduplicating sources in `dc_dict`. When unnormalized input dicts have duplicate sources (`["s1", "s1"]`), the conflict is not pruned, triggering a `ContractError` and `InvariantViolationError` crash against `uniqueItems: true`.

---

## 3. Caveats

- In production cases with genuine NVIDIA NIM API keys (e.g. 64-char keys like `nvapi-je_vL73TA7...`), line 62 does scrub them. The leak specifically impacts keys shorter than 16 characters (such as test keys, mocked keys, or sub-tokens like `nvapi-testkey12345`).
- Under normal workflow operation, `DataConflict` is created via the `DataConflict` dataclass, whose `.to_dict()` deduplicates sources. The vulnerability only manifests if `PolicyDecision.data_conflicts` contains raw dictionaries or un-normalized objects.
- Tests in `tests/test_m3_integration.py` (`test_workflow_solve_case_recovers_gracefully_from_gateway_error` and `test_workflow_solve_case_end_to_end_success`) fail under `pytest -q` because `@pytest.mark.asyncio` is used without `pytest-asyncio` in the virtual environment.

---

## 4. Conclusion & Required Changes

**Verdict: REQUEST_CHANGES**

To make `VerifierAgent` 100% resilient and pass all adversarial challenges, the following fixes are required:

1. **Fix Secret Scrubbing Regex**:
   In `src/student_agent/verifier.py:62`, reduce the quantifier from `{16,}` to `{8,}`:
   ```python
   re.compile(r"nvapi-[A-Za-z0-9_-]{8,}", re.IGNORECASE),
   ```
2. **Fix Empty Consumed Refs Provenance Check**:
   In `src/student_agent/verifier.py:265`, strictly enforce provenance even when `consumed_refs` is empty:
   ```python
   if ref_str not in consumed_refs:
       logger.error(...)
       continue
   ```
   (If `consumed_refs` is empty, no candidate ref should ever be accepted).
3. **Fix Data Conflict Source Deduplication**:
   In `src/student_agent/verifier.py:496-500`, deduplicate sources before validating length:
   ```python
   raw_sources = dc_dict.get("sources", [])
   clean_sources: list[str] = []
   if isinstance(raw_sources, list):
       seen_s: set[str] = set()
       for s in raw_sources:
           s_val = str(s).strip()[:80]
           if s_val and s_val not in seen_s:
               seen_s.add(s_val)
               clean_sources.append(s_val)
   if len(clean_sources) >= 2:
       dc_dict["sources"] = clean_sources[:5]
       valid_conflicts.append(dc_dict)
   ```

---

## 5. Verification Method

To independently verify all findings and reproduction tests:

```powershell
.venv\Scripts\python.exe -m pytest -q -s tests/test_m3_challenger_adversarial.py
```

Expected result: 13 passed, confirming the behavior of all 5 challenges and reproducing the flaws.
