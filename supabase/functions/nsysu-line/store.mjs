import {FlowError,addMinutes,buttons,cancelAction,dayOf,diaryURL,digest,instant,nextDay,randomToken} from './protocol.mjs';

const decoded=value=>{for(let count=0;count<2&&typeof value==='string';count++)value=JSON.parse(value);return value;};
const rows=async(tx,text,params=[])=> (await tx.query(text,params)).rows.map(row=>{
 if(row.result!==undefined)row.result=decoded(row.result);
 if(row.payload!==undefined)row.payload=decoded(row.payload);
 if(row.snapshot!==undefined)row.snapshot=decoded(row.snapshot);
 return row;
});
const one=async(tx,text,params=[])=> (await rows(tx,text,params))[0];
const json=value=>JSON.stringify(value);
const dateText=value=>value instanceof Date?value.toISOString().slice(0,10):String(value).slice(0,10);
const time=async tx=>instant((await one(tx,'select nsysu_line.now() as at')).at);
const allowed=(cfg,id)=>cfg.enabled&&(cfg.allow_all||cfg.allowed_users.includes(id));
const expiry=(job,now)=>new Date(now)>new Date(addMinutes(job.due_at,10))||(job.kind==='diary'&&dayOf(now)!==dateText(job.target_date));
const message=text=>({kind:'message',message:{type:'text',text}});
const entry=(text,label='開始綁定')=>({kind:'entry',text,label});
const currentBinding=(tx,id)=>one(tx,`select b.*,a.member,a.study,a.starts::text,a.ends::text,a.active as account_active from nsysu_line.bindings b
 join nsysu_line.accounts a using(account_hash) where line_user=$1`,[id]);

