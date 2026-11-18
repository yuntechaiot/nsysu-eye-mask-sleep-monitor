const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
function fixture({delayed=false,member='ycc00000001',origin='https://research.example.org'}={}){
 const nodes=new Map(),calls=[],codes=[];let resolve;
 const node=id=>{if(!nodes.has(id))nodes.set(id,{value:'',open:false,hidden:true,textContent:'',href:'',disabled:false,focus(){},select(){},showModal(){this.open=true;},close(){this.open=false;},replaceChildren(){},removeAttribute(key){delete this[key];}});return nodes.get(id);};
 const link=origin+'/?member='+member+'&invite='+'a'.repeat(64);
 const pending=new Promise(done=>resolve=done);
 const context=vm.createContext({URL,config:{diary_url:'https://research.example.org/'},location:{href:'https://research.example.org/'},session:null,
  el:node,val:id=>node(id).value,ensureQRCode:async()=>{},QRCode:Object.assign(function(element,options){codes.push(options.text);},{CorrectLevel:{M:1}}),
  fetch:async(url,options)=>{calls.push({url,options});if(delayed)await pending;return {ok:true,json:async()=>({status:'verified_research_account',member_id:member,diary_url:link})};}});
 vm.runInContext(fs.readFileSync('frontend/web/participant-entry.js','utf8'),context);
 const open=()=>vm.runInContext('openParticipantQR()',context);
 const submit=()=>{node('self-qr-account').value='ycc00000001';node('self-qr-password').value='SYNTHETIC_ONLY';return vm.runInContext('submitParticipantQR({preventDefault(){}})',context);};
 return {context,node,calls,codes,open,submit,resolve};
}
test('subject entry needs no admin session and displays only its corresponding QR and fixed link',async()=>{
 const f=fixture();f.open();await f.submit();
 assert.equal(f.calls[0].url,'/api/participant/diary-access');assert.equal(JSON.parse(f.calls[0].options.body).account,'ycc00000001');
 assert.equal(f.node('self-qr-result').hidden,false);assert.equal(f.node('self-qr-form').hidden,true);
 assert.equal(f.codes.length,1);assert.equal(f.codes[0],f.node('self-qr-link').value);
 assert.equal(f.node('self-qr-password').value,'');assert.equal(f.context.session,null);
 vm.runInContext('closeParticipantQR()',f.context);
 assert.equal(f.node('self-qr-link').value,'');assert.equal(f.node('self-qr-open').href,undefined);
});
test('a response cannot display another account or an external destination',async()=>{
 for(const options of [{member:'ycc00000050'},{origin:'https://foreign.invalid'}]){
  const f=fixture(options);f.open();await f.submit();assert.equal(f.codes.length,0);assert.equal(f.node('self-qr-result').hidden,true);
 }
});
test('closing the subject dialog discards a late response and does not restore its link',async()=>{
 const f=fixture({delayed:true});f.open();const pending=f.submit();
 assert.equal(f.node('self-qr-password').value,'');vm.runInContext('closeParticipantQR()',f.context);
 f.resolve();await pending;assert.equal(f.codes.length,0);assert.equal(f.node('self-qr-link').value,'');
});
test('a late response from the previous attempt cannot erase a newly entered password',async()=>{
 const f=fixture({delayed:true});f.open();const pending=f.submit();f.open();f.node('self-qr-password').value='SYNTHETIC_NEW_INPUT';
 f.resolve();await pending;assert.equal(f.node('self-qr-password').value,'SYNTHETIC_NEW_INPUT');assert.equal(f.codes.length,0);
});
