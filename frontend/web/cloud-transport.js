/* Streamlit iframe 使用既有 Supabase Auth/RLS；只取代兩個本機 API 入口。 */
(function(root){
 'use strict';
 if(!root.NSYSU_EMBED)return;
 const config=root.NSYSU_EMBED.config, network=root.fetch.bind(root);
 const response=(status,payload)=>new Response(JSON.stringify(payload),{status,headers:{'Content-Type':'application/json'}});
 async function remote(path,token,options={}){
  return network(config.supabase_url+path,{...options,headers:{apikey:config.publishable_key,'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{}),...options.headers}});
 }
 async function user(token){
  const result=await remote('/auth/v1/user',token);
  if(!result.ok)throw Object.assign(Error('登入已到期，請重新登入'),{status:401});
  return result.json();
 }
 async function rows(table,select,token){
  const found=[];
  for(let offset=0;offset<100000;offset+=1000){
   const result=await remote(`/rest/v1/${table}?select=${select}&order=member_id.asc&limit=1000&offset=${offset}`,token);
   if(!result.ok)throw Object.assign(Error('無法載入受試者清單，請確認連線與研究授權'),{status:503});
   const batch=await result.json();found.push(...batch);if(batch.length<1000)return found;
  }
  throw Object.assign(Error('受試者清單超過查詢上限，請聯絡研究團隊'),{status:503});
 }
 async function participants(options,includeArchived=false){
  const headers=new Headers(options.headers||{}),auth=headers.get('Authorization')||'';
  const token=auth.startsWith('Bearer ')?auth.slice(7):null;
  const account=token?await user(token):{};
  if((options.method||'GET').toUpperCase()==='GET'){
   const codes=await rows('participant_invites','member_id',token);
   const names=token?await rows('research_participants','member_id,display_name,archived_at',token):[];
   const labels=new Map(names.map(row=>[row.member_id,row.display_name]));
   const directory=token?names.filter(row=>includeArchived||!row.archived_at):codes.map(row=>({member_id:row.member_id,display_name:labels.get(row.member_id)||null}));
   return response(200,{participants:directory,can_manage:account.app_metadata?.participant_admin===true});
  }
  if((options.method||'GET').toUpperCase()!=='POST')return response(405,{error:'不支援此操作'});
  if(!token)return response(401,{error:'請先登入已開通的受試者管理員帳號'});
  if(account.app_metadata?.participant_admin!==true)return response(403,{error:'此帳號沒有新增受試者的權限，請聯絡專案管理員開通'});
  let data;try{data=JSON.parse(options.body);}catch{return response(400,{error:'請提供受試者編號與姓名'});}
  if(!data||Array.isArray(data)||typeof data.member_id!=='string'||!/^ycc[0-9]{8}$/.test(data.member_id.trim().toLowerCase()))return response(400,{error:'編號須為 ycc 加上 8 位數字'});
  if(data.display_name!=null&&(typeof data.display_name!=='string'||data.display_name.trim().length>80))return response(400,{error:'姓名最多 80 個字，可留空'});
  const result=await remote('/rest/v1/rpc/register_participant',token,{method:'POST',body:JSON.stringify({p_member_id:data.member_id.trim().toLowerCase(),p_display_name:data.display_name?.trim()||null})});
  if(!result.ok)return response(result.status===409?409:result.status===401?401:result.status===403?403:400,{error:result.status===409?'此受試者編號已存在，請選擇既有受試者或使用其他編號':'新增未完成，請重新整理清單並確認管理權限'});
  return response(201,{participant:await result.json()});
 }
 root.fetch=async function(input,options={}){
  if(input==='/api/config')return response(200,config);
  if(input==='/api/staff/login'){
   const expected=config.supabase_url+'/functions/v1/nsysu-staff-auth';
   if(config.staff_auth_url!==expected)return response(503,{error:'管理者登入服務尚未完成設定。'});
   return network(expected+'/login',{method:'POST',headers:{'Content-Type':'application/json'},body:options.body,redirect:'error'});
  }
  if(input==='/api/participant/diary-access'){
   const expected=config.supabase_url+'/functions/v1/nsysu-line/diary-access';
   if(config.participant_entry_url!==expected)return response(503,{error:'日誌入口服務尚未完成設定。'});
   return network(expected,{method:'POST',headers:{'Content-Type':'application/json'},body:options.body,redirect:'error'});
  }
  if(typeof input==='string'&&input.split('?')[0]==='/api/participants'){
   try{return await participants(options,new URL(input,'https://internal.invalid').searchParams.get('include_archived')==='1');}catch(error){return response(error.status||503,{error:error.status?error.message:'連線中斷，請重新整理清單後再重試'});}
  }
  return network(input,options);
 };
})(window);
