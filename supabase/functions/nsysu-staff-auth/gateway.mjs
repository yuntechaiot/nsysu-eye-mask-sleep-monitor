const encoder=new TextEncoder();
const uuid=/^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$/i;
const loginError='管理者帳號、密碼或研究授權不正確，請使用已授權的 DocterCloud 研究管理者帳號。';
export class StaffError extends Error{constructor(message,status=503){super(message);this.status=status;}}
export const hash=async text=>Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256',encoder.encode(text))),b=>b.toString(16).padStart(2,'0')).join('');
export function claims(token){
 try{
  const value=token.split('.')[1],data=JSON.parse(atob(value.replace(/-/g,'+').replace(/_/g,'/')));
  if(!uuid.test(data.sub)||!uuid.test(data.session_id)||data.role!=='authenticated'||!(data.exp>Date.now()/1000))throw Error();
  return data;
 }catch{throw new StaffError('登入已到期，請重新登入。',401);}
}
export function tokenCipher(encodedKey){
 const raw=Uint8Array.from(atob(encodedKey),c=>c.charCodeAt(0));if(raw.length!==32)throw Error('Private staff encryption key required');
 const key=crypto.subtle.importKey('raw',raw,'AES-GCM',false,['encrypt','decrypt']);
 const base64=bytes=>btoa(String.fromCharCode(...new Uint8Array(bytes)));
 const binary=value=>Uint8Array.from(atob(value),c=>c.charCodeAt(0));
 return {
  async seal(token,context){const iv=crypto.getRandomValues(new Uint8Array(12));const value=await crypto.subtle.encrypt({name:'AES-GCM',iv,additionalData:encoder.encode(context)},await key,encoder.encode(token));return 'v1.'+base64(iv)+'.'+base64(value);},
  async open(value,context){const [version,iv,data]=value.split('.');if(version!=='v1')throw Error('Invalid token envelope');return new TextDecoder().decode(await crypto.subtle.decrypt({name:'AES-GCM',iv:binary(iv),additionalData:encoder.encode(context)},await key,binary(data)));}
 };
}
export class AuthBroker{
 constructor(url,key,request=fetch){this.url=url;this.key=key;this.request=request;}
 async call(path,body,token=this.key){
  const response=await this.request(this.url+'/auth/v1/'+path,{method:body===undefined?'GET':'POST',headers:{apikey:this.key,Authorization:'Bearer '+token,'Content-Type':'application/json'},...(body===undefined?{}:{body:JSON.stringify(body)}),redirect:'error',signal:AbortSignal.timeout(15000)});
  if(!response.ok)throw new StaffError('登入服務暫時無法使用，請稍後重試。',response.status===401||response.status===403?401:503);
  return response.json();
 }
 async session(identity){
  // Admin generate_link returns a one-use proof; it does not send email.
  const link=await this.call('admin/generate_link',{type:'magiclink',email:identity.email});
  const token=link.hashed_token||link.properties?.hashed_token;
  if(typeof token!=='string'||!token)throw new StaffError('登入服務未回傳有效驗證。');
  const session=await this.call('verify',{type:'magiclink',token_hash:token});
  if(session.user?.id!==identity.id||session.user?.app_metadata?.diary_staff!==true||typeof session.access_token!=='string'||typeof session.refresh_token!=='string')throw new StaffError('此帳號尚未取得研究管理權限。',403);
  return session;
 }
 async user(token){return this.call('user',undefined,token);}
}
export class DocterIdentity{
 constructor(request=fetch){this.request=request;}
 async login(account,password){
  const response=await this.request('https://icare.docter.pro/back-end/app/login/researcher',{method:'POST',headers:{'Content-Type':'application/x-www-form-urlencoded'},body:new URLSearchParams({account,password}).toString(),redirect:'error',signal:AbortSignal.timeout(25000)});
  if(!response.ok)throw new StaffError(response.status>=500?'DocterCloud 暫時無法登入，請稍後再試。':loginError,response.status>=500?503:401);
  const payload=await response.json(),profile=payload.data;
  if(payload.success!==true||!profile||typeof profile.access_token!=='string'||!profile.access_token||profile.access_token.length>16384)throw new StaffError(loginError,401);
  return profile;
 }
}
export function createStaffGateway({store,auth,docter,cipher,allowedOrigin}){
 return async request=>{
  const origin=request.headers.get('origin');
  const headers={'Content-Type':'application/json','Cache-Control':'no-store','X-Content-Type-Options':'nosniff','Vary':'Origin',...(origin===allowedOrigin?{'Access-Control-Allow-Origin':origin,'Access-Control-Allow-Headers':'authorization,content-type,apikey','Access-Control-Allow-Methods':'POST, OPTIONS'}:{})};
  const reply=(body,status=200)=>new Response(JSON.stringify(body),{status,headers});
  try{
   if(origin&&origin!==allowedOrigin)return reply({error:'Invalid origin'},403);
   if(request.method==='OPTIONS')return new Response(null,{status:204,headers});
   const route=new URL(request.url).pathname.split('/').filter(Boolean).at(-1);
   if(request.method==='GET'&&route==='health')return reply({service:'nsysu-staff-auth',identity:'doctercloud-researcher'});
   if(request.method!=='POST')return reply({error:'POST required'},405);
   if(route==='session'){
    const authorization=request.headers.get('authorization')||'';
    if(!authorization.startsWith('Bearer ')||authorization.length>16384)throw new StaffError('請重新登入。',401);
    const token=authorization.slice(7),user=await auth.user(token),data=claims(token);
    if(user.id!==data.sub||user.app_metadata?.diary_staff!==true)throw new StaffError('管理權限已變更，請重新登入。',403);
    const record=await store.read(data.sub,data.session_id);
    if(!record)throw new StaffError('請使用 DocterCloud 管理者帳號重新登入。',401);
    return reply({access_token:await cipher.open(record.token_cipher,data.sub+':'+data.session_id)});
   }
   if(route!=='login')return reply({error:'Not found'},404);
   if(Number(request.headers.get('content-length')||0)>8192)throw new StaffError('Request too large',413);
   const raw=await request.text();if(encoder.encode(raw).length>8192)throw new StaffError('Request too large',413);
   const input=JSON.parse(raw);
   if(!input||Array.isArray(input)||typeof input.account!=='string'||!/^\s*[A-Za-z][A-Za-z0-9_-]{3,31}\s*$/.test(input.account)||typeof input.password!=='string'||!input.password||input.password.length>256)throw new StaffError(loginError,401);
   const account=input.account.trim().toLowerCase();await store.limit(await hash(account));
   const identity=await store.identity(account);if(!identity)throw new StaffError(loginError,401);
   const profile=await docter.login(identity.account,input.password);
   const session=await auth.session(identity),data=claims(session.access_token);
   if(data.sub!==identity.id)throw new StaffError('研究身分不一致，登入未完成。',403);
   const expires=Number.isFinite(profile.expires_in)&&profile.expires_in>0?new Date(Date.now()+profile.expires_in*1000).toISOString():null;
   const encrypted=await cipher.seal(profile.access_token,data.sub+':'+data.session_id);
   await store.save(identity.id,data.session_id,await hash(account),encrypted,expires);
   // Only the internal Auth session reaches the browser; Docter tokens stay encrypted in private storage.
   return reply({access_token:session.access_token,refresh_token:session.refresh_token,token_type:'bearer',expires_at:data.exp,
    expires_in:Math.max(0,data.exp-Math.floor(Date.now()/1000)),user:session.user});
  }catch(error){
   if(error instanceof StaffError)return reply({error:error.message},error.status);
   if(error instanceof SyntaxError)return reply({error:'Invalid JSON'},400);
   return reply({error:'登入服務暫時無法完成操作，請稍後再試。'},503);
  }
 };
}
