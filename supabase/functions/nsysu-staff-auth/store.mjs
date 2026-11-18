import {StaffError} from './gateway.mjs';
const rows=async(tx,text,args=[])=> (await tx.query(text,args)).rows;
const one=async(tx,text,args=[])=>(await rows(tx,text,args))[0];
export class StaffStore{
 constructor(database){this.database=database;}
 transaction(work){return this.database.transaction(async tx=>{await tx.query('set local role nsysu_staff_api');return work(tx);});}
 async limit(account){
  const allowed=await this.transaction(async tx=>{
   await tx.query("delete from nsysu_staff.attempts where at<now()-interval '15 minutes'");
   for(const bucket of ['staff:global','staff:'+account])await tx.query('select pg_advisory_xact_lock(hashtextextended($1,2))',[bucket]);
   for(const [bucket,limit] of [['staff:global',200],['staff:'+account,5]])if(+(await one(tx,'select count(*) n from nsysu_staff.attempts where bucket=$1',[bucket])).n>=limit)return false;
   for(const bucket of ['staff:global','staff:'+account])await tx.query('insert into nsysu_staff.attempts(bucket) values($1)',[bucket]);
   return true;
  });
  if(!allowed)throw new StaffError('嘗試次數較多，請 15 分鐘後再試。',429);
 }
 identity(account){return this.transaction(async tx=>{const value=(await one(tx,'select nsysu_staff.identity($1) as value',[account])).value;return typeof value==='string'?JSON.parse(value):value;});}
 save(user,session,account,encrypted,expires){return this.transaction(async tx=>{
  if((await one(tx,'select nsysu_staff.allowed_session($1,$2) as allowed',[user,session])).allowed!==true)throw new StaffError('管理權限已變更，登入未完成。',403);
  await tx.query('select nsysu_staff.finish_login($1,$2,$3,$4,$5)',[user,session,account,encrypted,expires]);
 });}
 read(user,session){return this.transaction(async tx=>{
  if((await one(tx,'select nsysu_staff.allowed_session($1,$2) as allowed',[user,session])).allowed!==true)return null;
  return one(tx,'select token_cipher from nsysu_staff.sessions where user_id=$1 and session_id=$2 and (provider_expires is null or provider_expires>now())',[user,session]);
 });}
}
