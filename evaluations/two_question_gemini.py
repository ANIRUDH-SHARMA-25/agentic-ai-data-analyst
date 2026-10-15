"""Approval-gated synthetic retail cases; optional first-question-only diagnostic."""
import argparse
import json
import io
import logging
import time
import warnings
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
from fastapi.testclient import TestClient
from langchain.agents.middleware import after_model
from langsmith import tracing_context

import backend.agent.analyst as analyst
from backend.agent.config import AgentSettings
from backend.config import APISettings
from backend.main import create_app
from frontend.charts import build_chart
from evaluations.retail_explanations import explanation_checks
from evaluations.synthetic_diagnostics import verified_synthetic_payload, bounded_explanation, console_summary, redact

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / ".tmp/gemini36-two-question-2026-10-15.json"
QUESTIONS = (
    "List total revenue grouped by category, ordered highest to lowest.",
    "How much revenue did the second category in that list generate?",
)


class WireBudget:
    """Only this endpoint is permitted; count failed attempts too, before dispatch."""
    def __init__(self, report, save, *, clock=time.monotonic, sleeper=time.sleep):
        self.report, self.save, self.clock, self.sleeper = report, save, clock, sleeper
        self.last_start = None
        self.current = None

    def request(self, request):
        if (request.method != "POST" or request.url.host != "generativelanguage.googleapis.com"
                or request.url.path != "/v1beta/models/gemini-3.6-flash:generateContent"):
            raise analyst.AnalysisError("Unexpected provider endpoint blocked.", 422)
        if self.report["generation_attempts"] >= self.report["request_budget"] or self.current["generation_attempts"] >= 4:
            self.current["failure_category"] = "request_budget_exhausted"
            raise analyst.AnalysisError("Evaluation request budget exhausted.", 429)
        if self.last_start is not None:
            delay = 35 - (self.clock() - self.last_start)
            if delay > 0:
                self.sleeper(delay)
        now = self.clock()
        gap = None if self.last_start is None else now - self.last_start
        self.last_start = now
        self.report["generation_attempts"] += 1
        self.current["generation_attempts"] += 1
        self.current["provider_attempts"].append({"start_gap_seconds": gap, "upstream_http_status": None})
        self.save()

    def response(self, response):
        self.current["provider_attempts"][-1]["upstream_http_status"] = response.status_code
        self.save()


def matches(index, rows, expected):
    """Validate ordered numerical evidence, independently of the final answer."""
    if index == 0:
        return rows == expected[0]
    return rows in (expected[1], [[expected[1][0][1]]], expected[0])



def assess_case(index, data, case, expected, conversation_id):
    """Keep fresh SQL evidence, explanation correctness and continuity separate."""
    checks = explanation_checks(index, data["answer"], expected)
    same = bool(data.get("conversation_id")) and (conversation_id is None or data["conversation_id"] == conversation_id)
    context_ok = index == 0 or (same and case["prior_context_present"] and case["prior_grouped_result_matches"])
    execution_ok = (case["tools_used"] == data["tools_used"] == ["inspect_dataset", "execute_sql"]
                    and len(case["sql_results"]) == 1 and bool(data["sql"]))
    if execution_ok:
        result = case["sql_results"][0]
        execution_ok = (data["sql"] == result["sql"] and data["rows"] == result["rows"]
                        and data["columns"] == result["columns"])
    numeric_ok = execution_ok and matches(index, data["rows"], expected)
    answer_ok = (checks["expected_facts_present"] and checks["numerical_claims_supported"]
                 and (index == 0 or checks["second_category_identified"]))
    return {**checks, "same_conversation": same, "sql_execution_verified": execution_ok,
            "numerical_evidence_valid": numeric_ok, "conversation_continuity_verified": context_ok,
            "final_answer_verified": bool(answer_ok)}


