const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

function fixture(){
 const message={textContent:''},status={hidden:true,querySelector:()=>message};
 const calls=[],pending=[],timers=new Map();let nextTimer=0,placed=0;
 const control={isConnected:true,matches:()=>true,getClientRects:()=>[{}],closest:()=>null,insertAdjacentElement:()=>placed++};
 const root={document:{getElementById:()=>status,activeElement:control,addEventListener(){}},
  setTimeout(callback){timers.set(++nextTimer,callback);return nextTimer;},clearTimeout(id){timers.delete(id);},
  fetch(...args){calls.push(args);return new Promise((resolve,reject)=>pending.push({resolve,reject}));}};
 vm.runInNewContext(fs.readFileSync('frontend/web/request-status.js','utf8'),{window:root});
 return {root,status,message,pending,calls,timers,placed:()=>placed};
}

test('request feedback appears immediately, preserves the response and clears only after all concurrent requests',async()=>{
 const f=fixture(),options={method:'POST',body:'SYNTHETIC_BODY'};
 const first=f.root.fetch('/api/first',options),second=f.root.fetch('/api/second');
 assert.equal(f.status.hidden,false);assert.match(f.message.textContent,/正在處理，請稍候/);assert.equal(f.placed(),1);
 assert.equal(f.calls[0][1],options);
 const response={status:200};f.pending[0].resolve(response);assert.equal(await first,response);
 assert.equal(f.status.hidden,false);
 f.pending[1].resolve({status:503});assert.equal((await second).status,503);
 assert.equal(f.status.hidden,true);assert.equal(f.timers.size,0);
});

test('slow request explains the delay without retrying; rejection keeps the error and releases the wait state',async()=>{
 const f=fixture(),loading=f.root.fetch('/api/slow');
 f.timers.values().next().value();assert.match(f.message.textContent,/連線較慢/);assert.equal(f.calls.length,1);
 const error=Error('SYNTHETIC_OFFLINE');f.pending[0].reject(error);
 await assert.rejects(loading,caught=>caught===error);
 assert.equal(f.status.hidden,true);assert.equal(f.timers.size,0);
 const next=f.root.fetch('/api/again');assert.match(f.message.textContent,/正在處理/);
 f.pending[1].resolve({status:200});await next;
 assert.equal(f.status.hidden,true);
});
