const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

function fixture({cloudDepth=0}={}){
 const storage=new Map(),requests=[],messages=[],timers=[];
 const peer={postMessage(message,origin){requests.push({message,origin});}};
 let parent={opener:peer,postMessage(message){messages.push(message);}};
 for(let depth=0;depth<cloudDepth;depth++)parent={parent,postMessage(message){messages.push(message);}};
 let listener,storageListener,sequence=0;
 const context=vm.createContext({parent,location:{origin:'http://127.0.0.1:64666'},URL,
  crypto:{randomUUID(){return `synthetic-nonce-${++sequence}`;}},
  sessionStorage:{getItem:key=>storage.get(key)||null,setItem:(key,value)=>storage.set(key,value),removeItem:key=>storage.delete(key)},
  document:{querySelector(){return {textContent:''};}},
  addEventListener(type,callback){if(type==='message')listener=callback;if(type==='storage')storageListener=callback;},
  setInterval(){},setTimeout(callback){timers.push(callback);}});
 const html=fs.readFileSync('frontend/auth_bridge/index.html','utf8');
 vm.runInContext(html.match(/<script>([\s\S]*?)<\/script>/)[1],context);
 const session={access_token:'SYNTHETIC_ACCESS',refresh_token:'SYNTHETIC_REFRESH',user:{id:'SYNTHETIC_ADMIN'}};
 const dispatch=event=>listener(event);
 const render=()=>dispatch({source:parent,origin:'http://127.0.0.1:64666',data:{type:'streamlit:render',args:{diary_url:'http://127.0.0.1:64665/',operation:'read',session:null}}});
 const reply=(overrides={})=>dispatch({source:peer,origin:'http://127.0.0.1:64665',data:{type:'nsysu:session',nonce:requests.at(-1).message.nonce,session},...overrides});
 const values=()=>messages.filter(message=>message.type==='streamlit:setComponentValue');
 const externalStorage=value=>{if(value)storage.set('vtca-session',JSON.stringify(value));else storage.delete('vtca-session');storageListener({key:'vtca-session',storageArea:context.sessionStorage});};
 return {render,reply,timers,values,storage,externalStorage};
}

test('completed management handoff is not emitted again by the fallback timer',()=>{
 const bridge=fixture();
 bridge.render();bridge.reply();
 assert.equal(bridge.values().length,1);
 assert.equal(bridge.values()[0].value.session.access_token,'SYNTHETIC_ACCESS');
 bridge.timers[0]();
 assert.equal(bridge.values().length,1);
});

test('unanswered handoff falls back once and rejects its late response',()=>{
 const bridge=fixture();
 bridge.render();bridge.timers[0]();
 assert.equal(bridge.values().length,1);
 assert.equal(bridge.values()[0].value.session,null);
 bridge.reply();
 assert.equal(bridge.values().length,1);
 assert.equal(bridge.storage.size,0);
});

test('handoff ignores responses from a different origin or window',()=>{
 const bridge=fixture();
 bridge.render();
 bridge.reply({origin:'https://untrusted.invalid'});
 bridge.reply({source:{}});
 assert.equal(bridge.values().length,0);
 bridge.reply();
 assert.equal(bridge.values().length,1);
});

test('return component rotation and explicit logout update the Python research session',()=>{
 const bridge=fixture();bridge.render();bridge.reply();
 bridge.externalStorage({access_token:'SYNTHETIC_ROTATED',refresh_token:'SYNTHETIC_REFRESH'});
 assert.equal(bridge.values().at(-1).value.session.access_token,'SYNTHETIC_ROTATED');
 assert(bridge.values().at(-1).value.session_updated);
 bridge.externalStorage(null);
 assert.equal(bridge.values().at(-1).value.session,null);assert(bridge.values().at(-1).value.logged_out);
});

test('research bridge finds the original diary opener through the hosted cloud wrapper',()=>{
 const bridge=fixture({cloudDepth:2});bridge.render();bridge.reply();
 assert.equal(bridge.values().length,1);assert.equal(bridge.values()[0].value.session.access_token,'SYNTHETIC_ACCESS');
});
