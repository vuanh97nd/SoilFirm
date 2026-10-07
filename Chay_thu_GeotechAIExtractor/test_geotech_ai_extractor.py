import asyncio,json,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import pandas as pd
from geotech_ai_extractor import *

def proposal(**updates):
 obj=dict.fromkeys(PARAMETERS);obj.update(data_start_row=2,gamma={'column':'A','confidence':.99,'unit':'T/m³','group':None});obj.update(updates)
 return MappingProposal.model_validate(obj)

def completion(content):
 return NS(choices=[NS(finish_reason='stop',message=NS(content=content,refusal=None))],usage=NS(prompt_tokens=100,completion_tokens=50))

class Tests(unittest.TestCase):
 def setUp(self): self.x=GeotechAIExtractor(api_key='test-not-sent',retries=0)
 def tearDown(self): self.x.close()
 def test_comma_and_null_zero(self):
  for raw,expected in [('1,73',1.73),('0',0.),('',None),(None,None),('null',None),(float('nan'),None),('1,2e-3',.0012)]:
   with self.subTest(raw=raw):self.assertEqual(self.x.parse_number(raw),expected)
 def test_ambiguous_not_guessed(self):
  for raw in ['1.234,56','1,234.56','1.2.3','7°58\'','<2','#REF!',True,float('inf')]:
   with self.subTest(raw=raw),self.assertRaises(ExtractionError):self.x.parse_number(raw)
 def test_explicit_thousands(self):
  with GeotechAIExtractor(api_key='test',decimal=',',thousands='.') as x:
   self.assertEqual(x.parse_number('1.234,56'),1234.56)
   with self.assertRaises(ExtractionError):x.parse_number('12.34,56')
 def test_none_never_zero(self):
  frame=pd.DataFrame([['γ','e0'],['1,7',''],['0','0']]);m=proposal(e0={'column':'B','confidence':.99,'unit':'1','group':None})
  rows,_=self.x.apply_mapping(frame,m);self.assertIsNone(rows[0]['e0']);self.assertEqual(rows[1]['gamma'],0)
 def test_invalid_cell_blocks_whole_result(self):
  frame=pd.DataFrame([['γ'],['1,7'],['#REF!']]);before=frame.copy(deep=True)
  with self.assertRaises(ExtractionError):self.x.apply_mapping(frame,proposal())
  pd.testing.assert_frame_equal(frame,before)
 def test_bad_columns(self):
  for m in [proposal(gamma={'column':'Z','confidence':.99,'unit':None,'group':None}),proposal(e0={'column':'A','confidence':.99,'unit':'1','group':None}),proposal(gamma={'column':'A','confidence':.5,'unit':'T/m³','group':None})]:
   with self.assertRaises(ExtractionError):self.x.validate_mapping(m,pd.DataFrame([['γ'],['1,7']]))
 def test_required_missing(self):
  with GeotechAIExtractor(api_key='test',required=('e0',)) as x:
   with self.assertRaises(ExtractionError):x.apply_mapping(pd.DataFrame([['γ'],['1,7']]),proposal())
 def test_conflicting_group(self):
  with GeotechAIExtractor(api_key='test',expected_groups={'phi':'cắt trực tiếp'}) as x:
   with self.assertRaises(ExtractionError):x.validate_mapping(proposal(phi={'column':'B','confidence':.99,'unit':'độ','group':'UU'}),pd.DataFrame([['γ','φ'],[1.7,12]]))
 def test_excel_corrupt_and_csv_actual(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'good.xlsx';pd.DataFrame([['γ','e0'],['1,7',''],['0','0']]).to_excel(p,index=False,header=False)
   frame=self.x.read_file(p);rows,_=self.x.apply_mapping(frame,proposal());self.assertEqual(rows[0]['gamma'],1.7)
   bad=Path(d)/'bad.xlsx';bad.write_text('broken')
   with self.assertRaises(ExtractionError):self.x.read_file(bad)
   csvfile=Path(d)/'good.csv';csvfile.write_text('γ;e0\n1,7;\n0;0\n',encoding='utf-8-sig')
   frame=self.x.read_file(csvfile);self.assertEqual(frame.iat[1,0],'1,7');self.assertEqual(frame.iat[1,1],'')
 def test_only_ten_rows_and_excel_column_ids(self):
  frame=pd.DataFrame([['header']*28]+[[i]*28 for i in range(2000)])
  context=self.x.build_context(frame);self.assertEqual(len(context['rows']),10);self.assertEqual(context['columns'][-1],'AB');self.assertNotIn('1999',json.dumps(context))
 def test_duplicate_json_key_rejected(self):
  with self.assertRaises(ExtractionError):json.loads('{"gamma":null,"gamma":null}',object_pairs_hook=reject_duplicate_keys)
 def test_ai_bad_response_no_result(self):
  for raw in ['', '{', json.dumps({**proposal().model_dump(),'gamma_value':1.7})]:
   with self.subTest(raw=raw),patch('geotech_ai_extractor.OpenAI') as client:
    client.return_value.__enter__.return_value.chat.completions.create.return_value=completion(raw)
    with self.assertRaises(ExtractionError):self.x.propose_mapping({'columns':['A']})
 def test_ai_offline_blocks_return(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/'data.csv';p.write_text('γ;e0\n1,7;1,5\n')
   with patch.object(self.x,'propose_mapping',side_effect=ExtractionError('AI timeout')):
    with self.assertRaises(ExtractionError):self.x.extract_file(p)
 def test_success_ai_to_python(self):
  with tempfile.TemporaryDirectory() as d,patch('geotech_ai_extractor.OpenAI') as client:
   p=Path(d)/'data.csv';p.write_text('γ;e0\n1,73;1,5\n')
   client.return_value.__enter__.return_value.chat.completions.create.return_value=completion(proposal().model_dump_json())
   result=self.x.extract_file(p);self.assertEqual(result.records[0]['gamma'],1.73);self.assertIsNone(result.records[0]['e0']);self.assertEqual(result.prompt_tokens,100)
 def test_background_errors_isolated_and_async(self):
  def fake(path,**kw):
   if path=='bad':raise ExtractionError('hỏng')
   return ExtractionResult(path,0,{},[],[],0,None,None)
  with patch.object(self.x,'extract_file',side_effect=fake):
   job=self.x.extract_files_background(['good','bad','good2']);items=[f.result(timeout=5) for f in job.futures]
   self.assertIsNotNone(items[0].result);self.assertIsNotNone(items[1].error);self.assertIsNotNone(items[2].result)
   items=asyncio.run(self.x.extract_files_async(['good','bad']));self.assertIsNotNone(items[1].error)
 def test_cancel_no_result(self):
  event=threading.Event();event.set()
  with self.assertRaises(ExtractionError):self.x.extract_file('not-read.xlsx',cancel=event)
if __name__=='__main__':unittest.main(verbosity=2)
