# Original User Request

## 2026-09-25T03:57:35Z

# Teamwork Project Prompt — Draft

> Status: Launched
> Goal: Craft prompt → get user approval → delegate to teamwork_preview
> Requested team: Full Team

Build a multi-agent e-commerce complaint investigation system (K4-L3A) in Python, integrating Agent-to-Agent (A2A) coordination, an MCP Gateway for evidence retrieval, and a pipeline structure. The code must be production-ready and heavily commented/annotated for educational purposes. 

Working directory: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A
Integrity mode: benchmark

## Requirements

### R1. Multi-Agent Coordination Pipeline
Implement an Agent-to-Agent (A2A) workflow (e.g., Coordinator, Order Agent, Payment Agent, Policy Agent, Verifier) inside `src/student_agent/workflow.py`. The agents must coordinate to analyze the complaint and gather evidence. The team can choose any framework or approach that works best.

### R2. LLM Integration
Use the provided NVIDIA API key (`Bearer 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`) and model (`Llama 3.1 Nemotron Safety Guard 8B v3`) để cấp nguồn cho các agent trong workflow.

### R3. MCP Gateway Integration
Agents must use the provided MCP Gateway (via tool discovery) to fetch authoritative data. Fake or guessed `evidence_ref` values are strictly prohibited. Agents must emit trace events using `trace.emit(...)` when consuming tool results.

### R4. Educational Code Comments
Every major class, function, and logical step must include detailed inline comments (bằng tiếng Việt) explaining *how* it works, *what* it does, and *why* it is necessary in that specific place, to help the user learn.

## Verification Resources
- Test suite: `pytest -q`
- E2E Validation scripts: `day09 run` and `day09 validate`

## Acceptance Criteria

### Functional Implementation
- [ ] `day09 run` executes successfully across the input cases without throwing exceptions.
- [ ] `day09 validate` passes successfully, validating that outputs match the schema and trace logs contain the correct `evidence_ref` items without hallucinations.
- [ ] Code is heavily commented for a learner to easily read and understand the "why" and "how" of the multi-agent orchestration.

## 2026-09-25T05:11:51Z

# Teamwork Project Prompt — Draft

> Status: Launched
> Goal: Craft prompt → get user approval → delegate to teamwork_preview
> Requested team: Full Team

Build a multi-agent e-commerce complaint investigation system (K4-L3A) in Python, integrating Agent-to-Agent (A2A) coordination, an MCP Gateway for evidence retrieval, and a pipeline structure. The code must be production-ready and heavily commented/annotated for educational purposes. 

Working directory: c:\Users\Lenovo\Desktop\VIN_UNI\LAB\K4-L3A-MultiAgent-MCP-A2A
Integrity mode: benchmark

## Requirements

### R1. Multi-Agent Coordination Pipeline
Implement an Agent-to-Agent (A2A) workflow (e.g., Coordinator, Order Agent, Payment Agent, Policy Agent, Verifier) inside `src/student_agent/workflow.py`. The agents must coordinate to analyze the complaint and gather evidence. The team can choose any framework or approach that works best.

### R2. LLM Integration
Use the provided NVIDIA API key (`Bearer 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`) and model (`deepseek-ai/deepseek-v4.1-flash`) để cấp nguồn cho các agent trong workflow.

### R3. MCP Gateway Integration
Agents must use the provided MCP Gateway (via tool discovery) to fetch authoritative data. Fake or guessed `evidence_ref` values are strictly prohibited. Agents must emit trace events using `trace.emit(...)` when consuming tool results.

### R4. Educational Code Comments
Every major class, function, and logical step must include detailed inline comments (bằng tiếng Việt) explaining *how* it works, *what* it does, and *why* it is necessary in that specific place, to help the user learn.

## Verification Resources
- Test suite: `pytest -q`
- E2E Validation scripts: `day09 run` and `day09 validate`

## Acceptance Criteria

### Functional Implementation
- [ ] `day09 run` executes successfully across the input cases without throwing exceptions.
- [ ] `day09 validate` passes successfully, validating that outputs match the schema and trace logs contain the correct `evidence_ref` items without hallucinations.
- [ ] Code is heavily commented for a learner to easily read and understand the "why" and "how" of the multi-agent orchestration.
- [ ] Must achieve a 99% or near-perfect score on the objective schema and validation tests.
