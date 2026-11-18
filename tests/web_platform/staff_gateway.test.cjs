const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs/promises');
const {randomUUID}=require('node:crypto');
const modules=Promise.all([import('@electric-sql/pglite'),import('../../supabase/functions/nsysu-staff-auth/gateway.mjs'),import('../../supabase/functions/nsysu-staff-auth/store.mjs')]);
const origin='https://nsysu-eye-mask-sleep-monitor.streamlit.app';
const actor='11111111-1111-4111-8111-111111111111',sid='22222222-2222-4222-8222-222222222222';
const jwt=(sub=actor,session=sid)=>'synthetic.'+Buffer.from(JSON.stringify({sub,session_id:session,role:'authenticated',exp:Math.floor(Date.now()/1000)+3600})).toString('base64url')+'.SYNTHETIC_SIGNATURE';
async function fixture(t){
 const [{PGlite},gateway,{StaffStore}]=await modules;
 const db=new PGlite();t.after(()=>db.close());
 await db.exec(`create role anon;create role authenticated;create schema auth;create schema nsysu_private;
 create table auth.users(id uuid primary key,email text,raw_app_meta_data jsonb,raw_user_meta_data jsonb default '{}',deleted_at timestamptz,banned_until timestamptz);
 create table auth.sessions(id uuid primary key,user_id uuid,not_after timestamptz);
 create function auth.jwt() returns jsonb language sql stable as $$select coalesce(nullif(current_setting('request.jwt.claims',true),''),'{}')::jsonb$$;
 create function auth.uid() returns uuid language sql stable as $$select nullif(auth.jwt()->>'sub','')::uuid$$;`);
 const migration=(await fs.readdir('supabase/migrations')).find(name=>name.endsWith('_unified_docter_staff_auth.sql'));
 await db.exec(await fs.readFile('supabase/migrations/'+migration,'utf8'));
 const activation=(await fs.readdir('supabase/migrations')).find(name=>name.endsWith('_complete_staff_auth_activation.sql'));
 await db.exec(await fs.readFile('supabase/migrations/'+activation,'utf8'));
 await db.query("insert into auth.users(id,email,raw_app_meta_data) values($1,'nsysu_test@diary.nsysu.invalid',$2)",[actor,JSON.stringify({diary_staff:true,participant_admin:true,diary_username:'NSYSU_TEST'})]);
 await db.query('insert into auth.sessions values($1,$2,null)',[sid,actor]);
 const store=new StaffStore({transaction:work=>db.transaction(work)}),calls=[];
 const auth={session:async identity=>{calls.push('internal-session');return {access_token:jwt(),refresh_token:'SYNTHETIC_REFRESH',user:{id:identity.id,app_metadata:{diary_staff:true}}};},
  user:async()=>({id:actor,app_metadata:{diary_staff:true}})};
 const docter={login:async(account,password)=>{calls.push({account,password});return {access_token:'SYNTHETIC_DOCTER_TOKEN',expires_in:3600};}};
 const cipher=gateway.tokenCipher(Buffer.alloc(32,7).toString('base64'));
 const app=gateway.createStaffGateway({store,auth,docter,cipher,allowedOrigin:origin});
 const login=(account='nsysu_test',password='SYNTHETIC_Pass')=>app(new Request('https://cloud.example/login',{method:'POST',headers:{Origin:origin},body:JSON.stringify({account,password})}));
 const session=(token=jwt())=>app(new Request('https://cloud.example/session',{method:'POST',headers:{Authorization:'Bearer '+token},body:'{}'}));
 return {db,store,app,auth,docter,cipher,calls,login,session,gateway};
}

