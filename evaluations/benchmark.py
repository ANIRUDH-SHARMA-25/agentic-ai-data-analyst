"""MOCKED evaluation of plumbing, real SQL execution, and independent oracles."""

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter
from typing import Callable
from uuid import uuid4

import pandas as pd
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from backend.agent.analyst import DataAnalysisAgent
from backend.agent.config import AgentSettings
from backend.config import APISettings
from backend.data.csv_processing import load_csv
from backend.main import create_app
from evaluations.fake_model import ScriptedModel, call_tool

ROOT = Path(__file__).resolve().parents[1]
TOP = 'SELECT category, SUM(revenue) AS total FROM dataset GROUP BY category ORDER BY total DESC LIMIT 1'


@dataclass(frozen=True)
class Case:
    name: str
    question: str
    sql: str
    expected: Callable[[pd.DataFrame], list[list]] | None
    frame: str = 'retail'
    rejection: bool = False


def scalar(function):
    return lambda frame: [[function(frame)]]


def groups(frame, column='category', *, ascending=False):
    values = frame.groupby(column)['revenue'].sum().rename('total').reset_index()
    values = values.sort_values(['total', column], ascending=[ascending, True])
    return [[name, float(value)] for name, value in values.itertuples(index=False, name=None)]


def cases() -> list[Case]:
    return [
        Case('total_revenue', 'Total revenue?', 'SELECT SUM(revenue) FROM dataset', scalar(lambda f:float(f.revenue.sum()))),
        Case('total_quantity', 'Total items sold?', 'SELECT SUM(quantity) FROM dataset', scalar(lambda f:int(f.quantity.sum()))),
        Case('row_count', 'How many sales rows?', 'SELECT COUNT(*) FROM dataset', scalar(len)),
        Case('average_revenue', 'Average sale revenue?', 'SELECT AVG(revenue) FROM dataset', scalar(lambda f:float(f.revenue.mean()))),
        Case('maximum_revenue', 'Largest sale revenue?', 'SELECT MAX(revenue) FROM dataset', scalar(lambda f:float(f.revenue.max()))),
        Case('minimum_revenue', 'Smallest sale revenue?', 'SELECT MIN(revenue) FROM dataset', scalar(lambda f:float(f.revenue.min()))),
        Case('category_totals', 'Revenue by category?', 'SELECT category, SUM(revenue) FROM dataset GROUP BY category ORDER BY SUM(revenue) DESC', groups),
        Case('highest_category', 'Highest revenue category?', TOP, lambda f:groups(f)[:1]),
        Case('lowest_category', 'Lowest revenue category?', TOP.replace('DESC','ASC'), lambda f:groups(f,ascending=True)[:1]),
        Case('product_totals', 'Revenue by product?', 'SELECT product, SUM(revenue) FROM dataset GROUP BY product ORDER BY SUM(revenue) DESC, product ASC', lambda f:groups(f,'product')),
        Case('electronics_filter', 'Electronics revenue?', "SELECT SUM(revenue) FROM dataset WHERE category = 'Electronics'", scalar(lambda f:float(f.loc[f.category=='Electronics','revenue'].sum()))),
        Case('quantity_filter', 'Sales rows of at least five units?', 'SELECT COUNT(*) FROM dataset WHERE quantity >= 5', scalar(lambda f:int((f.quantity>=5).sum()))),
        Case('date_filter', 'Revenue from January third onward?', "SELECT SUM(revenue) FROM dataset WHERE date >= '2026-01-03'", scalar(lambda f:float(f.loc[f.date>='2026-01-03','revenue'].sum()))),
        Case('unique_products', 'How many products?', 'SELECT COUNT(DISTINCT product) FROM dataset', scalar(lambda f:int(f['product'].nunique()))),
        Case('category_count', 'How many categories?', 'SELECT COUNT(DISTINCT category) FROM dataset', scalar(lambda f:int(f.category.nunique()))),
        Case('missing_count', 'How many missing revenue values?', 'SELECT COUNT(*) FROM dataset WHERE revenue IS NULL', scalar(lambda f:int(f.revenue.isna().sum())),frame='missing'),
        Case('nonmissing_average', 'Mean of nonmissing revenue?', 'SELECT AVG(revenue) FROM dataset', scalar(lambda f:float(f.revenue.mean())),frame='missing'),
        Case('coalesced_sum', 'Sum revenue treating missing as zero?', 'SELECT SUM(COALESCE(revenue, 0)) FROM dataset', scalar(lambda f:float(f.revenue.fillna(0).sum())),frame='missing'),
        Case('unknown_column', 'Sum profit?', 'SELECT SUM(profit) FROM dataset', None,rejection=True),
        Case('ddl_rejection', 'Drop dataset?', 'DROP TABLE dataset', None,rejection=True),
        Case('file_rejection', 'Read a local secret file?', "SELECT * FROM read_csv('secret.csv')", None,rejection=True),
        Case('join_rejection', 'Join with another dataset?', 'SELECT a.revenue FROM dataset a JOIN dataset b ON a.category=b.category', None,rejection=True),
    ]


