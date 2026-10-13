"""HTTP boundary, chart fidelity, and real Streamlit widget interaction tests."""
import json
from pathlib import Path
from unittest.mock import Mock
from uuid import uuid4

import httpx
import pytest
from streamlit.testing.v1 import AppTest

from frontend.api_client import APIClient, APIClientError
from frontend.charts import build_chart
from frontend.config import FrontendSettings
from frontend.session import initialize_session, load_dataset, submit_question

ID = str(uuid4())
INFO = dict(dataset_id=ID, row_count=2, column_count=2, columns=['category', 'revenue'],
            dtypes={'category':'str','revenue':'int64'}, preview=[{'category':'A','revenue':10}],
            missing_values={'category':0,'revenue':0}, statistics={'revenue':{'sum':30}})
RESULT = dict(answer='Computed totals.', sql='SELECT category, SUM(revenue) FROM dataset GROUP BY category',
              columns=['category','total'], rows=[['Electronics',260],['Home',150],['Stationery',120]],
              row_count=3, tools_used=['inspect_dataset','execute_sql'])


def client(handler, **settings):
    return APIClient(FrontendSettings(**settings), transport=httpx.MockTransport(handler))


def test_http_contract():
    seen=[]
    def handler(req):
        seen.append(req)
        if req.url.path == '/health': return httpx.Response(200,json={'status':'ok'})
        if req.url.path == '/analyze': return httpx.Response(200,json=RESULT)
        return httpx.Response(201 if req.url.path == '/upload' else 200,json=INFO)
    api=client(handler)
    assert api.health()['status']=='ok'
    assert api.upload('data.csv',b'category,revenue\nA,10\n')['dataset_id']==ID
    assert b'name="file"' in seen[-1].content and b'filename="data.csv"' in seen[-1].content
    assert api.inspect(ID)['statistics']==INFO['statistics']
    assert api.analyze(ID,'  Revenue by category?  ')==RESULT
    assert json.loads(seen[-1].content)=={'dataset_id':ID,'question':'Revenue by category?'}
    assert seen[-1].extensions['timeout']['read']==300
    assert len(seen)==4


@pytest.mark.parametrize('status,word',[(400,'invalid'),(404,'expired'),(413,'size'),(415,'CSV'),(422,'unsupported'),(429,'rate-limited'),(502,'provider'),(503,'unavailable'),(504,'time limit'),(500,'could not')])
def test_backend_errors_sanitized_once(status,word):
    seen=[]
    def handler(req):
        seen.append(req)
        return httpx.Response(status,json={'detail':'private exception sk-secret'})
    with pytest.raises(APIClientError,match=word) as err:
        client(handler).analyze(ID,'Revenue?')
    assert err.value.status_code==status and 'sk-secret' not in str(err.value)
    assert len(seen)==1


@pytest.mark.parametrize('exception,word',[(httpx.ConnectError,'Cannot reach'),(httpx.ReadTimeout,'not retried')])
def test_transport_errors_no_retry(exception,word):
    seen=[]
    def handler(req):
        seen.append(req); raise exception('private error',request=req)
    with pytest.raises(APIClientError,match=word): client(handler).analyze(ID,'Revenue?')
    assert len(seen)==1


def test_missing_key_and_optional_sql():
    with pytest.raises(APIClientError,match='Set GOOGLE_API_KEY'):
        client(lambda req:httpx.Response(503,json={'detail':'GOOGLE_API_KEY is required'})).analyze(ID,'Revenue?')
    result={**RESULT,'sql':None,'columns':[],'rows':[],'row_count':0}
    assert client(lambda req:httpx.Response(200,json=result)).analyze(ID,'Statistics?')==result


@pytest.mark.parametrize('payload',[b'not json',b'[]',b'{"answer":NaN}',json.dumps({**RESULT,'row_count':7}).encode(),json.dumps({**RESULT,'rows':[[{},1]],'row_count':1}).encode()])
def test_invalid_responses(payload):
    with pytest.raises(APIClientError,match='unexpected'):
        client(lambda req:httpx.Response(200,content=payload)).analyze(ID,'Revenue?')


@pytest.mark.parametrize('filename,payload',[('a.txt',b'a\n1'),('a.csv',b''),('a.csv',b'12345')])
def test_upload_rejected_before_network(filename,payload):
    api=client(lambda req:pytest.fail('unexpected network'),max_upload_bytes=4)
    with pytest.raises(APIClientError): api.upload(filename,payload)


def test_inspection_wrong_id_and_bad_uuid():
    api=client(lambda req:httpx.Response(200,json={**INFO,'dataset_id':str(uuid4())}))
    with pytest.raises(APIClientError): api.inspect(ID)
    with pytest.raises(APIClientError): api.inspect('not-uuid')
    with pytest.raises(APIClientError): client(lambda req:httpx.Response(200,json={**INFO,'dataset_id':3})).upload('a.csv',b'a\n1')


