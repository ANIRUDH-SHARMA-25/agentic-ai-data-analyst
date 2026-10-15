"""Approval, wire budgets and the exact two-case runner; all provider I/O mocked."""
import json
import httpx
import pytest
from langchain_google_genai import ChatGoogleGenerativeAI
from backend.agent.analyst import AnalysisError, create_gemini_model
from evaluations.two_question_gemini import QUESTIONS, WireBudget, run_two

SDK_GENERATE = ChatGoogleGenerativeAI._generate


class FakeClock:
    def __init__(self):
        self.now = 0.
    def __call__(self):
        return self.now
    def sleep(self, delay):
        self.now += delay


def test_wire_budget_limits_and_interval():
    clock = FakeClock()
    report = {"generation_attempts":0,"request_budget":8}
    budget = WireBudget(report,lambda:None,clock=clock,sleeper=clock.sleep)
    request = httpx.Request("POST","https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent")
    gaps = []
    for _ in range(2):
        budget.current = {"generation_attempts":0,"provider_attempts":[]}
        for _ in range(4):
            budget.request(request)
        gaps += [a["start_gap_seconds"] for a in budget.current["provider_attempts"]]
        with pytest.raises(AnalysisError,match="budget"):
            budget.request(request)
    assert report["generation_attempts"] == 8
    assert gaps[0] is None and all(gap >= 35 for gap in gaps[1:])
    budget.current = {"generation_attempts":0,"provider_attempts":[]}
    with pytest.raises(AnalysisError,match="budget"):
        budget.request(request)
    assert budget.current["generation_attempts"] == 0
    with pytest.raises(AnalysisError,match="endpoint"):
        budget.request(httpx.Request("GET","https://generativelanguage.googleapis.com/v1beta/models"))


def test_two_case_approval_precedes_model(tmp_path):
    assert QUESTIONS == ("List total revenue grouped by category, ordered highest to lowest.",
                         "How much revenue did the second category in that list generate?")
    with pytest.raises(ValueError,match="approval"):
        run_two(output=tmp_path/"report.json")