def historical_context(messages) -> list[dict]:
    for message in messages:
        if isinstance(message, HumanMessage) and message.content.startswith('Historical conversation evidence'):
            return json.loads(message.content.split('\n',1)[1])
    return []


def evidence_answer(messages):
    """Fake prose depends on tool output, never on the expected-answer oracle."""
    evidence=json.loads([m for m in messages if isinstance(m,ToolMessage)][-1].content)
    return AIMessage(content='MOCKED explanation of newly computed evidence: '+json.dumps(evidence.get('rows',[])))


def sql_model(query: str | Callable, *, rejection=False) -> ScriptedModel:
    sql_call = (lambda messages:call_tool('execute_sql',{'query':query(messages)})) if callable(query) else call_tool('execute_sql',{'query':query})
    responses=[call_tool('inspect_dataset'),sql_call]
    if rejection:
        responses.append(call_tool('execute_sql',{'query':query}))
    else:
        responses.append(evidence_answer)
    return ScriptedModel(responses=responses)


def rows_equal(actual: list[list], expected: list[list]) -> bool:
    if len(actual)!=len(expected): return False
    for left,right in zip(actual,expected):
        if len(left)!=len(right): return False
        for a,b in zip(left,right):
            if b is None:
                if a is not None: return False
            elif isinstance(b,(float,int)) and not isinstance(b,bool):
                if not isinstance(a,(float,int)) or isinstance(a,bool): return False
                if isinstance(b,int):
                    if a!=b or (isinstance(a,float) and abs(b)>2**53-1): return False
                elif not math.isclose(a,b,rel_tol=1e-9,abs_tol=1e-9): return False
            elif a!=b: return False
    return True


