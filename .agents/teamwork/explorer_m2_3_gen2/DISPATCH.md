## 2026-09-25T04:50:02Z
You are Explorer M2.3 (Evidence Integration Explorer).
Your assigned working directory: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\explorer_m2_3_gen2
Original Request path: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\ORIGINAL_REQUEST.md
Scope document: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A\.agents\teamwork\PROJECT.md

MANDATORY INSTRUCTIONS:
1. First, read ORIGINAL_REQUEST.md and PROJECT.md.
2. Read schemas in `contracts/schemas/` and inspect foundation modules in `src/student_agent/`.
3. Maintain your BRIEFING.md and progress.md with 'Last visited: [timestamp]' in your assigned directory.
4. Objective: Produce a comprehensive design and implementation specification for Evidence Mapping & Trace Integration in `src/student_agent/policy.py` & `src/student_agent/specialists.py`:
   - Trace event `policy_decided`: actor `"policy-agent"`, correct payload attributes, schema adherence.
   - Trace event `handoff`: transitions between specialists and to policy agent.
   - Claim Assessment Adjudication: mapping each customer claim to a verdict (`supported`, `unsupported`, `partially_supported`, `insufficient_evidence`), confidence, and strict evidence linkage (only genuine `evidence_refs` consumed by `ToolAdapter`).
   - Cross-domain conflict detection: detecting discrepancies between order status, payment records, and carrier events. Schema requirement: `sources` array must contain at least 2 distinct domain sources (`minItems: 2`).
   - Invariant enforcement and error resilience.
   - Requirement R4: Detailed Vietnamese comments (*what*, *how*, *why*) on all functions.
5. Strictly READ-ONLY. DO NOT write or edit source code files.
6. Write your detailed findings and code specification to `handoff.md` in your working directory.
7. Send a message to caller with a summary of findings and the path to `handoff.md`.
