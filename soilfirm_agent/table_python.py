"""Interpret generated parse_rows(rows) functions; no exec, imports or host access."""
import ast,json,os,subprocess,sys,re
from pathlib import Path
if __package__:
    from .calculator import NumericPython
    from .documents import number
else:
    sys.path.insert(0,str(Path(__file__).resolve().parent))
    from calculator import NumericPython
    from documents import number

class TablePython(NumericPython):
    def __init__(self,rows):
        super().__init__();self.values['rows']=rows;self.rows=rows;self.steps=0
    def checked(self,v):
        if v is None:return None
        if isinstance(v,str) and len(v)<=4000:return v
        if isinstance(v,(list,tuple)) and len(v)<=10000:return list(v)
        return super().checked(v)
    def tick(self):
        self.steps+=1
        if self.steps>100000:raise ValueError('Table function operation budget exceeded')
    def evaluate(self,n):
        self.tick()
        if isinstance(n,ast.Subscript):
            obj=self.evaluate(n.value);key=self.evaluate(n.slice)
            if not isinstance(obj,(dict,list,tuple,str)):raise ValueError('Invalid index target')
            return obj[key]
        if isinstance(n,ast.Compare):
            left=self.evaluate(n.left)
            for op,rightnode in zip(n.ops,n.comparators):
                right=self.evaluate(rightnode)
                tests={ast.Eq:lambda:left==right,ast.NotEq:lambda:left!=right,ast.Is:lambda:left is right,ast.IsNot:lambda:left is not right,ast.Lt:lambda:left<right,ast.LtE:lambda:left<=right,ast.Gt:lambda:left>right,ast.GtE:lambda:left>=right,ast.In:lambda:left in right,ast.NotIn:lambda:left not in right}
                if type(op) not in tests or not tests[type(op)]():return False
                left=right
            return True
        if isinstance(n,ast.BoolOp):
            for v in n.values:
                value=self.evaluate(v)
                if isinstance(n.op,ast.And) and not value or isinstance(n.op,ast.Or) and value:return value
            return value
        if isinstance(n,ast.UnaryOp) and isinstance(n.op,ast.Not):return not self.evaluate(n.operand)
        if isinstance(n,ast.Call):
            args=[self.evaluate(a) for a in n.args]
            if n.keywords:raise ValueError('No keyword arguments')
            if isinstance(n.func,ast.Name):
                helpers={'number':number,'text':lambda v:'' if v is None else str(v).strip(),'len':len,'cell':self.cell,'record':self.record,'lower':lambda v:str(v).lower(),'split':lambda v,sep=None:str(v).split(sep),'replace':lambda v,old,new:str(v).replace(old,new),'findall':self.findall}
                if n.func.id in helpers:return self.checked(helpers[n.func.id](*args))
            if isinstance(n.func,ast.Attribute):
                obj=self.evaluate(n.func.value)
                if n.func.attr=='get' and isinstance(obj,dict):return obj.get(*args)
                if n.func.attr=='append' and isinstance(obj,list) and len(obj)<10000 and len(args)==1:obj.append(args[0]);return None
                raise ValueError('Only dict.get/list.append allowed')
        return super().evaluate(n)
    def findall(self,pattern,value):
        if not isinstance(pattern,str) or len(pattern)>200 or len(str(value))>4000:raise ValueError('Regex input exceeds limit')
        return re.findall(pattern,str(value))
    def cell(self,row,column):
        if row not in self.rows:raise ValueError('Unknown row')
        return next((c['value'] for c in row['cells'] if c['column']==str(column)),None)
    def record(self,row,values):
        if row not in self.rows or not isinstance(values,dict):raise ValueError('record requires original row and values dict')
        return {'values':values,'source':row['_source'],'raw_cells':row['cells'],'generated':True}
    def block(self,body):
        for n in body:
            self.tick()
            if isinstance(n,ast.Assign) and len(n.targets)==1 and isinstance(n.targets[0],ast.Name):
                name=n.targets[0].id
                if name.startswith('_') or name in ('rows','number','cell','record','len','text'):raise ValueError('Reserved variable')
                self.values[name]=self.evaluate(n.value)
            elif isinstance(n,ast.Expr):self.evaluate(n.value)
            elif isinstance(n,ast.If):
                result=self.block(n.body if self.evaluate(n.test) else n.orelse)
                if result is not None:return result
            elif isinstance(n,ast.For) and isinstance(n.target,ast.Name) and not n.orelse:
                if n.target.id.startswith('_') or n.target.id=='rows':raise ValueError('Invalid loop variable')
                data=self.evaluate(n.iter)
                if not isinstance(data,list) or len(data)>1000:raise ValueError('Loop requires bounded list')
                for item in data:
                    self.values[n.target.id]=item;result=self.block(n.body)
                    if result is not None:return result
            elif isinstance(n,ast.Return):return self.evaluate(n.value)
            else:raise ValueError('Unsupported function syntax: '+type(n).__name__)
        return None
    def run_function(self,code):
        if len(code)>16000:raise ValueError('Function too long')
        tree=ast.parse(code)
        if len(list(ast.walk(tree)))>1500 or len(tree.body)!=1:raise ValueError('Provide one parse_rows function only')
        f=tree.body[0]
        if not isinstance(f,ast.FunctionDef) or f.name!='parse_rows' or f.decorator_list or f.returns or f.args.defaults or f.args.kwonlyargs or f.args.vararg or f.args.kwarg or f.args.posonlyargs or len(f.args.args)!=1 or f.args.args[0].arg!='rows' or f.args.args[0].annotation:raise ValueError('Expected def parse_rows(rows)')
        result=self.block(f.body)
        if not isinstance(result,list) or len(result)>10000:raise ValueError('Return records list')
        for r in result:
            if not isinstance(r,dict) or set(r)!={'values','source','raw_cells','generated'} or not r.get('generated') or not any(r['source']==row['_source'] and r['raw_cells']==row['cells'] for row in self.rows):raise ValueError('Return only record(row, values) outputs with original source')
        json.dumps(result,allow_nan=False);return result

