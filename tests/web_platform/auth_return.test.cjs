const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

const homeOrigin='http://127.0.0.1:64660',researchOrigin='http://127.0.0.1:64661';
const credentials=(suffix='NEW')=>({access_token:'SYNTHETIC_ACCESS_'+suffix,refresh_token:'SYNTHETIC_REFRESH_'+suffix,
 expires_at:Date.now()/1000+3600,user:{id:'SYNTHETIC_ADMIN',app_metadata:{diary_staff:true}}});
function events(){const listeners=new Map();return {
 addEventListener(type,fn){if(!listeners.has(type))listeners.set(type,new Set());listeners.get(type).add(fn);},
 removeEventListener(type,fn){listeners.get(type)?.delete(fn);},
 dispatch(type,event){for(const fn of [...listeners.get(type)||[]])fn(event);}
};}
function storage(){const values=new Map();return {values,getItem:key=>values.get(key)||null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)};}
function fixture({embedded=false,defer=false,empty=false}={}){
 const homeEvents=events(),researchEvents=events(),homeStorage=storage(),researchStorage=storage();
 const nodes=new Map(),timers=[],requests=[],responses=[],streamlit=[];
 const node=id=>{if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',hidden:false,href:'',addEventListener(type,fn){this[type]=fn;},replaceChildren(){},removeAttribute(){},classList:{add(){},remove(){},contains(){return false;}}});return nodes.get(id);};
 const researchRoot={},homeRoot={},homeSource=embedded?{parent:homeRoot}:homeRoot;
 const peer={parent:researchRoot,postMessage(message,origin){requests.push({message,origin});if(!defer)queueMicrotask(()=>researchEvents.dispatch('message',{source:homeSource,origin:homeOrigin,data:message}));}};
 homeSource.postMessage=(message,origin)=>{responses.push({message,origin});queueMicrotask(()=>homeEvents.dispatch('message',{source:peer,origin:researchOrigin,data:message}));};
 const researchParent={postMessage(message){streamlit.push(message);}};
 const researchContext=vm.createContext({parent:researchParent,location:{origin:researchOrigin},URL,Set,sessionStorage:researchStorage,
  document:{getElementById:node},window:{open(url){node('opened-url').value=url;return homeRoot;}},...researchEvents});
 const html=fs.readFileSync('frontend/auth_return/index.html','utf8');
 vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],researchContext);
 researchEvents.dispatch('message',{source:researchParent,origin:researchOrigin,data:{type:'streamlit:render',args:{diary_url:homeOrigin+'/'}}});
 if(!empty)researchStorage.setItem('vtca-session',JSON.stringify(credentials()));
 const context=vm.createContext({URL,URLSearchParams,Set,Map,Date,console,sessionStorage:homeStorage,document:{getElementById:node},
  location:{origin:homeOrigin,href:homeOrigin+'/?auth_return=1',search:'?auth_return=1'},
  crypto:{randomUUID:()=> 'synthetic-return-nonce'},...homeEvents,setTimeout(fn){timers.push(fn);return timers.length;},clearTimeout(){},
  fetch:async()=>({ok:true,json:async()=>credentials('REFRESHED')}),VTCA:{esc:String},invitationCache:new Map(),fixedInvitationLoads:new Map(),directoryLoaded:false,
  clearParticipantNames(){},clearHistoryDirectory(){},closeManagementDialog(){}});
 context.window=context;context.parent=embedded?{opener:peer}:context;context.opener=embedded?null:peer;
 vm.runInContext(fs.readFileSync('frontend/web/diary.js','utf8').replace(/\ninit\(\);\s*$/,''),context);
 vm.runInContext(fs.readFileSync('frontend/web/workspace.js','utf8'),context);
 vm.runInContext(`config={dashboard_url:'${researchOrigin}/',supabase_url:'${homeOrigin}/acceptance/supabase',publishable_key:'sb_publishable_SYNTHETIC'};updateAccount=()=>{};cancelEdit=()=>{};`,context);
 const click=()=>node('home').click({preventDefault(){}});
 const restore=()=>vm.runInContext('restoreResearchSession()',context);
 const session=()=>vm.runInContext('session',context);
 return {click,restore,session,context,homeEvents,researchEvents,homeStorage,researchStorage,peer,homeSource,researchParent,node,timers,requests,responses,streamlit};
}

test('return link transfers the current login into an empty new diary tab without URL credentials',async()=>{
 const f=fixture();f.click();await f.restore();
 assert.equal(f.session().access_token,credentials().access_token);
 assert.equal(JSON.parse(f.homeStorage.getItem('vtca-session')).refresh_token,credentials().refresh_token);
 const url=new URL(f.node('opened-url').value);
 assert.equal(url.origin,homeOrigin);assert.equal(url.search,'?auth_return=1');
 assert(!url.href.includes('SYNTHETIC'));assert.equal(f.requests[0].origin,researchOrigin);
});

