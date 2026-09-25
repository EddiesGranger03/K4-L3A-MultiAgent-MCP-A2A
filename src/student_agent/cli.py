from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path

from .cases import load_case_set
from .config import Settings
from .contracts import Contracts
from .mcp_gateway import connect_gateway
from .model_triage import ModelTriageClient
from .submission import package_submission, validate_artifacts
from .trace import TraceWriter
from .workflow import solve_case


def _root(value: str) -> Path:
    return Path(value).resolve()


def _model_client(settings: Settings) -> ModelTriageClient | None:
    if not settings.model_id:
        return None
    assert settings.model_base_url is not None
    assert settings.model_api_key is not None
    return ModelTriageClient(
        base_url=settings.model_base_url,
        api_key=settings.model_api_key,
        model_id=settings.model_id,
    )


async def _show_tools(root: Path) -> None:
    settings = Settings.load(root)
    contracts = Contracts(root / "contracts" / "schemas")
    async with connect_gateway(settings.mcp_endpoint, settings.team_api_key, contracts) as gateway:
        for tool in await gateway.list_tools():
            print(tool)


async def _run(root: Path, *, resume: bool = False, use_model: bool = True) -> None:
    settings = Settings.load(root)
    model = _model_client(settings) if use_model else None
    case_set = load_case_set(root)
    contracts = Contracts(root / "contracts" / "schemas")
    output_root = root / "outputs"
    trace_path = root / "traces" / "trace.jsonl"
    case_trace_root = root / "traces" / "cases"
    output_root.mkdir(parents=True, exist_ok=True)
    case_trace_root.mkdir(parents=True, exist_ok=True)
    if not resume:
        for stale in output_root.glob("*.json"):
            stale.unlink()
        for stale in case_trace_root.glob("*.jsonl"):
            stale.unlink()
        trace_path.unlink(missing_ok=True)

    for case_id in case_set.case_ids:
        target = output_root / f"{case_id}.json"
        case_trace = case_trace_root / f"{case_id}.jsonl"
        if resume and target.exists() and case_trace.exists():
            previous_output = json.loads(target.read_text(encoding="utf-8"))
            contracts.validate_output(previous_output, str(target))
            if previous_output.get("case_id") != case_id:
                raise ValueError(f"{target} has a mismatched case_id")
            if not previous_output["evidence_refs"]:
                target.unlink()
                case_trace.unlink()
            else:
                previous_events = case_trace.read_text(encoding="utf-8").splitlines()
                if not previous_events or (
                    json.loads(previous_events[-1]).get("event_type") != "case_finalized"
                ):
                    raise ValueError(f"{case_trace} does not end with case_finalized")
                print(f"SKIP: {case_id}", flush=True)
                continue
        for attempt in range(1, 4):
            temporary_trace = case_trace.with_suffix(".jsonl.tmp")
            temporary_trace.unlink(missing_ok=True)
            trace = TraceWriter(temporary_trace, contracts)
            try:
                async with connect_gateway(
                    settings.mcp_endpoint, settings.team_api_key, contracts
                ) as gateway:
                    if not await gateway.list_tools():
                        raise RuntimeError("MCP Gateway returned no tools")
                    trace.emit(case_id=case_id, event_type="case_received", actor="coordinator")
                    output = await solve_case(case_set.cases[case_id], gateway, trace, model)
                contracts.validate_output(output, f"outputs/{case_id}.json")
                if output.get("case_id") != case_id:
                    raise ValueError(f"solver returned a mismatched case_id for {case_id}")
                if not output["evidence_refs"]:
                    raise RuntimeError("MCP returned no evidence for this case")
                if output["assessment"]["primary_issue"] == "insufficient_evidence" and attempt < 3:
                    raise RuntimeError("required MCP evidence was incomplete")
                trace.emit(
                    case_id=case_id,
                    event_type="case_finalized",
                    actor="coordinator",
                    evidence_refs=output["evidence_refs"][:20],
                    attributes={"primary_issue": output["assessment"]["primary_issue"]},
                )
                temporary_output = target.with_suffix(".json.tmp")
                temporary_output.write_text(
                    json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
                temporary_output.replace(target)
                temporary_trace.replace(case_trace)
                print(f"OK: {case_id}", flush=True)
                break
            except Exception as exc:
                temporary_trace.unlink(missing_ok=True)
                if attempt == 3:
                    raise RuntimeError(f"{case_id} failed after three attempts") from exc
                print(f"RETRY: {case_id} ({attempt}/3)", flush=True)
                await asyncio.sleep(attempt)

    merged = trace_path.with_suffix(".jsonl.tmp")
    with merged.open("w", encoding="utf-8") as handle:
        for case_id in case_set.case_ids:
            handle.write((case_trace_root / f"{case_id}.jsonl").read_text(encoding="utf-8"))
    merged.replace(trace_path)


async def _sample(root: Path, case_id: str, output_dir: Path) -> tuple[Path, Path, Path]:
    settings = Settings.load(root)
    model = _model_client(settings)
    if model is None:
        raise ValueError("sample requires MODEL, OPENROUTER_BASE_URL and OPENROUTER_API_KEY")
    case_set = load_case_set(root)
    if case_id not in case_set.cases:
        raise ValueError(f"case_id is not in case-set: {case_id}")
    contracts = Contracts(root / "contracts" / "schemas")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{case_id}.output.json"
    triage_path = output_dir / f"{case_id}.triage.json"
    trace_path = output_dir / f"{case_id}.trace.jsonl"
    trace_path.unlink(missing_ok=True)
    trace = TraceWriter(trace_path, contracts)
    trace.emit(case_id=case_id, event_type="case_received", actor="coordinator")
    async with connect_gateway(settings.mcp_endpoint, settings.team_api_key, contracts) as gateway:
        if not await gateway.list_tools():
            raise RuntimeError("MCP Gateway returned no tools")
        output = await solve_case(case_set.cases[case_id], gateway, trace, model)
    if model.last_result is None:
        raise RuntimeError("Model triage failed; sample output was not created")
    contracts.validate_output(output, str(output_path))
    trace.emit(
        case_id=case_id,
        event_type="case_finalized",
        actor="coordinator",
        evidence_refs=output["evidence_refs"][:20],
        attributes={"primary_issue": output["assessment"]["primary_issue"]},
    )
    output_path.write_text(
        json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    triage_path.write_text(
        json.dumps(model.last_result.public_dict(), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return output_path, triage_path, trace_path


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="Day09 L3A student workflow")
    result.add_argument("--root", default=".", help="repository root (default: current directory)")
    commands = result.add_subparsers(dest="command", required=True)
    commands.add_parser("validate-inputs", help="validate case-set.json and all 100 inputs")
    commands.add_parser("mcp-tools", help="authenticate and list discovered MCP tools")
    run = commands.add_parser("run", help="run the implemented workflow for all cases")
    run.add_argument("--resume", action="store_true", help="continue completed cases")
    run.add_argument("--no-model", action="store_true", help="skip online triage")
    sample = commands.add_parser("sample", help="run one case with model and MCP evidence")
    sample.add_argument("--case-id", default="L3A_CASE_001")
    sample.add_argument("--output-dir", default="demo")
    commands.add_parser("validate", help="validate outputs and observable trace")
    package = commands.add_parser("package", help="validate and build the submission ZIP")
    package.add_argument("--output", default="dist/submission.zip")
    return result


def main() -> None:
    args = parser().parse_args()
    root = _root(args.root)
    try:
        if args.command == "validate-inputs":
            case_set = load_case_set(root)
            print(
                f"OK: {case_set.variant_id} / {case_set.version} / {len(case_set.case_ids)} cases"
            )
        elif args.command == "mcp-tools":
            asyncio.run(_show_tools(root))
        elif args.command == "run":
            asyncio.run(_run(root, resume=args.resume, use_model=not args.no_model))
        elif args.command == "sample":
            paths = asyncio.run(_sample(root, args.case_id, root / args.output_dir))
            print("OK: " + " / ".join(str(path) for path in paths))
        elif args.command == "validate":
            case_set = load_case_set(root)
            contracts = Contracts(root / "contracts" / "schemas")
            _, trace = validate_artifacts(root, case_set, contracts)
            print(f"OK: {len(case_set.case_ids)} outputs / {len(trace)} trace events")
        elif args.command == "package":
            destination = package_submission(root, root / args.output)
            print(f"OK: {destination}")
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc


if __name__ == "__main__":
    main()
