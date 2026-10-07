// Bộ nhớ dùng chung: trial bị chặn; chỉ quản trị viên công bố.
const MEMORY_FIELDS = new Set(['code','borehole_name','sample_id','category','depth_from','depth_to','test_depth','gamma','e0','cc','cs','pc','cv_constant','co','cohesion_c','friction_phi','phi_cu_effective','spt_n']);
const MEMORY_REGISTRY = {"code":{"label":"Mã lớp","unit":"text","type":"text","units":{},"alias":["code","Mã lớp"]},"borehole_name":{"label":"Tên lỗ khoan","unit":"text","type":"text","units":{},"alias":["borehole_name","Tên lỗ khoan"]},"sample_id":{"label":"Số hiệu mẫu","unit":"text","type":"text","units":{},"alias":["sample_id","Số hiệu mẫu"]},"category":{"label":"Loại đất","unit":"text","type":"text","units":{},"alias":["category","Loại đất"],"enum":["Đất dính","Đất rời"],"value_aliases":{"Clay":"Đất dính","Sand":"Đất rời"}},"depth_from":{"label":"Độ sâu từ","unit":"m","type":"number","units":{"m":1,"cm":0.01,"mm":0.001},"min":0,"alias":["depth_from","Độ sâu từ"]},"depth_to":{"label":"Độ sâu đến","unit":"m","type":"number","units":{"m":1,"cm":0.01,"mm":0.001},"min":0,"alias":["depth_to","Độ sâu đến"]},"test_depth":{"label":"Độ sâu thí nghiệm","unit":"m","type":"number","units":{"m":1,"cm":0.01,"mm":0.001},"min":0,"alias":["test_depth","Độ sâu thí nghiệm"]},"gamma":{"label":"Dung trọng tự nhiên","type":"number","min":0,"alias":["gamma","Dung trọng tự nhiên","γ","dung trọng","bulk density","natural density"],"unit":"T/m³","units":{"T/m³":1,"g/cm³":1,"kg/m³":0.001,"kN/m³":0.10197162129779283},"min_exclusive":true,"groups":["natural_density"]},"e0":{"label":"Hệ số rỗng ban đầu","type":"number","min":0,"alias":["e0","Hệ số rỗng ban đầu"],"unit":"1","units":{"1":1},"min_exclusive":true},"cc":{"label":"Chỉ số nén","type":"number","min":0,"alias":["cc","Chỉ số nén"],"unit":"1","units":{"1":1},"groups":["consolidation"]},"cs":{"label":"Chỉ số nở","type":"number","min":0,"alias":["cs","Chỉ số nở"],"unit":"1","units":{"1":1},"groups":["consolidation"]},"pc":{"label":"Áp lực tiền cố kết","type":"number","min":0,"alias":["pc","Áp lực tiền cố kết"],"unit":"T/m²","units":{"T/m²":1,"kg/cm²":10,"kgf/cm²":10,"kPa":0.10197162129779283,"kN/m²":0.10197162129779283},"groups":["consolidation"]},"cv_constant":{"label":"Hệ số cố kết trung bình","type":"number","min":0,"alias":["cv_constant","Hệ số cố kết trung bình","Cvtb","Cv trung bình"],"unit":"10^-3 cm²/s","units":{"10^-3 cm²/s":1,"10^-4 cm²/s":0.1,"cm²/s":1000,"m²/s":10000000.0,"m²/year":0.3168808781402895},"min_exclusive":true,"groups":["consolidation"]},"co":{"label":"Sức kháng cắt không thoát nước","type":"number","min":0,"alias":["co","Sức kháng cắt không thoát nước","Su","Co","C0","cu không thoát nước","undrained shear strength"],"unit":"T/m²","units":{"T/m²":1,"kg/cm²":10,"kgf/cm²":10,"kPa":0.10197162129779283,"kN/m²":0.10197162129779283},"groups":["undrained","vane_undisturbed"]},"cohesion_c":{"label":"Lực dính","type":"number","min":0,"alias":["cohesion_c","Lực dính"],"unit":"T/m²","units":{"T/m²":1,"kg/cm²":10,"kgf/cm²":10,"kPa":0.10197162129779283,"kN/m²":0.10197162129779283},"groups":["direct_shear","triaxial_UU"]},"friction_phi":{"label":"Góc ma sát trong","type":"number","min":0,"alias":["friction_phi","Góc ma sát trong"],"unit":"degree","units":{"degree":1,"degree-minute":1},"max":90,"max_exclusive":true,"groups":["direct_shear","triaxial_UU"]},"phi_cu_effective":{"label":"Góc ma sát hữu hiệu CU","type":"number","min":0,"alias":["phi_cu_effective","Góc ma sát hữu hiệu CU"],"unit":"degree","units":{"degree":1,"degree-minute":1},"max":90,"max_exclusive":true,"groups":["triaxial_CU_effective"]},"spt_n":{"label":"Chỉ số N-SPT","type":"number","min":0,"alias":["spt_n","Chỉ số N-SPT","N-SPT","Nspt","N value","blow count"],"unit":"blows/30cm","units":{"blows/30cm":1},"integer":true}};
const memorySchemaJobs = new WeakMap();
function memoryError(message,status=400){const error=new Error(message);error.status=status;throw error;}
export function sharedMemoryAccess(actor,admin=false){
 if(!actor)memoryError('Đăng nhập để dùng bộ nhớ chung.',401);
 if(actor.is_system!==true && (!actor.tier || String(actor.tier).trim().toLowerCase()==='trial'))memoryError('Tài khoản dùng thử không được dùng bộ nhớ chung.',403);
 if(admin&&actor.is_system!==true)memoryError('Chỉ quản trị viên được công bố quy tắc dùng chung.',403);
}
function memoryKeys(value,keys){if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).some(k=>!keys.includes(k))||keys.some(k=>!(k in value)))memoryError('Sai cấu trúc bộ nhớ.');}
function memoryString(value,max=600){if(typeof value!=='string'||value.length>max)memoryError('Nhãn bộ nhớ không hợp lệ.');}
function memoryCanonical(value){if(Array.isArray(value))return '['+value.map(memoryCanonical).join(',')+']';if(value&&typeof value==='object')return '{'+Object.keys(value).sort().map(k=>JSON.stringify(k)+':'+memoryCanonical(value[k])).join(',')+'}';return JSON.stringify(value);}
async function memoryHash(value){const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(memoryCanonical(value)));return [...new Uint8Array(bytes)].map(b=>b.toString(16).padStart(2,'0')).join('');}
export function validateSharedPayload(kind,payload){
 if(kind==='mapping'){
  memoryKeys(payload,['signature','registry_hash','columns','answer','overrides']);
  if(!/^[a-f0-9]{64}$/.test(payload.signature)||!/^[a-f0-9]{64}$/.test(payload.registry_hash))memoryError('Chữ ký biểu mẫu không hợp lệ.');
  if(!Array.isArray(payload.columns)||!payload.columns.length||payload.columns.length>200)memoryError('Danh sách cột không hợp lệ.');
  const ids=new Set();for(const c of payload.columns){memoryKeys(c,['cot_id','label','symbol','unit','group']);if(!Number.isSafeInteger(c.cot_id)||c.cot_id<1||c.cot_id>16384||ids.has(c.cot_id))memoryError('Cột trùng hoặc sai vị trí.');ids.add(c.cot_id);for(const k of ['label','symbol','unit','group'])memoryString(c[k]);}
  const a=payload.answer;memoryKeys(a,['task','items','khong_chac']);if(a.task!=='column_mapping'||!Array.isArray(a.items)||!Array.isArray(a.khong_chac))memoryError('Sai schema ánh xạ.');
  const seen=new Set(),targets=new Set();for(const item of a.items){memoryKeys(item,['cot_id','thong_so','do_tin_cay','ly_do']);if(!ids.has(item.cot_id)||seen.has(item.cot_id)||!(item.thong_so==='unknown'||MEMORY_FIELDS.has(item.thong_so))||typeof item.do_tin_cay!=='number'||!Number.isFinite(item.do_tin_cay)||item.do_tin_cay<0||item.do_tin_cay>1)memoryError('Ánh xạ sai hoặc tạo thông số.');seen.add(item.cot_id);memoryString(item.ly_do,180);if(item.ly_do.trim().split(/\s+/).filter(Boolean).length>=12)memoryError('Lý do ánh xạ quá dài.');if(item.thong_so!=='unknown'){if(targets.has(item.thong_so))memoryError('Trùng thông số đích.');targets.add(item.thong_so);}}
  if(a.khong_chac.some(id=>!ids.has(id))||new Set(a.khong_chac).size!==a.khong_chac.length)memoryError('Cột chưa chắc không hợp lệ.');
  if(!payload.overrides||Array.isArray(payload.overrides)||typeof payload.overrides!=='object')memoryError('Đơn vị hiệu chỉnh không hợp lệ.');
  for(const [id,v] of Object.entries(payload.overrides)){if(!/^\d+$/.test(id)||!ids.has(Number(id))||!v||typeof v!=='object'||Array.isArray(v)||Object.keys(v).some(k=>!['unit','group'].includes(k)))memoryError('Hiệu chỉnh ngoài metadata.');for(const value of Object.values(v))memoryString(value);}
 }else if(kind==='knowledge'){
  memoryKeys(payload,['topic','title','body','source']);for(const k of ['topic','title','body','source'])memoryString(payload[k],k==='body'?12000:500);
  if(!payload.title.trim()||!payload.body.trim()||!payload.source.trim())memoryError('Kiến thức thiếu nội dung hoặc căn cứ.');
 }else memoryError('Loại bộ nhớ không được phép.');
 if(memoryCanonical(payload).length>100000)memoryError('Bản ghi bộ nhớ quá lớn.',413);
 return payload;
}
export function validateSharedPublication(kind,payload){
 validateSharedPayload(kind,payload);
 if(kind!=='mapping')return;
 for(const item of payload.answer.items){
  if(item.thong_so==='unknown')continue;
  const c=payload.columns.find(c=>c.cot_id===item.cot_id),spec=MEMORY_REGISTRY[item.thong_so],override=payload.overrides[String(c.cot_id)]||{};
  if(spec.type!=='text' && !Object.hasOwn(spec.units,c.unit))memoryError('Đơn vị nguồn chưa rõ; chỉ dùng quy tắc riêng, không công bố chung.');
  if(spec.groups&&!spec.groups.includes(c.group))memoryError('Nhóm thí nghiệm nguồn chưa rõ; không công bố chung.');
  if(override.unit!==undefined&&override.unit!==c.unit || override.group!==undefined&&override.group!==c.group)memoryError('Không dùng hiệu chỉnh đơn vị/nhóm riêng cho mọi biểu mẫu.');
 }
}
export async function ensureSharedMemorySchema(db){
 if(memorySchemaJobs.has(db))return memorySchemaJobs.get(db);
 const job=db.batch([
  db.prepare("CREATE TABLE IF NOT EXISTS shared_memory_items (id TEXT PRIMARY KEY,kind TEXT NOT NULL,payload TEXT NOT NULL,owner TEXT NOT NULL,state TEXT NOT NULL DEFAULT 'pending' CHECK(state IN ('pending','approved','rejected','disabled')),reviewer TEXT NOT NULL DEFAULT '',created_at TEXT NOT NULL,reviewed_at TEXT NOT NULL DEFAULT '')"),
  db.prepare("CREATE TABLE IF NOT EXISTS shared_memory_changes (seq INTEGER PRIMARY KEY AUTOINCREMENT,item_id TEXT NOT NULL,kind TEXT NOT NULL,state TEXT NOT NULL CHECK(state IN ('approved','disabled','rejected')),payload TEXT NOT NULL,reviewer TEXT NOT NULL,created_at TEXT NOT NULL)"),
  db.prepare('CREATE INDEX IF NOT EXISTS shared_memory_state ON shared_memory_items(state,created_at)')
 ]);memorySchemaJobs.set(db,job);try{return await job;}catch(e){memorySchemaJobs.delete(db);throw e;}
}
export async function handleSharedMemory(db,actor,path,body){
 sharedMemoryAccess(actor,path!=='/api/memory/shared/sync');
 await ensureSharedMemorySchema(db);
 const now=new Date().toISOString();
 if(path==='/api/memory/shared/sync'){
  if(Object.keys(body).some(k=>!['username','key','device_id','session_id','items','cursor'].includes(k)))memoryError('Yêu cầu có trường ngoài schema.');
  const items=body.items||[],cursor=body.cursor??0;
  if(actor.is_system!==true && Array.isArray(items) && items.length)memoryError('Chỉ Admin được tự cập nhật bộ nhớ AI.',403);
  if(!Array.isArray(items)||items.length>20||!Number.isSafeInteger(cursor)||cursor<0)memoryError('Lô đồng bộ không hợp lệ.');
  const prepared=[],ack=[],clientIds=new Set();
  for(const item of items){memoryKeys(item,['client_id','kind','payload']);if(!/^[a-f0-9]{64}$/.test(item.client_id)||clientIds.has(item.client_id))memoryError('Mã đồng bộ trùng hoặc sai.');clientIds.add(item.client_id);validateSharedPayload(item.kind,item.payload);const id=await memoryHash([item.kind,item.payload]);validateSharedPublication(item.kind,item.payload);prepared.push(db.prepare("INSERT INTO shared_memory_items(id,kind,payload,owner,state,reviewer,reviewed_at,created_at) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET state=CASE WHEN shared_memory_items.state='pending' THEN 'approved' ELSE shared_memory_items.state END,reviewer=CASE WHEN shared_memory_items.state='pending' THEN excluded.reviewer ELSE shared_memory_items.reviewer END,reviewed_at=CASE WHEN shared_memory_items.state='pending' THEN excluded.reviewed_at ELSE shared_memory_items.reviewed_at END").bind(id,item.kind,memoryCanonical(item.payload),actor.username,'approved',actor.username,now,now));prepared.push(db.prepare("INSERT INTO shared_memory_changes(item_id,kind,state,payload,reviewer,created_at) SELECT ?,?,'approved',?,?,? WHERE NOT EXISTS (SELECT 1 FROM shared_memory_changes WHERE item_id=?)").bind(id,item.kind,memoryCanonical(item.payload),actor.username,now,id));ack.push(item.client_id);}
  if(prepared.length)await db.batch(prepared);
  const result=await db.prepare('SELECT seq,item_id,kind,state,payload,reviewer,created_at FROM shared_memory_changes WHERE seq>? ORDER BY seq LIMIT 20').bind(cursor).all();
  const changes=(result.results||[]).map(r=>({...r,payload:JSON.parse(r.payload)}));const next=changes.length?changes[changes.length-1].seq:cursor;
  const last=await db.prepare('SELECT COALESCE(MAX(seq),0) AS seq FROM shared_memory_changes').first();
  return {success:true,ack,changes,cursor:next,more:Number(last.seq)>next};
 }
 if(path==='/api/memory/shared/pending'){
  const offset=body.offset??0;if(!Number.isSafeInteger(offset)||offset<0)memoryError('Trang không hợp lệ.');
  const r=await db.prepare("SELECT id,kind,payload,owner,state,reviewer,created_at FROM shared_memory_items WHERE state IN ('pending','approved') ORDER BY created_at DESC LIMIT 50 OFFSET ?").bind(offset).all();
  return {success:true,items:(r.results||[]).map(item=>({...item,payload:JSON.parse(item.payload)}))};
 }
 if(path==='/api/memory/shared/review'){
  if(!/^[a-f0-9]{64}$/.test(body.id)||!['approved','rejected','disabled'].includes(body.state))memoryError('Quyết định không hợp lệ.');
  const item=await db.prepare('SELECT * FROM shared_memory_items WHERE id=?').bind(body.id).first();if(!item)memoryError('Không tìm thấy bản ghi.',404);
  if(body.state==='approved')validateSharedPublication(item.kind,JSON.parse(item.payload));
  else validateSharedPayload(item.kind,JSON.parse(item.payload));
  // Một batch: cập nhật và ghi nhật ký công bố/thu hồi cùng giao dịch.
  await db.batch([
   db.prepare('UPDATE shared_memory_items SET state=?,reviewer=?,reviewed_at=? WHERE id=?').bind(body.state,actor.username,now,body.id),
   db.prepare('INSERT INTO shared_memory_changes(item_id,kind,state,payload,reviewer,created_at) VALUES(?,?,?,?,?,?)').bind(body.id,item.kind,body.state,item.payload,actor.username,now)
  ]);
  return {success:true,id:body.id,state:body.state};
 }
 memoryError('Không có API bộ nhớ này.',404);
}
