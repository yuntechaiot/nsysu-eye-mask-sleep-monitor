import {FlowError,buttons,cancelAction,digest,normalizeEvent,randomToken,validAccount,verifyPassword,verifySignature} from './protocol.mjs';

const response=(value,status=200)=>new Response(JSON.stringify(value),{status,headers:{'Content-Type':'application/json','Cache-Control':'no-store','X-Content-Type-Options':'nosniff'}});
async function parallel(items,work,width=4){
 let next=0;
 await Promise.all(Array.from({length:Math.min(width,items.length)},async()=>{while(next<items.length){const item=items[next++];await work(item);}}));
}
export class LineTransport {
 constructor(token,request=fetch){this.token=token;this.request=request;}
 async call(path,payload,headers={}){
  return this.request('https://api.line.me/v2/bot/'+path,{method:'POST',headers:{Authorization:'Bearer '+this.token,'Content-Type':'application/json',...headers},body:JSON.stringify(payload),signal:AbortSignal.timeout(10000),redirect:'error'});
 }
 async linkToken(identity){
  const result=await this.call('user/'+encodeURIComponent(identity)+'/linkToken',{});
  if(!result.ok)throw new Error('LINE link unavailable');
  const data=await result.json();
  if(typeof data.linkToken!=='string'||!data.linkToken||data.linkToken.length>1000)throw new Error('Invalid LINE link');
  return data.linkToken;
 }
 async push(payload,retry){
  try{
   const result=await this.call('message/push',payload,{'X-Line-Retry-Key':retry});
   const accepted=result.headers.get('x-line-accepted-request-id');
   if(result.ok||result.status===409&&accepted)return {status:'accepted',requestId:accepted||result.headers.get('x-line-request-id')};
   if(result.status>=500)return {status:'retry',error:'upstream_5xx'};
   return {status:'failed',error:result.status===429?'rate_or_quota':'http_'+result.status};
  }catch{return {status:'uncertain',error:'network'};}
 }
}

export function createGateway({store,line,secret,bindingURL,waitUntil=promise=>promise.catch(()=>{})}){
 async function finish(record){
  const result=record.result;
  let body=result.message,token;
  if(result.kind==='entry'){
   token=await line.linkToken(record.line_user);
   const url=new URL(bindingURL);
   if(url.protocol!=='https:')throw new Error('HTTPS required');
   url.searchParams.set('link_token',token);
   body=buttons(result.text,[{type:'uri',label:result.label||'開始綁定',uri:url.href},cancelAction]);
  }
  if(!body)return;
  const key=await store.finishEvent(record,body,token);
  if(key)await store.dispatch(key,line);
 }
 async function tick(){
  await parallel(await store.unfinished(),record=>finish(record));
  await store.plan();
  const results=[];
  await parallel(await store.pending(),async({job_key:key})=>{const result=await store.dispatch(key,line);if(result)results.push(result);});
  return results;
 }
 return async request=>{
  try{
   const route=new URL(request.url).pathname.split('/').filter(Boolean).at(-1);
   if(request.method==='GET'&&route==='health')return response({service:'nsysu-line-cloud',local_backend:false});
   if(request.method!=='POST')return response({error:'POST required'},405);
   if(Number(request.headers.get('content-length')||0)>65536)return response({error:'Request too large'},413);
   const rawBytes=new Uint8Array(await request.arrayBuffer());
   if(rawBytes.length>65536)return response({error:'Request too large'},413);
   if(route==='webhook'){
    if(!await verifySignature(rawBytes,request.headers.get('x-line-signature'),secret))return response({error:'Invalid signature'},401);
    const raw=new TextDecoder('utf-8',{fatal:true}).decode(rawBytes);
    const data=JSON.parse(raw);
    if(!Array.isArray(data.events)||data.events.length>100)throw new FlowError('Invalid events');
    let processed=0;
    for(const value of data.events){
     const event=normalizeEvent(value);
     if(!event)continue;
     const record=await store.applyEvent(event);
     if(record){processed++;waitUntil(finish(record).catch(()=>{/* durable event/outbox recovers via Cron */}));}
    }
    return response({processed});
   }
   if(route==='tick'){
    if(!await store.consumeCronTicket(request.headers.get('authorization')))return response({error:'Unauthorized'},401);
    return response({jobs:await tick()});
   }
   if(route==='prepare-link'){
    const input=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(rawBytes));
    if(!input||Array.isArray(input)||typeof input!=='object')throw new FlowError('請提供研究帳號與密碼。');
    if(typeof input.link_token!=='string'||!input.link_token||input.link_token.length>1000)throw new FlowError('請從 LINE 重新開啟「開始綁定」。',401);
    const hash=await digest(String(input.account));
    const account=await store.credentials(await digest(input.link_token),hash,await digest(input.link_token));
    if(!validAccount(input.account)||!account||!await verifyPassword(input.password,account.password_hash))throw new FlowError('研究帳號或密碼不正確，請核對研究團隊配發的資料。',401);
    const nonce=randomToken();
    await store.prepareProof(await digest(input.link_token),hash,await digest(nonce));
    const url=new URL('https://access.line.me/dialog/bot/accountLink');
    url.searchParams.set('linkToken',input.link_token);url.searchParams.set('nonce',nonce);
    return response({status:'pending_line_confirmation',link_url:url.href});
   }
   return response({error:'Not found'},404);
  }catch(error){
   if(error instanceof FlowError)return response({error:error.message},error.status);
   if(error instanceof SyntaxError)return response({error:'Invalid JSON'},400);
   return response({error:'服務暫時無法完成操作，請回到 LINE 稍後重試。'},503);
  }
 };
}
