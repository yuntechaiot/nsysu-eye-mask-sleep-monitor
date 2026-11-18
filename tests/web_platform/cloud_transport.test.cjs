const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const code=fs.readFileSync(require.resolve('../../frontend/web/cloud-transport.js'),'utf8');
function browser(handler,extra={}){
 const calls=[];
 const window={NSYSU_EMBED:{config:{supabase_url:'https://project.supabase.co',publishable_key:'sb_publishable_TEST',...extra}},fetch:async(url,options)=>{calls.push({url,options});return handler(url,options);}};
 vm.runInNewContext(code,{window,Response,Headers,Map,JSON,Error,URL});
 return {window,calls};
}
const ok=data=>new Response(JSON.stringify(data),{status:200});
test('cloud homepage exposes only public configuration without HTTP localhost',async()=>{
 const {window,calls}=browser(()=>assert.fail('no network expected'));
 const result=await window.fetch('/api/config');assert.equal((await result.json()).publishable_key,'sb_publishable_TEST');assert.equal(calls.length,0);
});
test('anonymous directory never requests private participant names',async()=>{
 const {window,calls}=browser(url=>{assert(url.includes('/participant_invites?'));return ok([{member_id:'ycc00000051'}]);});
 const data=await(await window.fetch('/api/participants')).json();
 assert.deepEqual(data,{participants:[{member_id:'ycc00000051',display_name:null}],can_manage:false});
 assert.equal(calls.length,1);
});
test('verified caller JWT is used for RLS queries and names',async()=>{
 const {window,calls}=browser((url,options)=>{
  assert.equal(options.headers.Authorization,'Bearer VERIFIED');
  if(url.endsWith('/auth/v1/user'))return ok({app_metadata:{participant_admin:true}});
  return ok(url.includes('/participant_invites?')?[{member_id:'ycc00000051'}]:[{member_id:'ycc00000051',display_name:'SYNTHETIC'}]);
 });
 const data=await(await window.fetch('/api/participants',{headers:{Authorization:'Bearer VERIFIED'}})).json();
 assert.equal(data.can_manage,true);assert.equal(data.participants[0].display_name,'SYNTHETIC');assert.equal(calls.length,3);
});
test('user_metadata cannot grant administrator permission',async()=>{
 const {window,calls}=browser(url=>{assert(url.endsWith('/auth/v1/user'));return ok({app_metadata:{},user_metadata:{participant_admin:true}});});
 const result=await window.fetch('/api/participants',{method:'POST',headers:{Authorization:'Bearer VERIFIED'},body:JSON.stringify({member_id:'ycc00000051'})});
 assert.equal(result.status,403);assert.equal(calls.length,1);
});
test('administrator registration uses existing caller-authorized RPC',async()=>{
 const {window,calls}=browser((url,options)=>{
  if(url.endsWith('/auth/v1/user'))return ok({app_metadata:{participant_admin:true}});
  assert(url.endsWith('/rest/v1/rpc/register_participant'));assert.equal(options.headers.Authorization,'Bearer VERIFIED');
  assert.deepEqual(JSON.parse(options.body),{p_member_id:'ycc00000051',p_display_name:'SYNTHETIC'});return ok({member_id:'ycc00000051'});
 });
 const result=await window.fetch('/api/participants',{method:'POST',headers:{Authorization:'Bearer VERIFIED'},body:JSON.stringify({member_id:'YCC00000051',display_name:'SYNTHETIC'})});
 assert.equal(result.status,201);assert.equal(calls.length,2);
});
test('expired identity does not query participant data',async()=>{
 const {window,calls}=browser(()=>new Response('{}',{status:401}));
 assert.equal((await window.fetch('/api/participants',{headers:{Authorization:'Bearer EXPIRED'}})).status,401);
 assert.equal(calls.length,1);
});

test('management password is submitted only to the pinned cloud identity broker',async()=>{
 const {window,calls}=browser(()=>ok({access_token:'SYNTHETIC'}),{staff_auth_url:'https://project.supabase.co/functions/v1/nsysu-staff-auth'});
 const body=JSON.stringify({account:'SYNTHETIC_ADMIN',password:'SYNTHETIC_Pass'});
 assert.equal((await window.fetch('/api/staff/login',{method:'POST',body})).status,200);
 assert.equal(calls[0].url,'https://project.supabase.co/functions/v1/nsysu-staff-auth/login');
 assert.equal(calls[0].options.body,body);assert.equal(calls[0].options.redirect,'error');
 const wrong=browser(()=>assert.fail('Password must not leave the project'),{staff_auth_url:'https://foreign.invalid'});
 assert.equal((await wrong.window.fetch('/api/staff/login',{body})).status,503);
});

test('personal diary credentials use the dedicated project endpoint without an admin JWT',async()=>{
 const {window,calls}=browser(()=>ok({status:'verified_research_account'}),{participant_entry_url:'https://project.supabase.co/functions/v1/nsysu-line/diary-access'});
 const body=JSON.stringify({account:'ycc00000001',password:'SYNTHETIC_Pass'});
 assert.equal((await window.fetch('/api/participant/diary-access',{method:'POST',body})).status,200);
 assert.equal(calls[0].url,'https://project.supabase.co/functions/v1/nsysu-line/diary-access');
 assert.equal(calls[0].options.headers.Authorization,undefined);
});