test('Docter researcher is the sole password verifier and only an internal session reaches the browser',async t=>{
 const f=await fixture(t),response=await f.login(' nSySu_TeSt ','SYNTHETIC_CaSe');
 assert.equal(response.status,200);assert.equal(response.headers.get('access-control-allow-origin'),origin);
 const body=await response.json();assert.equal(body.access_token,jwt());assert.equal(typeof body.expires_at,'number');
 assert.deepEqual(f.calls,[{account:'NSYSU_TEST',password:'SYNTHETIC_CaSe'},'internal-session']);
 assert(!JSON.stringify(body).includes('SYNTHETIC_DOCTER_TOKEN'));
 const saved=(await f.db.query('select * from nsysu_staff.sessions')).rows[0];
 assert.equal((await f.db.query('select require_docter from nsysu_staff.config')).rows[0].require_docter,true);
 assert(!saved.token_cipher.includes('SYNTHETIC_DOCTER_TOKEN'));assert(!JSON.stringify(saved).includes('SYNTHETIC_CaSe'));
 const recovered=await f.session();assert.equal(recovered.status,200);assert.equal((await recovered.json()).access_token,'SYNTHETIC_DOCTER_TOKEN');
});

test('unregistered and disabled accounts cannot acquire project privileges',async t=>{
 const f=await fixture(t);
 assert.equal((await f.login('unregistered')).status,401);assert.equal(f.calls.length,0);
 await f.db.query("update auth.users set raw_app_meta_data='{}',raw_user_meta_data=$1",[JSON.stringify({diary_staff:true})]);
 assert.equal((await f.login()).status,401);assert.equal(f.calls.length,0);
});

test('failed Docter verification never creates an internal auth session or stores a token',async t=>{
 const f=await fixture(t);f.docter.login=async()=>{throw new f.gateway.StaffError('Invalid',401);};
 assert.equal((await f.login()).status,401);assert(!f.calls.includes('internal-session'));
 assert.equal((await f.db.query('select count(*)::int n from nsysu_staff.sessions')).rows[0].n,0);
});

test('mismatched internal identity and invalid sessions fail closed',async t=>{
 const f=await fixture(t);f.auth.session=async()=>({access_token:jwt(randomUUID()),refresh_token:'SYNTHETIC',user:{id:actor}});
 assert.equal((await f.login()).status,403);
 assert.equal((await f.db.query('select count(*)::int n from nsysu_staff.sessions')).rows[0].n,0);
 assert.equal((await f.session('not-a-valid-jwt')).status,401);
});

test('private schema and auth tables are not readable by browser or backend roles',async t=>{
 const f=await fixture(t);
 const result=(await f.db.query("select has_schema_privilege('authenticated','nsysu_staff','usage') browser,has_table_privilege('nsysu_staff_api','auth.users','select') users,has_function_privilege('anon','nsysu_staff.identity(text)','execute') lookup")).rows[0];
 assert.deepEqual(result,{browser:false,users:false,lookup:false});
});

test('Docter-backed RLS can reject legacy sessions and respects revocation',async t=>{
 const f=await fixture(t);
 await f.db.query('update nsysu_staff.config set require_docter=true');
 await f.db.query("select set_config('request.jwt.claims',$1,false)",[JSON.stringify({sub:actor,session_id:sid})]);
 const allowed=async()=> (await f.db.query('select nsysu_private.is_diary_staff() allowed')).rows[0].allowed;
 assert.equal(await allowed(),false);assert.equal((await f.login()).status,200);assert.equal(await allowed(),true);
 await f.db.query('delete from auth.sessions where id=$1',[sid]);
 assert.equal(await allowed(),false);assert.equal((await f.session()).status,401);
 assert.equal((await f.db.query('select count(*)::int n from nsysu_staff.sessions')).rows[0].n,0);
});

test('another authenticated user or tampered encrypted token cannot recover a Docter token',async t=>{
 const f=await fixture(t);await f.login();
 f.auth.user=async()=>({id:randomUUID(),app_metadata:{diary_staff:true}});
 assert.equal((await f.session()).status,403);
 f.auth.user=async()=>({id:actor,app_metadata:{diary_staff:true}});
 const bad=await f.cipher.seal('SYNTHETIC_OTHER',actor+':'+randomUUID());
 await f.db.query('update nsysu_staff.sessions set token_cipher=$1',[bad]);
 const result=await f.session();assert.equal(result.status,503);assert(!JSON.stringify(await result.json()).includes('SYNTHETIC_OTHER'));
});