@pytest.mark.parametrize("failure,expected_attempts",[("first_question_only",3),(None,6),("full_table_followup",6),("scalar_followup",6),("followup_wrong_order",5),("followup_wrong_value",5),("followup_wrong_answer",6),("followup_wrong_rank",6),("provider",1),("tool",1),("sql",2),("wrong_sql_result",2),("wrong_answer",3),("truncation",1)])
def test_actual_sdk_two_case_runner_offline(monkeypatch,tmp_path,failure,expected_attempts):
    seen = []
    def handler(request):
        body = json.loads(request.content)
        seen.append(body)
        assert body["generationConfig"]["maxOutputTokens"] == 1200
        assert not any(d.get("name") not in {"inspect_dataset","get_statistics","execute_sql"} for t in body["tools"] for d in t["functionDeclarations"])
        if failure == "provider":
            return httpx.Response(503,json={"error":{"code":503,"status":"UNAVAILABLE","message":"private raw details"}})
        step = (len(seen)-1)%3
        question = (len(seen)-1)//3
        if step == 0:
            part = {"functionCall":{"name":"get_statistics" if failure=="tool" else "inspect_dataset","args":{}},"thoughtSignature":"c2ln"}
        elif step == 1:
            sql = "SELECT category, SUM(revenue) AS total FROM dataset GROUP BY category ORDER BY total DESC" if question==0 else "SELECT category, SUM(revenue) AS total FROM dataset WHERE category = 'Home' GROUP BY category"
            if question == 1:
                if failure in {"full_table_followup","followup_wrong_answer","followup_wrong_rank"}:
                    sql = "SELECT category, SUM(revenue) AS total FROM dataset GROUP BY category ORDER BY total DESC"
                if failure == "scalar_followup":
                    sql = "SELECT SUM(revenue) AS total FROM dataset WHERE category = 'Home'"
                if failure == "followup_wrong_order":
                    sql = "SELECT category, SUM(revenue) AS total FROM dataset GROUP BY category ORDER BY total ASC"
                if failure == "followup_wrong_value":
                    sql = "SELECT category, SUM(revenue) + 1 AS total FROM dataset WHERE category = 'Home' GROUP BY category"
            if failure == "sql":sql = "DROP TABLE dataset"
            if failure == "wrong_sql_result":sql = "SELECT SUM(revenue) FROM dataset"
            part = {"functionCall":{"name":"execute_sql","args":{"query":sql}},"thoughtSignature":"c2ln"}
        else:
            answer = "Electronics 260, Home 150, Stationery 120." if question==0 else "Home was the second category and generated 150."
            if failure=="wrong_answer":answer="Electronics generated 999."
            if question == 1 and failure == "followup_wrong_answer":answer="The second category was Electronics with 260. Home generated 150."
            if question == 1 and failure == "followup_wrong_rank":answer="Home was the first category and generated 150."
            part={"text":answer}
        return httpx.Response(200,json={"modelVersion":"gemini-3.6-flash","candidates":[{"content":{"role":"model","parts":[part]},"finishReason":"MAX_TOKENS" if failure=="truncation" else "STOP"}]})
    transport=httpx.MockTransport(handler)
    def constructor(**kwargs):
        return ChatGoogleGenerativeAI(**kwargs,client_args={"transport":transport})
    monkeypatch.setattr("backend.agent.analyst.ChatGoogleGenerativeAI",constructor)
    def generate(self,*args,**kwargs):
        assert self.client._api_client._http_options.client_args["transport"] is transport
        return SDK_GENERATE(self,*args,**kwargs)
    monkeypatch.setattr(ChatGoogleGenerativeAI,"_generate",generate)
    monkeypatch.setenv("GOOGLE_API_KEY","offline-fake-key")
    monkeypatch.setenv("GOOGLE_FREE_TIER_CONFIRMED","true")
    clock=FakeClock()
    output=tmp_path/"report.json"
    result=run_two(approved=True,output=output,model_factory=create_gemini_model,clock=clock,sleeper=clock.sleep,first_question_only=failure=="first_question_only")
    assert result["generation_attempts"] == len(seen) == expected_attempts
    successful = failure in {"first_question_only",None,"full_table_followup","scalar_followup"}
    followup_failure = failure is not None and failure.startswith("followup_")
    assert result["success"] is successful
    assert len(result["cases"]) == (2 if (successful and failure!="first_question_only") or followup_failure else 1)
    assert "offline-fake-key" not in output.read_text() and "private raw details" not in output.read_text()
    for case in result["cases"]:
        if case.get("backend_http_status")==200:
            assert case["final_explanation_local"]["synthetic_dataset_only"]
            assert case["final_explanation_local"]["text"]
            assert len(case["final_explanation_local"]["text"].encode("utf-8"))<=8192
    if failure in {"wrong_answer","followup_wrong_answer","followup_wrong_rank"}:
        assert result["cases"][-1]["validation_failures"]
    if failure=="first_question_only":
        assert result["request_budget"]==4 and result["question_count"]==1
        assert result["cases"][0]["chart_generated"]
        assert all("How much revenue did the second" not in json.dumps(body) for body in seen)
    if successful and failure!="first_question_only":
        assert [case["generation_attempts"] for case in result["cases"]] == [3,3]
        assert result["cases"][0]["chart_generated"]
        assert result["cases"][1]["same_conversation"] and result["cases"][1]["prior_grouped_result_matches"]
        expected_rows = ([["Electronics",260],["Home",150],["Stationery",120]] if failure=="full_table_followup"
                         else [[150]] if failure=="scalar_followup" else [["Home",150]])
        assert result["cases"][1]["rows"] == expected_rows
        assert result["cases"][1]["final_answer_verified"]
        assert result["cases"][1]["numerical_evidence_valid"]
        assert all(case["tools_used"]==["inspect_dataset","execute_sql"] for case in result["cases"])
        assert output.with_name(output.stem + "-chart.html").exists()
    with pytest.raises(ValueError,match="Existing report"):
        run_two(approved=True,output=output)
    assert len(seen)==expected_attempts


EXPECTED = [[["Electronics",260],["Home",150],["Stationery",120]],[["Home",150]]]


