const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const {createHmac,pbkdf2Sync,randomUUID}=require('node:crypto');
const modules=Promise.all([import('@electric-sql/pglite'),import('../../supabase/functions/nsysu-line/store.mjs'),import('../../supabase/functions/nsysu-line/gateway.mjs'),import('../../supabase/functions/nsysu-line/protocol.mjs')]);
const password='SYNTHETIC_PASSWORD',secret='SYNTHETIC_CHANNEL_SECRET',identity='SYNTHETIC_LINE_A';
const migration=fs.readdir('supabase/migrations').then(names=>'supabase/migrations/'+names.find(name=>name.endsWith('_cloud_line_gateway.sql')));

async function fixture(t){
 const [{PGlite},{CloudStore},{createGateway},protocol]=await modules;
 const db=new PGlite();t.after(()=>db.close());
 await db.exec(`create role anon;create role authenticated;create schema nsysu_private;create schema vault;
 create table public.research_participants(member_id text primary key,archived_at timestamptz);
 create table public.sleep_logs(member_id text,date text,date_definition text);
 create table vault.decrypted_secrets(id uuid primary key,decrypted_secret text);
 create table nsysu_private.diary_invitations(member_id text primary key,fixed_secret_id uuid,revoked_at timestamptz);
 create function nsysu_private.check_diary_invitation(m text,t text) returns boolean language sql stable as $$
 select exists(select 1 from nsysu_private.diary_invitations i join vault.decrypted_secrets v on v.id=i.fixed_secret_id where i.member_id=m and i.revoked_at is null and v.decrypted_secret=t)$$;`);
 await db.exec(await fs.readFile(await migration,'utf8'));
 // Match postgres.js typed JSONB serialization, including its treatment of strings.
 const store=new CloudStore({transaction:work=>db.transaction(tx=>work({query:(sql,args=[])=>{
  const jsonIndexes=sql.includes('insert into nsysu_line.events(')?[3]:sql.includes('insert into nsysu_line.outbox(')?[sql.includes("values($1,'diary'")?7:3]:[];
  return tx.query(sql,args.map((value,index)=>jsonIndexes.includes(index)?JSON.stringify(value):value));
 }}))});
 const salt='SYNTHETIC_SALT',hash='pbkdf2:sha256:600000$'+salt+'$'+pbkdf2Sync(password,salt,600000,32,'sha256').toString('hex');
 for(const [member,capability] of [['ycc00000001','a'.repeat(64)],['ycc00000050','b'.repeat(64)]]){
  const id=randomUUID();
  await db.query('insert into public.research_participants values($1,null)',[member]);
  await db.query('insert into vault.decrypted_secrets values($1,$2)',[id,capability]);
  await db.query('insert into nsysu_private.diary_invitations values($1,$2,null)',[member,id]);
  await db.query('insert into nsysu_line.accounts(account_hash,password_hash,study,member) values($1,$2,$3,$4)',[await protocol.digest(member),hash,'SYNTHETIC_STUDY',member]);
 }
 await db.query('update nsysu_line.config set enabled=true,allowed_users=$1',[ [identity,'SYNTHETIC_LINE_B'] ]);
 let clock='2026-11-17T23:59:00+08:00';
 async function at(value){clock=value;await db.exec(`create or replace function nsysu_line.now() returns timestamptz language sql volatile set search_path='' as $$ select '${new Date(value).toISOString()}'::timestamptz $$`);}
 await at(clock);
 const calls=[],pending=[];let next=0,result='accepted';
 const line={linkToken:async()=> 'SYNTHETIC_LINK_'+(++next),push:async(payload,key)=>{calls.push({payload,key});return {status:result,error:result==='accepted'?null:'SYNTHETIC_NETWORK'};}};
 const gateway=createGateway({store,line,secret,bindingURL:'https://research.example.org/?view=line',waitUntil:promise=>pending.push(promise)});
 async function tickRequest(){
  const ticket=protocol.randomToken();
  await db.query("insert into nsysu_line.cron_tickets values($1,nsysu_line.now()+interval '2 minutes')",[await protocol.digest(ticket)]);
  return new Request('https://cloud.example.org/tick',{method:'POST',headers:{Authorization:'Bearer '+ticket},body:'{}'});
 }
 async function send(action='start',options={}){
  const event={type:'postback',webhookEventId:options.id||randomUUID(),timestamp:options.stamp??new Date(clock).getTime(),source:{type:'user',userId:options.identity||identity},postback:{data:'binding:'+action}};
  if(action==='linked'||action==='link_failed'){event.type='accountLink';event.link={result:action==='linked'?'ok':'failed',nonce:options.nonce};delete event.postback;}
  if(action==='unfollow'){event.type='unfollow';delete event.postback;}
  if(action==='follow'){event.type='follow';delete event.postback;}
  const raw=JSON.stringify({events:[event]});
  const request=new Request('https://cloud.example.org/webhook',{method:'POST',headers:{'x-line-signature':options.signature||createHmac('sha256',secret).update(raw).digest('base64')},body:raw});
  const response=await gateway(request);
  await Promise.all(pending.splice(0));
  return response;
 }
 async function prepare(member='ycc00000001',candidate=password){
  const uri=calls.at(-1).payload.messages[0].template.actions[0].uri;
  return gateway(new Request('https://cloud.example.org/prepare-link',{method:'POST',body:JSON.stringify({link_token:new URL(uri).searchParams.get('link_token'),account:member,password:candidate})}));
 }
 async function bind(member='ycc00000001',who=identity){
  await send('start',{identity:who});const response=await prepare(member);assert.equal(response.status,200);
  const value=await response.json();const nonce=new URL(value.link_url).searchParams.get('nonce');
  await send('linked',{identity:who,nonce});return nonce;
 }
 const records=async table=>(await db.query('select * from nsysu_line.'+table)).rows;
 return {db,store,gateway,line,calls,send,prepare,bind,at,records,protocol,tickRequest,setResult:value=>result=value};
}

