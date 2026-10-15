"""Sealed SDK/HTTP browser-backend tests; never invoke a provider."""
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Event
import httpx
import pytest
from fastapi.testclient import TestClient
from langchain_google_genai import ChatGoogleGenerativeAI
from backend.agent.analyst import create_gemini_model
from evaluations.browser_acceptance import prepare_app
from evaluations.synthetic_diagnostics import verified_synthetic_payload
from evaluations.two_question_gemini import QUESTIONS

SDK_GENERATE=ChatGoogleGenerativeAI._generate


class Clock:
    def __init__(self):self.now=0
    def __call__(self):return self.now
    def sleep(self,seconds):self.now+=seconds


def setup(monkeypatch,tmp_path,failure=None,hold=None):
    seen=[]
    def handler(request):
        body=json.loads(request.content)
        seen.append(body)
        if hold and len(seen)==1:
            hold[0].set()
            assert hold[1].wait(5)
        assert request.url.path=="/v1beta/models/gemini-3.6-flash:generateContent"
        assert body["generationConfig"]["maxOutputTokens"]==1200
        if failure=="quota" or (failure=="quota_final" and len(seen)==3):
            return httpx.Response(429,json={"error":{"code":429,"status":"RESOURCE_EXHAUSTED","message":"private quota detail"}})
        if failure=="provider":return httpx.Response(503,json={"error":{"code":503,"status":"UNAVAILABLE","message":"private provider detail"}})
        step=(len(seen)-1)%3
        if step==0:part={"functionCall":{"name":"get_statistics" if failure=="tool" else "inspect_dataset","args":{}},"thoughtSignature":"c2ln"}
        elif step==1:
            sql="DROP TABLE dataset" if failure=="sql" else "SELECT category, SUM(revenue) AS total FROM dataset GROUP BY category ORDER BY total DESC"
            part={"functionCall":{"name":"execute_sql","args":{"query":sql}},"thoughtSignature":"c2ln"}
        else:
            answer="Electronics 260; Home 150; Stationery 120." if len(seen)==3 else "Home was second with 150."
            if failure=="answer":answer="Home was second with 999."
            part={"text":answer}
        return httpx.Response(200,json={"candidates":[{"content":{"role":"model","parts":[part]},"finishReason":"STOP"}]})
    transport=httpx.MockTransport(handler)
    def constructor(**kwargs):return ChatGoogleGenerativeAI(**kwargs,client_args={"transport":transport})
    monkeypatch.setattr("backend.agent.analyst.ChatGoogleGenerativeAI",constructor)
    def generate(self,*args,**kwargs):
        assert self.client._api_client._http_options.client_args["transport"] is transport
        return SDK_GENERATE(self,*args,**kwargs)
    monkeypatch.setattr(ChatGoogleGenerativeAI,"_generate",generate)
    monkeypatch.setenv("GOOGLE_API_KEY","offline-test-secret")
    monkeypatch.setenv("GOOGLE_FREE_TIER_CONFIRMED","true")
    clock=Clock()
    app=prepare_app(approved=True,output=tmp_path/"browser.json",model_factory=create_gemini_model,clock=clock,sleeper=clock.sleep)
    return app,seen


def upload(client,payload=None):
    response=client.post("/upload",files={"file":("retail.csv",payload or verified_synthetic_payload(),"text/csv")})
    assert response.status_code==201
    return response.json()["dataset_id"]


def test_requires_execution_approval_before_any_configuration(tmp_path):
    with pytest.raises(ValueError,match="approval"):prepare_app(output=tmp_path/"no.json")


def test_full_ui_http_sequence_reset_reruns_and_extra_submissions(monkeypatch,tmp_path):
    app,seen=setup(monkeypatch,tmp_path)
    with TestClient(app) as client:
        dataset=upload(client)
        for _ in range(3):
            assert client.get("/health").status_code==200
            assert client.get(f"/dataset/{dataset}").status_code==200
        assert not seen
        first=client.post("/analyze",json={"dataset_id":dataset,"question":QUESTIONS[0]})
        assert first.status_code==200,first.text
        cid=first.json()["conversation_id"]
        second=client.post("/analyze",json={"dataset_id":dataset,"question":QUESTIONS[1],"conversation_id":cid})
        assert second.status_code==200,second.text
        assert second.json()["conversation_id"]==cid
        report=app.state.browser_report
        assert report["success"] and report["generation_attempts"]==len(seen)==6
        assert report["cases"][1]["conversation_continuity_verified"]
        assert report["cases"][1]["second_category_identified"]
        assert all(c["chart_generated"] and c["final_answer_verified"] for c in report["cases"])
        assert all(a["start_gap_seconds"] is None or a["start_gap_seconds"]>=35 for c in report["cases"] for a in c["provider_attempts"])
        assert client.delete(f"/conversation/{cid}",params={"dataset_id":dataset}).status_code==200
        assert report["reset_verified"]
        assert client.delete(f"/conversation/{cid}",params={"dataset_id":dataset}).status_code==410
        # Clearing UI or rerunning cannot reopen the analysis gate.
        assert client.post("/analyze",json={"dataset_id":dataset,"question":QUESTIONS[0]}).status_code==422
        assert len(seen)==6
        contents=(tmp_path/"browser.json").read_text()
        assert "offline-test-secret" not in contents and "private provider detail" not in contents
        assert all(len(c["final_explanation_local"]["text"].encode())<=8192 for c in report["cases"])
    with pytest.raises(ValueError,match="restarting"):prepare_app(approved=True,output=tmp_path/"browser.json")


