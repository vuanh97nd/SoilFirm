import unittest,json,tempfile,time,threading
from pathlib import Path
from unittest.mock import patch
import pandas as pd
from geotech_ai_extractor import GeotechAIExtractor
from mapping_proposer import MappingFailure
class IntegrationTests(unittest.TestCase):
 def test_pandas_preserves_null_zero_and_comma(self):
  cols=[{'cot_id':1},{'cot_id':2}]
  rows=GeotechAIExtractor.prepare_soilfirm_rows(cols,[{1:'1,73',2:None},{1:0,2:''}])
  self.assertEqual(rows,[{1:'1,73',2:None},{1:0,2:None}])
 def test_actual_excel_coordinates(self):
  with tempfile.TemporaryDirectory() as tmp:
   path=Path(tmp)/'fixture.xlsx';pd.DataFrame([['γ','e0'],['1,73',''],[0,1.5]]).to_excel(path,index=False,header=False,sheet_name='S')
   rows=GeotechAIExtractor.read_soilfirm_excel_rows(path,'S',[{'cot_id':1},{'cot_id':2}],[{'row':2,'cells':{}},{'row':3,'cells':{}}])
   self.assertEqual(rows[0][1],'1,73');self.assertIsNone(rows[0][2]);self.assertEqual(rows[1][1],0)
 def test_mapping_blocked_extra_numeric_field(self):
  response=json.dumps({'task':'column_mapping','items':[{'cot_id':1,'thong_so':'gamma','do_tin_cay':.99,'ly_do':'dung trọng','value':1.7}],'khong_chac':[]})
  with self.assertRaises(MappingFailure):GeotechAIExtractor.propose_soilfirm_mapping([{'cot_id':1,'label':'γ','unit':'T/m³'}],[],lambda _:response)
 def test_numeric_samples_not_sent(self):
  called=[]
  with self.assertRaises(MappingFailure):GeotechAIExtractor.propose_soilfirm_mapping([{'cot_id':1,'label':'γ','samples':[1.7]}],[],lambda payload:called.append(payload))
  self.assertFalse(called)
 def test_ordered_parallel_reader(self):
  lock=threading.Lock();active=0;maximum=0
  def read(index,path):
   nonlocal active,maximum
   with lock:active+=1;maximum=max(maximum,active)
   time.sleep(.02*(4-index))
   with lock:active-=1
   return path
  result=list(GeotechAIExtractor.iter_files_ordered(['A','B','C'],read))
  self.assertEqual([r[2] for r in result],['A','B','C']);self.assertGreater(maximum,1);self.assertLessEqual(maximum,3)
if __name__=='__main__':unittest.main()