test('cloud exact account grammar and PBKDF2 verification',async()=>{
 const [,,,p]=await modules;
 for(const account of ['ycc00000001','ycc00000050'])assert.equal(p.validAccount(account),true);
 for(const account of ['yc00000001','YCC00000001','ycc00000000','ycc00000051','ycc0000001','ycc00000001\n'])assert.equal(p.validAccount(account),false);
 const salt='SYNTHETIC_SALT',hash='pbkdf2:sha256:600000$'+salt+'$'+pbkdf2Sync(password,salt,600000,32,'sha256').toString('hex');
 assert.equal(await p.verifyPassword(password,hash),true);assert.equal(await p.verifyPassword('wrong',hash),false);
 assert.equal(await p.verifyPassword(password,hash+'\n'),false);assert.equal(await p.verifyPassword(password,'scrypt:invalid'),false);
});

test('cloud schema denies browser roles and backend cannot read Vault or diaries directly',async t=>{
 const f=await fixture(t);
 for(const role of ['anon','authenticated']){
  await assert.rejects(f.db.transaction(async tx=>{await tx.exec('set local role '+role);await tx.query('select * from nsysu_line.accounts');}));
  await assert.rejects(f.db.transaction(async tx=>{await tx.exec('set local role '+role);await tx.query("select nsysu_line.diary_snapshot('ycc00000001','2026-11-18')");}));
 }
 await assert.rejects(f.store.transaction(tx=>tx.query('select * from vault.decrypted_secrets')));
 await assert.rejects(f.store.transaction(tx=>tx.query('select * from public.sleep_logs')));
});

test('signed menu replies without timer; duplicate, forged and other-recipient events do not send',async t=>{
 const f=await fixture(t);
 assert.equal((await f.send('start',{id:'same'})).status,200);assert.equal(f.calls.length,1);
 await f.send('start',{id:'same'});assert.equal(f.calls.length,1);
 assert.equal((await f.send('cancel',{signature:'bad'})).status,401);
 await f.send('start',{identity:'SYNTHETIC_NOT_ALLOWED'});assert.equal(f.calls.length,1);
 assert.equal((await f.records('outbox'))[0].attempts,1);
});

test('verified active friend events synchronize the shared menu; forged, excluded and unfollow events do not',async t=>{
 const f=await fixture(t),synced=[];
 f.line.syncRichMenu=async who=>{synced.push(who);return true;};
 await f.send('follow');assert.deepEqual(synced,[identity]);
 await f.send('start',{identity:'SYNTHETIC_LINE_B'});assert.deepEqual(synced,[identity,'SYNTHETIC_LINE_B']);
 await f.send('start',{signature:'bad'});await f.send('start',{identity:'SYNTHETIC_NOT_ALLOWED'});await f.send('unfollow');
 assert.equal(synced.length,2);
});

test('menu synchronization failure does not block binding replies or the personal diary test',async t=>{
 const f=await fixture(t);
 f.line.syncRichMenu=async()=>{throw Error('SYNTHETIC_MENU_UNAVAILABLE');};
 await f.bind();assert.equal((await f.records('bindings')).length,1);
 const job=(await f.records('outbox')).find(item=>item.slot?.startsWith('binding-test:'));
 assert.equal(job.status,'accepted');assert.equal(job.attempts,1);
});

test('LINE menu transport uses the current default and only pinned authenticated API paths',async()=>{
 const [,,{LineTransport}]=await modules,requests=[],menu='richmenu-'+'a'.repeat(32);
 const line=new LineTransport('SYNTHETIC_TOKEN',async(url,options)=>{
  requests.push({url,options});return new Response(JSON.stringify(requests.length===1?{richMenuId:menu}:{}));
 });
 assert.equal(await line.syncRichMenu('SYNTHETIC_LINE_A'),true);
 assert.equal(requests[0].url,'https://api.line.me/v2/bot/user/all/richmenu');assert.equal(requests[0].options.method,'GET');
 assert.equal(requests[1].url,'https://api.line.me/v2/bot/user/SYNTHETIC_LINE_A/richmenu/'+menu);
 assert.equal(requests[1].options.method,'POST');
 assert.ok(requests.every(request=>request.options.headers.Authorization==='Bearer SYNTHETIC_TOKEN'&&request.options.redirect==='error'));
 const invalid=[];
 const malformed=new LineTransport('SYNTHETIC_TOKEN',async url=>{invalid.push(url);return new Response(JSON.stringify({richMenuId:'https://foreign.invalid/menu'}));});
 assert.equal(await malformed.syncRichMenu(identity),false);assert.equal(invalid.length,1);
 const absent=new LineTransport('SYNTHETIC_TOKEN',async()=>new Response('{}',{status:404}));
 assert.equal(await absent.syncRichMenu(identity),false);
});

