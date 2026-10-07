import json, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from copy import deepcopy
import ai_analysis_data as d
import geology_statistics as g
from geotech_memory import GeotechMemory
ROOT=Path(__file__).parent
class Var:
 def __init__(self,x):self.x=x
 def get(self):return self.x
 def set(self,x):self.x=x
class View:
 def __init__(self):
  self.data={'samples':[],'layer_catalog':{},'revision':0};self.project=SimpleNamespace(soils=[])
  self.layer=Var('');self.hole=Var('Tất cả');self.indicator=Var('γ');self.pressure_kind=Var('e-logP');self.layer_map={};self.status=Var('')
 def store(self):return self.data
 def data_project(self):return self.project
 def layer_id(self):return self.layer_map.get(self.layer.get())
 def update_ai_summary(self):pass
 def refresh(self):
  self.layer_map={str(i)+'. '+e['code']:e['id'] for i,e in enumerate(self.data['layer_catalog'].values(),1)}
class TemplateTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.db=Path(self.tmp.name)/'memory.sqlite3'
  self.registry=json.loads((ROOT/'parameter_registry.json').read_text())
  self.catalog=json.loads((ROOT/'geotech_template_catalog.json').read_text())
  self.memory=GeotechMemory(self.db)
 def tearDown(self):self.tmp.cleanup()
 def test_persistence_not_automatic_rules(self):
  self.assertEqual(self.memory.load_reference_templates('P1',self.registry),84)
  self.assertEqual(self.memory.load_reference_templates('P1',self.registry),0)
  m=GeotechMemory(self.db)
  with m.connection() as db:self.assertEqual(db.execute('SELECT count(*) FROM templates WHERE scope=?',('P1',)).fetchone()[0],84)
  for entry in self.catalog['templates']:self.assertIsNone(m.lookup_mapping('P1',entry['columns'],self.registry))
 def test_metadata_only(self):
  for e in self.catalog['templates']:
   for col in e['columns']:self.assertFalse(set(col)&{'values','value','samples','rows'})
  tong=next(e for e in self.catalog['templates'] if e['sheet']=='Tong')
  self.assertEqual(next(c['label'] for c in tong['columns'] if c['cot_id']==6),'Su')
  self.assertNotIn('33.924',json.dumps(tong['columns']))
 def test_rag_scoped_units_groups_and_budget(self):
  self.memory.load_reference_templates('P1',self.registry)
  entry=next(e for e in self.catalog['templates'] if e['file']=='BTH.xlsm' and e['sheet']=='BTH')
  gamma=next(c for c in entry['columns'] if c.get('candidate_id')=='gamma')
  ctx=self.memory.template_context('P1',[gamma],self.registry)
  self.assertIn('gamma',ctx);self.assertLessEqual(len(ctx),1600)
  self.assertEqual(self.memory.template_context('P2',[gamma],self.registry),'')
  for field in ('unit','group'):
   wrong=dict(gamma);wrong[field]='wrong'
   self.assertEqual(self.memory.template_context('P1',[wrong],self.registry),'')
 def test_bad_catalog_refuses_values(self):
  bad=deepcopy(self.catalog);bad['templates'][0]['columns'][0]['values']=[1,2,3]
  p=Path(self.tmp.name)/'bad.json';p.write_text(json.dumps(bad))
  with self.assertRaises(ValueError):self.memory.load_reference_templates('P1',self.registry,p)
 def test_source_header_stops_before_samples(self):
  p=ROOT/'inputs'/'05. Bieu do cat canh.xlsx'
  if not p.exists():self.skipTest('Không có bản sao mẫu; test metadata vẫn chạy.')
  b=d.open_source_excel(p)
  try:
   ctx=d._excel_header_context(b['Tong']);self.assertNotIn('33.924',ctx);self.assertIn('F: Su',ctx)
  finally:b.close()
 def test_import_su_selects_measured_indicator(self):
  v=View();rows=[{'code':'1','values':{'co':2.1},'borehole_name':'LK1','sample_id':'M1','test_depth':2}]
  g.GeologyStatistics.import_ai_samples(v,rows)
  self.assertEqual(v.indicator.get(),'Co');self.assertEqual(v.data['samples'][0]['co'],2.1)
 def test_import_curve_selects_curve(self):
  v=View();rows=[{'code':'1','values':{'ep':[.25,.5],'e':[1,.9]},'borehole_name':'LK1','sample_id':'M1'}]
  g.GeologyStatistics.import_ai_samples(v,rows)
  self.assertEqual(v.indicator.get(),'e-logP')
 def test_keep_indicator_with_data(self):
  v=View();v.indicator.set('Cc');g.GeologyStatistics.import_ai_samples(v,[{'code':'1','values':{'gamma':1.8,'cc':.2}}]);self.assertEqual(v.indicator.get(),'Cc')
if __name__=='__main__':unittest.main()
