# BRIEFING — 2026-09-25T05:23:00Z

## Mission
Investigate `src/student_agent/llm_client.py` and its usage across `src/student_agent/` for switching to NVIDIA NIM DeepSeek v4.1-flash with the updated API key, evaluating OpenAI API compatibility, error resilience, and Vietnamese educational comments.

## 🔒 My Identity
- Archetype: explorer
- Roles: LLM Client & DeepSeek NIM Investigator
- Working directory: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\explorer_m3_1
- Original parent: fdf0e6be-87a9-40bd-9323-b9d471924980
- Milestone: M3 (LLM Client update & DeepSeek v4.1-flash NIM integration)

## 🔒 Key Constraints
- Read-only investigation — do NOT implement
- Do NOT write or modify source code files
- Write only to .agents/teamwork/explorer_m3_1/

## Current Parent
- Conversation ID: fdf0e6be-87a9-40bd-9323-b9d471924980
- Updated: 2026-09-25T05:15:35Z

## Investigation State
- **Explored paths**:
  - `ORIGINAL_REQUEST.md` (lines 41-79: timestamp 2026-09-25T05:11:51Z update)
  - `PROJECT.md` (architecture, interface contract 1, milestones)
  - `src/student_agent/llm_client.py` (840 lines)
  - `src/student_agent/specialists.py` (CoordinatorAgent, run_specialists_pipeline)
  - `src/student_agent/policy.py` (ClaimAdjudicator, PolicyEngine)
  - `src/student_agent/cli.py` & `config.py` & `submission.py`
  - `tests/test_m1_challenger_stress.py` (offline fallbacks, mock transport, test assertions)
- **Key findings**:
  1. Current `llm_client.py` uses `DEFAULT_NVIDIA_MODEL = "nvidia/llama-3.1-nemotron-safety-guard-8b-v3"` and old key `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`.
  2. Switch requires updating model to `"deepseek-ai/deepseek-v4.1-flash"` and key to `"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"`.
  3. Header prepends `Bearer `, so incoming key with `Bearer ` prefix must be sanitized in `__init__` to avoid `Bearer Bearer ...`.
  4. OpenAI compatibility confirmed for endpoint `https://integrate.api.nvidia.com/v1/chat/completions`.
  5. DeepSeek reasoning protection: add regex pre-cleaning for `<think>.*?</think>` in `_extract_json`.
  6. Existing test caveat: `tests/test_m1_challenger_stress.py:504` expects `source == "nvidia_nemotron_guard"`.
  7. Vietnamese educational annotations (WHAT, HOW, WHY) exist and need alignment with DeepSeek v4.1-flash.
- **Unexplored areas**: None within scope. All 4 prompt requirements fully investigated.

## Key Decisions Made
- Keep `source` default backward-compatible or document exact sync needed with `test_m1_challenger_stress.py`.
- Provide concrete before/after code snippets for implementer (Worker).

## Artifact Index
- `DISPATCH.md` — Inbound instruction log
- `BRIEFING.md` — Working memory and context
- `progress.md` — Liveness and status heartbeat
- `handoff.md` — Final structured handoff report
