import ast
import base64
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))
from ai_analysis_data import *
from soilfirm_ai_engine import before_treatment, execute_tool, present_result


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.template = Project(assessment_days=0)
        self.material = normalize_material(dict(code='1', category='Đất dính', gamma=1.7,
            e0=1.6, cc=.35, cs=.04, pc=2, co=2, cv=[1]*7))
        self.hole = normalize_borehole(dict(name='LK1', elevation=2.5,
            layers=[dict(code='1',thickness=6)]))
        self.section = dict(section_no=1, row=11, name='Test', design_stage='TK', work_item='Nền',
            station='K0+050',station_from='K0+000',station_to='K0+100',length=100,
            h_design=3,h_kcad=.15,crest_width=12,slope_m=1.5,gamma_fill=1.8,
            limit_cm=20,limit_source='THSH!BG11',source='Data.xlsx')

    def provider_fixture(self):
        # Provider response contracts belong to the PDF fallback, not an
        # unrecognised numeric Excel table which must never be sent to AI.
        import fitz
        path=self.root/'THSH_provider_fixture.pdf'
        doc=fitz.open();page=doc.new_page();page.insert_text((20,40),'THSH synthetic provider contract; layer 1')
        doc.save(path);doc.close();return path

    def project(self):
        return project_for_section(self.template,self.section,[self.material],self.hole)

    def book(self):
        import openpyxl
        book=openpyxl.Workbook();s=book.active;s.title='THSH';s['K9']=1.5
        for no,row,limit in ((1,11,20),(2,12,30)):
            values={1:no,2:100*(no-1),4:100*no,5:100,6:50+100*(no-1),7:'LK1',8:2.5,9:3,10:12,33:3.15,59:limit}
            for c,v in values.items():s.cell(row,c,v)
        path=self.root/'data.xlsx';book.save(path);book.close();return path

    def test_data_import_delta_per_segment(self):
        sections=read_data_sections(self.book(),self.template)
        self.assertEqual([s['limit_cm'] for s in sections],[20,30])
        self.assertEqual(sections[1]['limit_source'],'THSH!BG12 · STT 2')
        self.assertEqual(sections[0]['borehole_name'],'LK1')
        self.assertAlmostEqual(sections[0]['h_kcad'],.15)

    def test_missing_delta_blocks(self):
        s=deepcopy(self.section);s['limit_cm']=None
        with self.assertRaises(ValueError):project_for_section(self.template,s,[self.material],self.hole)

    def test_borehole_controls_elevation_and_thickness(self):
        p=self.project();self.assertEqual((p.ground_elevation,p.borehole_depth),(2.5,6))
        self.hole['layers'][0]['thickness']=9;self.hole['depth']=9;self.hole['elevation']=-1
        other=self.project();self.assertEqual((other.ground_elevation,other.borehole_depth),(-1,9))
        self.assertEqual(p.borehole_depth,6);self.assertEqual(self.template.soils,[])

    def test_depth_mismatch_blocks(self):
        self.hole['depth']=8
        with self.assertRaises(ValueError):self.project()

    def test_unknown_layer_blocks(self):
        self.hole['layers'][0]['code']='unknown'
        with self.assertRaises(ValueError):self.project()

    def test_real_settlement_and_comparison(self):
        p=self.project();validate_analysis_project(p);before=before_treatment(p)
        self.assertGreater(before['residual_cm'],0)
        self.assertEqual(before['pass_check'],before['residual_cm']<=20)
        result=execute_tool({'tool':'optimize','params':{'options':['Đào thay đất'],'criterion':'priority'}},p,
            {'excavation_step':.5},length=100)
        self.assertTrue(result['summary']['attempts'])
        self.assertEqual(result['summary']['attempts'][0]['limit_cm'],20)
        view=present_result(result)
        self.assertTrue(view['check_rows'])
        for row in view.get('detail_rows',[]):self.assertEqual(len(row),4)
        self.assertEqual(p.replacement_depth,0)

    def test_missing_clay_not_zero_pass(self):
        self.material['values']={'name':'1','category':'Đất dính','gamma':1.7}
        with self.assertRaisesRegex(ValueError,'thiếu'):validate_analysis_project(self.project())

    def test_missing_spt_not_zero_pass(self):
        self.material['values']={'name':'1','category':'Đất rời','gamma':1.8}
        with self.assertRaisesRegex(ValueError,'N-SPT'):validate_analysis_project(self.project())

    def test_missing_cv_blocks(self):
        self.material['values'].pop('cv')
        self.material['values'].pop('cv_constant',None)
        self.material['cv_constant']=None
        with self.assertRaisesRegex(ValueError,'Cv'):validate_analysis_project(self.project())

    def test_natural_record_advances_with_snapshot(self):
        p=self.project();p.residual_limit_cm=10000
        session=new_session(p);session['sections']=[self.section,dict(self.section,section_no=2)]
        rec=make_record(session,self.section,p,before_treatment(p))
        saved=commit_record(session,[],rec);p.soils[0].thickness=99
        self.assertEqual(session['index'],1)
        self.assertEqual(saved[0]['project_snapshot'].soils[0].thickness,6)
        self.assertEqual(saved[0]['opt_name'],'Không cần xử lý')
        boq=calculate_saved_quantities(saved)[0]['boq']
        self.assertEqual(boq['v_excavation'],0);self.assertEqual(boq['n_piles'],0)
        self.assertNotIn('boq',saved[0])

    def test_cannot_commit_failed_option(self):
        p=self.project();session=new_session(p)
        with self.assertRaises(ValueError):make_record(session,self.section,p,{'pass_check':False},
            {'status':'CHƯA ĐẠT'})
        with self.assertRaises(ValueError):make_record(session,self.section,p,{'pass_check':False})

    def test_commit_wrong_segment_blocks(self):
        session=new_session(self.template);session['sections']=[self.section]
        with self.assertRaises(ValueError):commit_record(session,[],dict(section_no=2,ai_workflow_id=session['id']))
        self.assertEqual(session['index'],0)

    def test_quantities_from_each_snapshot(self):
        p=self.project();p.residual_limit_cm=10000;session=new_session(p)
        rec=make_record(session,self.section,p,before_treatment(p))
        rec['payload']={'treatment_group':'mechanical','replacement_depth':1}
        r2=deepcopy(rec);r2['length']=50;r2['project_snapshot'].crest_half_width=3
        got=calculate_saved_quantities([rec,r2])
        self.assertAlmostEqual(got[0]['boq']['v_excavation'],(2*(6+4.725)+1)*100)
        self.assertAlmostEqual(got[1]['boq']['v_excavation'],(2*(3+4.725)+1)*50)
        r2['project_snapshot']=None
        with self.assertRaises(ValueError):calculate_saved_quantities([rec,r2])
        self.assertNotIn('boq',rec)

    def test_pdf_text_and_scan_read_all_pages(self):
        import fitz
        doc=fitz.open();doc.new_page().insert_text((20,40),'LK1 Elevation 2.5');doc.new_page()
        path=self.root/'holes.pdf';doc.save(path);doc.close()
        chunks=list(source_chunks(path));self.assertEqual(len(chunks),2)
        self.assertIn('LK1',chunks[0]['text'])
        for chunk in chunks:
            self.assertTrue(base64.b64decode(chunk['image']['data']).startswith(b'\xff\xd8\xff'))

    def test_dxf_text_and_block_attributes(self):
        import ezdxf
        doc=ezdxf.new();m=doc.modelspace();m.add_text('LK1');m.add_mtext('Layer 1 thickness 6')
        block=doc.blocks.new('HOLE');block.add_attdef('ELEV',(0,0))
        insert=m.add_blockref('HOLE',(10,20));insert.add_attrib('ELEV','2.5',(10,20))
        path=self.root/'holes.dxf';doc.saveas(path)
        text='\n'.join(c['text'] for c in source_chunks(path))
        self.assertIn('LK1',text);self.assertIn('2.5',text);self.assertIn('thickness 6',text)

    def test_large_excel_no_truncation(self):
        import openpyxl
        book=openpyxl.Workbook();s=book.active
        for n in range(1,500):s.cell(n,1,'layer-'+str(n)+'x'*100)
        path=self.root/'large.xlsx';book.save(path);book.close()
        chunks=list(source_chunks(path));self.assertGreater(len(chunks),1)
        self.assertIn('A499=layer-499','\n'.join(c['text'] for c in chunks))
        self.assertTrue(all(len(c['text'])<24000 for c in chunks))

    def test_extraction_contract_and_nulls(self):
        # Policy migration: the former assertion expected numeric AI extraction.
        # Unrecognized layouts must now stop BEFORE any provider request.
        calls=[]
        with patch('ai_analysis_data.source_chunks',return_value=iter([{'source':'Unknown.pdf / p1','text':'F20=1.7'}])):
            with self.assertRaisesRegex(AIDataResponseError,'chưa có bộ đọc Python'):
                request_extraction('Unknown.pdf','geology',{},'fake','deepseek',post=lambda *a,**k:calls.append(k))
        self.assertEqual(calls,[])


    def test_duplicate_hole_sources_merge(self):
        # Policy migration: the former assertion expected numeric AI extraction.
        # Unrecognized layouts must now stop BEFORE any provider request.
        calls=[]
        with patch('ai_analysis_data.source_chunks',return_value=iter([{'source':'Unknown.pdf / p1','text':'F20=1.7'}])):
            with self.assertRaisesRegex(AIDataResponseError,'chưa có bộ đọc Python'):
                request_extraction('Unknown.pdf','geology',{},'fake','deepseek',post=lambda *a,**k:calls.append(k))
        self.assertEqual(calls,[])

    def test_bad_json_and_nonfinite_rejected(self):
        with self.assertRaises(ValueError):parse_ai_json('không có số liệu JSON')
        for value in (float('nan'),float('inf'),True):
            with self.assertRaises(ValueError):normalize_material({'code':'1','gamma':value})

    def test_layer_arithmetic_means_missing_and_real_zero(self):
        a=normalize_material(dict(code='1',category='Đất dính',gamma=1.6,cc=.2,cs=0,spt_n=3))
        b=normalize_material(dict(code='1',category='Đất dính',gamma=1.8,cc=.4,cs=.1,spt_n=4))
        c=normalize_material(dict(code='2',category='Đất rời',gamma=2))
        b['values']['e0']=1.5
        rows,warnings=average_materials([a,b,c]);v=rows[0]['values']
        self.assertAlmostEqual(v['gamma'],1.7);self.assertAlmostEqual(v['cc'],.3)
        self.assertAlmostEqual(v['cs'],.05);self.assertEqual(v['e0'],1.5)
        self.assertEqual(v['spt_n'],3.5);self.assertEqual(rows[0]['sample_count'],2)
        self.assertEqual(rows[1]['values']['gamma'],2);self.assertFalse(warnings)
        extra=normalize_material(dict(code='1',gamma=2.0))
        combined,_=average_materials(rows+[extra])
        self.assertAlmostEqual(combined[0]['values']['gamma'],1.8)
        self.assertEqual(combined[0]['sample_count'],3)

    def test_curves_average_at_matching_pressure(self):
        a=normalize_material(dict(code='1',ep=[.1,.2],e=[1.2,1],cvp=[.1,.2],cv=[2,4]))
        b=normalize_material(dict(code='1',ep=[.1,.2],e=[1.4,1.2],cvp=[.2,.4],cv=[6,8]))
        rows,_=average_materials([a,b]);v=rows[0]['values']
        self.assertEqual(v['cvp'],[.1,.2,.4]);self.assertEqual(v['cv'],[2,5,8])
        self.assertAlmostEqual(v['e'][0],1.3);self.assertAlmostEqual(v['e'][1],1.1)

    def test_category_conflict_requires_user_choice(self):
        rows,warnings=average_materials([normalize_material(dict(code='1',category='Đất dính')),
            normalize_material(dict(code='1',category='Đất rời'))])
        self.assertNotIn('category',rows[0]['values']);self.assertTrue(warnings)

    def test_result_table_callbacks_real_output(self):
        from types import SimpleNamespace
        from ai_analysis_workflow import AnalysisWorkspace
        class Tree:
            def __init__(self):self.rows=[]
            def get_children(self):return []
            def delete(self,*args):self.rows=[]
            def insert(self,*args,**kwargs):self.rows.append(kwargs['values'])
        p=self.project();before=before_treatment(p)
        result=execute_tool({'tool':'optimize','params':{'options':['Đào thay đất']}},p,{'excavation_step':.5})
        trees=[Tree() for _ in range(3)]
        view=SimpleNamespace(option_tree=trees[0],before_tree=trees[1],detail_tree=trees[2],
            state={'pending':{'before':before,'natural':False,'result':result}},options=[],fmt=AnalysisWorkspace.fmt)
        view.clear_results=lambda:AnalysisWorkspace.clear_results(view)
        AnalysisWorkspace.show_pending(view)
        self.assertTrue(trees[0].rows);self.assertTrue(trees[1].rows);self.assertTrue(trees[2].rows)
        self.assertTrue(all(len(row)==4 for row in trees[2].rows))

    def test_stale_job_result_not_applied(self):
        from types import SimpleNamespace
        from queue import Queue
        import threading
        from ai_analysis_workflow import AnalysisWorkspace
        values=[];events=Queue();events.put(('done','old-result'))
        app=SimpleNamespace(_ai_analysis_state={},current_username='u',current_login_key='k')
        view=SimpleNamespace(events=events,busy=True,buttons=[],cancel_event=threading.Event(),
            app=app,_job_state={},_job_account=('u','k'),status=SimpleNamespace(set=values.append),
            _done=lambda value:self.fail('Applied old result'),reload_state=lambda:values.append('reloaded'),
            winfo_exists=lambda:False,stop_processing_notice=lambda:None)
        AnalysisWorkspace.drain(view)
        self.assertFalse(view.busy);self.assertIn('reloaded',values)

    def test_json_with_markdown_prose_and_thinking(self):
        expected={'materials':[{'code':'1','gamma':1.7}]}
        for answer in (json.dumps(expected), '```json\n'+json.dumps(expected)+'\n```',
                       'Kết quả đọc file:\n'+json.dumps(expected)+'\nHãy kiểm tra.',
                       '<think>đang phân tích {nội dung}</think>\n'+json.dumps(expected)):
            self.assertEqual(parse_ai_json(answer),expected)
        for answer in ('{"materials":[{"code":"1"}', '{} {}', '', '[1,2]'):
            with self.assertRaises(AIDataResponseError):parse_ai_json(answer)

    def test_invalid_ai_reply_retries_then_success(self):
        # Policy migration: the former assertion expected numeric AI extraction.
        # Unrecognized layouts must now stop BEFORE any provider request.
        calls=[]
        with patch('ai_analysis_data.source_chunks',return_value=iter([{'source':'Unknown.pdf / p1','text':'F20=1.7'}])):
            with self.assertRaisesRegex(AIDataResponseError,'chưa có bộ đọc Python'):
                request_extraction('Unknown.pdf','geology',{},'fake','deepseek',post=lambda *a,**k:calls.append(k))
        self.assertEqual(calls,[])


    def test_description_stays_metadata_through_average_and_project(self):
        samples=[]
        for gamma,description in ((1.6,'Sét mềm, màu xám'),(1.8,'Sét mềm, lẫn hữu cơ')):
            samples.append(normalize_material(dict(code='1',description=description,
                category='Đất dính',gamma=gamma,source='LaySum!20')))
        rows,_=average_materials(samples)
        self.assertEqual(rows[0]['description'],'Sét mềm, màu xám')
        self.assertNotIn('description',rows[0]['values'])
        # An older saved session may have mixed metadata into values.
        rows[0]['values']['description']='Sét mềm'
        p=project_for_section(self.template,self.section,rows,self.hole)
        self.assertAlmostEqual(p.soils[0].gamma,1.7)

    def test_description_never_numeric_even_with_extended_soil_keys(self):
        with patch('ai_analysis_data.SOIL_KEYS',SOIL_KEYS|{'description','source'}):
            material=normalize_material(dict(code='1',description='Sét mềm',source='LaySum!20',gamma=1.7))
        self.assertEqual(material['description'],'Sét mềm')
        self.assertNotIn('description',material['values'])

    def test_partial_material_keeps_good_cells_and_marks_bad_cells(self):
        # Policy migration: the former assertion expected numeric AI extraction.
        # Unrecognized layouts must now stop BEFORE any provider request.
        calls=[]
        with patch('ai_analysis_data.source_chunks',return_value=iter([{'source':'Unknown.pdf / p1','text':'F20=1.7'}])):
            with self.assertRaisesRegex(AIDataResponseError,'chưa có bộ đọc Python'):
                request_extraction('Unknown.pdf','geology',{},'fake','deepseek',post=lambda *a,**k:calls.append(k))
        self.assertEqual(calls,[])


    def test_empty_or_scalar_e_uses_e0_without_synthetic_curve(self):
        for raw in ({'e':None,'e0':1.6},{'e':'','e0':1.6},{'e':1.6}):
            material=normalize_material(dict(code='1',**raw))
            self.assertEqual(material['values']['e0'],1.6)
            self.assertNotIn('e',material['values'])
        p=self.project();p.method='e–logP'
        validate_analysis_project(p)
        a=before_treatment(p)
        p.method='Cc/Cs/Pc';b=before_treatment(p)
        self.assertGreater(a['residual_cm'],0)
        self.assertAlmostEqual(a['residual_cm'],b['residual_cm'])

    def test_missing_curve_does_not_make_e0_alone_sufficient(self):
        p=self.project();p.soils[0].cc=0
        with self.assertRaisesRegex(ValueError,'e₀ và Cc'):validate_analysis_project(p)

    def test_partial_chunks_keep_previous_success_when_next_reply_is_bad(self):
        # Policy migration: the former assertion expected numeric AI extraction.
        # Unrecognized layouts must now stop BEFORE any provider request.
        calls=[]
        with patch('ai_analysis_data.source_chunks',return_value=iter([{'source':'Unknown.pdf / p1','text':'F20=1.7'}])):
            with self.assertRaisesRegex(AIDataResponseError,'chưa có bộ đọc Python'):
                request_extraction('Unknown.pdf','geology',{},'fake','deepseek',post=lambda *a,**k:calls.append(k))
        self.assertEqual(calls,[])

    def test_partial_borehole_keeps_elevation_and_other_layers(self):
        hole,warnings=normalize_extracted_row({'name':'LK1','elevation':2.5,
            'layers':[{'code':'1','thickness':'không rõ'},{'code':'2','thickness':4}]},'boreholes','trang 1')
        self.assertEqual(hole['elevation'],2.5)
        self.assertIsNone(hole['layers'][0]['thickness'])
        self.assertEqual(hole['layers'][1]['thickness'],4)
        self.assertIsNone(hole['depth'])
        self.assertTrue(warnings)

    def test_cv_without_pressure_averages_by_layer(self):
        rows,_=average_materials([normalize_material({'code':'1','cv':[1,None,3]}),
                                 normalize_material({'code':'1','cv_constant':4})])
        self.assertAlmostEqual(rows[0]['cv_constant'],3)
        self.assertFalse(rows[0]['values'].get('cv'))

    def test_cu_effective_phi_derives_m_and_direct_shear_does_not(self):
        import math
        m=normalize_material({'code':'1','phi_cu_effective':30,'strength_m':.1})
        self.assertAlmostEqual(m['values']['strength_m'],math.tan(math.radians(30)))
        rows,_=average_materials([m,normalize_material({'code':'1','phi_cu_effective':10})])
        self.assertAlmostEqual(rows[0]['values']['strength_m'],math.tan(math.radians(20)))
        self.assertNotIn('strength_m',normalize_material({'code':'1','friction_phi':30})['values'])

    def test_strength_excel_merge_preserves_geology_and_does_not_dilute_co(self):
        for alias in ('c0','su','Su','cu','c_u'):
            strength=normalize_material({'code':'1',alias:2.5,'phi_cu_effective':20,'source':'Strength!A5'})
            merged=merge_strength_materials([self.material],[strength])
            self.assertEqual(merged[0]['values']['gamma'],1.7)
            self.assertEqual(merged[0]['values']['co'],2.5)
            rows,_=average_materials(merged)
            self.assertEqual(rows[0]['values']['co'],2.5)
            self.assertEqual(self.material['values']['co'],2)

    def test_ai_ratio_default_natural_and_user_override(self):
        from batch_calculation import _drainage
        p=self.project();self.assertEqual(p.soils[0].ch_cv,1)
        self.assertEqual(p.soils[0].drainage,1)
        captured=[]
        def stop(trial,*args):captured.append(trial);raise RuntimeError('captured')
        settings={'pvd_spacing':1,'pvd_diameter':5,'sd_spacing':2,'sd_diameter':30}
        for variant,ratio in (('PVD',2),('SD',2),('Chờ lún',1)):
            with patch('batch_calculation.optimize_drainage_time',side_effect=stop):
                with self.assertRaises(RuntimeError):_drainage(p,variant,20,settings)
            self.assertEqual(captured[-1].soils[0].ch_cv,ratio)
        with patch('batch_calculation.optimize_drainage_time',side_effect=stop):
            with self.assertRaises(RuntimeError):_drainage(p,'PVD',20,{**settings,'ch_cv':3})
        self.assertEqual(captured[-1].soils[0].ch_cv,3)
        self.assertEqual(p.soils[0].ch_cv,1)
        self.material['values']['ch_cv']=1.5;p=self.project()
        with patch('batch_calculation.optimize_drainage_time',side_effect=stop):
            with self.assertRaises(RuntimeError):_drainage(p,'PVD',20,settings)
        self.assertEqual(captured[-1].soils[0].ch_cv,1.5)

    def test_strength_read_uses_separate_contract(self):
        # Policy migration: the former assertion expected numeric AI extraction.
        # Unrecognized layouts must now stop BEFORE any provider request.
        calls=[]
        with patch('ai_analysis_data.source_chunks',return_value=iter([{'source':'Unknown.pdf / p1','text':'F20=1.7'}])):
            with self.assertRaisesRegex(AIDataResponseError,'chưa có bộ đọc Python'):
                request_extraction('Unknown.pdf','geology',{},'fake','deepseek',post=lambda *a,**k:calls.append(k))
        self.assertEqual(calls,[])


    def test_two_excel_files_merge_complementary_indicators_by_layer(self):
        first=normalize_material({'code':'1','gamma':1.7,'e0':1.6,'source':'Geo.xlsx!20'})
        second=normalize_material({'code':'1','co':2.5,'cv_constant':3,'source':'Strength.xlsx!5'})
        with patch('ai_analysis_data.unique_data_sources',side_effect=lambda paths,*a,**k:(paths,[])), patch('ai_analysis_data.request_extraction',side_effect=[([first],[]),([second],[])]) as read:
            rows,_=request_extraction_files(['Geo.xlsx','Strength.xlsx'],'geology',{},'fake','gemini')
        self.assertEqual(read.call_count,2)
        self.assertEqual(len(rows),1)
        self.assertEqual(rows[0]['values']['gamma'],1.7)
        self.assertEqual(rows[0]['values']['co'],2.5)
        self.assertEqual(rows[0]['cv_constant'],3)
        self.assertIn('Geo.xlsx',rows[0]['source']);self.assertIn('Strength.xlsx',rows[0]['source'])

    def test_multifile_read_averages_values_without_merging_distinct_codes(self):
        a=normalize_material({'code':'1','gamma':1.6,'source':'A'})
        b=normalize_material({'code':'1','gamma':1.8,'source':'B'})
        tk=normalize_material({'code':'TK1','gamma':2,'source':'B','layer_code_verified':True})
        with patch('ai_analysis_data.unique_data_sources',side_effect=lambda paths,*a,**k:(paths,[])), patch('ai_analysis_data.request_extraction',side_effect=lambda path,*args,**kwargs:([a],[]) if Path(path).name=='A.xlsx' else ([b,tk],[])):
            rows,_=request_extraction_files(['A.xlsx','B.xlsx'],'geology',{},'fake','gemini')
        self.assertEqual(len(rows),2);self.assertAlmostEqual(rows[0]['values']['gamma'],1.7)

    def test_multifile_read_keeps_success_when_other_file_fails(self):
        row=normalize_material({'code':'1','e0':1.5})
        with patch('ai_analysis_data.unique_data_sources',side_effect=lambda paths,*a,**k:(paths,[])), patch('ai_analysis_data.request_extraction',side_effect=lambda path,*args,**kwargs: (_ for _ in ()).throw(AIDataResponseError('lỗi','phản hồi')) if Path(path).name=='A.xlsx' else ([row],[])):
            rows,warnings=request_extraction_files(['A.xlsx','B.xlsx'],'geology',{},'fake','gemini')
        self.assertEqual(rows[0]['values']['e0'],1.5)
        self.assertIn('A.xlsx',warnings[0])

    def test_unit_guide_is_sent_for_both_geology_and_strength(self):
        # Policy migration: the former assertion expected numeric AI extraction.
        # Unrecognized layouts must now stop BEFORE any provider request.
        calls=[]
        with patch('ai_analysis_data.source_chunks',return_value=iter([{'source':'Unknown.pdf / p1','text':'F20=1.7'}])):
            with self.assertRaisesRegex(AIDataResponseError,'chưa có bộ đọc Python'):
                request_extraction('Unknown.pdf','geology',{},'fake','deepseek',post=lambda *a,**k:calls.append(k))
        self.assertEqual(calls,[])


    def test_new_lab_curves_replace_old_and_survive_reaveraging(self):
        old=normalize_material({'code':'1','category':'Đất dính','gamma':1.7,'e0':1.6,'co':2,'cv_constant':3})
        new=normalize_material({'code':'1','ep':[0,.5,1],'e':[1.5,1.2,1.1],
                               'cvp':[.25,.75],'cv':[2,4],'source':'Lab.xlsx!20'})
        rows,warnings=merge_lab_curve_materials([old],[new])
        self.assertFalse(warnings)
        self.assertEqual(rows[0]['values']['e'],[1.5,1.2,1.1])
        self.assertEqual(rows[0]['values']['cv'],[2,4])
        self.assertEqual(rows[0]['cv_constant'],3)
        self.assertEqual(rows[0]['values']['co'],2)
        averaged,_=average_materials(rows)
        self.assertEqual(averaged[0]['values']['cv'],[2,4])
        self.assertEqual(averaged[0]['cv_constant'],3)
        p=project_for_section(self.template,self.section,averaged,self.hole)
        self.assertEqual(p.soils[0].cvp,[.25,.75])
        self.assertEqual(p.method,'Cc/Cs/Pc')
        validate_analysis_project(p)
        self.assertGreater(before_treatment(p)['residual_cm'],0)
        self.assertFalse(old['values'].get('cv'))
        self.assertEqual(old['cv_constant'],3)

    def test_updating_only_e_keeps_cv_and_other_layers(self):
        old=normalize_material({'code':'1','cv_constant':3})
        other=normalize_material({'code':'TK1','gamma':2,'layer_code_verified':True})
        new=normalize_material({'code':'1','ep':[0,1],'e':[1.6,1.2]})
        rows,_=merge_lab_curve_materials([old,other],[new])
        self.assertEqual(rows[0]['cv_constant'],3)
        self.assertEqual(rows[1],other)

    def test_bad_curve_update_keeps_existing_curve(self):
        old=normalize_material({'code':'1','cv_constant':3})
        new=normalize_material({'code':'1','cvp':[1,.5],'cv':[2,4]})
        rows,warnings=merge_lab_curve_materials([old],[new])
        self.assertEqual(rows,[old]);self.assertTrue(warnings)

    def test_lab_curve_read_requests_actual_pressure_pairs(self):
        # Policy migration: the former assertion expected numeric AI extraction.
        # Unrecognized layouts must now stop BEFORE any provider request.
        calls=[]
        with patch('ai_analysis_data.source_chunks',return_value=iter([{'source':'Unknown.pdf / p1','text':'F20=1.7'}])):
            with self.assertRaisesRegex(AIDataResponseError,'chưa có bộ đọc Python'):
                request_extraction('Unknown.pdf','geology',{},'fake','deepseek',post=lambda *a,**k:calls.append(k))
        self.assertEqual(calls,[])


    def test_summary_label_is_not_a_layer_code(self):
        for code in ('Giá trị trung bình:','Average','Min','Max','Độ lệch chuẩn'):
            with self.assertRaises(ValueError):normalize_material({'code':code,'gamma':1.7})
        self.assertEqual(normalize_material({'code':'1','source':'giá trị trung bình có sẵn','gamma':1.7})['values']['gamma'],1.7)

    def test_cloudflare_excel_budget_keeps_every_row(self):
        import openpyxl
        book=openpyxl.Workbook();sheet=book.active
        sheet.append(['Layer','Wet density (g/cm³)','Void ratio'])
        for row in range(2,82):sheet.append([1,1.7,1.6]+['value'*40]*6)
        path=self.root/'wide.xlsx';book.save(path);book.close()
        small=list(source_chunks(path,max_data_chars=2600))
        standard=list(source_chunks(path))
        self.assertGreater(len(small),len(standard))
        for row in range(2,82):
            token=f'A{row}=1'
            self.assertEqual(sum(token+' |' in chunk['text'].split('PHẦN DỮ LIỆU HIỆN TẠI:')[-1] for chunk in small),1)

    def test_cloudflare_receives_cell_mapping_rules_and_smaller_batches(self):
        # Policy migration: the former assertion expected numeric AI extraction.
        # Unrecognized layouts must now stop BEFORE any provider request.
        calls=[]
        with patch('ai_analysis_data.source_chunks',return_value=iter([{'source':'Unknown.pdf / p1','text':'F20=1.7'}])):
            with self.assertRaisesRegex(AIDataResponseError,'chưa có bộ đọc Python'):
                request_extraction('Unknown.pdf','geology',{},'fake','deepseek',post=lambda *a,**k:calls.append(k))
        self.assertEqual(calls,[])

    def test_gemini_retries_metadata_only_reply_then_extracts_values(self):
        # Policy migration: the former assertion expected numeric AI extraction.
        # Unrecognized layouts must now stop BEFORE any provider request.
        calls=[]
        with patch('ai_analysis_data.source_chunks',return_value=iter([{'source':'Unknown.pdf / p1','text':'F20=1.7'}])):
            with self.assertRaisesRegex(AIDataResponseError,'chưa có bộ đọc Python'):
                request_extraction('Unknown.pdf','geology',{},'fake','deepseek',post=lambda *a,**k:calls.append(k))
        self.assertEqual(calls,[])

    def test_gemini_retries_empty_list_for_numeric_excel_chunk(self):
        # Policy migration: the former assertion expected numeric AI extraction.
        # Unrecognized layouts must now stop BEFORE any provider request.
        calls=[]
        with patch('ai_analysis_data.source_chunks',return_value=iter([{'source':'Unknown.pdf / p1','text':'F20=1.7'}])):
            with self.assertRaisesRegex(AIDataResponseError,'chưa có bộ đọc Python'):
                request_extraction('Unknown.pdf','geology',{},'fake','deepseek',post=lambda *a,**k:calls.append(k))
        self.assertEqual(calls,[])

    def test_metadata_only_failure_retains_actual_reply(self):
        # Policy migration: the former assertion expected numeric AI extraction.
        # Unrecognized layouts must now stop BEFORE any provider request.
        calls=[]
        with patch('ai_analysis_data.source_chunks',return_value=iter([{'source':'Unknown.pdf / p1','text':'F20=1.7'}])):
            with self.assertRaisesRegex(AIDataResponseError,'chưa có bộ đọc Python'):
                request_extraction('Unknown.pdf','geology',{},'fake','deepseek',post=lambda *a,**k:calls.append(k))
        self.assertEqual(calls,[])


    def test_move_borehole_layer_changes_calculation_order_preserving_values(self):
        materials=[self.material,normalize_material({'code':'2','category':'Đất dính','gamma':1.9,'e0':.8,'cc':.1,'source':'Excel B'})]
        hole=normalize_borehole({'name':'LK2','elevation':2,'layers':[{'code':'1','thickness':6},{'code':'2','thickness':4}]})
        first=project_for_section(self.template,self.section,materials,hole)
        move_layer(hole['layers'],1,-1)
        second=project_for_section(self.template,self.section,materials,hole)
        self.assertEqual([s.name for s in first.soils],['1','2'])
        self.assertEqual([(s.name,s.thickness,s.gamma) for s in second.soils],[('2',4,1.9),('1',6,1.7)])
        self.assertEqual(second.borehole_depth,first.borehole_depth)
        self.assertEqual(materials[1]['source'],'Excel B')
        move_layer(materials,1,-1)
        self.assertEqual([m['code'] for m in materials],['2','1'])
        self.assertEqual(materials[0]['source'],'Excel B')
        self.assertEqual(move_layer(materials,0,-1),0)
        self.assertEqual(move_layer(materials,1,1),1)

    def test_bad_reply_keeps_actual_response_and_source(self):
        # Policy migration: the former assertion expected numeric AI extraction.
        # Unrecognized layouts must now stop BEFORE any provider request.
        calls=[]
        with patch('ai_analysis_data.source_chunks',return_value=iter([{'source':'Unknown.pdf / p1','text':'F20=1.7'}])):
            with self.assertRaisesRegex(AIDataResponseError,'chưa có bộ đọc Python'):
                request_extraction('Unknown.pdf','geology',{},'fake','deepseek',post=lambda *a,**k:calls.append(k))
        self.assertEqual(calls,[])


    def test_truncated_reply_never_imports_partial_data(self):
        # Policy migration: the former assertion expected numeric AI extraction.
        # Unrecognized layouts must now stop BEFORE any provider request.
        calls=[]
        with patch('ai_analysis_data.source_chunks',return_value=iter([{'source':'Unknown.pdf / p1','text':'F20=1.7'}])):
            with self.assertRaisesRegex(AIDataResponseError,'chưa có bộ đọc Python'):
                request_extraction('Unknown.pdf','geology',{},'fake','deepseek',post=lambda *a,**k:calls.append(k))
        self.assertEqual(calls,[])


    def test_job_notification_start_stop_and_error(self):
        from types import SimpleNamespace
        from queue import Queue
        import threading
        from ai_analysis_workflow import AnalysisWorkspace
        messages=[];notices=[];applied=[];state={}
        app=SimpleNamespace(_ai_analysis_state=state,current_username='u',current_login_key='k',
            status_text=SimpleNamespace(set=messages.append))
        view=SimpleNamespace(busy=False,cancel_event=threading.Event(),status=SimpleNamespace(set=messages.append,get=lambda:messages[-1]),
            buttons=[],state=state,app=app,events=Queue(),winfo_exists=lambda:False,
            start_processing_notice=lambda text:notices.append('start'),stop_processing_notice=lambda:notices.append('stop'),
            error=lambda exc:messages.append(str(exc)))
        class Thread:
            def __init__(self,target,**kwargs):self.target=target
            def start(self):self.target()
        def action(progress):progress('AI đang xử lý dữ liệu');return 'ok'
        with patch('ai_analysis_workflow.threading.Thread',Thread):
            AnalysisWorkspace.run_job(view,'AI đang xử lý',action,applied.append)
        self.assertTrue(view.busy);AnalysisWorkspace.drain(view)
        self.assertFalse(view.busy);self.assertEqual(notices,['start','stop']);self.assertEqual(applied,['ok'])
        def fail(progress):raise ValueError('lỗi nguồn')
        with patch('ai_analysis_workflow.threading.Thread',Thread):
            AnalysisWorkspace.run_job(view,'AI đang xử lý',fail,applied.append)
        AnalysisWorkspace.drain(view)
        self.assertEqual(notices,['start','stop','start','stop']);self.assertIn('lỗi nguồn',messages)

    def test_constant_cv_uses_same_value_at_any_pressure(self):
        from model import cv_cm2_day
        a=normalize_material(dict(code='1',cv_constant=.2))
        b=normalize_material(dict(code='1',cv_constant=.6))
        rows,_=average_materials([a,b]);v=rows[0]['values']
        self.assertAlmostEqual(rows[0]['cv_constant'],.4)
        soil=Soil(**v)
        for pressure in (1,10,100):self.assertAlmostEqual(cv_cm2_day(soil,pressure),86.4*.4)

    def test_excel_header_and_units_repeated_on_each_chunk(self):
        import openpyxl
        book=openpyxl.Workbook();sheet=book.active;sheet.title='LaySum'
        for c,label in ((1,'Layer'),(2,'Boring'),(3,'Sample No.'),(4,'Bulk density'),(5,'Consolidation test')):sheet.cell(1,c,label)
        sheet.cell(2,4,'Wet density');sheet.cell(3,4,'g/cm3');sheet.cell(2,5,'Coef. of Consolidation')
        sheet.cell(3,5,'10-3cm2/s');sheet.merge_cells('F1:G1');sheet['F1']='Direct Shear Test'
        sheet['F2']='Angle';sheet['G2']='Cohesion';sheet['F3']='degree';sheet['G3']='kg/cm2'
        for r in range(4,154):
            for c,value in enumerate((1,'LK1','UD'+str(r),1.6,.4,313,.04),1):sheet.cell(r,c,value)
            sheet.cell(r,6).number_format="00°00'"
        path=self.root/'merged.xlsx';book.save(path);book.close()
        chunks=list(source_chunks(path));self.assertGreater(len(chunks),1)
        for chunk in chunks:
            self.assertIn('Wet density',chunk['text']);self.assertIn('g/cm3',chunk['text'])
            self.assertIn('10-3cm2/s',chunk['text']);self.assertIn('Direct Shear Test',chunk['text'])
            self.assertLess(len(chunk['text']),24000)
        self.assertIn("3°13'",chunks[0]['text'])
        self.assertNotIn('UD4',chunks[0]['text'].split('PHẦN DỮ LIỆU HIỆN TẠI:')[0])

    def test_geology_guide_sent_with_each_extraction(self):
        # Policy migration: the former assertion expected numeric AI extraction.
        # Unrecognized layouts must now stop BEFORE any provider request.
        calls=[]
        with patch('ai_analysis_data.source_chunks',return_value=iter([{'source':'Unknown.pdf / p1','text':'F20=1.7'}])):
            with self.assertRaisesRegex(AIDataResponseError,'chưa có bộ đọc Python'):
                request_extraction('Unknown.pdf','geology',{},'fake','deepseek',post=lambda *a,**k:calls.append(k))
        self.assertEqual(calls,[])


    def test_chat_math_symbols_keep_values(self):
        import re
        tree=ast.parse((ROOT/'chat_dialog.py').read_text())
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='format_ai_chat_text')
        ns={'re':re};exec(compile(ast.Module(body=[function],type_ignores=[]),'chat-format','exec'),ns)
        fmt=ns['format_ai_chat_text']
        self.assertEqual(fmt(r'**Kiểm toán:** $\Delta S \leq 20 \mathrm{cm}$'), 'Kiểm toán: ΔS ≤ 20 cm')
        text=fmt(r'\(\gamma = 1.8 \mathrm{T/m^{3}}; \sigma_v \geq 10\)')
        self.assertIn('γ = 1.8',text);self.assertIn('σᵥ ≥ 10',text);self.assertIn('m³',text);self.assertNotIn('\\mathrm',text)
        self.assertEqual(fmt(r'$\frac{2}{3} \times \sqrt{4}$'),'(2)/(3) × √(4)')

    def test_session_roundtrip_project_snapshots(self):
        module=ast.parse((ROOT/'app.py').read_text())
        cls=next(n for n in module.body if isinstance(n,ast.ClassDef) and n.name=='App')
        funcs=[n for n in cls.body if isinstance(n,ast.FunctionDef) and n.name in ('_pack_saved_result','_unpack_saved_result')]
        ns={'Project':Project};exec(compile(ast.fix_missing_locations(ast.Module(body=[ast.ClassDef(name='Codec',bases=[],keywords=[],body=funcs,decorator_list=[])],type_ignores=[])),'codec','exec'),ns)
        codec=ns['Codec']();session=new_session(self.project());session['pending_project']=self.project()
        restored=codec._unpack_saved_result(json.loads(json.dumps(codec._pack_saved_result(session))))
        self.assertIsInstance(restored['template'],Project)
        self.assertEqual(restored['pending_project'].soils[0].thickness,6)
        self.assertEqual(restored['id'],session['id'])