@pytest.mark.parametrize('kwargs',[{'backend_url':'ftp://host'},{'backend_url':'http://user:secret@host'}, {'backend_url':'http://host:bad'}, {'request_timeout_seconds':0},{'analysis_timeout_seconds':601},{'max_upload_bytes':True}])
def test_invalid_settings(kwargs):
    with pytest.raises(ValueError): FrontendSettings(**kwargs)


def test_environment_settings(monkeypatch):
    monkeypatch.setenv('BACKEND_URL','http://localhost:9000/')
    monkeypatch.setenv('FRONTEND_ANALYSIS_TIMEOUT_SECONDS','480')
    assert FrontendSettings.from_environment().backend_url=='http://localhost:9000'
    assert FrontendSettings.from_environment().analysis_timeout_seconds==480


def test_retail_chart_from_actual_dataset(retail_frame):
    totals=retail_frame.groupby('category')['revenue'].sum().sort_values(ascending=False)
    chart=build_chart(['category','total'],[[label,float(value)] for label,value in totals.items()])
    assert chart.kind=='bar'
    assert list(chart.figure.data[0].x)==['Electronics','Home','Stationery']
    assert list(chart.figure.data[0].y)==[260,150,120]
    assert chart.figure.layout.yaxis.rangemode=='tozero'


def test_time_order_and_gaps():
    chart=build_chart(['month','revenue'],[['2026-03',30],['2026-01',10],['2026-02',None]])
    assert chart.kind=='line'
    assert [d.month for d in chart.figure.data[0].x]==[1,2,3]
    assert list(chart.figure.data[0].y)==[10,None,30]
    assert chart.figure.data[0].connectgaps is False


def test_reverse_columns_missing_and_decimal():
    chart=build_chart(['value','category'],[['1.25','A'],[None,'B'],['2.5','C'],['3',None]])
    assert chart.kind=='bar' and list(chart.figure.data[0].y)==[1.25,2.5]
    assert chart.excluded_rows==2


@pytest.mark.parametrize('columns,rows',[
    ([],[]),(['total'],[[530]]),(['category','total'],[['A',1]]),
    (['x','y'],[[1,2],[3,4]]),(['x','y'],[['A',True],['B',False]]),
    (['x','y'],[['A','bad'],['B','2']]),(['x','y'],[['A',None],['B',None]]),
    (['x','y'],[['A',1],['A',2]]),(['x','y'],[['2026-01-01',1],['bad',2]]),
    (['x','y'],[['2026-02-30',1],['2026-13-01',2]]),
    (['x','y'],[['A',2**53],['B',2]]),(['x','y'],[['A','1.1234567890123456789'],['B','2']]),
    (['x','y','z'],[['A',1,2],['B',3,4]]),(['x','x'],[['A',1],['B',2]]),
    (['x','y'],[[str(i)+'cat',i] for i in range(21)]),
    (['x','y'],[['2026-01-01T00:00:00Z',1],['2025-12-31T19:00:00-05:00',2]]),
])
def test_unsupported_charts(columns,rows):
    chart=build_chart(columns,rows)
    assert chart.figure is None and chart.reason


def test_session_upload_dedup_change_pending_inspect():
    api=Mock(); api.upload.return_value=INFO; api.inspect.return_value=INFO
    state={}; initialize_session(state)
    assert load_dataset(state,api,'a.csv',b'a\n1')
    state['history']=[{'question':'old'}]
    assert not load_dataset(state,api,'a.csv',b'a\n1')
    assert api.upload.call_count==api.inspect.call_count==1
    api.inspect.side_effect=[APIClientError('timed out'),INFO]
    with pytest.raises(APIClientError): load_dataset(state,api,'b.csv',b'b\n2')
    assert state['history']==[] and state['dataset_info'] is None
    assert load_dataset(state,api,'b.csv',b'b\n2')
    assert api.upload.call_count==2
    assert not any(isinstance(v,bytes) for v in state.values())


def test_session_errors_expiration_and_history_bound():
    state={}; initialize_session(state); state['dataset_id']=ID
    api=Mock(); api.analyze.return_value=RESULT
    for i in range(12): submit_question(state,api,f'question {i}')
    assert len(state['history'])==10 and state['history'][0]['question']=='question 2'
    api.analyze.side_effect=APIClientError('expired',404)
    submit_question(state,api,'again')
    assert state['dataset_expired'] and state['history'][-1]['response'] is None
    api.upload.return_value=INFO; api.inspect.return_value=INFO
    load_dataset(state,api,'a.csv',b'a\n1')
    assert not state['dataset_expired'] and not state['history']


@pytest.fixture
def app(monkeypatch):
    api=Mock(); api.upload.return_value=INFO; api.inspect.return_value=INFO; api.analyze.return_value=RESULT
    monkeypatch.setattr('frontend.app.APIClient',lambda settings:api)
    # AppTest executes app.py as __main__, so patch the class at its source.
    monkeypatch.setattr('frontend.api_client.APIClient',lambda settings:api)
    at=AppTest.from_file(Path(__file__).resolve().parents[1] / 'frontend/app.py',default_timeout=15).run()
    assert not at.exception
    return at,api


def button(at,label):
    return next(b for b in at.button if b.label==label)


