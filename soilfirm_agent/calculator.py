"""Restricted numerical Python, interpreted as AST in a short-lived process."""
import ast, json, math, operator, subprocess, sys, os
from pathlib import Path
OPS={ast.Add:operator.add,ast.Sub:operator.sub,ast.Mult:operator.mul,ast.Div:operator.truediv,ast.Mod:operator.mod}
FUNCTIONS={n:getattr(math,n) for n in ('sqrt','log','log10','exp','sin','cos','tan','asin','acos','atan','atan2','sinh','cosh','tanh','floor','ceil','fabs','hypot','erf')}
FUNCTIONS.update(abs=abs,min=min,max=max,round=round)
class NumericPython:
    def __init__(self,variables=None):
        self.values={'pi':math.pi,'e':math.e};self.steps=0
        for key,value in (variables or {}).items():
            if not key.isidentifier() or key.startswith('_') or key in FUNCTIONS:raise ValueError('Invalid variable')
            self.values[key]=self.checked(value)
    def checked(self,value):
        if isinstance(value,bool):return value
        if isinstance(value,(int,float)):
            if abs(value)>1e100 or not math.isfinite(value):raise ValueError('Non-finite/oversized result')
            return value
        if isinstance(value,str) and len(value)<500:return value
        if isinstance(value,(list,tuple)) and len(value)<=200:return [self.checked(x) for x in value]
        if isinstance(value,dict) and len(value)<=100 and all(isinstance(k,str) for k in value):return {k:self.checked(v) for k,v in value.items()}
        raise ValueError('Unsupported value')
    def evaluate(self,node):
        self.steps+=1
        if self.steps>10000:raise ValueError('Operation budget exceeded')
        if isinstance(node,ast.Constant):return self.checked(node.value)
        if isinstance(node,ast.Name) and not node.id.startswith('_'):return self.values[node.id]
        if isinstance(node,ast.BinOp):
            a,b=self.evaluate(node.left),self.evaluate(node.right)
            if not isinstance(a,(int,float)) or not isinstance(b,(int,float)):raise ValueError('Numeric operands required')
            if isinstance(node.op,ast.Pow):
                if abs(b)>1000:raise ValueError('Exponent exceeds limit')
                result=a**b
            else:result=OPS[type(node.op)](a,b)
            return self.checked(result)
        if isinstance(node,ast.UnaryOp) and isinstance(node.op,(ast.UAdd,ast.USub)):
            x=self.evaluate(node.operand);return self.checked(x if isinstance(node.op,ast.UAdd) else -x)
        if isinstance(node,ast.Call) and isinstance(node.func,ast.Name) and node.func.id in FUNCTIONS and not node.keywords:
            if len(node.args)>30:raise ValueError('Too many arguments')
            return self.checked(FUNCTIONS[node.func.id](*[self.evaluate(x) for x in node.args]))
        if isinstance(node,(ast.List,ast.Tuple)):return self.checked([self.evaluate(x) for x in node.elts])
        if isinstance(node,ast.Dict):return self.checked({self.evaluate(k):self.evaluate(v) for k,v in zip(node.keys,node.values)})
        raise ValueError('Unsupported Python syntax: '+type(node).__name__)
    def run(self,code):
        if len(code)>12000:raise ValueError('Code exceeds limit')
        tree=ast.parse(code)
        if len(list(ast.walk(tree)))>1000:raise ValueError('Code too complex')
        for line in tree.body:
            if not isinstance(line,ast.Assign) or len(line.targets)!=1 or not isinstance(line.targets[0],ast.Name):raise ValueError('Only simple assignments are allowed')
            name=line.targets[0].id
            if name.startswith('_') or name in FUNCTIONS:raise ValueError('Invalid assignment')
            self.values[name]=self.evaluate(line.value)
        if 'result' not in self.values:raise ValueError('Assign the final JSON-compatible result to result')
        return self.values['result']
    def root(self,expression,lower,upper,tolerance=1e-9):
        lower=float(lower);upper=float(upper);tolerance=float(tolerance)
        if not all(math.isfinite(v) for v in (lower,upper,tolerance)) or not lower<upper or not 1e-14<=tolerance<=1e-2:raise ValueError('Invalid root interval/tolerance')
        if len(expression)>2000:raise ValueError('Expression too long')
        tree=ast.parse(expression,mode='eval').body
        def f(x):self.values['x']=x;return float(self.evaluate(tree))
        a,b=lower,upper;fa,fb=f(a),f(b)
        if fa==0:return {'root':a,'residual':0,'iterations':0}
        if fb==0:return {'root':b,'residual':0,'iterations':0}
        if fa*fb>0:raise ValueError('Root must be bracketed by opposite signs')
        for n in range(1,201):
            x=(a+b)/2;fx=f(x)
            if abs(fx)<=tolerance or abs(b-a)<=tolerance:return {'root':x,'residual':fx,'interval':[a,b],'iterations':n}
            if fa*fx<0:b=x
            else:a=x;fa=fx
        raise ValueError('Root did not converge')
def execute_numeric(code='',variables=None,expression='',lower=0,upper=1,tolerance=1e-9):
    task=locals();worker=Path(__file__).resolve()
    executable=os.environ.get('SOILFIRM_PYTHON_EXE') or sys.executable
    if getattr(sys,'frozen',False) and not os.environ.get('SOILFIRM_PYTHON_EXE'):raise ValueError('Set SOILFIRM_PYTHON_EXE to a real Python interpreter for packaged applications')
    # No shell, no inherited API credentials; child reads only this JSON request.
    result=subprocess.run([executable,'-I','-S',str(worker)],input=json.dumps(task),text=True,capture_output=True,timeout=5,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),shell=False,env={**({'SYSTEMROOT':os.environ['SYSTEMROOT']} if 'SYSTEMROOT' in os.environ else {}),'PYTHONIOENCODING':'utf-8'})
    if result.returncode:raise ValueError('Numerical worker failed')
    data=json.loads(result.stdout)
    if not data['ok']:raise ValueError(data['error'])
    return data['result']
if __name__=='__main__':
    try:
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_CPU,(3,3));resource.setrlimit(resource.RLIMIT_AS,(256*1024*1024,256*1024*1024))
        except ImportError:pass
        task=json.loads(sys.stdin.read(50000));engine=NumericPython(task.get('variables'))
        value=engine.root(task['expression'],task['lower'],task['upper'],task['tolerance']) if task.get('expression') else engine.run(task['code'])
        print(json.dumps({'ok':True,'result':value},allow_nan=False))
    except Exception as exc:print(json.dumps({'ok':False,'error':str(exc)[:300]}))