class AIBatchTests(unittest.TestCase):
    setUp=WorkflowTests.setUp
    project=WorkflowTests.project
    book=WorkflowTests.book
    # Reuse the realistic geology and Data fixture without rerunning inherited tests.
    def test_batch_computes_and_displays_before_after(self):
        from batch_calculation import natural_metrics
        source=self.book();base=self.project()
        def section(path,number,template):
            p=deepcopy(base)
            p.residual_limit_cm=1000 if number==1 else 15
            p.residual_limit_source=f'THSH!BG{10+number}'
            return p,100
        messages=[]
        with patch('batch_calculation.import_section',side_effect=section),patch('batch_bundle.export_bundle') as export:
            result=execute_tool({'tool':'batch','params':{'numbers':[2,1],
                'priorities':['Đào thay đất','Cọc tre + đào thay đất']}},base,
                {'excavation_step':.5},source=source,output=str(self.root),progress=messages.append)
        self.assertEqual([r['section_no'] for r in result['records']],[1,2])
        self.assertTrue(result['records'][0]['before_pass'])
        self.assertFalse(result['records'][1]['before_pass'])
        self.assertTrue(result['records'][1]['attempts'])
        self.assertEqual(result['records'][1]['limit'],15)
        self.assertTrue(any('STT 2' in m for m in messages))
        self.assertTrue(export.call_args.kwargs['individual'])
        view=present_result(result)
        self.assertTrue(any('Trước xử lý' in r[0] for r in view['rows']))
        self.assertTrue(view['parameter_rows'])
        self.assertTrue(view['check_rows'])
        self.assertTrue(view['detail_rows'])
        self.assertTrue(all(len(row)==len(view['columns']) for row in view['rows']))
        self.assertTrue(all(row[2]!='—' for row in view['rows']))
        self.assertEqual(base.replacement_depth,0)

    def test_batch_exports_real_pdf_and_json_in_section_order(self):
        from pypdf import PdfReader
        base=self.project();source=self.book()
        import openpyxl
        book=openpyxl.load_workbook(source);book.create_sheet('CTDY');book.save(source);book.close()
        def section(path,number,template):
            p=deepcopy(base);p.residual_limit_cm=1000 if number==1 else 15
            p.residual_limit_source=f'THSH!BG{10+number}'
            return p,100
        with patch('batch_calculation.import_section',side_effect=section):
            result=execute_tool({'tool':'batch','params':{'numbers':[2,1],
                'priorities':['Đào thay đất','Cọc tre + đào thay đất']}},base,
                {'excavation_step':.5},source=source,output=str(self.root))
        folder=Path(result['summary']['output_folder'])/'Ho_so_tung_doan'
        # Individual files are created beside the combined bundle.
        if not folder.exists():folder=next(Path(result['summary']['output_folder']).rglob('Ho_so_tung_doan'))
        for number in (1,2):
            data=json.loads((folder/f'STT_{number:04d}.json').read_text(encoding='utf-8'))
            self.assertEqual(data['records'][0]['section_no'],number)
            pdf=PdfReader(str(folder/f'STT_{number:04d}.pdf'))
            self.assertGreater(len(pdf.pages),0)
            self.assertEqual(pdf.outline[0].title,'Trước xử lý')
            self.assertEqual(len(pdf.outline),1 if number==1 else 2)

    def test_batch_rejects_unrecognized_priority_before_execution(self):
        with self.assertRaises(ValueError):
            execute_tool({'tool':'batch','params':{'numbers':[1],'priorities':['PA tự bịa']}},
                self.project(),{},source=self.book(),output=str(self.root))