def test_app_empty_upload_analysis_rerun_and_clear(app):
    at,api=app
    assert at.chat_input[0].disabled and not api.mock_calls
    assert any('Upload a CSV' in x.value for x in at.info)
    at.file_uploader[0].upload('test.csv',b'category,revenue\nA,10\nB,20', 'text/csv').run()
    assert not api.mock_calls
    button(at,'Load dataset').click().run()
    assert not at.exception and not at.chat_input[0].disabled
    assert [m.value for m in at.metric]==['2','2','0']
    assert len(at.dataframe)==3 and api.upload.call_count==api.inspect.call_count==1
    at.chat_input[0].set_value('Revenue by category?').run()
    assert not at.exception and len(at.chat_message)==2 and len(at.get('plotly_chart'))==1
    assert len(at.dataframe)==4 and len(at.code)==1
    assert api.analyze.call_args.args==(ID,'Revenue by category?')
    at.run(); assert api.analyze.call_count==1 and api.upload.call_count==1
    button(at,'Clear dataset & history').click().run()
    assert at.chat_input[0].disabled and not at.chat_message


@pytest.mark.parametrize('status,message',[(503,'Set GOOGLE_API_KEY in the backend terminal'),(404,'expired'),(502,'provider failed'),(None,'Cannot reach backend')])
def test_app_errors(app,status,message):
    at,api=app
    button(at,'Try the retail sample').click().run()
    api.analyze.side_effect=APIClientError(message,status)
    at.chat_input[0].set_value('Revenue?').run()
    assert not at.exception and any(message in err.value for err in at.error)
    assert not at.get('plotly_chart') and not at.code
    at.run(); assert api.analyze.call_count==1
    if status==404: assert at.chat_input[0].disabled and at.warning


def test_app_no_sql_and_upload_failure(app):
    at,api=app
    api.upload.side_effect=APIClientError('invalid CSV',400)
    button(at,'Try the retail sample').click().run()
    assert not at.exception and at.chat_input[0].disabled and at.error
    api.upload.side_effect=None
    button(at,'Try the retail sample').click().run()
    api.analyze.return_value={**RESULT,'sql':None,'rows':[],'columns':[],'row_count':0}
    at.chat_input[0].set_value('Statistics?').run()
    assert not at.exception and not at.code and not at.get('plotly_chart')
    assert any('No SQL' in x.value for x in at.caption)


def test_app_dataset_switch_resets_results(app):
    at,api=app
    button(at,'Try the retail sample').click().run()
    at.chat_input[0].set_value('Revenue?').run()
    assert at.chat_message
    at.file_uploader[0].upload('new.csv',b'category,revenue\nB,20', 'text/csv').run()
    button(at,'Load dataset').click().run()
    assert not at.exception and not at.chat_message and not at.get('plotly_chart')
    assert api.upload.call_count==2 and api.analyze.call_count==1


def test_app_invalid_config(monkeypatch):
    monkeypatch.setenv('BACKEND_URL','ftp://host')
    at=AppTest.from_file(Path(__file__).resolve().parents[1] / 'frontend/app.py').run()
    assert not at.exception and any('configuration is invalid' in x.value for x in at.error)


def test_chart_time_point_cap():
    from datetime import datetime, timedelta
    rows=[[(datetime(2026,1,1)+timedelta(days=i)).isoformat(),i] for i in range(101)]
    assert build_chart(['day','value'],rows).figure is None
    chart=build_chart(['day','value'],rows[:100])
    assert chart.kind=='line' and len(chart.figure.data[0].y)==100


def test_app_line_rendering(app):
    at,api=app
    button(at,'Try the retail sample').click().run()
    api.analyze.return_value={**RESULT,'columns':['date','value'],'rows':[['2026-02',2],['2026-01',1]],'row_count':2}
    at.chat_input[0].set_value('Revenue over time?').run()
    assert not at.exception and len(at.get('plotly_chart'))==1
    spec=json.loads(at.get('plotly_chart')[0].proto.spec)
    assert spec['data'][0]['type']=='scatter'
    assert spec['data'][0]['y']==[1,2]


def test_display_precision_and_mixed_values():
    from frontend.app import display_frame
    large=2**63+1
    frame=display_frame([[large,'1.25'],[None,2]],['large','mixed'])
    assert frame['large'].tolist()==[str(large),None]
    assert frame['mixed'].tolist()==['1.25','2']
    import pyarrow as pa
    table=pa.Table.from_pandas(frame)
    assert table.column('large').to_pylist()==[str(large),None]


def test_app_large_integer_results(app):
    at,api=app
    button(at,'Try the retail sample').click().run()
    api.analyze.return_value={**RESULT,'columns':['label','value'],'rows':[['A',2**63+1],['B',None]],'row_count':2}
    at.chat_input[0].set_value('Values?').run()
    assert not at.exception and not at.get('plotly_chart')
    assert at.dataframe[-1].value['value'].iloc[0]==str(2**63+1)
    import pandas as pd
    assert pd.isna(at.dataframe[-1].value['value'].iloc[1])
