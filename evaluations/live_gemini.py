"""Small approval-gated REAL GEMINI evaluation; never imported/run by CI."""

import argparse
import json
import time
from pathlib import Path

import pandas as pd
from fastapi.testclient import TestClient
from langchain_core.callbacks import BaseCallbackHandler

from backend.agent.analyst import AnalysisError, DataAnalysisAgent, create_gemini_model
from backend.agent.config import AgentSettings
from backend.config import APISettings
from backend.main import create_app
from frontend.charts import build_chart

ROOT = Path(__file__).resolve().parents[1]


class RequestBudget(BaseCallbackHandler):
    raise_error = True

    def __init__(self, maximum=16, interval=35):
        self.maximum = maximum
        self.interval = interval
        self.attempts = 0
        self.last_start = None

    def on_chat_model_start(self, serialized, messages, **kwargs):
        if self.attempts >= self.maximum:
            raise AnalysisError("Live evaluation request budget exhausted.", 429)
        if self.last_start is not None:
            delay = self.interval - (time.monotonic() - self.last_start)
            if delay > 0:
                time.sleep(delay)
        self.attempts += 1
        self.last_start = time.monotonic()
        print(f"REAL GEMINI generation attempt {self.attempts}/{self.maximum}", flush=True)


def expected_tables(frame):
    grouped = frame.groupby("category")["revenue"].sum().sort_values(ascending=False)
    pairs = [[name, float(value)] for name, value in grouped.items()]
    return [[[float(frame.revenue.sum())]], pairs[:1], pairs, [pairs[1]]]


def table_matches(index, rows, expected):
    # For the contextual scalar question, a model may return only its amount.
    if index == 3 and rows == [[expected[0][1]]]:
        return True
    return rows == expected


def run_live(*, approved=False, max_calls=16, interval=35):
    if not approved:
        raise ValueError("Explicit human approval for live free-tier requests is required.")
    if not 1 <= max_calls <= 16 or interval < 35:
        raise ValueError("Use at most 16 generation attempts and at least 35 seconds between attempts.")
    settings = AgentSettings.from_environment()
    # Validate key, free confirmation and routing before the HTTP harness starts.
    # Client construction does not issue a generation request.
    model = create_gemini_model(settings)
    budget = RequestBudget(maximum=max_calls, interval=interval)
    model.callbacks = [budget]
    bounded_settings = AgentSettings(
        api_key=settings.api_key, model=settings.model,
        free_tier_confirmed=settings.free_tier_confirmed,
        model_timeout_seconds=settings.model_timeout_seconds,
        max_output_tokens=settings.max_output_tokens, max_model_calls=4, max_tool_calls=3,
    )
    agent = DataAnalysisAgent(settings=bounded_settings, model_factory=lambda _: model)
    path = ROOT / "data/sample/retail_sales.csv"
    frame = pd.read_csv(path)
    expected = expected_tables(frame)
    questions = [
        "What is the total revenue? Return the total as a single numeric value in the SQL table.",
        "Which category has the highest total revenue? Return its category and total revenue.",
        "List total revenue grouped by category, ordered highest to lowest. Return category and total revenue.",
        "How much revenue did the second category in that list generate?",
    ]
    report = {"label":"REAL GEMINI - synthetic retail only", "model":settings.model,
              "free_tier":"human-confirmed; billing not programmatically verified",
              "request_budget":max_calls, "generation_attempts":0, "cases":[],
              "human_explanation_and_browser_review_required":True}
    output = ROOT / ".tmp/gemini-live-evaluation.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    conversation_id = None
    with TestClient(create_app(APISettings(temporary_directory=ROOT/".tmp/live-uploads"), analyzer=agent)) as client:
        upload = client.post("/upload",files={"file":(path.name,path.read_bytes(),"text/csv")})
        upload.raise_for_status()
        dataset_id = upload.json()["dataset_id"]
        for index, question in enumerate(questions):
            response = client.post("/analyze",json={"dataset_id":dataset_id,"question":question,"conversation_id":conversation_id})
            item = {"question":question,"http_status":response.status_code,"expected":expected[index],"passed":False}
            if response.status_code == 200:
                data = response.json()
                item["result"] = data
                chart = build_chart(data["columns"],data["rows"])
                item["chart_type"] = chart.kind
                item["passed"] = (table_matches(index,data["rows"],expected[index])
                                  and data["tools_used"][0:1]==["inspect_dataset"]
                                  and "execute_sql" in data["tools_used"] and bool(data["sql"])
                                  and (conversation_id is None or data["conversation_id"]==conversation_id))
                conversation_id = data["conversation_id"]
                if index == 2:
                    item["passed"] = item["passed"] and chart.figure is not None
                    if chart.figure is not None:
                        chart.figure.write_html(ROOT/".tmp/gemini-category-chart.html",include_plotlyjs=True)
            else:
                # The API returns sanitized errors, not raw SDK errors or keys.
                item["error"] = response.json().get("detail","Analysis failed.")
            report["cases"].append(item)
            report["generation_attempts"] = budget.attempts
            output.write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False),encoding="utf-8")
            print(f"Case {index+1}: {'PASS' if item['passed'] else 'FAIL'} (HTTP {response.status_code})",flush=True)
            if not item["passed"]:
                break
    report["success"] = len(report["cases"])==4 and all(item["passed"] for item in report["cases"])
    output.write_text(json.dumps(report,indent=2,ensure_ascii=False,allow_nan=False),encoding="utf-8")
    return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approve-live-free-tier",action="store_true")
    parser.add_argument("--max-calls",type=int,default=16)
    args=parser.parse_args()
    report=run_live(approved=args.approve_live_free_tier,max_calls=args.max_calls)
    print(f"REAL GEMINI: {sum(c['passed'] for c in report['cases'])}/4; {report['generation_attempts']} generation attempts")
    raise SystemExit(0 if report["success"] else 1)


if __name__=="__main__":
    main()
