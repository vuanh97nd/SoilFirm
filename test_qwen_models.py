import ast,json,tempfile,threading,unittest
from pathlib import Path
from unittest.mock import patch
from types import SimpleNamespace
import local_ai_engine as engine
ROOT=Path(__file__).parent
EXPECTED={'ollama':'deepseek-r1:8b','ollama_qwen':'qwen3:8b','ollama_qwen_4b_q4':'qwen3:4b-q4_K_M','ollama_qwen_4b_q8':'qwen3:4b-q8_0'}
class Connection:
 def poll(self,timeout):return True
 def recv(self):return True,'{"answer":"kiểm thử"}'
 def close(self):pass
class Context:
 def __init__(self):self.models=[]
 def Pipe(self,duplex):return Connection(),Connection()
 def Process(self,**kw):
  self.models.append((kw['args'][3],kw['args'][4]))
  return SimpleNamespace(pid=1,start=lambda:None,is_alive=lambda:False,join=lambda **kw:None,close=lambda:None)
class ModelTests(unittest.TestCase):
 def test_extract_routes_exact_models(self):
  context=Context()
  with patch.object(engine.mp,'get_context',return_value=context):
   for name,model in EXPECTED.items():
    self.assertEqual(json.loads(engine.extract_geotech_local('Kiểm thử',max_retries=1,engine=name)),{'answer':'kiểm thử'})
    self.assertEqual(context.models[-1],(model,'__ollama__'))
 def test_unknown_engine_rejected(self):
  with self.assertRaises(engine.LocalAIError):engine.extract_geotech_local('test',engine='ollama_qwen_foo')
 def test_cancel_keeps_cancel_behavior(self):
  event=threading.Event();event.set()
  for name in EXPECTED:
   with self.assertRaises(InterruptedError):engine.extract_geotech_local('test',engine=name,cancel=event)
 def test_chat_and_reader_dropdowns_and_mappings(self):
  labels=set(EXPECTED.values())
  for filename in ('app.py','chat_dialog.py','ai_analysis_workflow.py'):
   tree=ast.parse((ROOT/filename).read_text())
   tuples=[{item.value for item in n.elts if isinstance(item,ast.Constant) and isinstance(item.value,str)} for n in ast.walk(tree) if isinstance(n,ast.Tuple)]
   self.assertTrue(any(labels<=t for t in tuples),filename)
   if filename!='app.py':
    mappings=[dict(zip([k.value for k in n.keys],[v.value for v in n.values])) for n in ast.walk(tree) if isinstance(n,ast.Dict) and all(isinstance(k,ast.Constant) for k in n.keys) and all(isinstance(v,ast.Constant) for v in n.values)]
    self.assertTrue(any(all(m.get(model)==kind for kind,model in EXPECTED.items()) for m in mappings),filename)
 def test_old_preference_migration(self):
  tree=ast.parse((ROOT/'app.py').read_text())
  method=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name=='_load_calculation_preferences')
  namespace={'json':json};exec(compile(ast.Module(body=[method],type_ignores=[]),'preferences','exec'),namespace)
  with tempfile.TemporaryDirectory() as directory:
   path=Path(directory)/'settings.json';app=SimpleNamespace(_calculation_preferences_path=lambda:path)
   for old,new in [('Qwen (miễn phí)','qwen3:8b'),('DeepSeek (miễn phí)','deepseek-r1:8b'),('DeepSeek (Miễn phí)','DeepSeek (g4f)')]+[(m,m) for m in EXPECTED.values()]:
    path.write_text(json.dumps({'provider':old}));self.assertEqual(namespace[method.name](app)['provider'],new)
if __name__=='__main__':unittest.main()