test('official account link is pending until verified callback; nonce owner, replay and original dates',async t=>{
 const f=await fixture(t);
 await f.send();
 const prepared=await f.prepare();const nonce=new URL((await prepared.json()).link_url).searchParams.get('nonce');
 assert.equal((await f.records('bindings')).length,0);
 await f.send('linked',{nonce,identity:'SYNTHETIC_LINE_B'});assert.equal((await f.records('bindings')).length,0);
 await f.send('linked',{nonce});const original=(await f.records('bindings'))[0];assert.ok(original);
 assert.equal(original.reminder_start.toISOString().slice(0,10),'2026-11-18');
 await f.send('linked',{nonce});assert.equal((await f.records('bindings')).length,1);
 await f.at('2026-11-19T10:00:00+08:00');await f.bind();
 assert.equal((await f.records('bindings'))[0].bound_at.getTime(),original.bound_at.getTime());
});

test('verified binding immediately sends each recipient their own diary test link before next-day reminders',async t=>{
 const f=await fixture(t);
 await f.bind('ycc00000001');await f.bind('ycc00000050','SYNTHETIC_LINE_B');
 const tests=f.calls.filter(call=>call.payload.messages[0].altText?.includes('【日誌連結測試】'));
 assert.equal(tests.length,2);
 for(const [index,member,who,capability] of [[0,'ycc00000001',identity,'a'.repeat(64)],[1,'ycc00000050','SYNTHETIC_LINE_B','b'.repeat(64)]]){
  const payload=tests[index].payload,body=payload.messages[0],url=new URL(body.template.actions[0].uri);
  assert.equal(payload.to,who);assert.equal(payload.messages.length,1);
  assert.equal(url.searchParams.get('member'),member);assert.equal(url.searchParams.get('invite'),capability);
  assert.equal(url.searchParams.get('date'),'2026-11-17');assert.ok(body.altText.includes(member));
  assert.ok(body.altText.includes('2026/11/18 09:00'));assert.ok(body.template.text.length<=160);
 }
 const jobs=(await f.records('outbox')).filter(job=>job.slot?.startsWith('binding-test:'));
 assert.equal(jobs.length,2);assert.ok(jobs.every(job=>job.status==='accepted'&&job.attempts===1));
 await f.store.plan();assert.equal((await f.records('outbox')).filter(job=>job.kind==='diary').length,0);
 await f.at('2026-11-18T09:00:00+08:00');await f.store.plan();
 assert.equal((await f.records('outbox')).filter(job=>job.kind==='diary').length,2);
});

test('open enrollment still requires registered credentials and a verified callback before the new recipient gets a test',async t=>{
 const f=await fixture(t),who='SYNTHETIC_NEW_RESEARCH_PARTICIPANT';
 await f.db.query('update nsysu_line.config set allow_all=true,allowed_users=$1',[[]]);
 await f.send('start',{identity:who});
 assert.equal((await f.records('bindings')).length,0);
 assert.equal((await f.prepare('ycc00000002')).status,401);
 const response=await f.prepare('ycc00000050');assert.equal(response.status,200);
 assert.equal((await f.records('bindings')).length,0);
 const nonce=new URL((await response.json()).link_url).searchParams.get('nonce');
 await f.send('linked',{identity:who,nonce});
 const tests=f.calls.filter(call=>call.payload.messages[0].altText?.includes('【日誌連結測試】'));
 assert.equal(tests.length,1);assert.equal(tests[0].payload.to,who);
 assert.equal(new URL(tests[0].payload.messages[0].template.actions[0].uri).searchParams.get('member'),'ycc00000050');
});

test('binding callback redelivery and proof replay do not repeat test; intentional same-account rebind does',async t=>{
 const f=await fixture(t);await f.send();
 const nonce=new URL((await (await f.prepare()).json()).link_url).searchParams.get('nonce');
 await f.send('linked',{id:'BIND_TEST',nonce});
 const original=(await f.records('bindings'))[0];
 await f.send('linked',{id:'BIND_TEST',nonce});await f.send('linked',{nonce});
 assert.equal(f.calls.filter(call=>call.payload.messages[0].altText?.includes('【日誌連結測試】')).length,1);
 await f.at('2026-11-18T08:00:00+08:00');await f.bind();
 assert.equal(f.calls.filter(call=>call.payload.messages[0].altText?.includes('【日誌連結測試】')).length,2);
 const binding=(await f.records('bindings'))[0];
 assert.equal(binding.bound_at.getTime(),original.bound_at.getTime());
 assert.equal(binding.reminder_start.getTime(),original.reminder_start.getTime());
});

