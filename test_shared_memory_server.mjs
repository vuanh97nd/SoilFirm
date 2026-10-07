import {strict as assert} from 'node:assert';
import {mkdtempSync,readFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {execFileSync} from 'node:child_process';
import {handleSharedMemory,sharedMemoryAccess,validateSharedPayload,validateSharedPublication} from './shared_memory_server.js';
import worker from './worker.js';
const folder=mkdtempSync(join(tmpdir(),'soilfirm-memory-'));const path=join(folder,'db.sqlite');
const script=`import sqlite3,json,sys
commands=json.load(sys.stdin);db=sqlite3.connect(sys.argv[1]);db.row_factory=sqlite3.Row
result=[]
with db:
 for c in commands:
  cur=db.execute(c['sql'],c['args']);result.append({'results':[dict(r) for r in cur.fetchall()] if cur.description else [],'success':True,'meta':{'changes':cur.rowcount}})
print(json.dumps(result))
`;
class Statement{constructor(db,sql,args=[]){this.db=db;this.sql=sql;this.args=args;}bind(...args){return new Statement(this.db,this.sql,args);}async all(){return this.db.call([this])[0];}async run(){return this.all();}async first(){return (await this.all()).results[0]||null;}}
class Database{prepare(sql){return new Statement(this,sql);}call(items){return JSON.parse(execFileSync('python',['-c',script,path],{input:JSON.stringify(items.map(s=>({sql:s.sql,args:s.args}))),encoding:'utf8'}));}async batch(items){return this.call(items);}}
const db=new Database(),admin={username:'admin',is_system:true,tier:'oem'},paid={username:'paid',tier:'oem'},trial={username:'trial',tier:'trial'};
const payload={signature:'a'.repeat(64),registry_hash:'b'.repeat(64),columns:[{cot_id:1,label:'Gamma',symbol:'γ',unit:'T/m³',group:'natural_density'}],answer:{task:'column_mapping',items:[{cot_id:1,thong_so:'gamma',do_tin_cay:.93,ly_do:'Dung trọng tự nhiên'}],khong_chac:[]},overrides:{}};
const item={client_id:'c'.repeat(64),kind:'mapping',payload};const route='/api/memory/shared/sync';
try{
 assert.throws(()=>sharedMemoryAccess({username:'t',tier:'TRIAL'}),e=>e.status===403);
 const unitless={...payload,columns:[{...payload.columns[0],unit:''}],overrides:{'1':{unit:'T/m³'}}};assert.throws(()=>validateSharedPublication('mapping',unitless));
 assert.throws(()=>sharedMemoryAccess(null),e=>e.status===401);assert.throws(()=>sharedMemoryAccess(trial),e=>e.status===403);assert.throws(()=>sharedMemoryAccess(paid,true),e=>e.status===403);
 for(const wrong of [{...payload,value:1},{...payload,answer:{...payload.answer,values:[1]}},{...payload,answer:{...payload.answer,items:[{...payload.answer.items[0],thong_so:'fake'}]}}])assert.throws(()=>validateSharedPayload('mapping',wrong));
 let r=await handleSharedMemory(db,paid,route,{items:[item],cursor:0});assert.equal(r.ack.length,1);assert.equal(r.changes.length,0,'Đề xuất chưa công bố không được tải');
 await handleSharedMemory(db,paid,route,{items:[item],cursor:0});assert.equal((await db.prepare('SELECT count(*) AS n FROM shared_memory_items').first()).n,1,'Retry không nhân bản');
 const list=await handleSharedMemory(db,admin,'/api/memory/shared/pending',{});const id=list.items[0].id;
 await assert.rejects(handleSharedMemory(db,paid,'/api/memory/shared/review',{id,state:'approved'}),e=>e.status===403);
 await handleSharedMemory(db,admin,'/api/memory/shared/review',{id,state:'approved'});
 r=await handleSharedMemory(db,{username:'other',tier:'oem'},route,{cursor:0});assert.equal(r.changes.length,1);assert.equal(r.changes[0].state,'approved');const cursor=r.cursor;
 await handleSharedMemory(db,admin,'/api/memory/shared/review',{id,state:'disabled'});
 r=await handleSharedMemory(db,paid,route,{cursor});assert.equal(r.changes.length,1);assert.equal(r.changes[0].state,'disabled');
 const bad=[item,{...item,client_id:'d'.repeat(64),payload:{...payload,rows:[1]}}];const before=(await db.prepare('SELECT count(*) AS n FROM shared_memory_items').first()).n;
 await assert.rejects(handleSharedMemory(db,paid,route,{items:bad,cursor:0}));assert.equal((await db.prepare('SELECT count(*) AS n FROM shared_memory_items').first()).n,before,'Lô sai không ghi phần hợp lệ');
 // Kiểm tra qua fetch thật của Worker: xác thực tài khoản từ bảng users.
 const env={DB:db,ADMIN_KEY:'dummy-test-admin-key'};
 await worker.fetch(new Request('https://test.invalid/api/update'),env);
 for(const [username,key,tier] of [['trial','dummy-test-trial-key','trial'],['paid','dummy-test-paid-key','oem']])await db.prepare("INSERT OR REPLACE INTO users(username,key,tier,expires_at) VALUES(?,?,?,'Vô hạn')").bind(username,key,tier).run();
 for(const [username,key,status] of [['trial','dummy-test-trial-key',403],['paid','wrong-test-key',401],['paid','dummy-test-paid-key',200]]){
  const response=await worker.fetch(new Request('https://test.invalid'+route,{method:'POST',body:JSON.stringify({username,key,cursor:0,items:[]})}),env);assert.equal(response.status,status,(await response.clone().text()));
 }
 console.log('PASS: Worker/D1 trên SQLite — xác thực, chặn trial, quyền admin, pending/approved/thu hồi, retry và lô sai.');
}finally{rmSync(folder,{recursive:true,force:true});}
