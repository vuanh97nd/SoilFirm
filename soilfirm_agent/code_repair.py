"""Admin source editing with exact-match replacement, syntax check and backup."""
import ast,hashlib,json,subprocess,uuid
from pathlib import Path
class CodeRepair:
    def __init__(self,root):self.root=Path(root).resolve()
    def path(self,name):
        p=(self.root/name).resolve()
        if not p.is_relative_to(self.root) or p.suffix not in ('.py','.js','.mjs','.json') or not p.is_file():raise ValueError('Select an existing source file within configured code root')
        if p.stat().st_size>1024*1024:raise ValueError('Source exceeds 1 MB')
        return p
    def read(self,path):
        p=self.path(path);text=p.read_text(encoding='utf-8');return {'path':path,'text':text,'sha256':hashlib.sha256(text.encode()).hexdigest()}
    def patch(self,path,expected_sha256,old,new,reason):
        p=self.path(path);before=p.read_text(encoding='utf-8')
        if hashlib.sha256(before.encode()).hexdigest()!=expected_sha256:raise ValueError('Source changed; read it again before patching')
        if not old or before.count(old)!=1 or not reason.strip():raise ValueError('Replacement requires one exact match and a reason')
        after=before.replace(old,new,1)
        if len(after.encode())>1024*1024:raise ValueError('Source exceeds 1 MB')
        if p.suffix=='.py':ast.parse(after,filename=str(p))
        elif p.suffix=='.json':json.loads(after)
        elif p.suffix in ('.js','.mjs'):
            # Syntax only; never runs the edited JavaScript.
            try:r=subprocess.run(['node','--input-type=module','--check'],input=after,text=True,capture_output=True,timeout=10,creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0),shell=False)
            except FileNotFoundError:raise ValueError('Node required for JS syntax checking') from None
            if r.returncode:raise ValueError('JavaScript syntax error: '+r.stderr[-400:])
        backup=self.root/'.soilfirm_ai_backups'/uuid.uuid4().hex
        if not backup.resolve().is_relative_to(self.root):raise ValueError('Backup path outside code root')
        backup.mkdir(parents=True)
        (backup/p.name).write_text(before,encoding='utf-8')
        (backup/'change.json').write_text(json.dumps({'path':path,'reason':reason,'old_sha256':expected_sha256,'new_sha256':hashlib.sha256(after.encode()).hexdigest()},ensure_ascii=False),encoding='utf-8')
        try:p.write_text(after,encoding='utf-8')
        except Exception:
            p.write_text(before,encoding='utf-8');raise
        return {'path':path,'backup':str(backup/p.name),'syntax_checked':True,'runtime_tested':False,'deployed':False}