test('cancel before binding-test event recovery suppresses the old account link after switching accounts',async t=>{
 const f=await fixture(t);await f.send();
 const nonce=new URL((await (await f.prepare()).json()).link_url).searchParams.get('nonce');
 const record=await f.store.applyEvent({id:'DELAYED_BIND_TEST',identity,stamp:Date.parse('2026-11-17T23:59:00+08:00'),action:'linked',nonce});
 assert.equal(record.result.kind,'binding_test');
 await f.send('cancel');await f.send(f.calls.at(-1).payload.messages[0].template.actions[0].data.slice(8));
 await f.at('2026-11-18T00:00:00+08:00');await f.bind('ycc00000050');
 assert.equal(await f.store.finishEvent(record,record.result.message),null);
 assert.equal((await f.records('events')).find(event=>event.event_id===record.event_id).finished,true);
 assert.equal(f.calls.filter(call=>call.payload.messages[0].altText?.includes('【日誌連結測試】')).length,1);
 assert.equal(new URL(f.calls.at(-1).payload.messages[0].template.actions[0].uri).searchParams.get('member'),'ycc00000050');
});

test('pending binding-test retry is cancelled on unbind and cannot send after a new binding',async t=>{
 const f=await fixture(t);f.setResult('uncertain');await f.bind();
 const job=(await f.records('outbox')).find(item=>item.slot?.startsWith('binding-test:'));
 assert.equal(job.attempts,1);assert.equal(job.status,'uncertain');
 f.setResult('accepted');await f.send('cancel');await f.send(f.calls.at(-1).payload.messages[0].template.actions[0].data.slice(8));
 assert.equal((await f.records('outbox')).find(item=>item.job_key===job.job_key).status,'cancelled');
 await f.at('2026-11-18T00:00:00+08:00');await f.bind('ycc00000050');
 const count=f.calls.length;assert.equal(await f.store.dispatch(job.job_key,f.line),null);assert.equal(f.calls.length,count);
});

test('binding test revalidates invitation and account before dispatch; unavailable invite has no test URL',async t=>{
 const f=await fixture(t);f.setResult('retry');await f.bind();
 const job=(await f.records('outbox')).find(item=>item.slot?.startsWith('binding-test:'));
 await f.db.query("update nsysu_private.diary_invitations set revoked_at=now() where member_id='ycc00000001'");
 await f.at('2026-11-18T00:00:00+08:00');f.setResult('accepted');
 const count=f.calls.length;await f.store.dispatch(job.job_key,f.line);assert.equal(f.calls.length,count);
 assert.equal((await f.records('outbox')).find(item=>item.job_key===job.job_key).status,'cancelled');
 await f.bind();assert.ok(f.calls.at(-1).payload.messages[0].text.includes('日誌測試連結暫時無法開啟'));
 assert.equal(f.calls.at(-1).payload.messages[0].template,undefined);
});

test('binding test respects future study start and remains available for a completed date without adding reminders',async t=>{
 const f=await fixture(t);await f.at('2026-11-18T08:00:00+08:00');
 await f.db.query("update nsysu_line.accounts set starts='2026-11-20',ends='2026-11-21' where member='ycc00000001'");
 await f.db.query("insert into public.sleep_logs values('ycc00000001','2026-11-20','wake_date')");
 await f.bind();
 const body=f.calls.at(-1).payload.messages[0],url=new URL(body.template.actions[0].uri);
 assert.equal(url.searchParams.get('date'),'2026-11-20');assert.ok(body.altText.includes('2026/11/20 09:00'));
 await f.at('2026-11-20T09:00:00+08:00');await f.store.plan();
 assert.equal((await f.records('outbox')).filter(job=>job.kind==='diary').length,0);
 assert.equal((await f.db.query('select * from public.sleep_logs')).rows.length,1);
});

test('wrong credentials, inactive account and another LINE binding cannot overwrite',async t=>{
 const f=await fixture(t);
 await f.send();assert.equal((await f.prepare('ycc00000001','wrong')).status,401);
 await f.bind();
 await f.send('start',{identity:'SYNTHETIC_LINE_B'});assert.equal((await f.prepare()).status,409);
 assert.equal((await f.records('bindings'))[0].line_user,identity);
});

test('two LINE confirmations for the same research account leave one owner and one diary test',async t=>{
 const f=await fixture(t),proofs=[];
 for(const who of [identity,'SYNTHETIC_LINE_B']){
  await f.send('start',{identity:who});
  const response=await f.prepare('ycc00000050');assert.equal(response.status,200);
  proofs.push({who,nonce:new URL((await response.json()).link_url).searchParams.get('nonce')});
 }
 await Promise.all(proofs.map(proof=>f.send('linked',{identity:proof.who,nonce:proof.nonce})));
 const bindings=await f.records('bindings');assert.equal(bindings.length,1);
 assert.equal(bindings[0].account_hash,await f.protocol.digest('ycc00000050'));
 const tests=f.calls.filter(call=>call.payload.messages[0].altText?.includes('【日誌連結測試】'));
 assert.equal(tests.length,1);assert.equal(tests[0].payload.to,bindings[0].line_user);
 const refused=f.calls.find(call=>call.payload.messages[0].text?.includes('每個研究帳號只能綁定一個 LINE'));
 assert.ok(refused);assert.notEqual(refused.payload.to,bindings[0].line_user);
});