@pytest.mark.parametrize("failure,attempts",[("provider",1),("tool",1),("sql",2),("answer",3)])
def test_failure_latches_closed_without_retries(monkeypatch,tmp_path,failure,attempts):
    app,seen=setup(monkeypatch,tmp_path,failure)
    with TestClient(app) as client:
        dataset=upload(client)
        for attempt in range(2):
            expected_status=502 if failure=="provider" and attempt==0 else 422
            assert client.post("/analyze",json={"dataset_id":dataset,"question":QUESTIONS[0]}).status_code==expected_status
        assert len(seen)==attempts and app.state.browser_report["halted"]
        assert "private provider detail" not in (tmp_path/"browser.json").read_text()


@pytest.mark.parametrize("failure",["duplicate","wrong_context","wrong_question","different_dataset"])
def test_unexpected_ui_submissions_cannot_spend_extra_budget(monkeypatch,tmp_path,failure):
    app,seen=setup(monkeypatch,tmp_path)
    with TestClient(app) as client:
        dataset=upload(client)
        first=client.post("/analyze",json={"dataset_id":dataset,"question":QUESTIONS[0]})
        assert first.status_code==200
        data={"dataset_id":dataset,"question":QUESTIONS[1],"conversation_id":first.json()["conversation_id"]}
        if failure=="duplicate":data["question"]=QUESTIONS[0]
        if failure=="wrong_context":data["conversation_id"]=None
        if failure=="wrong_question":data["question"]="Extra question"
        if failure=="different_dataset":data["dataset_id"]=upload(client)
        assert client.post("/analyze",json=data).status_code==422
        assert len(seen)==3 and app.state.browser_report["halted"]


def test_non_synthetic_data_and_exhausted_budget_never_dispatch(monkeypatch,tmp_path):
    app,seen=setup(monkeypatch,tmp_path)
    with TestClient(app) as client:
        dataset=upload(client,b"revenue\n99\n")
        assert client.post("/analyze",json={"dataset_id":dataset,"question":QUESTIONS[0]}).status_code==422
        assert not seen


def test_wire_budget_exhaustion_blocks_actual_transport(monkeypatch,tmp_path):
    app,seen=setup(monkeypatch,tmp_path)
    app.state.browser_report["generation_attempts"]=8
    with TestClient(app) as client:
        dataset=upload(client)
        assert client.post("/analyze",json={"dataset_id":dataset,"question":QUESTIONS[0]}).status_code==422
        assert not seen and app.state.browser_report["generation_attempts"]==8


def test_overlapping_submission_stops_further_generation(monkeypatch,tmp_path):
    entered,release=Event(),Event()
    app,seen=setup(monkeypatch,tmp_path,hold=(entered,release))
    with TestClient(app) as client,ThreadPoolExecutor(max_workers=1) as pool:
        dataset=upload(client)
        data={"dataset_id":dataset,"question":QUESTIONS[0]}
        first=pool.submit(client.post,"/analyze",json=data)
        try:
            assert entered.wait(5)
            assert client.post("/analyze",json=data).status_code==409
        finally:release.set()
        assert first.result(timeout=10).status_code==422
        assert len(seen)==1 and app.state.browser_report["halted"]


@pytest.mark.parametrize("failure,attempts",[("quota",1),("quota_final",3)])
def test_browser_quota_preserves_status_category_and_closes(monkeypatch,tmp_path,failure,attempts):
    app,seen=setup(monkeypatch,tmp_path,failure)
    with TestClient(app) as client:
        dataset=upload(client)
        response=client.post("/analyze",json={"dataset_id":dataset,"question":QUESTIONS[0]})
        assert response.status_code==429
        assert "quota" in response.json()["detail"].lower()
        assert "unsupported" not in response.text.lower()
        report=app.state.browser_report
        assert report["halted"] and not report["success"]
        assert report["failure_category"]=="quota_or_rate_limit"
        case=report["cases"][0]
        assert case["backend_http_status"]==429
        assert case["provider_diagnostic"]["upstream_http_status"]==429
        assert case["provider_diagnostic"]["upstream_status"]=="RESOURCE_EXHAUSTED"
        assert case["provider_attempts"][-1]["upstream_http_status"]==429
        if attempts==3:assert case["sql_results"][0]["rows"]==[["Electronics",260],["Home",150],["Stationery",120]]
        assert client.post("/analyze",json={"dataset_id":dataset,"question":QUESTIONS[0]}).status_code==429
        assert len(seen)==attempts
        contents=(tmp_path/"browser.json").read_text()
        assert "private quota detail" not in contents and "offline-test-secret" not in contents


@pytest.mark.parametrize("failure,attempts",[("quota",1),("quota_final",3)])
def test_normal_backend_and_frontend_quota_path(monkeypatch,tmp_path,failure,attempts):
    from backend.main import create_app
    from frontend.api_client import APIClient,APIClientError
    from frontend.config import FrontendSettings
    _,seen=setup(monkeypatch,tmp_path,failure)
    with TestClient(create_app()) as client:
        dataset=upload(client)
        def frontend_transport(request):
            response=client.post("/analyze",json=json.loads(request.content))
            return httpx.Response(response.status_code,json=response.json())
        api=APIClient(FrontendSettings(),transport=httpx.MockTransport(frontend_transport))
        with pytest.raises(APIClientError) as caught:api.analyze(dataset,QUESTIONS[0])
        assert caught.value.status_code==429 and len(seen)==attempts
        assert "quota" in str(caught.value).lower()
        assert "unsupported" not in str(caught.value).lower() and "private quota detail" not in str(caught.value)