def run_table_function(code,rows):
    executable=os.environ.get('SOILFIRM_PYTHON_EXE') or sys.executable
    if getattr(sys,'frozen',False) and not os.environ.get('SOILFIRM_PYTHON_EXE'):raise ValueError('Set SOILFIRM_PYTHON_EXE for packaged app')
    worker=Path(__file__).resolve();package=worker.parent.parent
    # Worker imports only package files and stdlib; no inherited provider credentials.
    env={'PYTHONIOENCODING':'utf-8',**({'SYSTEMROOT':os.environ['SYSTEMROOT']} if 'SYSTEMROOT' in os.environ else {})}
    command="import sys;sys.path.insert(0,sys.argv[1]);from soilfirm_agent.table_python import worker;worker()"
    # Package __init__ imports dependencies: worker script loads modules directly instead.
    r=subprocess.run([executable,'-I','-S',str(worker),'--worker'],input=json.dumps({'code':code,'rows':rows}),text=True,capture_output=True,timeout=8,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),shell=False,env=env)
    if r.returncode:raise ValueError('Table worker failed: '+r.stderr[-300:])
    data=json.loads(r.stdout)
    if not data['ok']:raise ValueError(data['error'])
    return data['records']

def worker():
    try:
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_CPU,(6,6));resource.setrlimit(resource.RLIMIT_AS,(512*1024*1024,512*1024*1024))
        except ImportError:pass
        raw=sys.stdin.read(4*1024*1024+1)
        if len(raw)>4*1024*1024:raise ValueError('Table input too large')
        task=json.loads(raw);records=TablePython(task['rows']).run_function(task['code'])
        print(json.dumps({'ok':True,'records':records},allow_nan=False))
    except Exception as exc:print(json.dumps({'ok':False,'error':str(exc)[:400]}))

if __name__=='__main__':worker()
