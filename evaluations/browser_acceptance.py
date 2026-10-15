"""Evaluation-only localhost backend. Never start live without separate approval."""
import argparse
import asyncio
import io
import json
import logging
import time
from contextlib import asynccontextmanager
from dataclasses import replace
from pathlib import Path
from threading import Lock
from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
from fastapi.responses import JSONResponse
from langchain.agents.middleware import after_model
from langsmith import tracing_context

import backend.agent.analyst as analyst
from backend.agent.config import AgentSettings
from backend.config import APISettings
from backend.main import create_app
from frontend.charts import build_chart
from evaluations.synthetic_diagnostics import ROOT, bounded_explanation, redact, verified_synthetic_payload
from evaluations.two_question_gemini import QUESTIONS, WireBudget, assess_case, matches

QUOTA_MESSAGE = "Gemini free-tier quota or rate limit was reached. Wait for quota availability; no automatic retry or paid fallback was used."

EXPECTED = [[["Electronics",260],["Home",150],["Stationery",120]],[["Home",150]]]


def prepare_app(*, approved=False, output=None, model_factory=analyst.create_gemini_model,
                clock=time.monotonic, sleeper=time.sleep):
    if not approved:
        raise ValueError("Separate execution approval and current Free-tier confirmation are required.")
    settings=replace(AgentSettings.from_environment(),model_timeout_seconds=60,
                     max_output_tokens=1200,max_model_calls=4,max_tool_calls=3)
    if not settings.free_tier_confirmed or not settings.api_key:
        raise ValueError("Backend key and current Free-tier confirmation are required.")
    output=Path(output or ROOT/".tmp/browser-acceptance-live.json").resolve()
    if not output.is_relative_to(ROOT/".tmp") or output.exists():
        raise ValueError("Use a fresh report under the repository .tmp; restarting this run is prohibited.")
    frame=pd.read_csv(io.BytesIO(verified_synthetic_payload()))
    report={"label":"BOUNDED BROWSER - synthetic retail only","model":settings.model,
            "request_budget":8,"per_question_budget":4,"generation_attempts":0,
            "minimum_start_interval_seconds":35,"timeout_seconds":60,"maximum_output_tokens":1200,
            "retries":0,"cases":[],"success":False,"halted":False,"reset_verified":False}
    output.parent.mkdir(parents=True,exist_ok=True)
    save_lock=Lock()
    def save():
        with save_lock:
            pending=output.with_suffix(".pending.json")
            pending.write_text(json.dumps(report,indent=2,allow_nan=False),encoding="utf-8")
            pending.replace(output)
    # Reserve the report before model construction. Even a process restart cannot reset its budget.
    with output.open("x",encoding="utf-8") as stream:json.dump(report,stream)
    budget=WireBudget(report,save,clock=clock,sleeper=sleeper)
    dataset_id=conversation_id=None
    index=0
    model=None
    def stop(category):
        report["halted"]=True
        report["failure_category"]=category
        save()
        raise analyst.AnalysisError("Browser evaluation stopped; review the local diagnostic report.",422)

    class GuardedAgent(analyst.DataAnalysisAgent):
        def analyze(self,current_frame,question,*,prior_context=None):
            nonlocal model
            case=budget.current
            if not current_frame.equals(frame):stop("non_synthetic_dataset")
            case["prior_context_present"]=bool(prior_context)
            case["prior_grouped_result_matches"]=bool(prior_context and prior_context[-1].get("rows")==EXPECTED[0])
            if index==1 and not case["prior_grouped_result_matches"]:stop("missing_prior_context")
            try:
                if model is None:
                    model=model_factory(settings)
                    prepared=model._prepare_request([analyst.HumanMessage(content=QUESTIONS[0])])["config"]
                    assert settings.model==model.model=="gemini-3.6-flash"
                    assert not model.client.vertexai and not getattr(model.client,"enterprise",False)
                    assert prepared.http_options.timeout==60000
                    assert prepared.http_options.retry_options.attempts==0
                    assert prepared.max_output_tokens==1200
                    model.client._api_client._httpx_client.event_hooks={"request":[budget.request],"response":[budget.response]}
                original_create=analyst.create_agent
                original_sql=analyst.execute_safe_sql
                @after_model
                def strict_selection(state,runtime):
                    message=state["messages"][-1]
                    calls=getattr(message,"tool_calls",[])
                    if getattr(message,"invalid_tool_calls",[]):stop("invalid_tool_call")
                    if message.response_metadata.get("finish_reason") not in {None,"STOP"}:stop("incomplete_generation")
                    completed=case["tools_used"]
                    if calls:
                        name="inspect_dataset" if not completed else "execute_sql"
                        if (len(calls)!=1 or len(completed)>=2 or calls[0]["name"]!=name
                            or set(calls[0]["args"])!=(set() if name=="inspect_dataset" else {"query"})):
                            stop("unexpected_tool_call")
                    elif completed!=["inspect_dataset","execute_sql"]:stop("missing_tool_evidence")
                def strict_create(*args,**kwargs):
                    for tool in kwargs["tools"]:
                        original,name=tool.func,tool.name
                        def wrap(*a,_fn=original,_name=name,**kw):
                            case["tools_used"].append(_name)
                            save()
                            return _fn(*a,**kw)
                        tool.func=wrap
                    kwargs["middleware"]=[*kwargs["middleware"],strict_selection]
                    graph=original_create(*args,**kwargs)
                    def invoke(*a,config=None,**kw):
                        return graph.invoke(*a,config={**(config or {}),"recursion_limit":32},**kw)
                    return SimpleNamespace(invoke=invoke)
                def strict_sql(*args,**kwargs):
                    try:result=original_sql(*args,**kwargs)
                    except (analyst.SQLValidationError,analyst.SQLExecutionError):stop("sql_failure")
                    case["sql_results"].append(result)
                    save()
                    if not matches(index,result["rows"],EXPECTED):stop("incorrect_numerical_result")
                    return result
                with patch.object(analyst,"create_agent",strict_create),patch.object(analyst,"execute_safe_sql",strict_sql),tracing_context(enabled=False):
                    return super().analyze(current_frame,question,prior_context=prior_context)
            except Exception as exc:
                report["halted"]=True
                diagnostic=getattr(exc,"provider_diagnostic",None)
                case["provider_diagnostic"]=diagnostic
                report.setdefault("failure_category",diagnostic["category"] if diagnostic else case.get("failure_category","application_error"))
                # Preserve provider mapping. Local budget/validation failures remain 422.
                status=getattr(exc,"status_code",502) if diagnostic else 422
                if status not in {429,502,503,504}:status=502 if diagnostic else 422
                message=QUOTA_MESSAGE if diagnostic and diagnostic["upstream_http_status"]==429 else "Browser evaluation stopped; sanitized diagnostics saved."
                save()
                raise analyst.AnalysisError(message,status) from None

    app=create_app(APISettings(temporary_directory=output.parent/"browser-uploads"),
                   analyzer=GuardedAgent(settings=settings,model_factory=lambda _:model))
    lock=asyncio.Lock()
    @app.middleware("http")
    async def guard(request,call_next):
        nonlocal dataset_id,conversation_id,index
        if request.method=="DELETE" and request.url.path.startswith("/conversation/"):
            response=await call_next(request)
            if (response.status_code==200 and report["success"]
                and request.url.path==f"/conversation/{conversation_id}"
                and request.query_params.get("dataset_id")==dataset_id):
                report["reset_verified"]=True
                save()
            return response
        if request.method!="POST" or request.url.path!="/analyze":return await call_next(request)
        if report["halted"] or report["success"]:
            status=429 if report.get("failure_category")=="quota_or_rate_limit" else 422
            detail=QUOTA_MESSAGE if status==429 else "This evaluation is closed; no more analysis requests are permitted."
            return JSONResponse({"detail":detail},status_code=status)
        if lock.locked():
            report["halted"]=True
            report["failure_category"]="overlapping_submission"
            save()
            return JSONResponse({"detail":"Overlapping analysis blocked."},status_code=409)
        async with lock:
            try:
                body=bytearray()
                async for chunk in request.stream():
                    body.extend(chunk)
                    if len(body)>32768:stop("unexpected_request")
                data=json.loads(body)
                request._body=bytes(body)
                if (index>=2 or data.get("question")!=QUESTIONS[index]
                    or (index==0 and data.get("conversation_id") is not None)
                    or (index==1 and (data.get("conversation_id")!=conversation_id or data.get("dataset_id")!=dataset_id))):
                    stop("unexpected_submission_or_context")
                case={"case_index":index+1,"generation_attempts":0,"provider_attempts":[],
                      "tools_used":[],"sql_results":[],"passed":False}
                report["cases"].append(case)
                budget.current=case
                save()
                response=await call_next(request)
                chunks=[chunk async for chunk in response.body_iterator]
                if sum(map(len,chunks))>262144:stop("oversized_response")
                payload=json.loads(b"".join(chunks))
                case["backend_http_status"]=response.status_code
                if response.status_code!=200:
                    report["halted"]=True
                    report.setdefault("failure_category","backend_failure")
                    save()
                    detail=QUOTA_MESSAGE if report.get("failure_category")=="quota_or_rate_limit" else "Browser evaluation stopped; sanitized diagnostics saved."
                    return JSONResponse({"detail":detail},status_code=response.status_code)
                case["final_explanation_local"]=bounded_explanation(payload["answer"],(settings.api_key,))
                case.update(assess_case(index,payload,case,EXPECTED,conversation_id))
                for failure in case["validation_failures"]:
                    failure["claim_excerpt"]=redact(failure["claim_excerpt"],(settings.api_key,))
                case["sql"],case["columns"],case["rows"]=payload["sql"],payload["columns"],payload["rows"]
                case["chart_generated"]=build_chart(payload["columns"],payload["rows"]).figure is not None
                case["passed"]=all(case[k] for k in ("sql_execution_verified","numerical_evidence_valid","final_answer_verified","conversation_continuity_verified","chart_generated"))
                if not case["passed"]:stop("answer_context_or_chart_failure")
                dataset_id,conversation_id=data["dataset_id"],payload["conversation_id"]
                index+=1
                report["success"]=index==2
                save()
                return JSONResponse(payload)
            except Exception:
                report["halted"]=True
                report.setdefault("failure_category","application_failure")
                save()
                return JSONResponse({"detail":"Browser evaluation stopped; review local sanitized diagnostics."},status_code=422)
    # A concurrent invalid submission must also prevent the next wire request.
    original_request=budget.request
    def closed_request(request):
        if report["halted"] or report["success"]:stop("closed_evaluation")
        original_request(request)
        if report["halted"] or report["success"]:stop("closed_evaluation")
    budget.request=closed_request
    original_lifespan=app.router.lifespan_context
    @asynccontextmanager
    async def lifespan(application):
        try:
            async with original_lifespan(application):yield
        finally:
            if model is not None:model.client.close()
    app.router.lifespan_context=lifespan
    app.state.browser_report=report
    return app


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--execute-approved-free-tier",action="store_true")
    parser.add_argument("--output",type=Path,default=ROOT/".tmp/browser-acceptance-live.json")
    args=parser.parse_args()
    if not args.execute_approved_free_tier:parser.error("Separate human execution approval required.")
    logging.disable(logging.CRITICAL)
    try:
        app=prepare_app(approved=True,output=args.output)
        import uvicorn
        uvicorn.run(app,host="127.0.0.1",port=8002,workers=1,access_log=False,log_level="critical")
    except Exception:
        raise SystemExit("Browser test backend stopped; raw details suppressed.") from None


if __name__=="__main__":main()