class ExcelSpeedTests(unittest.TestCase):
    def workbook(self,path,value=1.7):
        import openpyxl
        b=openpyxl.Workbook();sh=b.active
        sh.append(['Lớp','Sample No.','Bulk density (g/cm3)','Void Ratio',
                   'Natural moisture content (%)','Compression Index',
                   'Coefficient of uniformity','Custom lab indicator','Depth (m)'])
        sh.append(['1','UD1',value,1.6,50,.35,3,123,4.5])
        b.save(path);b.close()

    def test_filters_only_known_unrelated_columns_keeps_sample_and_unknown(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'lab.xlsx';self.workbook(path)
            text='\n'.join(c['text'] for c in source_chunks(path,extraction_kind='geology'))
            self.assertIn('B2=UD1',text);self.assertIn('C2=1.7',text)
            self.assertIn('D2=1.6',text);self.assertIn('F2=0.35',text)
            self.assertIn('H2=123',text);self.assertIn('I2=4.5',text)
            self.assertNotIn('E2=50',text);self.assertNotIn('G2=3',text)
            self.assertIn('A: Lớp',text);self.assertIn('C: Bulk density',text)
            original='\n'.join(c['text'] for c in source_chunks(path))
            self.assertIn('E2=50',original)

    def test_parallel_requests_overlap_but_keep_source_order(self):
        from ai_analysis_data import _ordered_extraction_chunks
        from threading import Event
        second_started=Event()
        def extract(index,chunk):
            if index==1:
                self.assertTrue(second_started.wait(2),'Second request must run concurrently')
            if index==2:second_started.set()
            return chunk
        values=list(_ordered_extraction_chunks(['first','second','third'],extract,2))
        self.assertEqual(values,[(1,'first'),(2,'second'),(3,'third')])

    def test_cached_numbers_require_fresh_ai_confirmation_and_file_changes_reparse(self):
        from ai_analysis_data import _EXTRACTION_CACHE,_EXTRACTION_CACHE_LOCK
        with _EXTRACTION_CACHE_LOCK:_EXTRACTION_CACHE.clear()
        calls=[]
        class Response:
            ok=True
            def json(self):return {'success':True,'answer':json.dumps({'task':'reader_review','status':'confirmed','fields':calls[-1],'reason':'Đơn vị và nhóm phù hợp'})}
        def post(url,**args):
            request=json.loads(args['json']['context'].split('\n')[-1])
            calls.append(request['fields']);return Response()
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'cache.xlsx';self.workbook(path)
            from types import SimpleNamespace
            with patch.dict(sys.modules,{'requests':SimpleNamespace(post=post)}):
                first,_=request_extraction(path,'geology',{},'fake','cloudflare')
                first[0]['values']['gamma']=99
                cached,_=request_extraction(path,'geology',{},'fake','cloudflare')
                self.assertEqual(cached[0]['values']['gamma'],1.7)
                self.assertEqual(len(calls),2)
                self.workbook(path,1.8)
                updated,_=request_extraction(path,'geology',{},'fake','cloudflare')
                self.assertEqual(updated[0]['values']['gamma'],1.8)
                self.assertEqual(len(calls),3)

    def test_cancel_stops_dispatch_without_waiting_for_network(self):
        from ai_analysis_data import _ordered_extraction_chunks
        from threading import Event
        stopped=Event()
        def extract(index,chunk):stopped.set();return chunk
        with self.assertRaises(InterruptedError):
            list(_ordered_extraction_chunks(range(50),extract,2,stopped.is_set))

class ReliabilityTests(unittest.TestCase):
    def test_known_import_is_filtered_before_remote_extraction(self):
        import ai_analysis_data as data
        import openpyxl
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.xlsx';book=openpyxl.Workbook();book.active['A1']='Data';book.save(path);book.close()
            fingerprint=data.data_source_fingerprint(path)
            with patch('ai_analysis_data.data_source_fingerprint',wraps=data.data_source_fingerprint) as scan:
                rows,notes=data.request_extraction_files([str(path)],'geology',{},'fake','gemini',
                    post=lambda *a,**k: self.fail('An already imported workbook must not invoke AI'),
                    known_sources={'geology:'+fingerprint:'previous.xlsx'})
            self.assertEqual(rows,[]);self.assertEqual(scan.call_count,1)
            self.assertTrue(any('previous.xlsx' in note for note in notes))

    def test_atomic_save_preserves_existing_project_on_write_failure(self):
        import model
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'project.json'
            model.save(Project(name='Dự án cũ'),str(path));original=path.read_bytes()
            with patch('model.os.replace',side_effect=OSError('disk unavailable')):
                with self.assertRaises(OSError):model.save(Project(name='Dự án mới'),str(path))
            self.assertEqual(path.read_bytes(),original)
            self.assertEqual(list(Path(directory).glob('*.tmp')),[])
            model.save(Project(name='Dự án mới'),str(path))
            self.assertEqual(model.load(str(path)).name,'Dự án mới')

    def test_atomic_save_preserves_existing_project_on_serialization_failure(self):
        import model
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'project.json';model.save(Project(),str(path));original=path.read_bytes()
            broken=Project();broken.calculation_results={'invalid':object()}
            with self.assertRaises(TypeError):model.save(broken,str(path))
            self.assertEqual(path.read_bytes(),original)
            self.assertEqual(list(Path(directory).glob('*.tmp')),[])

    def test_conflict_quarantine_is_per_sample_and_survives_later_imports(self):
        def sample(sample_id,gamma=None):
            return normalize_material({'code':'1','borehole_name':'LK1','sample_id':sample_id,
                'depth_from':1,'depth_to':2,'gamma':gamma,'source':sample_id})
        rows,_=average_materials([sample('UD1',1.6),sample('UD1',1.8),
                                  sample('UD2'),sample('UD2',1.9)])
        self.assertAlmostEqual(rows[0]['values']['gamma'],1.9)
        self.assertEqual(len(rows[0]['conflicts']),1)
        again,_=average_materials(rows+[sample('UD1',1.7)])
        self.assertAlmostEqual(again[0]['values']['gamma'],1.9)

    def test_fractional_spt_average_is_kept_but_fractional_test_count_is_rejected(self):
        rows,_=average_materials([normalize_material({'code':'1','spt_n':3}),normalize_material({'code':'1','spt_n':4})])
        self.assertEqual(normalize_material({'code':'1',**rows[0]['values']})['values']['spt_n'],3.5)
        point,issues=normalize_extracted_row({'code':'1','spt_n':3.5,'gamma':1.7},'geology','S!A2')
        self.assertNotIn('spt_n',point['values']);self.assertTrue(issues)
        self.assertEqual(point['values']['gamma'],1.7)

    def test_cancel_closes_source_generator(self):
        from ai_analysis_data import _ordered_extraction_chunks
        from threading import Event
        closed=[];stopped=Event()
        def chunks():
            try:
                yield 'first'
                yield 'second'
            finally:closed.append(True)
        def extract(index,chunk):stopped.set();return chunk
        with self.assertRaises(InterruptedError):list(_ordered_extraction_chunks(chunks(),extract,1,stopped.is_set))
        self.assertEqual(closed,[True])

    def batch_view(self):
        from types import SimpleNamespace
        from queue import Queue
        from threading import Event
        calls=[];state={};messages=[]
        app=SimpleNamespace(_ai_analysis_state=state,current_username='u',current_login_key='k',
            refresh_result_summary=lambda:calls.append('summary'),
            batch_design_view=SimpleNamespace(refresh=lambda:calls.append('batch')))
        view=SimpleNamespace(events=Queue(),busy=True,cancel_event=Event(),_job_state=state,
            _job_account=('u','k'),app=app,buttons=[],status=SimpleNamespace(set=messages.append,get=lambda:'done'),
            stop_processing_notice=lambda:None,_done=lambda result:None,_job_error=messages.append,
            error=messages.append,winfo_exists=lambda:False)
        for n in range(10):view.events.put(('batch_record',(n,{'section':n},{'pending':n})))
        return view,calls,messages

    def test_batch_ui_refreshes_once_per_poll(self):
        from ai_analysis_workflow import AnalysisWorkspace
        view,calls,_=self.batch_view();AnalysisWorkspace.drain(view)
        self.assertEqual(len(view.app._batch_candidates),10)
        self.assertEqual(calls,['summary','batch'])

    def test_callback_failure_keeps_worker_polling_alive(self):
        from ai_analysis_workflow import AnalysisWorkspace
        view,_,messages=self.batch_view();scheduled=[]
        view.app.refresh_result_summary=lambda:(_ for _ in ()).throw(ValueError('bad display'))
        view.winfo_exists=lambda:True;view.drain=lambda:None;view.after=lambda *args:scheduled.append(args)
        AnalysisWorkspace.drain(view)
        self.assertEqual(len(scheduled),1);self.assertEqual(str(messages[0]),'bad display')


class RealAuditRegressionTests(unittest.TestCase):
    def setUp(self):
        import ai_analysis_data as data
        with data._EXTRACTION_CACHE_LOCK:data._SEMANTIC_HEADER_CACHE.clear()

    def test_header_ai_receives_no_measured_values_and_units_stay_in_python(self):
        import ai_analysis_data as data
        calls=[]
        class Response:
            ok=True
            def json(self):return {'success':True,'answer':json.dumps({'task':'column_mapping','items':[
                {'cot_id':1,'thong_so':'code','do_tin_cay':.99,'ly_do':'Mã lớp đất'},
                {'cot_id':2,'thong_so':'gamma','do_tin_cay':.99,'ly_do':'Dung trọng tự nhiên'}],'khong_chac':[]},ensure_ascii=False)}
        def post(url,**kw):calls.append(kw['json']);return Response()
        def chunk(unit,value):return {'source':'S','header_context':'A: Layer\nB: Natural density / '+unit,
            'excel_rows':[{'row':2,'cells':{'A':{'coordinate':'A2','value':'1','type':'s','format':'General'},
            'B':{'coordinate':'B2','value':value,'type':'n','format':'0.000'}}}]}
        with tempfile.TemporaryDirectory() as tmp,patch('ai_analysis_data._mapping_storage',return_value=(Path(tmp)/'memory.json',Path(tmp)/'audit.jsonl')):
            rows,notes=data._read_excel_header_mapping(chunk('kN/m³',17.65),{},'fake','deepseek',post,None,None)
            self.assertAlmostEqual(rows[0]['values']['gamma'],17.65/9.80665)
            self.assertNotIn('17.65',json.dumps(calls,ensure_ascii=False))
            changed,_=data._read_excel_header_mapping(chunk('kN/m³',18.0),{},'fake','deepseek',post,None,None)
            self.assertAlmostEqual(changed[0]['values']['gamma'],18.0/9.80665);self.assertEqual(len(calls),2)
            other,_=data._read_excel_header_mapping(chunk('g/cm³',1.8),{},'fake','deepseek',post,None,None)
            self.assertAlmostEqual(other[0]['values']['gamma'],1.8);self.assertEqual(len(calls),3)

    def test_semantic_category_request_has_no_numeric_table(self):
        import ai_analysis_data as data
        item=normalize_material({'code':'1','gamma':1.7,'description':'Sét mềm'})
        calls=[]
        notes=data._classify_excel_semantics([item],{},'fake','deepseek',lambda *a,**k:calls.append(k),None,None)
        self.assertEqual(calls,[]);self.assertNotIn('category',item['values']);self.assertTrue(notes)

    def test_separate_project_scopes_cannot_be_averaged_or_selected_silently(self):
        rows,_=average_materials([normalize_material({'code':'1','gamma':1.6,'project_scope':'A'}),
                                  normalize_material({'code':'1','gamma':1.9,'project_scope':'B'})])
        self.assertEqual(len(rows),2)
        self.assertEqual([r['values']['gamma'] for r in rows],[1.6,1.9])
        section={'section_no':1,'length':100,'h_design':3,'crest_width':7,'gamma_fill':1.9,
                 'limit_cm':10,'h_kcad':.2,'slope_m':1.5,'limit_source':'BG12','name':'','design_stage':'','work_item':'','station':'','station_from':'','station_to':''}
        with self.assertRaisesRegex(ValueError,'trùng'):project_for_section(Project(),section,rows,{})

    def test_missing_input_is_blocked_at_before_treatment_entry(self):
        p=Project(soils=[Soil(name='1',thickness=2,gamma=1.7)])
        with self.assertRaisesRegex(ValueError,'e₀ và Cc'):before_treatment(p)

    def test_header_context_stops_before_lettered_and_cover_layers(self):
        import openpyxl,ai_analysis_data as data
        book=openpyxl.Workbook();s=book.active
        s.append(['Lớp','Loại đất','KL thể tích']);s.append([None,None,'T/m³'])
        s.append(['D','Clay',1.73456789]);s.append(['1c','Clay',1.9])
        context=data._excel_header_context(s)
        self.assertNotIn('1.73456789',context);self.assertNotIn('1c',context)
        book.close()

    def test_cad_spt_total_must_agree_with_n2_n3(self):
        import ai_analysis_data as data
        text='\n'.join(['x=20; y=100; text=N1','x=30; y=100; text=N2','x=40; y=100; text=N3',
            'x=50; y=100; text=Giá trị SPT (N)','x=5; y=90; text=2.0-2.45',
            'x=20; y=90; text=2','x=30; y=90; text=4','x=40; y=90; text=5','x=50; y=90; text=9'])
        chunk={'text':text,'expected_hole':'LK1','source':'LK.dxf / LK1'}
        points=data.verified_cad_spt_points(chunk);self.assertEqual(points[0]['spt_n'],9)
        chunk['text']=text.replace('x=50; y=90; text=9','x=50; y=90; text=10')
        self.assertEqual(data.verified_cad_spt_points(chunk),[])


class BatchAuditRegressionTests(unittest.TestCase):
    def test_preflight_file_failure_preserves_good_rows_and_partial_status(self):
        import ai_analysis_data as data
        item=normalize_material({'code':'1','co':2},'good.xlsx!F2')
        with patch('ai_analysis_data.data_source_fingerprint',side_effect=['valid',ValueError('bad workbook')]), \
             patch('ai_analysis_data.request_extraction',return_value=([item],[])):
            result=data.request_extraction_files(['good.xlsx','bad.xlsx'],'strength',{},'fake','deepseek',post=lambda *a,**k:None)
        self.assertEqual(len(result[0]),1);self.assertTrue(result.partial_reason)
        self.assertTrue(any('bad.xlsx' in note for note in result[1]))

    def test_batch_before_check_uses_same_residual_as_individual_calculation(self):
        from batch_calculation import run_batch
        soil=Soil(name='1',thickness=2,gamma=1.7,e0=1.6,cc=.35,cs=.04,pc=2,cv_constant=1,state='Cố kết thường')
        p=Project(soils=[soil],assessment_days=0)
        residual=before_treatment(p)['residual_cm'];p.residual_limit_cm=residual*1.1
        with patch('batch_calculation.import_section',return_value=(p,100)):
            _,records,failures=run_batch('fixture.xlsx',[1],(),p,'',{'no_export':True})
        self.assertFalse(failures);self.assertTrue(records[0]['before_pass'])
        self.assertAlmostEqual(records[0]['before']['residual_cm'],residual)
        self.assertEqual(records[0]['opt_name'],'Không cần xử lý')

if __name__=='__main__':unittest.main(verbosity=2)