test('database rejects a second LINE for an account and a second account for a LINE',async t=>{
 const f=await fixture(t);await f.bind();
 const [binding]=await f.records('bindings');
 await assert.rejects(f.db.query('insert into nsysu_line.bindings values($1,$2,$3,$4,true)',
  ['SYNTHETIC_LINE_B',binding.account_hash,binding.bound_at,binding.reminder_start]),error=>error.code==='23505');
 await assert.rejects(f.db.query('insert into nsysu_line.bindings values($1,$2,$3,$4,true)',
  [identity,await f.protocol.digest('ycc00000050'),binding.bound_at,binding.reminder_start]),error=>error.code==='23505');
 assert.equal((await f.records('bindings')).length,1);
});

test('only confirmed cancellation releases an account for another LINE; previous LINE gets no later diary',async t=>{
 const f=await fixture(t);await f.bind();
 await f.send('start',{identity:'SYNTHETIC_LINE_B'});
 const blocked=await f.prepare();assert.equal(blocked.status,409);
 assert.ok((await blocked.json()).error.includes('每個研究帳號只能綁定一個 LINE'));
 await f.send('cancel');const confirmation=f.calls.at(-1).payload.messages[0].template.actions[0].data.slice(8);
 await f.send('start',{identity:'SYNTHETIC_LINE_B'});assert.equal((await f.prepare()).status,409);
 await f.send(confirmation);assert.equal((await f.records('bindings')).length,0);
 await f.bind('ycc00000001','SYNTHETIC_LINE_B');
 await f.at('2026-11-18T09:00:00+08:00');await f.store.plan();
 const [job]=(await f.records('outbox')).filter(item=>item.kind==='diary');
 assert.ok(job);await f.store.dispatch(job.job_key,f.line);
 assert.equal(job.line_user,'SYNTHETIC_LINE_B');
 assert.equal(f.calls.filter(call=>call.payload.messages[0].template?.actions?.[0]?.label==='填寫睡眠日誌'&&call.payload.to===identity).length,0);
});

test('cancel requires confirmation, preserves diary, releases account, invalidates stale confirmation',async t=>{
 const f=await fixture(t);await f.bind();
 await f.db.query("insert into public.sleep_logs values('ycc00000001','2026-11-18','wake_date')");
 await f.send('cancel');const action=f.calls.at(-1).payload.messages[0].template.actions[0].data.slice(8);
 assert.equal((await f.records('bindings')).length,1);
 await f.send(action);assert.equal((await f.records('bindings')).length,0);
 assert.equal((await f.records('binding_history')).length,1);
 assert.equal((await f.db.query('select * from public.sleep_logs')).rows.length,1);
 await f.bind('ycc00000050');await f.send(action);
 assert.equal((await f.records('bindings')).length,1);assert.equal((await f.records('binding_history')).length,1);
});

test('Taipei next day first reminder, same-slot dedupe, open versus saved completion and next-day reset',async t=>{
 const f=await fixture(t);await f.bind();await f.store.plan();assert.equal((await f.records('outbox')).filter(j=>j.kind==='diary').length,0);
 await f.at('2026-11-18T09:00:00+08:00');await f.store.plan();await f.store.plan();
 let jobs=(await f.records('outbox')).filter(j=>j.kind==='diary');assert.equal(jobs.length,1);
 await f.store.dispatch(jobs[0].job_key,f.line);await f.store.dispatch(jobs[0].job_key,f.line);
 assert.equal(f.calls.filter(c=>c.payload.messages[0].template?.actions?.[0]?.label==='填寫睡眠日誌').length,1);
 await f.at('2026-11-18T11:00:00+08:00');await f.store.plan();
 assert.equal((await f.records('outbox')).filter(j=>j.kind==='diary').length,2);
 await f.db.query("insert into public.sleep_logs values('ycc00000001','2026-11-18','wake_date')");
 jobs=(await f.records('outbox')).filter(j=>j.kind==='diary');
 await f.store.dispatch(jobs[1].job_key,f.line);assert.equal((await f.records('outbox')).find(j=>j.job_key===jobs[1].job_key).status,'cancelled');
 await f.at('2026-11-18T13:00:00+08:00');await f.store.plan();
 jobs=(await f.records('outbox')).filter(j=>j.kind==='diary');assert.equal(jobs.length,2);
 await f.at('2026-11-19T09:00:00+08:00');await f.store.plan();assert.equal((await f.records('outbox')).filter(j=>j.kind==='diary').length,3);
});