def run_benchmark() -> dict:
    started=perf_counter()
    retail=load_csv(ROOT/'data/sample/retail_sales.csv')
    frames={'retail':retail, 'missing':pd.DataFrame({'category':['A','A','B'],'revenue':[10.,None,20.],'quantity':[1,None,2]})}
    outcomes=[]
    for case in cases():
        frame=frames[case.frame]
        agent=DataAnalysisAgent(settings=AgentSettings(),model_factory=lambda settings,c=case:sql_model(c.sql,rejection=c.rejection))
        if case.rejection:
            from backend.agent.analyst import AnalysisError
            try:
                agent.analyze(frame,case.question)
                passed=False
            except AnalysisError as exc:
                passed=exc.status_code==422 and 'correction' in str(exc)
            outcomes.append({'name':case.name,'group':'rejection','passed':passed})
        else:
            expected=case.expected(frame)  # Independent Pandas oracle, not SQL/model output.
            response=agent.analyze(frame,case.question)
            passed=rows_equal(response.rows,expected) and response.tools_used==['inspect_dataset','execute_sql']
            outcomes.append({'name':case.name,'group':'sql','passed':passed})

    # Three follow-ups through the real API; SQL thresholds come from retained evidence.
    def ranked_followup(messages):
        context=historical_context(messages)
        if not context or 'category' not in context[-1]['question'].lower():
            raise AssertionError('Missing topic context')
        threshold=context[-1]['rows'][0][1]
        return TOP.replace('ORDER BY',f'HAVING SUM(revenue) < {threshold} ORDER BY')
    def previous_category(messages):
        context=historical_context(messages)
        category=context[-1]['rows'][0][0]
        if category != 'Stationery': raise AssertionError('Incorrect previous category')
        return "SELECT SUM(quantity) FROM dataset WHERE category = 'Stationery'"
    scripts=iter([lambda m:TOP,ranked_followup,ranked_followup,previous_category])
    agent=DataAnalysisAgent(settings=AgentSettings(),model_factory=lambda settings:sql_model(next(scripts)))
    settings=APISettings(temporary_directory=ROOT/'.tmp/evaluation-uploads')
    with TestClient(create_app(settings,analyzer=agent)) as api:
        dataset_id=api.post('/upload',files={'file':('retail.csv',(ROOT/'data/sample/retail_sales.csv').read_bytes(),'text/csv')}).json()['dataset_id']
        cid=None
        questions=['Highest revenue category?','Which category was second?','Which category was third?','How many items did that category sell?']
        expected=[groups(retail)[:1],groups(retail)[1:2],groups(retail)[2:3],[[int(retail.loc[retail.category=='Stationery','quantity'].sum())]]]
        for index,(question,oracle) in enumerate(zip(questions,expected)):
            body={'dataset_id':dataset_id,'question':question}
            if cid: body['conversation_id']=cid
            response=api.post('/analyze',json=body)
            value=response.json()
            passed=response.status_code==200 and rows_equal(value.get('rows',[]),oracle)
            if index: outcomes.append({'name':f'followup_{index}','group':'followup','passed':passed and value.get('conversation_id')==cid})
            elif not passed: raise AssertionError('Follow-up seed failed')
            cid=value.get('conversation_id',cid)
        other_id=api.post('/upload',files={'file':('other.csv',b'revenue\n99\n','text/csv')}).json()['dataset_id']
        response=api.post('/analyze',json={'dataset_id':other_id,'conversation_id':cid,'question':'Total revenue?'})
        outcomes.append({'name':'dataset_isolation','group':'isolation','passed':response.status_code==409})
        response=api.post('/analyze',json={'dataset_id':dataset_id,'conversation_id':str(uuid4()),'question':'Total?'})
        outcomes.append({'name':'unknown_conversation','group':'isolation','passed':response.status_code==410})

    agent=DataAnalysisAgent(settings=AgentSettings(),model_factory=lambda settings:ScriptedModel(responses=[call_tool('inspect_dataset'),AIMessage(content='This dataset cannot forecast weather.')]))
    response=agent.analyze(retail,'Predict tomorrow weather')
    outcomes.append({'name':'unsupported_question','group':'unsupported','passed':response.sql is None and not response.rows})
    def metric(group):
        items=[x for x in outcomes if x['group']==group]
        return {'passed':sum(x['passed'] for x in items),'total':len(items)}
    return {'label':'MOCKED / DETERMINISTIC - not OpenAI model accuracy',
            'passed':sum(x['passed'] for x in outcomes),'total':len(outcomes),
            'sql_execution_correctness':metric('sql'),'followup_context_correctness':metric('followup'),
            'sql_rejection_behavior':metric('rejection'),'duration_seconds':round(perf_counter()-started,3),
            'cases':outcomes}


def main():
    parser=argparse.ArgumentParser(description='Run network-free mocked workflow evaluation.')
    parser.add_argument('--output',type=Path,help='Optional JSON report, restricted to repo .tmp or artifacts.')
    args=parser.parse_args()
    if args.output:
        path=args.output.resolve()
        if not any(path.is_relative_to(ROOT/folder) for folder in ('.tmp','artifacts')):
            parser.error('Reports must stay inside the repo .tmp or artifacts directory.')
    report=run_benchmark()
    print(report['label'])
    print(f"Task success: {report['passed']}/{report['total']} ({100*report['passed']/report['total']:.1f}%)")
    for name in ('sql_execution_correctness','followup_context_correctness','sql_rejection_behavior'):
        metric=report[name]; print(f"{name}: {metric['passed']}/{metric['total']}")
    print(f"Duration: {report['duration_seconds']:.3f}s")
    if args.output:
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    raise SystemExit(0 if report['passed']==report['total'] else 1)


if __name__=='__main__':
    main()
