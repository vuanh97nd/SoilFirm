import ast
from copy import deepcopy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from mapping_proposer import propose_mapping,MappingFailure,SYSTEM_PROMPT
from mapping_gate import (validate_mapping,apply_mapping,MappingRejected,alias_mapping,
                          save_mapping_memory,lookup_mapping_memory,fingerprint)
import ai_analysis_data as data

ROOT=Path(__file__).parent
REG=json.loads((ROOT/'parameter_registry.json').read_text(encoding='utf-8'))
COLS=[{'cot_id':1,'label':'Mã lớp','unit':'','group':''},
      {'cot_id':2,'label':'Dung trọng tự nhiên','unit':'kN/m³','group':'natural_density'}]
ROWS=[{1:'1a',2:17.16},{1:'1b',2:18.2}]
def answer(items=None,extra=None):
    result={'task':'column_mapping','items':items or [
      {'cot_id':1,'thong_so':'code','do_tin_cay':.99,'ly_do':'Mã lớp đất'},
      {'cot_id':2,'thong_so':'gamma','do_tin_cay':.99,'ly_do':'Dung trọng tự nhiên'}],'khong_chac':[]}
    if extra:result.update(extra)
    return json.dumps(result,ensure_ascii=False)

class SecurityTests(unittest.TestCase):
    def reject_unchanged(self,text,cols=None,rows=None,required=('code','gamma')):
        state={'rows':[{'gamma':1.88}],'results':{'old':True}}
        before=deepcopy(state)
        checked=validate_mapping(text,cols or COLS,rows or ROWS,REG,required,source_signature='source')
        self.assertEqual(checked.status,'rejected',checked.reasons)
        with self.assertRaises(MappingRejected):apply_mapping(checked,cols or COLS,rows or ROWS,REG,state,required=required,confirmed_by='user',source_signature='source')
        self.assertEqual(state,before)
    def test_malformed_json(self):self.reject_unchanged('{')
    def test_empty_json(self):self.reject_unchanged('')
    def test_prose(self):self.reject_unchanged('Tôi đã đọc xong dữ liệu.')
    def test_english_prose(self):self.reject_unchanged('The values are correct.')
    def test_markdown(self):self.reject_unchanged('```json\n'+answer()+'\n```')
    def test_trailing_prose(self):self.reject_unchanged(answer()+' Đã xong')
    def test_extra_root(self):self.reject_unchanged(answer(extra={'gamma':9.99}))
    def test_extra_item_measurement(self):
        x=json.loads(answer());x['items'][1]['value']=99;self.reject_unchanged(json.dumps(x))
    def test_fake_parameter(self):
        x=json.loads(answer());x['items'][1]['thong_so']='fake_gamma';self.reject_unchanged(json.dumps(x))
    def test_duplicate_columns(self):
        x=json.loads(answer());x['items'].append(x['items'][0]);self.reject_unchanged(json.dumps(x))
    def test_duplicate_targets(self):
        x=json.loads(answer());x['items'][1]['thong_so']='code';self.reject_unchanged(json.dumps(x))
    def test_nonexistent_column(self):
        x=json.loads(answer());x['items'][1]['cot_id']=900;self.reject_unchanged(json.dumps(x))
    def test_duplicate_json_keys(self):self.reject_unchanged(answer().replace('"task":','"task":"wrong","task":',1))
    def test_nan_confidence(self):self.reject_unchanged(answer().replace('0.99','NaN',1))
    def test_bool_column(self):self.reject_unchanged(answer().replace('"cot_id": 1','"cot_id": true'))
    def test_missing_field(self):
        x=json.loads(answer());del x['items'][0]['ly_do'];self.reject_unchanged(json.dumps(x))
    def test_english_reason(self):
        x=json.loads(answer());x['items'][1]['ly_do']='The column is density';self.reject_unchanged(json.dumps(x))
    def test_measurement_in_reason(self):
        x=json.loads(answer());x['items'][1]['ly_do']='Dung trọng bằng 1.7';self.reject_unchanged(json.dumps(x))
    def test_missing_required(self):
        x=json.loads(answer());x['items'][1]['thong_so']='unknown';self.reject_unchanged(json.dumps(x))
    def test_wrong_unit(self):
        cols=deepcopy(COLS);cols[1]['unit']='kPa';self.reject_unchanged(answer(),cols)
    def test_missing_unit(self):
        cols=deepcopy(COLS);cols[1]['unit']='';self.reject_unchanged(answer(),cols)
    def test_negative_gamma(self):self.reject_unchanged(answer(),rows=[{1:'1',2:-17}])
    def test_zero_gamma(self):self.reject_unchanged(answer(),rows=[{1:'1',2:0}])
    def test_numeric_text_invalid(self):self.reject_unchanged(answer(),rows=[{1:'1',2:'soil'}])
    def test_excel_error(self):self.reject_unchanged(answer(),rows=[{1:'1',2:'#DIV/0!'}])
    def test_too_many_blanks(self):self.reject_unchanged(answer(),rows=[{1:'1',2:None},{1:'2',2:None},{1:'3',2:17}])
    def test_wrong_experiment(self):
        cols=deepcopy(COLS);cols[1].update(unit='kPa',group='direct_shear')
        x=json.loads(answer());x['items'][1]['thong_so']='co';self.reject_unchanged(json.dumps(x),cols,required=('code','co'))
    def test_dry_density(self):
        cols=deepcopy(COLS);cols[1]['group']='dry_density';self.reject_unchanged(answer(),cols)
    def test_low_confidence_requires_confirmation(self):
        x=json.loads(answer());x['items'][1]['do_tin_cay']=.84
        text=json.dumps(x);v=validate_mapping(text,COLS,ROWS,REG,('code','gamma'),source_signature='source')
        self.assertEqual(v.status,'confirm')
        state={'rows':['old']};before=deepcopy(state)
        with self.assertRaises(MappingRejected):apply_mapping(v,COLS,ROWS,REG,state,required=('code','gamma'),confirmed_by='user',source_signature='source')
        self.assertEqual(state,before)
        v=validate_mapping(text,COLS,ROWS,REG,('code','gamma'),confirmed_by='user',source_signature='source')
        apply_mapping(v,COLS,ROWS,REG,state,required=('code','gamma'),confirmed_by='user',source_signature='source')
        self.assertAlmostEqual(state['rows'][0]['gamma'],17.16/9.80665)
    def test_high_confidence_does_not_write_before_apply(self):
        state={'rows':['old']};v=validate_mapping(answer(),COLS,ROWS,REG,('code','gamma'),source_signature='source')
        self.assertEqual(state,{'rows':['old']})
        with self.assertRaises(MappingRejected):apply_mapping(v,COLS,ROWS,REG,state,required=('code','gamma'),source_signature='source')
        self.assertEqual(state,{'rows':['old']})
    def test_valid_apply_and_undo(self):
        state={'rows':['old'],'results':{'retained':1}};before=deepcopy(state)
        v=validate_mapping(answer(),COLS,ROWS,REG,('code','gamma'),source_signature='source')
        backup=apply_mapping(v,COLS,ROWS,REG,state,required=('code','gamma'),confirmed_by='user',source_signature='source')
        self.assertEqual(state['results'],before['results']);self.assertEqual(state['rows'][0]['code'],'1a')
        self.assertAlmostEqual(state['rows'][0]['gamma'],17.16/9.80665)
        state.clear();state.update(backup);self.assertEqual(state,before)
    def test_source_change_rejected(self):
        v=validate_mapping(answer(),COLS,ROWS,REG,('code','gamma'),source_signature='source')
        state={'rows':['old']}
        with self.assertRaises(MappingRejected):apply_mapping(v,COLS,[{1:'1',2:19}],REG,state,required=('code','gamma'),confirmed_by='user',source_signature='source')
        self.assertEqual(state,{'rows':['old']})
    def test_conversion_failure_has_no_partial_commit(self):
        v=validate_mapping(answer(),COLS,ROWS,REG,('code','gamma'),source_signature='source')
        state={'rows':['old']}
        import mapping_gate
        original=mapping_gate.converted;count=0
        def failing(*args):
            nonlocal count
            count+=1
            if count==6:raise ValueError('Injected conversion failure')
            return original(*args)
        with patch('mapping_gate.converted',side_effect=failing):
            with self.assertRaises(ValueError):apply_mapping(v,COLS,ROWS,REG,state,required=('code','gamma'),confirmed_by='user',source_signature='source')
        self.assertEqual(state,{'rows':['old']})
    def test_commit_failure_rolls_back(self):
        class State(dict):
            once=True
            def update(self,other):
                if self.once:
                    self.once=False;self['rows']='partial';raise RuntimeError('Injected write failure')
                return super().update(other)
        state=State(rows=['old']);v=validate_mapping(answer(),COLS,ROWS,REG,('code','gamma'),source_signature='source')
        with self.assertRaises(RuntimeError):apply_mapping(v,COLS,ROWS,REG,state,required=('code','gamma'),confirmed_by='user',source_signature='source')
        self.assertEqual(state,{'rows':['old']})
    def test_proposer_limits_samples(self):
        with self.assertRaises(MappingFailure):propose_mapping([{'cot_id':1,'label':'x','samples':[1,2,3,4]}],[],lambda p:answer())
    def test_proposer_refuses_app_context(self):
        with self.assertRaises(MappingFailure):propose_mapping([{'cot_id':1,'label':'x','project':{}}],[],lambda p:answer())
    def test_network_failure_cases_do_not_change_state(self):
        for failure in (TimeoutError('timeout'),OSError('network'),ValueError('hết hạn mức')):
            with self.subTest(failure=str(failure)):
                count=0;state={'rows':['old']}
                def call(payload):
                    nonlocal count
                    count+=1;raise failure
                with self.assertRaises(MappingFailure):propose_mapping(COLS,[],call,retries=1)
                self.assertEqual(count,2);self.assertEqual(state,{'rows':['old']})
    def test_empty_service_response(self):
        count=0
        def call(payload):
            nonlocal count
            count+=1;return ''
        with self.assertRaises(MappingFailure):propose_mapping(COLS,[],call,retries=2)
        self.assertEqual(count,3)
    def test_mapping_memory_units_and_structure_isolation(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'memory.json';save_mapping_memory(p,COLS,REG,answer(),'user')
            self.assertEqual(lookup_mapping_memory(p,COLS,REG)['actor'],'user')
            changed=deepcopy(COLS);changed[1]['unit']='T/m³'
            self.assertIsNone(lookup_mapping_memory(p,changed,REG))
    def test_exact_alias_rules(self):
        proposal=json.loads(alias_mapping(COLS,REG))
        self.assertEqual(proposal['items'][0]['thong_so'],'code')
        self.assertEqual(proposal['items'][1]['thong_so'],'gamma')
        cols=deepcopy(COLS);cols[1]['label']='Dung trọng tự nhiên gần giống'
        self.assertEqual(json.loads(alias_mapping(cols,REG))['items'][1]['thong_so'],'unknown')
    def test_architecture_no_application_capabilities(self):
        tree=ast.parse((ROOT/'mapping_proposer.py').read_text())
        imports=[n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
        imports += [a.name for n in ast.walk(tree) if isinstance(n,ast.Import) for a in n.names]
        self.assertEqual(imports,['json'])
        names={n.id for n in ast.walk(tree) if isinstance(n,ast.Name)}
        self.assertFalse(names & {'app','project','Soil','Project','open','setattr','apply_mapping','exec','eval','__import__'})
        self.assertLess(len(SYSTEM_PROMPT.split()),200)
    def test_unknown_optional_stays_blank(self):
        x=json.loads(answer());x['items'][1]['thong_so']='unknown'
        v=validate_mapping(json.dumps(x),COLS,ROWS,REG,('code',),source_signature='source')
        state={};apply_mapping(v,COLS,ROWS,REG,state,required=('code',),confirmed_by='user',source_signature='source')
        self.assertNotIn('gamma',state['rows'][0])

if __name__=='__main__':unittest.main()

class WorkflowCommitTests(unittest.TestCase):
    """Real callback logic with fake widgets; no claim of GUI rendering."""
    def setUp(self):
        from types import SimpleNamespace,MethodType
        from ai_analysis_workflow import AnalysisWorkspace
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'source.txt';self.path.write_text('source')
        self.buttons={};buttons=self.buttons
        class Var:
            def __init__(self,*a,value='',**k):self.value=value
            def get(self):return self.value
            def set(self,v):self.value=v
        class Widget:
            def __init__(self,*a,**k):self.entries=[]
            def pack(self,*a,**k):pass
            def title(self,*a):pass
            def geometry(self,*a):pass
            def transient(self,*a):pass
            def destroy(self):pass
            def heading(self,*a,**k):pass
            def column(self,*a,**k):pass
            def insert(self,*a,**k):self.entries.append(k)
            def get_children(self):return self.entries
        class Button(Widget):
            def __init__(self,*a,**k):super().__init__();buttons[k['text']]=k['command']
        app=SimpleNamespace(project=SimpleNamespace(x=1),design_mode=Var(value='TÍNH MỘT ĐOẠN'),
                            current_username='user',current_login_key='key',populate=lambda:None)
        self.view=SimpleNamespace(app=app,state={'materials':['old']},options=[],busy=False,status=Var(),refresh=lambda:None,
                                  warning_summary=lambda w:'; '.join(w))
        for name in ('_import_snapshot','_restore_import','preview_import'):
            setattr(self.view,name,MethodType(getattr(AnalysisWorkspace,name),self.view))
        self.patches=[patch('ai_analysis_workflow.tk.Toplevel',Widget),patch('ai_analysis_workflow.tk.StringVar',Var),
                      patch('ai_analysis_workflow.ttk.Frame',Widget),patch('ai_analysis_workflow.ttk.Label',Widget),
                      patch('ai_analysis_workflow.ttk.Treeview',Widget),patch('ai_analysis_workflow.ttk.Button',Button),
                      patch('ai_analysis_data._mapping_storage',return_value=(Path(self.tmp.name)/'memory',Path(self.tmp.name)/'audit'))]
        for p in self.patches:p.start()
        self.rows=[{'code':'1','values':{'name':'1','gamma':1.8},'source':'S!B2=1.8'}]
    def tearDown(self):
        for p in reversed(self.patches):p.stop()
        self.tmp.cleanup()
    def preview(self,commit):self.view.preview_import((deepcopy(self.rows),[]),commit,[str(self.path)])
    def test_preview_and_cancel_preserve_old_application_data(self):
        before=self.view._import_snapshot();calls=[]
        self.preview(lambda r:calls.append(r));self.buttons['Hủy']()
        self.assertEqual(self.view._import_snapshot(),before);self.assertEqual(calls,[])
    def test_apply_then_undo_application_state(self):
        before=self.view._import_snapshot()
        self.preview(lambda r:self.view.state.update(materials=r[0]));self.buttons['Áp dụng']()
        self.assertEqual(self.view.state['materials'],self.rows)
        self.view._undo_last_import();self.assertEqual(self.view._import_snapshot(),before)
    def test_callback_failure_rolls_back_application_state(self):
        before=self.view._import_snapshot()
        def commit(r):
            self.view.state['materials']=r[0];self.view.app.project.x=999
            raise RuntimeError('Injected UI failure')
        self.preview(commit);self.buttons['Áp dụng']()
        self.assertEqual(self.view._import_snapshot(),before)
    def test_changed_source_blocks_application_commit(self):
        before=self.view._import_snapshot();calls=[]
        self.preview(lambda r:calls.append(r));self.path.write_text('changed')
        self.buttons['Áp dụng']();self.assertEqual(calls,[]);self.assertEqual(self.view._import_snapshot(),before)
    def test_changed_flow_blocks_application_commit(self):
        calls=[];self.preview(lambda r:calls.append(r))
        self.view.app.design_mode.set('TÍNH TOÀN TUYẾN');self.buttons['Áp dụng']();self.assertEqual(calls,[])
    def test_edits_after_import_are_not_overwritten_by_undo(self):
        self.preview(lambda r:self.view.state.update(materials=r[0]));self.buttons['Áp dụng']()
        self.view.state['materials'][0]['values']['gamma']=1.99
        self.view._undo_last_import();self.assertEqual(self.view.state['materials'][0]['values']['gamma'],1.99)

class HeaderBoundaryTests(unittest.TestCase):
    def test_header_failures_never_link_old_application_state(self):
        chunk={'source':'Geo.xlsx / S','header_context':'A: Mã lớp\nB: Dung trọng tự nhiên (T/m³)',
               'excel_rows':[{'row':2,'cells':{'A':{'coordinate':'A2','value':'1','type':'s','format':'General'},
               'B':{'coordinate':'B2','value':1.73,'type':'n','format':'General'}}}]}
        class Response:
            ok=True
            def __init__(self,text):self.text=text
            def json(self):return {'success':True,'answer':self.text}
        bad=['', '{', 'Hãy gửi lại file.', 'The column is density.',answer(extra={'value':99})]
        x=json.loads(answer());x['items'][1]['thong_so']='fake';bad.append(json.dumps(x))
        for reply in bad:
            with self.subTest(reply=reply),tempfile.TemporaryDirectory() as tmp:
                app_state={'materials':[{'gamma':1.8}],'approved':True};before=deepcopy(app_state);calls=[]
                with data._EXTRACTION_CACHE_LOCK:data._SEMANTIC_HEADER_CACHE.clear()
                def post(url,**kw):calls.append(kw['json']);return Response(reply)
                with patch('ai_analysis_data._mapping_storage',return_value=(Path(tmp)/'memory',Path(tmp)/'audit')):
                    with self.assertRaises(data.MappingReviewRequired):data._read_excel_header_mapping(chunk,{},'mock','deepseek',post,None,None)
                self.assertEqual(app_state,before);self.assertLessEqual(len(calls),2)
                self.assertTrue(all(c['tools'] is False for c in calls))
                self.assertNotIn('1.73',json.dumps(calls))

class ReadSummaryTests(unittest.TestCase):
    def test_counts_unique_samples_and_existing_pending_holes(self):
        state={'boreholes':[{'name':'LK1','layers':[{'code':'1'}]},{'name':'LK2','layers':[]}]}
        rows=[{'code':'1','borehole_name':'LK1','sample_id':'UD1','depth_from':1,'depth_to':2},
              {'code':'1','borehole_name':'LK1','sample_id':'UD1','depth_from':1,'depth_to':2},
              {'code':'1','borehole_name':'LK2','sample_id':'UD2'},
              {'code':'2','borehole_name':'LK3','sample_id':'UD3'}]
        before=deepcopy(state);s=data.build_read_summary(state,rows,'geology')
        self.assertEqual((s['boreholes'],s['samples'],s['matched_existing'],s['new_boreholes']), (3,3,2,1))
        self.assertEqual((s['with_geology'],s['without_geology']),(1,2));self.assertEqual(state,before)
    def test_averages_are_not_invented_samples(self):
        s=data.build_read_summary({},[{'code':'1','sample_count':5,'source':'BTH trung bình'}],'curves')
        self.assertEqual(s['samples'],0);self.assertEqual(s['unidentified_records'],1)
    def test_anonymous_measurements_not_invented_boreholes(self):
        s=data.build_read_summary({},[{'code':'1','test_depth':2,'strength_sample':{'test_depth':2}}],'strength')
        self.assertEqual(s['boreholes'],0);self.assertEqual(s['samples'],1);self.assertEqual(s['samples_without_borehole'],1)
    def test_borehole_layers_not_samples(self):
        s=data.build_read_summary({},[{'name':'LK1','layers':[{'code':'1'},{'code':'2'}]}],'boreholes')
        self.assertEqual(s['boreholes'],1);self.assertEqual(s['layers'],2);self.assertEqual(s['samples'],0)
        self.assertIn('Chưa liên kết',data.format_read_summary(s));self.assertIn('Đã áp dụng',data.format_read_summary(s,applied=True))


class MandatoryAIReviewTests(unittest.TestCase):
    def review(self,response):
        from mapping_proposer import review_reader_structure
        return review_reader_structure([{'source':'S','header':'B: Dung trọng tự nhiên / T/m³'}],
            {'gamma'},[{'id':'gamma','unit':'T/m³','alias':['dung trọng tự nhiên']}],lambda _:response,retries=0)
    def valid(self):return json.dumps({'task':'reader_review','status':'confirmed','fields':['gamma'],'reason':'Đơn vị và nhóm phù hợp'},ensure_ascii=False)
    def test_accept_structure_only(self):self.assertEqual(self.review(self.valid())['status'],'confirmed')
    def test_reject_empty(self):
        with self.assertRaises(MappingFailure):self.review('')
    def test_reject_malformed(self):
        with self.assertRaises(MappingFailure):self.review('{')
    def test_reject_measurements(self):
        obj=json.loads(self.valid());obj['value']=1.7
        with self.assertRaises(MappingFailure):self.review(json.dumps(obj))
    def test_reject_invented_fields(self):
        obj=json.loads(self.valid());obj['fields']=['invented']
        with self.assertRaises(MappingFailure):self.review(json.dumps(obj))
    def test_reject_unknown_or_incomplete(self):
        for status,fields in [('unknown',['gamma']),('rejected',['gamma']),('confirmed',[])]:
            obj=json.loads(self.valid());obj.update(status=status,fields=fields)
            with self.subTest(status=status,fields=fields),self.assertRaises(MappingFailure):self.review(json.dumps(obj))
    def test_timeout_retry_bounded(self):
        from mapping_proposer import review_reader_structure
        calls=[]
        def fail(_):calls.append(1);raise TimeoutError('Timeout')
        with self.assertRaises(MappingFailure):review_reader_structure(['source'],{'gamma'},[],fail)
        self.assertEqual(len(calls),2)
    def test_known_python_reader_does_not_return_without_ai(self):
        chunk={'source':'S','header_context':'A: Mã lớp\nB: Dung trọng tự nhiên / T/m³',
               'verified_samples':[{'code':'1','gamma':1.7,'source':'S'}]}
        state={'old':[1,2,3]};before=deepcopy(state)
        class Response:
            ok=True
            def json(self):return {'success':True,'answer':''}
        with tempfile.TemporaryDirectory() as tmp,patch('ai_analysis_data.source_chunks',return_value=[chunk]),patch('ai_analysis_data._mapping_storage',return_value=(Path(tmp)/'memory',Path(tmp)/'audit')):
            with self.assertRaises(data.AIDataResponseError):
                state['old']=data.request_extraction('sample.xlsx','geology',{},'fake','deepseek',post=lambda *a,**kw:Response())
        self.assertEqual(state,before)
    def test_known_reader_confirmation_then_return_no_measurements_sent(self):
        chunk={'source':'S','header_context':'A: Mã lớp\nB: Dung trọng tự nhiên / T/m³',
               'verified_samples':[{'code':'1','gamma':1.7654321,'source':'S'}]}
        calls=[]
        class Response:
            ok=True
            def json(self):
                fields=json.loads(calls[-1]['context'].split('\n')[-1])['fields']
                return {'success':True,'answer':json.dumps({'task':'reader_review','status':'confirmed','fields':fields,'reason':'Đơn vị và nhóm phù hợp'})}
        def post(*args,**kw):calls.append(kw['json']);return Response()
        with tempfile.TemporaryDirectory() as tmp,patch('ai_analysis_data.source_chunks',return_value=[chunk]),patch('ai_analysis_data._mapping_storage',return_value=(Path(tmp)/'memory',Path(tmp)/'audit')):
            rows,notes=data.request_extraction('sample.xlsx','geology',{},'fake','deepseek',post=post)
        self.assertEqual(rows[0]['values']['gamma'],1.7654321);self.assertEqual(len(calls),1)
        self.assertNotIn('1.7654321',json.dumps(calls));self.assertFalse(calls[0]['tools'])
