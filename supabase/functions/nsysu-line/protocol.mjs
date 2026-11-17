export class FlowError extends Error {
 constructor(message,status=400){super(message);this.status=status;}
}
export const validAccount=value=>typeof value==='string'&&value.length===11&&/^ycc000000(?:0[1-9]|[1-4][0-9]|50)$/.test(value);
const bytes=value=>new TextEncoder().encode(value);
const hex=value=>Array.from(new Uint8Array(value),n=>n.toString(16).padStart(2,'0')).join('');
export const digest=async value=>hex(await crypto.subtle.digest('SHA-256',bytes(value)));
export const randomToken=()=>hex(crypto.getRandomValues(new Uint8Array(32)));
export const dayOf=value=>new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Taipei'}).format(new Date(value));
export const nextDay=value=>dayOf(new Date(new Date(value).getTime()+86400000));
export const instant=value=>new Date(value).toISOString();
export const addMinutes=(value,minutes)=>instant(new Date(value).getTime()+minutes*60000);
export function constantTime(a,b){
 if(typeof a!=='string'||typeof b!=='string')return false;
 let diff=a.length^b.length;
 for(let i=0;i<Math.max(a.length,b.length);i++)diff|=(a.charCodeAt(i)||0)^(b.charCodeAt(i)||0);
 return diff===0;
}
export async function verifySignature(raw,signature,secret){
 if(!secret||typeof signature!=='string')return false;
 const key=await crypto.subtle.importKey('raw',bytes(secret),{name:'HMAC',hash:'SHA-256'},false,['sign']);
 const mac=new Uint8Array(await crypto.subtle.sign('HMAC',key,typeof raw==='string'?bytes(raw):raw));
 return constantTime(btoa(String.fromCharCode(...mac)),signature);
}
export async function verifyPassword(password,encoded){
 if(typeof password!=='string'||password.length>256||typeof encoded!=='string')return false;
 const match=/^pbkdf2:sha256:(\d+)\$([^$]{8,64})\$([a-f0-9]{64})$/.exec(encoded);
 if(!match||match[0]!==encoded||+match[1]<600000||+match[1]>2000000)return false;
 const key=await crypto.subtle.importKey('raw',bytes(password),'PBKDF2',false,['deriveBits']);
 const derived=await crypto.subtle.deriveBits({name:'PBKDF2',hash:'SHA-256',salt:bytes(match[2]),iterations:+match[1]},key,256);
 return constantTime(hex(derived),match[3]);
}
export function normalizeEvent(event){
 const id=event?.webhookEventId,identity=event?.source?.userId,stamp=event?.timestamp;
 if(typeof id!=='string'||id.length>200||!Number.isSafeInteger(stamp)||event?.source?.type!=='user'||typeof identity!=='string')return null;
 let action;
 if(event.type==='follow')action='start';
 if(event.type==='unfollow')action='unfollow';
 if(event.type==='message'&&event.message?.type==='text'&&typeof event.message.text==='string')action=({'開始綁定':'start','綁定':'start','bind':'start','重新綁定':'rebind','取消綁定':'cancel'})[event.message.text.trim()];
 if(event.type==='postback'&&/^binding:(?:start|rebind|cancel|(?:confirm|keep):[a-f0-9]{64})$/.test(event.postback?.data||''))action=event.postback.data.slice(8);
 if(event.type==='accountLink'&&/^[a-f0-9]{64}$/.test(event.link?.nonce||''))action=event.link.result==='ok'?'linked':'link_failed';
 return action?{id,identity,stamp,action,nonce:event.link?.nonce}:null;
}
export function buttons(text,actions){return {type:'template',altText:text,template:{type:'buttons',text,actions}};}
export const cancelAction={type:'postback',label:'取消綁定',data:'binding:cancel',displayText:'取消綁定'};
export function diaryURL(base,member,invite,day){
 const url=new URL(base);
 if(url.protocol!=='https:')throw new Error('HTTPS required');
 url.search='';url.hash='';url.searchParams.set('member',member);url.searchParams.set('invite',invite);url.searchParams.set('date',day);
 return url.href;
}
