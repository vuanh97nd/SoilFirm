"""Chạy: python -m unittest test_geotech_memory -v (không gọi dịch vụ AI thật)."""
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from types import SimpleNamespace
from geotech_memory import GeotechMemory,project_scope
import ai_analysis_data as data

class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.db=Path(self.temp.name)/'memory.sqlite3';self.mem=GeotechMemory(self.db)
        self.registry=json.loads(Path(__file__).with_name('parameter_registry.json').read_text())
        self.chunk={'source':'fixture.xlsx / Sheet1','header_context':'A: Mã lớp\nB: Dung trọng tự nhiên γ (T/m³)',
            'mapping_required':['code','gamma'],'memory_scope':'project-A','excel_rows':[
                {'row':2,'cells':{'A':{'value':'1','coordinate':'A2'},'B':{'value':1.8,'coordinate':'B2'}}}]}
        self.columns,_,_=data._strict_mapping_columns(self.chunk)
        self.answer=json.dumps({'task':'column_mapping','items':[
            {'cot_id':1,'thong_so':'code','do_tin_cay':1.0,'ly_do':'Người dùng xác nhận'},
            {'cot_id':2,'thong_so':'gamma','do_tin_cay':1.0,'ly_do':'Người dùng xác nhận'}],'khong_chac':[]},ensure_ascii=False)
        self.overrides={'1':{'unit':'','group':''},'2':{'unit':'T/m³','group':'natural_density'}}
    def remember(self):
        self.mem.remember_mapping('project-A',self.columns,self.registry,self.answer,overrides=self.overrides,
            original_answer='AI chưa chắc',source='fixture.xlsx / Sheet1',actor='tester',confirmed=True)
    def test_restart_and_scope(self):
        self.remember();reopened=GeotechMemory(self.db)
        self.assertEqual(reopened.lookup_mapping('project-A',self.columns,self.registry)['answer'],self.answer)
        self.assertIsNone(reopened.lookup_mapping('project-B',self.columns,self.registry))
    def test_units_structure_registry(self):
        self.remember();columns=deepcopy(self.columns);columns[1]['unit']='kN/m³'
        self.assertIsNone(self.mem.lookup_mapping('project-A',columns,self.registry))
        columns=deepcopy(self.columns);columns[1]['cot_id']=3
        self.assertIsNone(self.mem.lookup_mapping('project-A',columns,self.registry))
        registry=deepcopy(self.registry);registry['gamma']['max']=3
        self.assertIsNone(self.mem.lookup_mapping('project-A',self.columns,registry))
    def test_confirmation_required(self):
        with self.assertRaises(ValueError):self.mem.remember_mapping('project-A',self.columns,self.registry,self.answer,actor='tester')
        self.assertIsNone(self.mem.lookup_mapping('project-A',self.columns,self.registry))
    def test_corrections_not_rules(self):
        self.mem.record_correction('project-A','sample_edit',{'e0':None},{'e0':.95},actor='tester',confirmed=True,context={'cell':'B3'})
        self.assertEqual(len(self.mem.history('project-A')),1)
        self.assertEqual(self.mem.retrieve('project-A','e0'),[])
        self.assertIsNone(self.mem.lookup_mapping('project-A',self.columns,self.registry))
    def test_rag_confirmed_project_only(self):
        self.mem.add_knowledge('project-A','Cố kết','e0 và Cv','Giữ e0 và Cv trung bình cùng đường cong đo.',source='Quy tắc đã xác nhận',actor='tester',confirmed=True)
        self.mem.add_knowledge('project-A','Cố kết','e0 giả','Không được dùng bản nháp')
        self.mem.add_knowledge('project-B','Cố kết','e0 dự án khác','Kiến thức dự án B',source='test',actor='tester',confirmed=True)
        result=self.mem.retrieve('project-A','e0 Cv');self.assertEqual(len(result),1)
        self.assertEqual(result[0]['title'],'e0 và Cv')
        self.mem.disable_knowledge('project-A',result[0]['id']);self.assertEqual(self.mem.retrieve('project-A','e0 Cv'),[])
    def test_disable_rule(self):
        self.remember();revision=self.mem.revision('project-A');event=self.mem.history('project-A')[0]['id']
        self.mem.disable_mapping('project-A',event,'tester')
        self.assertIsNone(self.mem.lookup_mapping('project-A',self.columns,self.registry))
        self.assertGreater(self.mem.revision('project-A'),revision)
    def test_concurrent_events(self):
        def write(i):return self.mem.record_correction('project-A','sample_edit',i,i+1,actor='tester',confirmed=True)
        with ThreadPoolExecutor(max_workers=4) as pool:ids=list(pool.map(write,range(20)))
        self.assertEqual(len(set(ids)),20);self.assertEqual(len(self.mem.history('project-A')),20)
    def test_project_uuid_saved(self):
        p=SimpleNamespace(geology_statistics={});a=project_scope(p,'tester')
        self.assertEqual(a,project_scope(SimpleNamespace(geology_statistics=json.loads(json.dumps(p.geology_statistics))),'tester'))
        self.assertNotEqual(a,project_scope(SimpleNamespace(geology_statistics={}),'tester'))
        self.assertNotEqual(a,project_scope(p,'other'))
    def test_mapping_reuse_no_ai_and_current_numbers(self):
        self.remember()
        with patch('geotech_memory.default_path',return_value=self.db),patch.object(data,'_mapping_storage',return_value=(Path(self.temp.name)/'legacy.json',Path(self.temp.name)/'audit.jsonl')):
            rows,notes=data._read_excel_header_mapping(self.chunk,{},'mock','deepseek',lambda *a,**k:self.fail('Không được gọi AI khi mapping đã xác nhận'),None,None)
            self.assertEqual(rows[0]['values']['gamma'],1.8)
            chunk=deepcopy(self.chunk);chunk['excel_rows'][0]['cells']['B']['value']=1.9
            rows,_=data._read_excel_header_mapping(chunk,{},'mock','deepseek',lambda *a,**k:self.fail('AI không cần gọi'),None,None)
            self.assertEqual(rows[0]['values']['gamma'],1.9)
    def test_mapping_still_validates_numbers(self):
        self.remember();chunk=deepcopy(self.chunk);chunk['excel_rows'][0]['cells']['B']['value']='không có số'
        with patch('geotech_memory.default_path',return_value=self.db),patch.object(data,'_mapping_storage',return_value=(Path(self.temp.name)/'legacy.json',Path(self.temp.name)/'audit.jsonl')):
            with self.assertRaises(data.MappingReviewRequired):
                data._read_excel_header_mapping(chunk,{},'mock','deepseek',lambda *a,**k:self.fail('Không gọi AI'),None,None)
    def test_no_hallucinated_mapping_ids(self):
        wrong=json.loads(self.answer);wrong['items'][1]['thong_so']='made_up'
        with self.assertRaises(ValueError):self.mem.remember_mapping('project-A',self.columns,self.registry,json.dumps(wrong),actor='tester',confirmed=True)
        self.assertIsNone(self.mem.lookup_mapping('project-A',self.columns,self.registry))

if __name__=='__main__':unittest.main()