export class CloudStore {
 constructor(database){this.database=database;}
 transaction(work){return this.database.transaction(async tx=>{await tx.query('set local role nsysu_line_api');return work(tx);});}
 config(tx){return one(tx,'select * from nsysu_line.config where id=true');}
 lock(tx,id){return tx.query('select pg_advisory_xact_lock(hashtextextended($1,0))',[id]);}
 lockAccount(tx,hash){return tx.query('select pg_advisory_xact_lock(hashtextextended($1,3))',[hash]);}
 async consumeCronTicket(authorization){
  if(typeof authorization!=='string'||!/^Bearer [a-f0-9]{64}$/.test(authorization)||authorization.length!==71)return false;
  const hash=await digest(authorization.slice(7));
  return this.transaction(async tx=>Boolean(await one(tx,'delete from nsysu_line.cron_tickets where token_hash=$1 and expires_at>nsysu_line.now() returning token_hash',[hash])));
 }
 async active(tx,id){
  const cfg=await this.config(tx);
  const friend=await one(tx,'select active from nsysu_line.friends where line_user=$1',[id]);
  return allowed(cfg,id)&&friend?.active;
 }
 async limit(buckets,limit){
  const ok=await this.transaction(async tx=>{
   const now=await time(tx);
   await tx.query("delete from nsysu_line.attempts where at < $1::timestamptz-interval '15 minutes'",[now]);
   for(const bucket of [...buckets].sort())await tx.query('select pg_advisory_xact_lock(hashtextextended($1,1))',[bucket]);
   for(const bucket of buckets){
    if(+(await one(tx,'select count(*) as n from nsysu_line.attempts where bucket=$1',[bucket])).n>=limit)return false;
   }
   for(const bucket of buckets)await tx.query('insert into nsysu_line.attempts values($1,$2)',[bucket,now]);
   return true;
  });
  if(!ok)throw new FlowError('嘗試次數較多，請 15 分鐘後再試。',429);
 }
 async credentials(tokenHash,accountHash,ipHash){
  await this.limit(['prepare-global'],300);
  await this.limit(['link:'+ipHash],30);
  const request=await this.transaction(async tx=>{
   const now=await time(tx);
   const link=await one(tx,'select * from nsysu_line.link_requests where token_hash=$1 and expires_at>$2',[tokenHash,now]);
   return link&&await this.active(tx,link.line_user)?link:null;
  });
  if(!request)throw new FlowError('綁定連結已失效，請回到 LINE 點「開始綁定」。',401);
  await this.limit(['line:'+await digest(request.line_user),'account:'+accountHash],5);
  return this.transaction(tx=>one(tx,'select password_hash from nsysu_line.accounts where account_hash=$1 and active',[accountHash]));
 }
 async qrCredentials(accountHash){
  await this.limit(['qr-global'],300);await this.limit(['qr-account:'+accountHash],5);
  return this.transaction(tx=>one(tx,'select password_hash from nsysu_line.accounts where account_hash=$1 and active',[accountHash]));
 }
 async qrLink(accountHash){
  return this.transaction(async tx=>{
   const day=dayOf(await time(tx)),cfg=await this.config(tx);
   const account=await one(tx,'select member from nsysu_line.accounts where account_hash=$1 and active',[accountHash]);
   if(!account)throw new FlowError('研究帳號目前無法取得日誌入口，請聯絡研究團隊。',403);
   const snapshot=(await one(tx,'select nsysu_line.diary_snapshot($1,$2::date) as snapshot',[account.member,day])).snapshot;
   if(!snapshot?.active||!snapshot.invite)throw new FlowError('日誌入口目前未開放或已停用，請聯絡研究團隊。',403);
   return {member_id:account.member,diary_url:diaryURL(cfg.diary_url,account.member,snapshot.invite)};
  });
 }
 async prepareProof(tokenHash,accountHash,nonceHash){
  return this.transaction(async tx=>{
   const now=await time(tx);
   const request=await one(tx,'select * from nsysu_line.link_requests where token_hash=$1 and expires_at>$2',[tokenHash,now]);
   if(!request||!await this.active(tx,request.line_user))throw new FlowError('綁定連結已失效，請回到 LINE 重新開始。',401);
   await this.lock(tx,request.line_user);
   const account=await one(tx,'select * from nsysu_line.accounts where account_hash=$1 and active',[accountHash]);
   if(!account||account.ends&&dateText(account.ends)<dayOf(now))throw new FlowError('此研究帳號目前無法綁定，請聯絡研究團隊。',403);
   await this.lockAccount(tx,accountHash);
   const conflicts=await rows(tx,'select * from nsysu_line.bindings where line_user=$1 or account_hash=$2',[request.line_user,accountHash]);
   if(conflicts.some(b=>b.account_hash===accountHash&&b.line_user!==request.line_user))throw new FlowError('此研究帳號已綁定其他 LINE。每個研究帳號只能綁定一個 LINE，請先由原 LINE 取消綁定。',409);
   if(conflicts.some(b=>b.line_user===request.line_user&&b.account_hash!==accountHash))throw new FlowError('你的 LINE 已綁定其他研究帳號，請先回 LINE 取消原綁定後再更換帳號。',409);
   if(conflicts.some(b=>!b.active))throw new FlowError('此綁定已停用，請聯絡研究團隊。',403);
   await tx.query('update nsysu_line.link_proofs set used_at=$2 where token_hash=$1 and used_at is null',[tokenHash,now]);
   await tx.query('insert into nsysu_line.link_proofs values($1,$2,$3,$4,null)',[nonceHash,tokenHash,accountHash,request.expires_at]);
   return {expires_at:instant(request.expires_at)};
  });
 }
 async applyEvent(event){
  return this.transaction(async tx=>{
   const now=await time(tx),cfg=await this.config(tx);
   if(!allowed(cfg,event.identity))return null;
   await this.lock(tx,event.identity);
   const previous=await one(tx,'select * from nsysu_line.events where event_id=$1 for update',[event.id]);
   if(previous)return previous.line_user===event.identity?this.reclaim(tx,previous,now):null;
   const friend=await one(tx,'select * from nsysu_line.friends where line_user=$1',[event.identity]);
   let result={kind:'none'};
   if(!friend||+friend.event_ms<event.stamp||+friend.event_ms===event.stamp&&friend.active){
    await tx.query(`insert into nsysu_line.friends values($1,$2,$3)
     on conflict(line_user) do update set active=excluded.active,event_ms=excluded.event_ms`,[event.identity,event.action!=='unfollow',event.stamp]);
    result=await this.mutateEvent(tx,event,now);
   }
   const saved=await one(tx,`insert into nsysu_line.events(event_id,line_user,lease_until,result,due_at,finished)
    values($1,$2,$3,$4,$5,$6) returning *`,[event.id,event.identity,addMinutes(now,1),result,now,result.kind==='none']);
   return saved.finished?null:saved;
  });
 }
 async reclaim(tx,record,now){
  if(record.finished)return null;
  if(new Date(now)>new Date(addMinutes(record.due_at,10))||!await this.active(tx,record.line_user)){
   await tx.query('update nsysu_line.events set finished=true where event_id=$1',[record.event_id]);return null;
  }
  if(new Date(record.lease_until)>new Date(now))return null;
  return one(tx,'update nsysu_line.events set claim=gen_random_uuid(),lease_until=$2 where event_id=$1 returning *',[record.event_id,addMinutes(now,1)]);
 }
 async unfinished(){
  return this.transaction(async tx=>{
   const now=await time(tx),cfg=await this.config(tx);
   if(!cfg.enabled)return [];
   const pending=await rows(tx,`select * from nsysu_line.events where not finished and lease_until<=$1 order by due_at limit 8 for update skip locked`,[now]);
   const result=[];
   for(const record of pending){const claimed=await this.reclaim(tx,record,now);if(claimed)result.push(claimed);}
   return result;
  });
 }
 async mutateEvent(tx,event,now){
  const id=event.identity,binding=await currentBinding(tx,id);
  if(event.action==='unfollow'){
   await tx.query("update nsysu_line.outbox set status='cancelled' where line_user=$1 and status in ('pending','retry','uncertain')",[id]);
   await this.invalidate(tx,id,now);
   return {kind:'none'};
  }
  if(event.action==='start'||event.action==='rebind')return entry(binding?`目前綁定 ${binding.member}。同帳號可重新確認；更換帳號請先取消綁定。`:'請輸入研究團隊配發的帳號與密碼，完成 LINE 綁定。',binding?'重新綁定':'開始綁定');
  if(event.action==='cancel'){
   if(!binding)return entry('目前尚未綁定研究帳號。請點「開始綁定」。');
   if(!binding.active)return message('此綁定已由研究團隊停用，請聯絡研究團隊。');
   const token=randomToken();
   await tx.query('update nsysu_line.cancellations set used_at=$2 where line_user=$1 and used_at is null',[id,now]);
   await tx.query('insert into nsysu_line.cancellations values($1,$2,$3,$4,$5,null)',[await digest(token),id,binding.account_hash,binding.bound_at,addMinutes(now,10)]);
   return {kind:'message',message:buttons(`確定取消 ${binding.member} 的綁定？確認後停止後續提醒，已填日誌會保留。`,[
    {type:'postback',label:'確認取消',data:'binding:confirm:'+token,displayText:'確認取消綁定'},
    {type:'postback',label:'保留綁定',data:'binding:keep:'+token,displayText:'保留目前綁定'}])};
  }
  if(event.action.startsWith('confirm:')||event.action.startsWith('keep:')){
   const [action,token]=event.action.split(':');
   const confirm=await one(tx,'select * from nsysu_line.cancellations where token_hash=$1 and line_user=$2 and used_at is null and expires_at>=$3',[await digest(token),id,now]);
   if(!binding?.active||!confirm||confirm.account_hash!==binding.account_hash||instant(confirm.bound_at)!==instant(binding.bound_at))return message('確認已失效或綁定已變更。請重新點「取消綁定」。');
   await this.invalidate(tx,id,now);
   if(action==='keep')return message(`已保留 ${binding.member} 的綁定，提醒設定不變。`);
   await this.lockAccount(tx,binding.account_hash);
   await tx.query('insert into nsysu_line.binding_history(line_user,account_hash,study,member,bound_at,reminder_start,cancelled_at) values($1,$2,$3,$4,$5,$6,$7)',[id,binding.account_hash,binding.study,binding.member,binding.bound_at,binding.reminder_start,now]);
   await tx.query('delete from nsysu_line.bindings where line_user=$1',[id]);
   await tx.query("update nsysu_line.outbox set status='cancelled',processed_at=$2 where line_user=$1 and (kind='diary' or slot like 'binding-test:%') and status in ('pending','retry','uncertain')",[id,now]);
   return entry('已取消綁定，後續提醒已停止，已填日誌已保留。現在可以綁定新的研究帳號。');
  }
  if(event.action==='linked'||event.action==='link_failed'){
   const proof=await one(tx,`select p.*,r.line_user from nsysu_line.link_proofs p join nsysu_line.link_requests r using(token_hash)
    where p.nonce_hash=$1 and p.used_at is null and p.expires_at>$2 and r.expires_at>$2`,[await digest(event.nonce),now]);
   if(!proof||proof.line_user!==id)return message('綁定確認已失效，請重新點「開始綁定」。');
   await tx.query('update nsysu_line.link_proofs set used_at=$2 where nonce_hash=$1',[proof.nonce_hash,now]);
   if(event.action==='link_failed')return entry('LINE 授權未完成，尚未新增綁定。請重新開始。');
   const account=await one(tx,'select *,starts::text as start_day,ends::text as end_day from nsysu_line.accounts where account_hash=$1 and active',[proof.account_hash]);
   if(!account||account.end_day&&account.end_day<dayOf(now))return message('此研究帳號目前無法綁定，請聯絡研究團隊。');
   await this.lockAccount(tx,proof.account_hash);
   const others=await rows(tx,'select * from nsysu_line.bindings where account_hash=$1 or line_user=$2',[proof.account_hash,id]);
   if(others.some(b=>b.account_hash===proof.account_hash&&b.line_user!==id))return message('此研究帳號已綁定其他 LINE。每個研究帳號只能綁定一個 LINE，請先由原 LINE 取消綁定。');
   if(others.some(b=>b.line_user===id&&b.account_hash!==proof.account_hash))return message('你的 LINE 已綁定其他研究帳號，請先取消原綁定後再更換帳號。');
   if(others.some(b=>!b.active))return message('此綁定已停用，請聯絡研究團隊。');
   let start=others[0]?dateText(others[0].reminder_start):nextDay(now);
   if(!others.length){
    if(account.start_day&&account.start_day>start)start=account.start_day;
    if(account.end_day&&start>account.end_day)return message('研究已無後續提醒日期，請聯絡研究團隊。');
    await tx.query('insert into nsysu_line.bindings values($1,$2,$3,$4,true)',[id,account.account_hash,now,start]);
   }
   await this.invalidate(tx,id,now);
   const success=`綁定成功：${account.member}。首次睡眠日誌提醒：${start.replaceAll('-','/')} 上午 09:00。`;
   const day=account.start_day&&account.start_day>dayOf(now)?account.start_day:dayOf(now);
   const snapshot=(await one(tx,'select nsysu_line.diary_snapshot($1,$2::date) as snapshot',[account.member,day])).snapshot;
   if(!snapshot?.active||!/^[a-f0-9]{64}$/.test(snapshot.invite||''))return message(success+' 日誌測試連結目前未開放，請聯絡研究團隊。');
   const cfg=await this.config(tx);
   return {kind:'binding_test',binding:{account_hash:account.account_hash,member:account.member,study:account.study,bound_at:instant(others[0]?.bound_at||now)},day,
    message:buttons(`綁定成功：${account.member}。\n【日誌連結測試】請點下方確認帳號。\n日誌日期：${day.replaceAll('-','/')}。\n首次正式提醒：${start.replaceAll('-','/')} 09:00。`,[
     {type:'uri',label:'開啟我的日誌（測試）',uri:diaryURL(cfg.diary_url,account.member,snapshot.invite,day)}])};
  }
  return {kind:'none'};
 }
 async invalidate(tx,id,now){
  await tx.query('update nsysu_line.cancellations set used_at=$2 where line_user=$1 and used_at is null',[id,now]);
  await tx.query('update nsysu_line.link_proofs set used_at=$2 where used_at is null and token_hash in (select token_hash from nsysu_line.link_requests where line_user=$1)',[id,now]);
  await tx.query('update nsysu_line.link_requests set expires_at=$2 where line_user=$1',[id,now]);
 }
 async finishEvent(record,body,linkToken){
  return this.transaction(async tx=>{
   await this.lock(tx,record.line_user);
   const now=await time(tx),current=await one(tx,'select * from nsysu_line.events where event_id=$1 for update',[record.event_id]);
   if(!current||current.finished||current.claim!==record.claim)return null;
   if(!await this.active(tx,record.line_user)||new Date(now)>new Date(addMinutes(current.due_at,10))){
    await tx.query('update nsysu_line.events set finished=true where event_id=$1',[record.event_id]);return null;
   }
   const test=current.result.kind==='binding_test'?current.result:null;
   if(test&&!await this.bindingTestEligible(tx,current)){
    await tx.query('update nsysu_line.events set finished=true where event_id=$1',[record.event_id]);return null;
   }
   if(linkToken)await tx.query('insert into nsysu_line.link_requests values($1,$2,$3)',[await digest(linkToken),record.line_user,addMinutes(now,10)]);
   const key='interaction:'+record.event_id;
   await tx.query('insert into nsysu_line.outbox(job_key,kind,line_user,due_at,payload,study,member,target_date,slot) values($1,\'interaction\',$2,$3,$4,$5,$6,$7,$8) on conflict(job_key) do nothing',
    [key,record.line_user,current.due_at,{to:record.line_user,messages:[test?test.message:body]},test?.binding.study||null,test?.binding.member||null,test?.day||null,test?'binding-test:'+record.event_id:null]);
   await tx.query('update nsysu_line.events set finished=true where event_id=$1',[record.event_id]);
   return key;
  });
 }
 async bindingTestEligible(tx,record,body=record.result.message){
  const result=record.result,binding=await currentBinding(tx,record.line_user);
  if(result.kind!=='binding_test'||!binding?.active||!binding.account_active||binding.account_hash!==result.binding.account_hash||binding.member!==result.binding.member||binding.study!==result.binding.study||instant(binding.bound_at)!==result.binding.bound_at)return false;
  const snapshot=(await one(tx,'select nsysu_line.diary_snapshot($1,$2::date) as snapshot',[binding.member,result.day])).snapshot;
  if(!snapshot?.active||!/^[a-f0-9]{64}$/.test(snapshot.invite||''))return false;
  const cfg=await this.config(tx);
  return body?.template?.actions[0]?.uri===diaryURL(cfg.diary_url,binding.member,snapshot.invite,result.day);
 }
 async eligible(tx,id,day){
  if(!await this.active(tx,id))return null;
  const account=await one(tx,`select a.*,a.starts::text as start_day,a.ends::text as end_day,b.reminder_start::text as reminder_day
   from nsysu_line.bindings b join nsysu_line.accounts a using(account_hash) where b.line_user=$1 and b.active and a.active`,[id]);
  if(!account||day<account.reminder_day||account.start_day&&day<account.start_day||account.end_day&&day>account.end_day)return null;
  const snapshot=(await one(tx,'select nsysu_line.diary_snapshot($1,$2::date) as data',[account.member,day])).data;
  return snapshot.active&&!snapshot.completed&&/^[a-f0-9]{64}$/.test(snapshot.invite||'')?{account,snapshot}:null;
 }
 async plan(){
  return this.transaction(async tx=>{
   const now=await time(tx),cfg=await this.config(tx),day=dayOf(now);
   if(!cfg.enabled)return;
   const slots=[];
   for(let hour=9;hour<=21;hour+=2){
    const slot=String(hour).padStart(2,'0')+':00',due=day+'T'+slot+':00+08:00';
    if(new Date(now)>=new Date(due)&&new Date(now)<=new Date(addMinutes(due,10)))slots.push({slot,due});
   }
   if(!slots.length)return;
   const bindings=await rows(tx,'select line_user from nsysu_line.bindings where active order by line_user');
   for(const {line_user:id} of bindings){
    const eligible=await this.eligible(tx,id,day);
    if(!eligible)continue;
    for(const {slot,due} of slots){
     const {account,snapshot}=eligible;
     const key=json([account.study,account.member,day,slot]);
     const payload={to:id,messages:[buttons('請完成本次睡眠日誌。填寫完成後，今天將不再提醒。',[
      {type:'uri',label:'填寫睡眠日誌',uri:diaryURL(cfg.diary_url,account.member,snapshot.invite,day)}])]};
     await tx.query(`insert into nsysu_line.outbox(job_key,kind,line_user,study,member,target_date,slot,due_at,payload)
      values($1,'diary',$2,$3,$4,$5,$6,$7,$8) on conflict do nothing`,[key,id,account.study,account.member,day,slot,due,payload]);
    }
   }
  });
 }
 async pending(){
  return this.transaction(async tx=>rows(tx,`select job_key from nsysu_line.outbox where status in ('pending','retry','uncertain')
   and due_at<=nsysu_line.now() and (retry_at is null or retry_at<=nsysu_line.now()) order by due_at limit 32`));
 }
 async jobEligible(tx,job){
  if(job.payload.to!==job.line_user)return false;
  if(!await this.active(tx,job.line_user))return false;
  if(job.kind!=='diary'){
   if(!job.slot?.startsWith('binding-test:'))return true;
   const record=await one(tx,'select * from nsysu_line.events where event_id=$1 and line_user=$2',[job.slot.slice('binding-test:'.length),job.line_user]);
   return Boolean(record&&await this.bindingTestEligible(tx,record,job.payload.messages[0]));
  }
  const day=dateText(job.target_date),eligible=await this.eligible(tx,job.line_user,day);
  if(!eligible||eligible.account.member!==job.member||eligible.account.study!==job.study)return false;
  const cfg=await this.config(tx);
  return job.payload.messages[0]?.template?.actions[0]?.uri===diaryURL(cfg.diary_url,job.member,eligible.snapshot.invite,day);
 }
 async dispatch(key,line){
  const intent=await this.transaction(async tx=>{
   const job=await one(tx,'select * from nsysu_line.outbox where job_key=$1 for update',[key]);
   if(!job||!['pending','retry','uncertain'].includes(job.status))return null;
   const now=await time(tx);
   if(expiry(job,now)){
    await tx.query('update nsysu_line.outbox set status=$2,processed_at=$3 where job_key=$1',[key,job.uncertainty?'uncertain_final':'skipped',now]);return null;
   }
   if(new Date(now)<new Date(job.due_at)||job.retry_at&&new Date(now)<new Date(job.retry_at))return null;
   if(job.attempts>=3){await tx.query("update nsysu_line.outbox set status='uncertain_final' where job_key=$1",[key]);return null;}
   const lease=addMinutes(now,1);
   await tx.query("update nsysu_line.outbox set status='uncertain',uncertainty=true,attempts=attempts+1,retry_at=$2,processed_at=$3,error_code='dispatch_intent' where job_key=$1",[key,lease,now]);
   return {...job,attempts:job.attempts+1,lease};
  });
  if(!intent)return null;
  return this.transaction(async tx=>{
   await this.lock(tx,intent.line_user);
   const job=await one(tx,'select * from nsysu_line.outbox where job_key=$1 for update',[key]);
   if(job.status!=='uncertain'||job.attempts!==intent.attempts||instant(job.retry_at)!==intent.lease)return null;
   const eligible=await this.jobEligible(tx,job),now=await time(tx);
   if(!eligible||expiry(job,now)){
    await tx.query("update nsysu_line.outbox set status='cancelled',uncertainty=$2,processed_at=$3 where job_key=$1",[key,intent.uncertainty,now]);return null;
   }
   const outcome=await line.push(job.payload,job.retry_key);
   const finished=await time(tx);
   let status=outcome.status,unknown=['retry','uncertain'].includes(status)||(status!=='accepted'&&intent.uncertainty);
   if(status==='failed'&&unknown||['retry','uncertain'].includes(status)&&job.attempts>=3)status='uncertain_final';
   const retry=['retry','uncertain'].includes(status)?instant(new Date(finished).getTime()+30000*2**(job.attempts-1)):null;
   await tx.query('update nsysu_line.outbox set status=$2,uncertainty=$3,retry_at=$4,processed_at=$5,error_code=$6,request_id=$7 where job_key=$1',[key,status,unknown,retry,finished,outcome.error||null,outcome.requestId||null]);
   return {kind:job.kind,status};
  });
 }
}
