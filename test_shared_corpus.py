import json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from geotech_memory import GeotechMemory,packed,digest
from geotech_memory_sync import read_shared_seed,queue_template_references,queue_shared_seed
from push_shared_memory_seed import push
ROOT=Path(__file__).parent

class CorpusTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.memory=GeotechMemory(Path(self.tmp.name)/'test.sqlite')
        self.seed=ROOT/'shared_memory_seed.json';self.items=read_shared_seed(self.seed)
    def tearDown(self):self.tmp.cleanup()
    def test_source_coverage_and_traceability(self):
        report=json.loads((ROOT/'source_read_report.json').read_text())
        self.assertEqual(len(report),53)
        self.assertEqual(sum(x['status'].startswith('read_') for x in report),40)
        self.assertEqual(len({x['file'].split('/')[1] for x in report if x['file'].count('/')>1}),9)
        for item in self.items:
            self.assertIn('SHA-256',item['payload']['source'])
            self.assertEqual(item['kind'],'knowledge');self.assertEqual(item['state'],'pending')
            self.assertLessEqual(len(packed(item['payload'])),2700)
        self.assertGreater(len(self.items),1000)
    def test_queue_durable_idempotent_not_trusted(self):
        self.assertEqual(queue_template_references(self.memory,'admin'),len(self.items))
        self.assertEqual(queue_template_references(self.memory,'admin'),0)
        self.assertEqual(GeotechMemory(self.memory.path).retrieve('project','Cv'),[])
        with self.memory.connection() as db:
            self.assertEqual(db.execute('SELECT count(*) FROM shared_memory_outbox').fetchone()[0],len(self.items))
            self.assertEqual(db.execute('SELECT count(*) FROM shared_memory_cache').fetchone()[0],0)
    def test_bad_seed_rolls_back_entire_queue(self):
        data=json.loads(self.seed.read_text());data['items'][-1]['payload']['value']=1.8
        path=Path(self.tmp.name)/'bad.json';path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):queue_shared_seed(self.memory,'admin',path)
        with self.memory.connection() as db:self.assertEqual(db.execute('SELECT count(*) FROM shared_memory_outbox').fetchone()[0],0)
    def test_changed_body_hash_refused(self):
        data=json.loads(self.seed.read_text());data['items'][0]['payload']['body']='Không còn đúng nguồn'
        path=Path(self.tmp.name)/'bad.json';path.write_text(json.dumps(data))
        with self.assertRaises(ValueError):read_shared_seed(path)
    def test_shared_rag_searches_beyond_last_100_and_blocks_trial(self):
        self.memory.set_shared_access('full',True,'paid')
        with self.memory.connection() as db:
            for i in range(130):
                body='quy tắc đặc trưng eldorado' if i==0 else 'tham khảo chung'
                payload={'topic':'test','title':'nguồn','body':body,'source':'test'}
                db.execute('INSERT INTO shared_memory_cache VALUES(?,?,?,?,?)',(str(i),'knowledge',packed(payload),'admin',i))
        self.assertEqual(len(self.memory.retrieve('full','eldorado')),1)
        self.memory.set_shared_access('trial',False,'trial')
        self.assertEqual(self.memory.retrieve('trial','eldorado'),[])
    def test_push_batches_and_publication_separate(self):
        bundle=json.loads(self.seed.read_text());bundle['items']=bundle['items'][:21]
        path=Path(self.tmp.name)/'tiny.json';path.write_text(json.dumps(bundle))
        calls=[]
        def post(url,**kwargs):
            calls.append((url,kwargs['json']))
            if url.endswith('/sync'):
                body={'success':True,'ack':[x['client_id'] for x in kwargs['json']['items']],'changes':[],'cursor':0,'more':False}
            else:body={'success':True}
            return SimpleNamespace(status_code=200,ok=True,content=packed(body).encode(),json=lambda:body)
        result=push(path,'https://test.invalid',{'username':'admin','key':'dummy'},post=post,sleep=lambda n:None)
        self.assertEqual(result['submitted'],21);self.assertEqual(result['published'],0);self.assertEqual(len(calls),2)
        calls.clear()
        result=push(path,'https://test.invalid',{'username':'admin','key':'dummy'},True,post=post,sleep=lambda n:None)
        self.assertEqual(result['published'],21);self.assertEqual(len(calls),23)
    def test_push_rejects_non_admin_before_network(self):
        with self.assertRaises(ValueError):
            push(self.seed,'https://test.invalid',{'username':'trial','key':'dummy'},post=lambda *a,**k:self.fail('Không gọi mạng'),sleep=lambda n:None)

if __name__=='__main__':unittest.main()