test('all seven daily slots, wrong date/member/draft do not stop target reminder',async t=>{
 const f=await fixture(t);await f.bind();
 await f.db.query("insert into public.sleep_logs values('ycc00000001','2026-11-17','wake_date'),('ycc00000050','2026-11-18','wake_date'),('ycc00000001','2026-11-18','draft')");
 for(let hour=0;hour<24;hour++){
  await f.at('2026-11-18T'+String(hour).padStart(2,'0')+':00:00+08:00');await f.store.plan();
  for(const {job_key} of await f.store.pending())await f.store.dispatch(job_key,f.line);
 }
 const jobs=(await f.records('outbox')).filter(j=>j.kind==='diary');
 assert.deepEqual(jobs.map(j=>j.slot),['09:00','11:00','13:00','15:00','17:00','19:00','21:00']);
 assert.ok(jobs.every(j=>j.status==='accepted'&&j.attempts===1));
 for(const job of jobs){
  const body=job.payload.messages[0],url=new URL(body.template.actions[0].uri);
  assert.equal(body.template.text.startsWith(job.slot==='09:00'?'早安～昨天睡得好嗎？':'小小提醒～'),true);
  assert.ok(body.template.text.includes('研究帳號：ycc00000001'));
  assert.ok(body.template.text.includes('日誌日期：2026/11/18'));
  assert.ok(body.template.text.length<=160);assert.equal(body.altText,body.template.text);
  assert.equal(url.searchParams.get('member'),'ycc00000001');assert.equal(url.searchParams.get('date'),'2026-11-18');
  assert.equal(url.searchParams.get('invite'),'a'.repeat(64));
 }
});

test('cancel keep/expiry, account link expiry, and disabled binding remain effective',async t=>{
 const f=await fixture(t);await f.bind();await f.send('cancel');
 let action=f.calls.at(-1).payload.messages[0].template.actions[0].data.slice(8);
 await f.send(action.replace('confirm:','keep:'));await f.send(action);assert.equal((await f.records('bindings')).length,1);
 await f.send('cancel');action=f.calls.at(-1).payload.messages[0].template.actions[0].data.slice(8);
 await f.at('2026-11-18T00:11:00+08:00');await f.send(action);assert.equal((await f.records('bindings')).length,1);
 await f.send('start');const nonce=new URL((await (await f.prepare()).json()).link_url).searchParams.get('nonce');
 await f.at('2026-11-18T00:22:00+08:00');await f.send('linked',{nonce});assert.equal((await f.records('bindings')).length,1);
 await f.db.exec('update nsysu_line.bindings set active=false');await f.send('cancel');
 assert.ok(f.calls.at(-1).payload.messages[0].text.includes('停用'));
});

test('stopped/blocked/revoked invites and grace prevent any later diary dispatch',async t=>{
 const f=await fixture(t);await f.bind();await f.at('2026-11-18T09:00:00+08:00');await f.store.plan();
 const job=(await f.records('outbox')).find(j=>j.kind==='diary');
 await f.at('2026-11-18T09:11:00+08:00');await f.store.dispatch(job.job_key,f.line);
 assert.equal((await f.records('outbox')).find(j=>j.job_key===job.job_key).status,'skipped');
 await f.at('2026-11-18T11:00:00+08:00');await f.send('unfollow');await f.store.plan();
 assert.equal((await f.records('outbox')).filter(j=>j.kind==='diary').length,1);
 await f.send('start',{stamp:new Date('2026-11-18T10:59:00+08:00').getTime()});assert.equal((await f.records('friends'))[0].active,false);
 await f.at('2026-11-18T13:00:00+08:00');await f.send('start');
 await f.db.query("update nsysu_private.diary_invitations set revoked_at=now() where member_id='ycc00000001'");
 await f.store.plan();assert.equal((await f.records('outbox')).filter(j=>j.kind==='diary').length,1);
});

test('unfinished event recovers without applying cancellation again and disabled settings never send',async t=>{
 const f=await fixture(t);await f.bind();
 const e={id:'INTERRUPTED_EVENT',identity,stamp:new Date('2026-11-17T23:59:00+08:00').getTime(),action:'cancel'};
 await f.store.applyEvent(e);assert.equal((await f.records('cancellations')).length,1);
 await f.at('2026-11-18T00:01:00+08:00');
 const request=await f.tickRequest();
 assert.equal((await f.gateway(request)).status,200);assert.equal((await f.records('cancellations')).length,1);
 assert.equal((await f.records('events')).find(x=>x.event_id===e.id).finished,true);
 const count=f.calls.length;await f.db.exec('update nsysu_line.config set enabled=false');await f.send('start');
 assert.equal(f.calls.length,count);
 assert.equal((await f.gateway(new Request('https://cloud.example.org/tick',{method:'POST',body:'{}'}))).status,401);
});

test('credential limits persist after wrong passwords and arbitrary endpoints expose no management data',async t=>{
 const f=await fixture(t);await f.send();
 for(let i=0;i<5;i++)assert.equal((await f.prepare('ycc00000001','wrong')).status,401);
 assert.equal((await f.prepare()).status,429);
 assert.equal((await f.gateway(new Request('https://cloud.example.org/accounts'))).status,405);
 assert.equal((await f.gateway(new Request('https://cloud.example.org/tick',{method:'POST',headers:{Authorization:'Bearer WRONG'},body:'{}'}))).status,401);
});

test('migration rollback removes only new line schema and preserves original diary',async t=>{
 const f=await fixture(t);
 await f.db.query("insert into public.sleep_logs values('ycc00000001','2026-11-18','wake_date')");
 await f.db.exec(await fs.readFile('docs/rollback_cloud_line_gateway.sql','utf8'));
 assert.equal((await f.db.query('select count(*) as n from public.sleep_logs')).rows[0].n,1);
 assert.equal((await f.db.query("select count(*) as n from pg_namespace where nspname='nsysu_line'")).rows[0].n,0);
});