test('cloud embedded diary obtains the latest rotated session rather than a stale copied tab session',async()=>{
 const f=fixture({embedded:true});
 vm.runInContext(`session=${JSON.stringify(credentials('OLD'))}`,f.context);
 f.click();await f.restore();
 assert.equal(f.session().access_token,credentials().access_token);
});

test('return page reload reconnects the trusted research peer after the URL marker has been removed',async()=>{
 const f=fixture();f.click();await f.restore();
 assert.equal(f.homeStorage.getItem('nsysu-research-return-origin'),researchOrigin);
 vm.runInContext("location.search='?view=workspace';dashboardPeers.clear();dashboardFrames.clear();",f.context);
 await f.restore();
 assert.equal(f.requests.length,2);
 assert.equal(vm.runInContext('dashboardFrames.size',f.context),1);
 await vm.runInContext('session.expires_at=0;authHeaders()',f.context);
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(JSON.parse(f.researchStorage.getItem('vtca-session')).access_token,credentials('REFRESHED').access_token);
 await vm.runInContext('signOut()',f.context);
 assert.equal(f.homeStorage.getItem('nsysu-research-return-origin'),null);
});

test('return component never discloses a session to an unrecognized window or foreign origin',async()=>{
 const f=fixture();const data={type:'nsysu:return-session-request',nonce:'test'};
 f.researchEvents.dispatch('message',{source:f.homeSource,origin:homeOrigin,data});
 assert.equal(f.responses.length,0); // no user clicked the return link
 f.click();
 f.researchEvents.dispatch('message',{source:{postMessage(){throw Error('leak');}},origin:homeOrigin,data});
 f.researchEvents.dispatch('message',{source:f.homeSource,origin:'https://foreign.invalid',data});
 assert.equal(f.responses.length,0);
 await f.restore();assert.equal(f.responses.length,1);
});

test('diary ignores wrong source/origin/nonce and a late return response after timeout',async()=>{
 const f=fixture({defer:true});f.click();const pending=f.restore();
 const data={type:'nsysu:return-session',nonce:f.requests[0].message.nonce,session:credentials()};
 f.homeEvents.dispatch('message',{source:{},origin:researchOrigin,data});
 f.homeEvents.dispatch('message',{source:f.peer,origin:'https://foreign.invalid',data});
 f.homeEvents.dispatch('message',{source:f.peer,origin:researchOrigin,data:{...data,nonce:'wrong'}});
 assert.equal(f.session(),null);f.timers[0]();await pending;
 f.homeEvents.dispatch('message',{source:f.peer,origin:researchOrigin,data});
 assert.equal(f.session(),null);assert.equal(f.homeStorage.values.size,0);
});

test('a logged-out research page cannot recover a stale copied diary session',async()=>{
 const f=fixture({empty:true});f.click();
 vm.runInContext(`session=${JSON.stringify(credentials('OLD'))}`,f.context);
 await f.restore();assert.equal(f.session(),null);assert.equal(f.homeStorage.values.size,0);
});

test('explicit diary logout clears the research browser session and delayed updates do not restore login',async()=>{
 const f=fixture();f.click();await f.restore();
 await vm.runInContext('signOut()',f.context);await new Promise(resolve=>setImmediate(resolve));
 assert.equal(f.session(),null);assert.equal(f.researchStorage.getItem('vtca-session'),null);
 f.homeEvents.dispatch('message',{source:f.peer,origin:researchOrigin,data:{type:'nsysu:session-update',session:credentials()}});
 assert.equal(f.session(),null);
});

test('automatic access-token refresh synchronizes the returned diary session with research',async()=>{
 const f=fixture();f.click();await f.restore();
 await vm.runInContext('session.expires_at=0;authHeaders()',f.context);
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(f.session().access_token,credentials('REFRESHED').access_token);
 assert.equal(JSON.parse(f.researchStorage.getItem('vtca-session')).access_token,credentials('REFRESHED').access_token);
});

test('research session rotation/logout in another component reaches the returned diary',async()=>{
 const f=fixture();f.click();await f.restore();
 f.researchStorage.setItem('vtca-session',JSON.stringify(credentials('ROTATED')));
 f.researchEvents.dispatch('storage',{key:'vtca-session',storageArea:f.researchStorage});
 await new Promise(resolve=>setImmediate(resolve));
 assert.equal(f.session().access_token,credentials('ROTATED').access_token);
 f.researchStorage.removeItem('vtca-session');
 f.researchEvents.dispatch('storage',{key:'vtca-session',storageArea:f.researchStorage});
 await new Promise(resolve=>setImmediate(resolve));assert.equal(f.session(),null);
});
