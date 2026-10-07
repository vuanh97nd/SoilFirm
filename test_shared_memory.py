import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from geotech_memory import GeotechMemory,packed,digest,structure_signature
from geotech_memory_sync import sync_shared_memory,queue_bth_reading_reference
from mapping_gate import validate_mapping
ROOT=Path(__file__).parent
class SharedTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'memory.sqlite';self.m=GeotechMemory(self.path)
  self.registry=json.loads((ROOT/'parameter_registry.json').read_text())
  self.columns=[{'cot_id':1,'label':'Lớp','symbol':'','unit':'','group':''},{'cot_id':2,'label':'Dung trọng tự nhiên','symbol':'γ','unit':'T/m³','group':'natural_density'}]
  self.answer={'task':'column_mapping','items':[{'cot_id':1,'thong_so':'code','do_tin_cay':.95,'ly_do':'Mã lớp'},{'cot_id':2,'thong_so':'gamma','do_tin_cay':.98,'ly_do':'Dung trọng tự nhiên'}],'khong_chac':[]}
  self.payload={'signature':structure_signature(self.columns,self.registry),'registry_hash':digest(self.registry),'columns':self.columns,'answer':self.answer,'overrides':{}}
  self.credentials={'username':'userA','key':'dummy-test-key'}
  self.change={'seq':1,'item_id':'e'*64,'kind':'mapping','state':'approved','payload':self.payload,'reviewer':'admin','created_at':'2026-10-05'}
 def tearDown(self):self.tmp.cleanup()
 def response(self,body,status=200):return SimpleNamespace(status_code=status,ok=status==200,content=packed(body).encode(),json=lambda:body)
 def post(self,url,**kw):
  changes=[self.change] if kw['json']['cursor']==0 else []
  return self.response({'success':True,'ack':[r['client_id'] for r in kw['json']['items']],'changes':changes,'cursor':1,'more':False})
 def sync(self,scope='P2',eligible=True,post=None):return sync_shared_memory('https://test.invalid',self.credentials,scope,eligible,post=post or self.post,path=self.path)
 def queue(self):self.m.remember_mapping('P1',self.columns,self.registry,packed(self.answer),actor='userA',confirmed=True)
 def queued(self):
  with self.m.connection() as db:return db.execute('SELECT count(*) FROM shared_memory_outbox').fetchone()[0]
 def test_trial_no_network_no_shared_cache(self):
  self.sync();self.assertIsNotNone(self.m.lookup_mapping('P2',self.columns,self.registry))
  r=self.sync(eligible=False,post=lambda *a,**k:self.fail('Trial không được gọi server'))
  self.assertFalse(r['success']);self.assertIsNone(self.m.lookup_mapping('P2',self.columns,self.registry))
 def test_restart_and_cross_project_shared(self):
  self.assertTrue(self.sync()['success']);other=GeotechMemory(self.path);other.set_shared_access('new-project',True,'userB')
  rule=other.lookup_mapping('new-project',self.columns,self.registry);self.assertEqual(rule['origin'],'shared_server')
  self.assertIsNone(other.lookup_mapping('not-enabled',self.columns,self.registry))
 def test_offline_keeps_queue_and_cache(self):
  self.sync();self.queue()
  def fail(*a,**k):raise TimeoutError('test timeout')
  r=self.sync(post=fail);self.assertFalse(r['success']);self.assertEqual(self.queued(),1);self.assertIsNotNone(self.m.lookup_mapping('P2',self.columns,self.registry))
 def test_403_disables_cache_keeps_queue(self):
  self.sync();self.queue();self.sync(post=lambda *a,**k:self.response({},403))
  self.assertEqual(self.queued(),1);self.assertIsNone(self.m.lookup_mapping('P2',self.columns,self.registry))
 def test_ack_only_after_valid_full_response(self):
  self.queue();queue_bth_reading_reference(self.m,'userA');before=self.queued()
  def bad(url,**kw):
   item=dict(self.change);item['payload']={**self.payload,'numbers':[1.8]}
   return self.response({'success':True,'ack':[kw['json']['items'][0]['client_id']],'changes':[item],'cursor':1,'more':False})
  self.assertFalse(self.sync(post=bad)['success']);self.assertEqual(self.queued(),before)
  with self.m.connection() as db:self.assertEqual(db.execute('SELECT count(*) FROM shared_memory_cache').fetchone()[0],0)
 def test_valid_ack_and_no_values_or_credentials_in_queue(self):
  self.queue();self.assertTrue(self.sync()['success']);self.assertEqual(self.queued(),0)
  self.assertNotIn('key',self.payload);self.assertNotIn('rows',self.payload)
 def test_revoke_removes_rule(self):
  self.sync();self.change={**self.change,'seq':2,'state':'disabled'}
  def revoke(url,**kw):return self.response({'success':True,'ack':[],'changes':[self.change],'cursor':2,'more':False})
  self.sync(post=revoke);self.assertIsNone(self.m.lookup_mapping('P2',self.columns,self.registry))
 def test_private_rule_wins_and_disabled_rule_blocks_fallback(self):
  self.sync();self.queue();self.m.set_shared_access('P1',True,'userA')
  self.assertEqual(self.m.lookup_mapping('P1',self.columns,self.registry)['origin'],'user_sqlite')
  event=self.m.history('P1')[0]['id'];self.m.disable_mapping('P1',event,'userA');self.assertIsNone(self.m.lookup_mapping('P1',self.columns,self.registry))
 def test_unit_changes_no_reuse_and_invalid_numbers_gate(self):
  self.sync();changed=[dict(c) for c in self.columns];changed[1]['unit']='kN/m³'
  self.assertIsNone(self.m.lookup_mapping('P2',changed,self.registry))
  valid=validate_mapping(packed(self.answer),self.columns,[{1:'1',2:1.8}],self.registry,required=('code','gamma'))
  invalid=validate_mapping(packed(self.answer),self.columns,[{1:'1',2:'bad'}],self.registry,required=('code','gamma'))
  self.assertEqual(valid.status,'accepted');self.assertNotEqual(invalid.status,'accepted')
 def test_unconfirmed_knowledge_not_shared(self):
  ident=self.m.add_knowledge('P1','Đất','Tên','Nội dung',source='TCVN',actor='userA',confirmed=False)
  with self.assertRaises(ValueError):self.m.share_knowledge('P1',ident,'userA')
  self.assertEqual(self.queued(),0)
if __name__=='__main__':unittest.main()