@pytest.mark.parametrize("rows,valid", [
    ([["Home",150]],True), ([[150]],True),
    (EXPECTED[0],True),
    ([["Home",150],["Electronics",260],["Stationery",120]],False),
    ([["Stationery",120],["Home",150],["Electronics",260]],False),
    ([["Electronics",260],["Home",151],["Stationery",120]],False),
    ([["Electronics",260],["Home",150]],False),
    ([["Home",150],["Home",150]],False), ([["Home",-150]],False),
])
def test_followup_evidence_shapes_and_order(rows,valid):
    from evaluations.two_question_gemini import matches
    assert matches(1,rows,EXPECTED) is valid


@pytest.mark.parametrize("answer,valid", [
    ("Home was the second category and generated 150.",True),
    ("The second-highest category is Home with revenue 150.",True),
    ("Home ranked #2, generating $150.00.",True),
    ("Home is second with 150, behind Electronics with 260.",True),
    ("Electronics was first with 260; Home was second with 150; Stationery was third with 120.",True),
    ("Electronics 260, Home 150, Stationery 120.",False),
    ("Home generated 150.",False),
    ("The second category was Electronics with 260. Home generated 150.",False),
    ("Home was first with 150.",False),
    ("Home was second with -150.",False),
    ("Home was second with 1500.",False),
    ("Home was second but did not generate 150.",False),
    ("Home was second with 150 million.",False),
    ("Home was second with 120, while Stationery generated 150.",False),
    ("",False),
])
def test_followup_answer_requires_correct_association_and_rank(answer,valid):
    from evaluations.two_question_gemini import explanation_checks
    checks=explanation_checks(1,answer,EXPECTED)
    assert bool(checks["expected_facts_present"] and checks["numerical_claims_supported"] and checks["second_category_identified"]) is valid


def test_swapped_category_amounts_do_not_pass_name_number_mentions():
    from evaluations.two_question_gemini import explanation_checks
    checks=explanation_checks(0,"Electronics 150, Home 260, Stationery 120.",EXPECTED)
    assert not checks["expected_facts_present"]


@pytest.mark.parametrize("broken",["none","id","context","prior_result","tools","sql_trace","sql_text","table_only"])
def test_continuity_execution_and_answer_are_separate(broken):
    from copy import deepcopy
    from evaluations.two_question_gemini import assess_case
    data={"answer":"Home was second with 150.","conversation_id":"same", "sql":"SELECT category, total FROM dataset", "columns":["category","total"], "rows":deepcopy(EXPECTED[0]), "tools_used":["inspect_dataset","execute_sql"]}
    case={"tools_used":list(data["tools_used"]),"sql_results":[{key:deepcopy(data[key]) for key in ("sql","columns","rows")}],"prior_context_present":True,"prior_grouped_result_matches":True}
    if broken=="id":data["conversation_id"]="different"
    if broken=="context":case["prior_context_present"]=False
    if broken=="prior_result":case["prior_grouped_result_matches"]=False
    if broken=="tools":case["tools_used"]=["inspect_dataset"]
    if broken=="sql_trace":case["sql_results"]=[]
    if broken=="sql_text":data["sql"]="SELECT different FROM dataset"
    if broken=="table_only":data["answer"]="Electronics 260, Home 150, Stationery 120."
    checks=assess_case(1,data,case,EXPECTED,"same")
    passed=all(checks[k] for k in ("numerical_evidence_valid","sql_execution_verified","conversation_continuity_verified","final_answer_verified"))
    assert passed is (broken=="none")
    if broken in {"id","context","prior_result"}:
        assert checks["final_answer_verified"] and not checks["conversation_continuity_verified"]
    if broken=="table_only":
        assert checks["numerical_evidence_valid"] and checks["conversation_continuity_verified"] and not checks["final_answer_verified"]


def test_single_question_global_budget_is_hard():
    clock=FakeClock()
    report={"generation_attempts":0,"request_budget":4}
    budget=WireBudget(report,lambda:None,clock=clock,sleeper=clock.sleep)
    request=httpx.Request("POST","https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent")
    budget.current={"generation_attempts":0,"provider_attempts":[]}
    for _ in range(4):budget.request(request)
    budget.current={"generation_attempts":0,"provider_attempts":[]}
    with pytest.raises(AnalysisError,match="budget"):budget.request(request)
    assert report["generation_attempts"]==4