test('durable uncertain attempt, concurrent dispatch and restart keep original retry identity',async t=>{
 const f=await fixture(t);await f.bind();await f.at('2026-11-18T09:00:00+08:00');await f.store.plan();
 const key=(await f.records('outbox')).find(j=>j.kind==='diary').job_key;
 f.setResult('uncertain');await f.store.dispatch(key,f.line);const first=(await f.records('outbox')).find(j=>j.job_key===key);
 assert.equal(first.attempts,1);assert.equal(first.uncertainty,true);
 await f.at('2026-11-18T09:01:00+08:00');f.setResult('accepted');
 const [, {CloudStore}]=await modules;const restarted=new CloudStore(f.store.database);
 await Promise.all([restarted.dispatch(key,f.line),f.store.dispatch(key,f.line)]);
 const after=(await f.records('outbox')).find(j=>j.job_key===key);
 assert.equal(after.attempts,2);assert.equal(after.status,'accepted');assert.equal(after.retry_key,first.retry_key);
});

test('process crash after external call keeps durable attempts and never exceeds three',async t=>{
 const f=await fixture(t);await f.bind();await f.at('2026-11-18T09:00:00+08:00');await f.store.plan();
 const key=(await f.records('outbox')).find(j=>j.kind==='diary').job_key,retries=[];
 f.line.push=async(payload,retry)=>{retries.push(retry);throw Error('SYNTHETIC_PROCESS_DEATH');};
 for(const minute of ['00','02','04']){
  await f.at('2026-11-18T09:'+minute+':00+08:00');await assert.rejects(f.store.dispatch(key,f.line));
 }
 await f.at('2026-11-18T09:06:00+08:00');await f.store.dispatch(key,f.line);
 const row=(await f.records('outbox')).find(j=>j.job_key===key);
 assert.equal(row.attempts,3);assert.equal(row.status,'uncertain_final');assert.equal(row.uncertainty,true);
 assert.equal(retries.length,3);assert.equal(new Set(retries).size,1);
});

test('Cron tickets are one-time, expire, and are required before the worker runs',async t=>{
 const f=await fixture(t),request=await f.tickRequest();
 assert.equal((await f.gateway(request.clone())).status,200);
 assert.equal((await f.gateway(request.clone())).status,401);
 const stale=await f.tickRequest();await f.at('2026-11-18T00:02:00+08:00');
 assert.equal((await f.gateway(stale)).status,401);
});

test('cloud scheduler SQL is inactive, uses one-time tickets, and is not executable by backend/browser roles',async t=>{
 const f=await fixture(t);
 await f.db.exec(`create schema net;create schema cron;
 create table net.requests(headers jsonb);
 create table cron.job(jobid bigint generated always as identity primary key,jobname text unique,schedule text,command text,active boolean default true);
 create function net.http_post(url text,headers jsonb,body jsonb,timeout_milliseconds integer) returns bigint language plpgsql as $$begin insert into net.requests values(headers);return 1;end$$;
 create function cron.schedule(name text,pattern text,sql text) returns bigint language plpgsql as $$declare id bigint;begin insert into cron.job(jobname,schedule,command) values(name,pattern,sql) on conflict(jobname) do update set schedule=excluded.schedule,command=excluded.command returning jobid into id;return id;end$$;
 create function cron.alter_job(id bigint,active boolean) returns void language sql as $$update cron.job set active=$2 where jobid=$1$$;`);
 const schedulerName=(await fs.readdir('supabase/migrations')).find(name=>name.endsWith('_cloud_line_scheduler.sql'));
 const source=(await fs.readFile('supabase/migrations/'+schedulerName,'utf8')).replace(/^create extension.*$/gm,'');
 await f.db.exec(source);await f.db.exec(source);
 const jobs=(await f.db.query('select * from cron.job')).rows;
 assert.equal(jobs.length,1);assert.equal(jobs[0].active,false);assert.equal(jobs[0].command.trim(),'select nsysu_line.request_tick();');
 await f.db.query('select nsysu_line.request_tick()');
 const ticket=(await f.db.query('select * from net.requests')).rows[0].headers.Authorization;
 assert.match(ticket,/^Bearer [a-f0-9]{64}$/);
 assert.equal((await f.db.query('select token_hash from nsysu_line.cron_tickets')).rows[0].token_hash,await f.protocol.digest(ticket.slice(7)));
 await assert.rejects(f.store.transaction(tx=>tx.query('select nsysu_line.request_tick()')));
 await f.db.exec('update nsysu_line.config set enabled=false');await f.db.query('select nsysu_line.request_tick()');
 assert.equal((await f.db.query('select * from net.requests')).rows.length,1);
});

test('expired or no-longer-allowed interrupted events retire without calling LINE again',async t=>{
 const f=await fixture(t);await f.send();
 await f.store.applyEvent({id:'STALE_ENTRY',identity,stamp:new Date('2026-11-17T23:59:00+08:00').getTime(),action:'start'});
 await f.at('2026-11-18T00:11:00+08:00');
 f.line.linkToken=async()=>assert.fail('Expired event must not request a new LINE link');
 await f.gateway(await f.tickRequest());
 assert.equal((await f.records('events')).find(e=>e.event_id==='STALE_ENTRY').finished,true);
});

