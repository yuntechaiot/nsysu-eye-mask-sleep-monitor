const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');

function fixture(){
 const nodes=new Map(),opened=[];
 const node=id=>{if(!nodes.has(id))nodes.set(id,{value:'',textContent:'',hidden:false,innerHTML:'',replaceChildren(){},removeAttribute(){},classList:{add(name){opened.push([id,name]);},remove(){},contains(){return false;}}});return nodes.get(id);};
 let resolve;
 const pending=new Promise(done=>resolve=done);
 const context=vm.createContext({sessionStorage:{getItem(){return null;},setItem(){},removeItem(){}},document:{getElementById:node},
  VTCA:{esc:String},Map,console,pending,invitationCache:new Map(),fixedInvitationLoads:new Map(),directoryLoaded:false,
  clearParticipantNames(){},clearHistoryDirectory(){},closeManagementDialog(){}});
 const code=fs.readFileSync('frontend/web/diary.js','utf8').replace(/\ninit\(\);\s*$/,'');
 vm.runInContext(code,context);
 vm.runInContext("session={user:{id:'SYNTHETIC_ADMIN'}};allRows=()=>pending;updateAccount=()=>{};cancelEdit=()=>{};",context);
 return {context,resolve,opened};
}

test('export response arriving after actual local logout cannot restore private data or reopen dialog',async()=>{
 const {context,resolve,opened}=fixture();
 const loading=vm.runInContext('openExport()',context);
 await vm.runInContext('signOut(true)',context);
 resolve([{name:'SYNTHETIC_PRIVATE_RECORD'}]);await loading;
 assert.equal(vm.runInContext('exportData.length',context),0);
 assert.equal(opened.some(([id])=>id==='export-modal'),false);
 vm.runInContext('downloadCSV()',context); // no session => no download creation
});

test('authorized completed export still opens with its records',async()=>{
 const {context,resolve,opened}=fixture();
 const loading=vm.runInContext('openExport()',context);
 resolve([{name:'SYNTHETIC_PRIVATE_RECORD'}]);await loading;
 assert.equal(vm.runInContext('exportData.length',context),1);
 assert.equal(opened.some(([id])=>id==='export-modal'),true);
});