test('provider expiry and current project-role revocation stop recovery',async t=>{
 const f=await fixture(t);await f.login();
 await f.db.query("update nsysu_staff.sessions set provider_expires=now()-interval '1 second'");
 assert.equal((await f.session()).status,401);
 await f.db.query('update nsysu_staff.sessions set provider_expires=null');
 await f.db.query('update auth.users set banned_until=now()+interval \'1 day\'');
 assert.equal((await f.session()).status,401);
});

test('login attempt limits survive gateway/store reconstruction',async t=>{
 const f=await fixture(t);
 for(let i=0;i<5;i++)assert.equal((await f.login('unregistered')).status,401);
 assert.equal((await f.login('unregistered')).status,429);
 const another=new f.store.constructor(f.store.database);
 await assert.rejects(async()=>another.limit(await f.gateway.hash('unregistered')),/15/);
});

test('foreign origins, malformed requests and unknown routes do not invoke credentials',async t=>{
 const f=await fixture(t);
 assert.equal((await f.app(new Request('https://cloud.example/login',{method:'POST',headers:{Origin:'https://foreign.invalid'},body:'{}'}))).status,403);
 const preflight=await f.app(new Request('https://cloud.example/login',{method:'OPTIONS',headers:{Origin:origin}}));
 assert.equal(preflight.status,204);assert.equal(preflight.headers.get('access-control-allow-origin'),origin);
 assert.equal((await f.app(new Request('https://cloud.example/login',{method:'POST',body:'['}))).status,400);
 assert.equal((await f.app(new Request('https://cloud.example/unknown',{method:'POST',body:'{}'}))).status,404);
 assert.equal(f.calls.length,0);
});

test('provider transport pins the documented researcher endpoint and sends no database keys',async()=>{
 const [{},api]=await modules,calls=[];
 const provider=new api.DocterIdentity(async(url,options)=>{calls.push({url,options});return new Response(JSON.stringify({success:true,data:{access_token:'SYNTHETIC_DOCTER'}}));});
 await provider.login('NSYSU_TEST','SYNTHETIC_CaSe');
 assert.equal(calls[0].url,'https://icare.docter.pro/back-end/app/login/researcher');
 assert.equal(new URLSearchParams(calls[0].options.body).get('password'),'SYNTHETIC_CaSe');
 assert.equal(calls[0].options.headers.apikey,undefined);assert.equal(calls[0].options.headers.Authorization,undefined);assert.equal(calls[0].options.redirect,'error');
});

test('internal broker uses generated one-time proof without sending an email or rechecking a website password',async()=>{
 const [,api]=await modules,calls=[];
 const broker=new api.AuthBroker('https://project.supabase.co','SYNTHETIC_SERVER_KEY',async(url,options)=>{
  calls.push({url,options});
  return new Response(JSON.stringify(url.endsWith('admin/generate_link')?{hashed_token:'SYNTHETIC_PROOF'}:{access_token:jwt(),refresh_token:'SYNTHETIC_REFRESH',user:{id:actor,app_metadata:{diary_staff:true}}}));
 });
 await broker.session({id:actor,email:'synthetic@diary.nsysu.invalid'});
 assert.equal(calls.length,2);assert(calls[0].url.endsWith('/admin/generate_link'));assert(calls[1].url.endsWith('/verify'));
 assert.deepEqual(JSON.parse(calls[1].options.body),{type:'magiclink',token_hash:'SYNTHETIC_PROOF'});
 assert(!JSON.stringify(calls).includes('grant_type=password'));assert(!calls.some(call=>call.url.endsWith('/otp')));
});

test('rollback preserves existing auth identities, sessions and research diary rows',async t=>{
 const f=await fixture(t);await f.login();
 await f.db.exec("create table public.keep_diary(id int);insert into public.keep_diary values(1)");
 await f.db.exec(await fs.readFile('docs/rollback_unified_docter_staff_auth.sql','utf8'));
 assert.equal((await f.db.query('select count(*)::int n from auth.users')).rows[0].n,1);
 assert.equal((await f.db.query('select count(*)::int n from auth.sessions')).rows[0].n,1);
 assert.equal((await f.db.query('select count(*)::int n from public.keep_diary')).rows[0].n,1);
});