test('personal QR credentials return only the matching fixed diary capability without LINE binding or admin access',async t=>{
 const f=await fixture(t);
 await f.db.query('update nsysu_line.config set enabled=false,allowed_users=$1',[[]]);
 const request=member=>new Request('https://cloud.example/diary-access',{method:'POST',headers:{Origin:'https://research.example.org'},body:JSON.stringify({account:member,password})});
 const first=await f.gateway(request('ycc00000001')),last=await f.gateway(request('ycc00000050'));
 assert.equal(first.status,200);assert.equal(first.headers.get('access-control-allow-origin'),'https://research.example.org');
 const a=await first.json(),b=await last.json();
 assert.equal(a.member_id,'ycc00000001');assert.equal(b.member_id,'ycc00000050');
 const link=new URL(a.diary_url);assert.equal(link.searchParams.get('member'),a.member_id);assert.equal(link.searchParams.get('invite'),'a'.repeat(64));assert.equal(link.searchParams.has('date'),false);
 assert.notEqual(a.diary_url,b.diary_url);assert.equal((await f.gateway(request('ycc00000001'))).status,200);
 assert.equal((await f.records('bindings')).length,0);assert.equal((await f.records('outbox')).length,0);assert.equal(f.calls.length,0);
 assert.equal(a.access_token,undefined);assert.equal(a.password_hash,undefined);
});

test('personal QR rejects bad passwords, inactive/revoked enrollment and foreign origins',async t=>{
 const f=await fixture(t);
 const request=(account='ycc00000001',candidate=password,origin='https://research.example.org')=>new Request('https://cloud.example/diary-access',{method:'POST',headers:{Origin:origin},body:JSON.stringify({account,password:candidate})});
 assert.equal((await f.gateway(request('ycc00000001','wrong'))).status,401);
 for(const invalid of ['yc00000001','ycc00000000','ycc00000051','YCC00000001'])assert.equal((await f.gateway(request(invalid))).status,401);
 assert.equal((await f.gateway(request('ycc00000001',password,'https://foreign.invalid'))).status,403);
 await f.db.query("update nsysu_private.diary_invitations set revoked_at=now() where member_id='ycc00000001'");
 assert.equal((await f.gateway(request())).status,403);
 await f.db.query("update nsysu_line.accounts set active=false where member='ycc00000050'");
 assert.equal((await f.gateway(request('ycc00000050'))).status,401);
});

test('personal QR errors preserve allowed CORS and repeated password guessing is throttled',async t=>{
 const f=await fixture(t);
 const request=()=>new Request('https://cloud.example/diary-access',{method:'POST',headers:{Origin:'https://research.example.org'},body:JSON.stringify({account:'ycc00000001',password:'wrong'})});
 for(let i=0;i<5;i++){const response=await f.gateway(request());assert.equal(response.status,401);assert.equal(response.headers.get('access-control-allow-origin'),'https://research.example.org');}
 assert.equal((await f.gateway(request())).status,429);
 const preflight=await f.gateway(new Request('https://cloud.example/diary-access',{method:'OPTIONS',headers:{Origin:'https://research.example.org'}}));
 assert.equal(preflight.status,204);
});


test('friendly binding and cancellation copy keeps account context and confirmation actions',async t=>{
 const f=await fixture(t);await f.bind('ycc00000050');
 let body=f.calls.at(-1).payload.messages[0];
 assert.ok(body.template.text.startsWith('已幫你完成綁定囉～'));
 assert.ok(body.template.text.includes('研究帳號：ycc00000050'));
 await f.send('rebind');body=f.calls.at(-1).payload.messages[0];
 assert.ok(body.template.text.includes('ycc00000050'));
 assert.ok(body.template.text.includes('先取消目前的綁定'));
 await f.send('cancel');body=f.calls.at(-1).payload.messages[0];
 assert.ok(body.template.text.includes('要取消研究帳號 ycc00000050 的綁定嗎？'));
 assert.ok(body.template.text.includes('已經填好的日誌會保留'));
 assert.equal((await f.records('bindings')).length,1);
 const action=body.template.actions[0].data.slice(8);await f.send(action);
 assert.equal((await f.records('bindings')).length,0);
 assert.ok(f.calls.at(-1).payload.messages[0].template.text.startsWith('已幫你取消綁定'));
 assert.ok(f.calls.every(call=>call.payload.messages.every(message=>message.type!=='template'||message.template.text.length<=160)));
});

test('friendly credential and service errors remain distinct without creating a binding',async t=>{
 const f=await fixture(t);await f.send('start');
 const wrong=await f.prepare('ycc00000001','SYNTHETIC_WRONG_PASSWORD');
 assert.equal(wrong.status,401);assert.match((await wrong.json()).error,/這次還沒核對成功/);
 f.store.credentials=async()=>{throw Error('SYNTHETIC_UPSTREAM_UNAVAILABLE');};
 const unavailable=await f.prepare();assert.equal(unavailable.status,503);
 assert.match((await unavailable.json()).error,/目前服務暫時連不上/);
 assert.equal((await f.records('bindings')).length,0);
});