def run_two(*, approved=False, output=OUTPUT, model_factory=analyst.create_gemini_model,
            clock=time.monotonic, sleeper=time.sleep, first_question_only=False):
    if not approved:
        raise ValueError("Explicit approval for this bounded free-tier run is required.")
    output = Path(output).resolve()
    if not output.is_relative_to(ROOT / ".tmp"):
        raise ValueError("Reports and synthetic explanations must stay under repository .tmp.")
    if output.exists():
        raise ValueError("Existing report prevents repeating the evaluation.")
    settings = replace(AgentSettings.from_environment(), model_timeout_seconds=60,
                       max_output_tokens=1200, max_model_calls=4, max_tool_calls=3)
    payload = verified_synthetic_payload()
    frame = pd.read_csv(io.BytesIO(payload))
    ranked = frame.groupby("category")["revenue"].sum().sort_values(ascending=False)
    expected = [[[name, int(value)] for name, value in ranked.items()], [[ranked.index[1], int(ranked.iloc[1])]]]
    assert expected == [[["Electronics",260],["Home",150],["Stationery",120]],[["Home",150]]]
    questions = QUESTIONS[:1] if first_question_only else QUESTIONS
    report = {"label":"REAL GEMINI - synthetic retail only", "question_count":len(questions), "model":settings.model,
              "free_tier":"fresh human confirmation; billing disabled; not programmatically audited",
              "request_budget":4 * len(questions), "per_question_budget":4, "minimum_start_interval_seconds":35,
              "timeout_seconds":60, "maximum_output_tokens":1200, "retries":0,
              "generation_attempts":0, "cases":[], "success":False}
    output.parent.mkdir(parents=True, exist_ok=True)
    def save():
        output.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    budget = WireBudget(report, save, clock=clock, sleeper=sleeper)
    model = model_factory(settings)
    prepared = model._prepare_request([analyst.HumanMessage(content=QUESTIONS[0])])["config"]
    assert settings.model == "gemini-3.6-flash" and model.model == settings.model
    assert not model.client.vertexai and not getattr(model.client, "enterprise", False)
    assert prepared.http_options.timeout == 60000 and prepared.http_options.retry_options.attempts == 0
    assert prepared.max_output_tokens == 1200
    model.client._api_client._httpx_client.event_hooks = {"request":[budget.request], "response":[budget.response]}
    original_create = analyst.create_agent
    original_sql = analyst.execute_safe_sql
    index = 0

    def fail(category, detail):
        budget.current["failure_category"] = category
        raise analyst.AnalysisError(detail, 422)

    @after_model
    def strict_selection(state, runtime):
        message = state["messages"][-1]
        calls = getattr(message, "tool_calls", [])
        if getattr(message, "invalid_tool_calls", []):
            fail("invalid_tool_call", "Invalid tool call; evaluation stopped.")
        finish = message.response_metadata.get("finish_reason")
        if finish not in {None, "STOP"}:
            fail("incomplete_generation", "Generation did not complete; evaluation stopped.")
        if calls:
            completed = budget.current["tools_used"]
            expected_name = "inspect_dataset" if not completed else "execute_sql"
            if (len(calls) != 1 or len(completed) >= 2 or calls[0]["name"] != expected_name
                    or set(calls[0]["args"]) != (set() if expected_name == "inspect_dataset" else {"query"})):
                fail("unexpected_tool_call", "Unexpected tool selection; evaluation stopped.")
        elif budget.current["tools_used"] != ["inspect_dataset", "execute_sql"]:
            fail("missing_tool_evidence", "Expected fresh tool evidence is missing.")

    def strict_create(*args, **kwargs):
        for tool in kwargs["tools"]:
            original = tool.func
            name = tool.name
            def wrap(original=original, name=name):
                def execute(*args, **kwargs):
                    budget.current["tools_used"].append(name)
                    save()
                    return original(*args, **kwargs)
                return execute
            tool.func = wrap()
        kwargs["middleware"] = [*kwargs["middleware"], strict_selection]
        graph = original_create(*args, **kwargs)
        def invoke(*args, config=None, **kwargs):
            # The evaluation-only guard adds graph steps; HTTP/model budgets
            # remain four per question, with the selected global cap enforced.
            return graph.invoke(*args, config={**(config or {}), "recursion_limit":32}, **kwargs)
        return SimpleNamespace(invoke=invoke)

    def strict_sql(*args, **kwargs):
        try:
            result = original_sql(*args, **kwargs)
        except analyst.SQLValidationError:
            fail("sql_validation_failure", "SQL validation failed; no correction or retry permitted.")
        except analyst.SQLExecutionError:
            fail("sql_execution_failure", "SQL execution failed; evaluation stopped.")
        budget.current["sql_results"].append(result)
        save()
        budget.current["numerical_evidence_valid"] = matches(index, result["rows"], expected)
        if not budget.current["numerical_evidence_valid"]:
            fail("incorrect_numerical_result", "SQL results differ from independent expectations.")
        return result

    class EvaluationAgent(analyst.DataAnalysisAgent):
        def analyze(self, frame, question, *, prior_context=None):
            budget.current["prior_context_present"] = bool(prior_context)
            budget.current["prior_grouped_result_matches"] = bool(prior_context and prior_context[-1].get("rows") == expected[0])
            try:
                return super().analyze(frame, question, prior_context=prior_context)
            except analyst.AnalysisError as exc:
                budget.current["provider_diagnostic"] = exc.provider_diagnostic
                budget.current["application_error"] = str(exc)
                if not budget.current.get("failure_category"):
                    budget.current["failure_category"] = "provider_error" if exc.provider_diagnostic else "application_error"
                raise

    previous_logging = logging.root.manager.disable
    logging.disable(logging.CRITICAL)
    save()
    try:
        with warnings.catch_warnings(), tracing_context(enabled=False), patch.object(analyst,"create_agent",strict_create), patch.object(analyst,"execute_safe_sql",strict_sql):
            warnings.simplefilter("ignore")
            agent = EvaluationAgent(settings=settings, model_factory=lambda _: model)
            app = create_app(APISettings(temporary_directory=output.parent/"two-case-uploads"), analyzer=agent)
            with TestClient(app) as client:
                uploaded = client.post("/upload",files={"file":("retail_sales.csv",payload,"text/csv")})
                uploaded.raise_for_status()
                dataset_id = uploaded.json()["dataset_id"]
                conversation_id = None
                for index, question in enumerate(questions):
                    case = {"case_index":index+1, "generation_attempts":0, "provider_attempts":[],
                            "tools_used":[], "sql_results":[], "passed":False, "chart_generated":False,
                            "numerical_evidence_valid":False, "final_answer_verified":False,
                            "conversation_continuity_verified":False}
                    report["cases"].append(case)
                    budget.current = case
                    save()
                    response = client.post("/analyze",json={"dataset_id":dataset_id,"question":question,"conversation_id":conversation_id})
                    case["backend_http_status"] = response.status_code
                    if response.status_code != 200:
                        save()
                        break
                    data = response.json()
                    case["sql"] = data["sql"]
                    case["columns"], case["rows"] = data["columns"], data["rows"]
                    case["final_explanation_local"] = bounded_explanation(data["answer"],secrets=(settings.api_key,))
                    case.update(assess_case(index, data, case, expected, conversation_id))
                    for failure in case["validation_failures"]:
                        failure["claim_excerpt"] = redact(failure["claim_excerpt"],secrets=(settings.api_key,))
                    chart = build_chart(data["columns"], data["rows"])
                    case["chart_generated"] = chart.figure is not None
                    case["chart_type"] = chart.kind
                    if index == 0 and chart.figure is not None:
                        chart_path = output.with_name(output.stem + "-chart.html")
                        chart.figure.write_html(chart_path, include_plotlyjs=True)
                        case["chart_file"] = chart_path.name
                    case["passed"] = (case["numerical_evidence_valid"] and case["sql_execution_verified"]
                                      and case["conversation_continuity_verified"] and case["final_answer_verified"]
                                      and (index != 0 or case["chart_generated"]))
                    if not case["passed"]:
                        case["failure_category"] = "answer_context_or_chart_check_failed"
                    conversation_id = data["conversation_id"]
                    save()
                    if not case["passed"]:
                        break
        report["success"] = len(report["cases"]) == len(questions) and all(c["passed"] for c in report["cases"])
    except Exception:
        report["failure_category"] = "evaluation_application_error"
    finally:
        save()
        model.client.close()
        logging.disable(previous_logging)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approve-two-question-free-tier", action="store_true")
    parser.add_argument("--first-question-only", action="store_true", help="Only grouped revenue; hard maximum four generation attempts. Requires separate approval.")
    parser.add_argument("--output", type=Path, default=OUTPUT, help="Fresh report path under the repository .tmp directory.")
    args = parser.parse_args()
    if not args.output.resolve().is_relative_to(ROOT / ".tmp"):
        parser.error("Reports must stay in the repository .tmp directory.")
    try:
        result = run_two(approved=args.approve_two_question_free_tier, output=args.output, first_question_only=args.first_question_only)
    except Exception:
        print("Evaluation stopped before completion; raw details suppressed.")
        raise SystemExit(1)
    print(json.dumps(console_summary(result)))
    raise SystemExit(0 if result["success"] else 1)


if __name__ == "__main__":
    main()
