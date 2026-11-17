'use strict';
let config, session=null;
try{session=JSON.parse(sessionStorage.getItem('vtca-session')||'null');if(session&&(!session.access_token||session.user?.app_metadata?.diary_staff!==true))session=null;}catch{sessionStorage.removeItem('vtca-session');}
let currentMember=null, editingId=null, records=[], allSummary={}, exportData=[];
let currentStep=0, entryPurpose='diary', dirty=false, saving=false, postAuthAction=null, authGeneration=0;
const el=id=>document.getElementById(id), val=id=>el(id).value;
const today=()=>new Date().toLocaleDateString('sv-SE',{timeZone:'Asia/Taipei'});
const previousDay=day=>new Date(Date.parse(day+'T12:00:00+08:00')-86400000).toLocaleDateString('sv-SE',{timeZone:'Asia/Taipei'});
const text=v=>VTCA.esc(v);
async function authHeaders() {
  if(session && session.expires_at*1000 < Date.now()+30000){
    const response=await fetch(config.supabase_url+'/auth/v1/token?grant_type=refresh_token',{method:'POST',headers:{apikey:config.publishable_key,'Content-Type':'application/json'},body:JSON.stringify({refresh_token:session.refresh_token})});
    if(!response.ok){await signOut();throw Error('登入已到期，請重新登入');}
    session=await response.json();if(session.user?.app_metadata?.diary_staff!==true){await signOut();throw Error('此帳號沒有日誌管理權限');}sessionStorage.setItem('vtca-session',JSON.stringify(session));
  }
  return {apikey:config.publishable_key,'Content-Type':'application/json',...(session?{Authorization:'Bearer '+session.access_token}:{})};
}
async function sbFetch(path,opts={}){
  const response=await fetch(config.supabase_url+'/rest/v1'+path,{method:opts.method||'GET',headers:{...await authHeaders(),Prefer:opts.prefer||'return=representation'},body:opts.body});
  if(!response.ok){throw Error(response.status===401?'登入已到期，請重新登入。':response.status===403?'這個帳號沒有此受試者的存取權限，請聯絡研究團隊。':response.status===400?'資料尚未儲存，請核對必填欄位與睡眠日期。':'暫時無法讀取或儲存資料，請稍後重試。');}
  const t=await response.text();return t?JSON.parse(t):[];
}
async function allRows(query){
  const rows=[];
  for(let offset=0;offset<100000;offset+=1000){const batch=await sbFetch(query+'&limit=1000&offset='+offset);rows.push(...batch);if(batch.length<1000)return rows;}
  throw Error('資料量超過查詢上限，請使用 Dashboard 日期篩選');
}
async function signIn(event){
  event?.preventDefault();const button=el('auth-submit');button.disabled=true;el('auth-status').textContent='正在登入…';
  try{
    const r=await fetch(config.supabase_url+'/auth/v1/token?grant_type=password',{method:'POST',headers:{apikey:config.publishable_key,'Content-Type':'application/json'},body:JSON.stringify({email:VTCA.diaryEmail(val('auth-email')),password:val('auth-password')})});
    if(!r.ok)throw Error('登入失敗，請檢查帳密');
    const signed=await r.json();if(signed.user?.app_metadata?.diary_staff!==true)throw Error('此帳號沒有日誌管理權限');
    session=signed;authGeneration++;sessionStorage.setItem('vtca-session',JSON.stringify(session));el('auth-password').value='';
    const action=postAuthAction;updateAccount();closeAuth();await loadParticipants();
    if(el('admin-page').classList.contains('active'))await refreshSummary();
    if(el('history-page').classList.contains('active')){await loadHistoryParticipants();await loadHistory();}
    if(action==='export')await openExport();
    if(action==='participants')await openParticipantDialog();
    if(action==='diary')await openMember(currentMember);
    if(action==='entry')showMemberEntry('diary');
    if(action==='workspace'||!action)await goWorkspace();
    if(action==='qr')await goQR();
    if(action==='research')await openResearch();
    if(action==='members')await goAdmin();
    if(action==='history')showHistory();
  }catch(e){el('auth-status').textContent=e.message;}finally{button.disabled=false;}
}
async function signOut(localOnly=false){
  if(!localOnly)notifyResearchLogout();
  if(session&&!localOnly)void fetch(config.supabase_url+'/auth/v1/logout?scope=local',{method:'POST',headers:{apikey:config.publishable_key,Authorization:'Bearer '+session.access_token}}).catch(()=>{});
  session=null;authGeneration++;sessionStorage.removeItem('vtca-session');records=[];exportData=[];allSummary={};editingId=null;
  postAuthAction=null;invitationCache.clear();fixedInvitationLoads.clear();clearParticipantNames();el('history-area').replaceChildren();el('qr-grid').replaceChildren();el('selected-qr').replaceChildren();el('selected-qr').removeAttribute('title');el('participant-link').value='';el('selected-member-label').textContent='';updateAccount();el('auth-password').value='';el('submission-receipt').textContent='';
  closeManagementDialog();clearHistoryDirectory();
  el('export-table-wrap').textContent='請先登入';closeExport();cancelEdit();
  if(directoryLoaded)await loadParticipants();
  if(el('admin-page').classList.contains('active'))await refreshSummary();
  if(el('history-page').classList.contains('active'))await loadHistoryParticipants();
  if(currentMember||el('history-page').classList.contains('active'))await loadHistory();
}
function showPage(id){document.querySelectorAll('.page').forEach(p=>p.classList.toggle('active',p.id===id));window.scrollTo(0,0);}
function selectScale(id,value){el(id).querySelectorAll('.scale-btn').forEach(b=>{const active=+b.dataset.v===value;b.classList.toggle('selected',active);b.setAttribute('aria-pressed',String(active));});dirty=true;}
function getScale(id){const b=el(id).querySelector('.selected');return b?+b.dataset.v:null;}
function initChoiceGroups(){
 document.querySelectorAll('.radio-group,.check-group').forEach(g=>g.addEventListener('change',event=>{
  if(g.id==='cg-disturbance'){
   if(event.target.checked&&event.target.value==='無'){g.querySelectorAll('input').forEach(i=>i.checked=i===event.target);selectScale('scale-disturbance',0);}
   else if(event.target.checked)g.querySelector('input[value="無"]').checked=false;
  }
  g.querySelectorAll('label').forEach(l=>l.classList.toggle('selected',l.querySelector('input').checked));
 }));
}
function buildAdminGrid(){
 el('qr-grid').innerHTML='';
 participants.forEach(row=>{
  const mid=row.member_id;
  const card=document.createElement('a');card.className='qr-card';card.href='?member='+mid;card.dataset.mid=mid;
  card.innerHTML=`<div class="mid">${text(participantLabel(row))}</div><div class="cnt">選擇並取得 QR Code →</div>`;
  card.dataset.search=`${mid} ${row.display_name||''}`.toLocaleLowerCase();
  card.addEventListener('click',event=>{event.preventDefault();showMemberEntry('diary');selectParticipant(mid);});
  el('qr-grid').appendChild(card);
 });
 filterGrid();
}
function filterGrid(){document.querySelectorAll('.qr-card').forEach(c=>c.hidden=!c.dataset.search.includes(val('search-input').trim().toLocaleLowerCase()));}
async function refreshSummary(){
 const summary={},generation=authGeneration;if(session){const rows=await allRows('/sleep_logs?select=member_id&order=id.asc');if(generation!==authGeneration||!session)return;rows.forEach(r=>summary[r.member_id]=(summary[r.member_id]||0)+1);}allSummary=summary;
 buildAdminGrid();el('stat-total').textContent=session?Object.values(allSummary).reduce((a,b)=>a+b,0):'需登入';el('stat-active').textContent=session?Object.keys(allSummary).length:'需登入';
}
async function openMember(mid){if(!await ensureDiaryAccess(mid))return;const resume=currentMember===mid&&dirty;currentMember=mid;el('member-chip').textContent=mid;showPage('member-page');if(!resume)cancelEdit();setRoute('diary',mid);}
function cancelEdit(){
 editingId=null;const target=new URLSearchParams(window.NSYSU_EMBED?window.NSYSU_EMBED.initial_query:location.search).get('date');const day=target&&/^\d{4}-\d{2}-\d{2}$/.test(target)?target:today();
 ['f-name','f-headphone','f-sleep-onset','f-wakeups','f-lights-out','f-waso','f-wore-watch','f-sleep-medication','f-drank-alcohol'].forEach(id=>el(id).value='');
 el('f-date').value=day;el('f-bed-date').value=previousDay(day);el('f-lights-date').value=previousDay(day);el('f-out-date').value=day;
 el('wake-date-hint').textContent='最後醒來日期：'+day;
 el('f-sleep-time').value='23:00';el('f-morning-wake-time').value='07:00';el('f-wake-time').value='07:15';
 document.querySelectorAll('.radio-item,.check-item,.scale-btn').forEach(e=>{e.classList.remove('selected');if(e.matches('.scale-btn'))e.setAttribute('aria-pressed','false');});
 document.querySelectorAll('input[type=checkbox],input[type=radio]').forEach(e=>e.checked=false);
 el('submit-btn').textContent='確認送出日誌';el('diary-heading').textContent='記錄昨晚的睡眠';dirty=false;setStep(0,false);
}
async function goAdmin(event){event?.preventDefault();if(saving||!await workspaceAuth('members'))return;showPage('admin-page');setRoute('members');loadParticipants();refreshSummary().catch(e=>showToast(e.message,'error'));}
const FIELD_NAMES={'f-headphone':'耳機使用分鐘','f-sleep-onset':'入睡所需分鐘','f-wakeups':'夜間醒來次數','f-waso':'夜間清醒分鐘'};
function fail(message,id){const error=Error(message);error.field=id;throw error;}
function integer(id,min,max){const raw=val(id);const n=Number(raw);if(raw===''||!Number.isInteger(n)||n<min||n>max)fail(`請填寫${FIELD_NAMES[id]}（${min}–${max} 的整數）`,id);return n;}
async function submitRecord(){
 const btn=el('submit-btn');
 if(saving)return;
 try{
  for(let step=0;step<3;step++){try{validateStep(step);}catch(error){setStep(step,false);throw error;}}
  if(currentStep!==3){setStep(3);return;}
  const times=VTCA.diaryTimes({date:val('f-date'),bedDate:val('f-bed-date'),bed:val('f-sleep-time'),lightsDate:val('f-lights-date'),lights:val('f-lights-out'),wake:val('f-morning-wake-time'),outDate:val('f-out-date'),out:val('f-wake-time')});
  const fallback=document.querySelector('input[name=fallback]:checked')?.value;
  const disturbance=[...document.querySelectorAll('#cg-disturbance input:checked')].map(i=>i.value).join(',');
  if(!val('f-name').trim()||!fallback||!disturbance||getScale('scale-quality')===null||getScale('scale-disturbance')===null)throw Error('請完成姓名、醒後睡回、干擾因素與品質評分');
  const row={member_id:currentMember,name:val('f-name').trim(),date:val('f-date'),headphone_min:integer('f-headphone',0,600),sleep_time:val('f-sleep-time'),sleep_onset_min:integer('f-sleep-onset',0,300),wakeup_count:integer('f-wakeups',0,20),fallback_sleep:fallback,disturbance,disturbance_scale:getScale('scale-disturbance'),morning_wake_time:val('f-morning-wake-time'),wake_time:val('f-wake-time'),sleep_quality:getScale('scale-quality'),...times,wore_watch:VTCA.tri(val('f-wore-watch')),sleep_medication:VTCA.tri(val('f-sleep-medication')),drank_alcohol:VTCA.tri(val('f-drank-alcohol')),subjective_waso_minutes:val('f-waso')===''?null:integer('f-waso',0,1440)};
  btn.disabled=true;saving=true;btn.textContent='正在送出…';el('signout-btn').disabled=true;
  const path='/sleep_logs'+(editingId?'?id=eq.'+editingId+'&member_id=eq.'+encodeURIComponent(currentMember):'');
  let result=[];
  if(!session&&!editingId)await submitInvitedDiary(row);
  else result=await sbFetch(path,{method:editingId?'PATCH':'POST',prefer:'return=representation',body:JSON.stringify(row)});
  if(editingId&&!result.length)throw Error('沒有更新任何紀錄，請確認寫入授權');
  const changed=editingId!==null;dirty=false;editingId=null;
  el('success-title').textContent=changed?'日誌已更新':'日誌已送出';
  el('success-description').textContent=`${currentMember} · ${row.date} 的睡眠紀錄已保存。`;
  el('submission-receipt').innerHTML=`<h2 class="card-title">這次的紀錄</h2>${reviewList([['上床',row.bedtime_at.slice(0,16).replace('T',' ')],['開始嘗試入睡',row.lights_out_at?.slice(0,16).replace('T',' ')||'未填'],['最後醒來',row.final_wake_at.slice(0,16).replace('T',' ')],['實際離床',row.out_of_bed_at.slice(0,16).replace('T',' ')],['主觀入睡時間',row.sleep_onset_min+' 分鐘'],['是否配戴手錶',boolLabel(row.wore_watch)]])}`;
  showPage('success-page');setRoute('submitted',currentMember);showToast(changed?'日誌已更新':'日誌已送出');
 }catch(e){showFormError(e);}finally{btn.disabled=false;saving=false;el('signout-btn').disabled=false;btn.textContent=editingId?'確認儲存修改':'確認送出日誌';}
}
const boolLabel=v=>v===true?'是':v===false?'否':'未填／不確定';
function legacyClock(row){
 if(row.bedtime)return row.bedtime.slice(0,5);
 if(VTCA.validClock(row.sleep_time)&&((row.sleep_time_ampm==='AM'&&+row.sleep_time.slice(0,2)<12)||(row.sleep_time_ampm==='PM'&&+row.sleep_time.slice(0,2)>=12)))return row.sleep_time;
 return '待確認（原始值保留）';
}
async function loadHistory(){
 const area=el('history-area'),request=++historyLoadRequest;records=[];
 el('history-login-button').hidden=!!session;
 if(!session){area.innerHTML='<div class="card empty"><h2>登入後，就能查看與修改</h2><p>歷史資料需要登入並取得此受試者授權。填寫新的日誌仍然無需登入。</p></div>';return;}
 if(!currentMember){area.innerHTML='<div class="card empty"><h2>請先選擇受試者</h2><p>選擇上方的受試者，即可載入對應的歷史日誌。</p></div>';return;}
 const requestedMember=currentMember, requestedGeneration=authGeneration;
 area.textContent='正在讀取歷史紀錄…';
 try{
  const response=await allRows('/sleep_logs?member_id=eq.'+encodeURIComponent(requestedMember)+'&order=date.desc,id.desc');
  if(request!==historyLoadRequest||!session||authGeneration!==requestedGeneration||currentMember!==requestedMember)return;
  records=response;
  area.innerHTML=records.length?records.map(r=>`<div class="rec-item"><div class="rec-head"><span class="rec-name">${text(r.name)}</span><span>${text(r.date)} · ${r.date_definition==='wake_date'?'醒來日期':'舊日期定義待確認'}</span><button class="btn btn-outline" onclick="editRecord(${r.id})">編輯</button><button class="btn btn-danger" onclick="deleteDiary(${r.id})">刪除</button></div><div class="rec-grid">${[['上床',legacyClock(r)],['關燈',r.lights_out_time?.slice(0,5)||'未填'],['主觀 SOL',r.sleep_onset_min+' 分鐘'],['最後醒來',(r.final_wake_time||r.morning_wake_time)?.slice(0,5)],['實際離床',(r.out_of_bed_time||r.wake_time)?.slice(0,5)],['夜醒',r.wakeup_count+' 次'],['主觀 WASO',r.subjective_waso_minutes==null?'未填':r.subjective_waso_minutes+' 分鐘'],['手錶',boolLabel(r.wore_watch)],['助眠藥物',boolLabel(r.sleep_medication)],['飲酒',boolLabel(r.drank_alcohol)],['品質',r.sleep_quality+'/5'],['耳機',r.headphone_min+' 分鐘']].map(([k,v])=>`<div>${k}：${text(v)}</div>`).join('')}</div></div>`).join(''):'此帳號授權範圍內沒有歷史紀錄';
 }catch(e){if(request===historyLoadRequest&&authGeneration===requestedGeneration&&currentMember===requestedMember)area.textContent=e.message;}
}
function editRecord(id){
 const r=records.find(r=>r.id===id);if(!r)return;cancelEdit();editingId=id;
 const dateOf=(s,backup)=>s?new Date(s).toLocaleDateString('sv-SE',{timeZone:'Asia/Taipei'}):backup;
 const fields={'f-name':r.name,'f-date':r.date,'f-headphone':r.headphone_min,'f-sleep-time':r.bedtime?.slice(0,5)||'','f-bed-date':dateOf(r.bedtime_at,previousDay(r.date)),'f-lights-out':r.lights_out_time?.slice(0,5)||'','f-lights-date':dateOf(r.lights_out_at,dateOf(r.bedtime_at,previousDay(r.date))),'f-sleep-onset':r.sleep_onset_min,'f-wakeups':r.wakeup_count,'f-morning-wake-time':(r.final_wake_time||r.morning_wake_time).slice(0,5),'f-wake-time':(r.out_of_bed_time||r.wake_time).slice(0,5),'f-out-date':dateOf(r.out_of_bed_at,r.date),'f-waso':r.subjective_waso_minutes??'','f-wore-watch':r.wore_watch??'','f-sleep-medication':r.sleep_medication??'','f-drank-alcohol':r.drank_alcohol??''};
 Object.entries(fields).forEach(([k,v])=>el(k).value=String(v));
 el('wake-date-hint').textContent='最後醒來日期：'+r.date;
 document.querySelectorAll('input[name=fallback]').forEach(e=>e.checked=e.value===r.fallback_sleep);
 document.querySelectorAll('#cg-disturbance input').forEach(e=>e.checked=(r.disturbance||'').split(',').includes(e.value));
 document.querySelectorAll('.radio-item,.check-item').forEach(e=>e.classList.toggle('selected',e.querySelector('input').checked));
 selectScale('scale-quality',r.sleep_quality);selectScale('scale-disturbance',r.disturbance_scale);
 dirty=false;el('diary-heading').textContent='修改歷史睡眠日誌';el('submit-btn').textContent='確認儲存修改';showPage('member-page');setStep(0,false);setRoute('diary',currentMember);
 if(r.date_definition!=='wake_date')showToast('舊紀錄請核對醒來日期與上床日期；不會自動補關燈時間','error');
}
async function openExport(){
 if(!session){postAuthAction='export';openAuth();return;}
 const generation=authGeneration,user=session.user.id;
 try{const loaded=await allRows('/sleep_logs?order=member_id,date.desc,id.asc');if(!session||generation!==authGeneration||session.user.id!==user)return;exportData=loaded;el('export-modal').classList.add('open');el('export-table-wrap').textContent=`共 ${exportData.length} 筆授權紀錄，可下載完整 CSV。`;}catch(e){showToast(e.message,'error');}
}
function closeExport(e){if(!e||e.target===el('export-modal'))el('export-modal').classList.remove('open');}
function downloadCSV(){
 if(!session||!exportData.length)return;
 const cols=Object.keys(exportData[0]);const safe=v=>{v=typeof v==='object'?JSON.stringify(v):String(v??'');if(/^[=+\-@\t\r]/.test(v))v="'"+v;return '"'+v.replace(/"/g,'""')+'"';};
 const blob=new Blob(['\uFEFF'+[cols.join(','),...exportData.map(r=>cols.map(c=>safe(r[c])).join(','))].join('\r\n')],{type:'text/csv;charset=utf-8;'});
 const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download='authorized_sleep_logs.csv';a.click();URL.revokeObjectURL(a.href);
}
let toastTimer;
function showToast(msg,type='success'){el('toast').textContent=msg;el('toast').className='toast '+type+' show';clearTimeout(toastTimer);toastTimer=setTimeout(()=>el('toast').classList.remove('show'),6500);}
async function init(){
 try{
  const response=await fetch('/api/config');if(!response.ok)throw Error('無法連線');config=await response.json();initChoiceGroups();updateAccount();lineNotice();
  ['dashboard-link','home-dashboard-link'].forEach(id=>{el(id).href='?view=workspace';});
  el('diary-form').addEventListener('input',()=>dirty=true);
  el('diary-form').addEventListener('change',()=>dirty=true);
  ['f-sleep-time','f-lights-out','f-morning-wake-time','f-wake-time'].forEach(id=>el(id).addEventListener('input',()=>{const raw=val(id);if(/^\d{4}$/.test(raw)){const clock=raw.slice(0,2)+':'+raw.slice(2);if(VTCA.validClock(clock))el(id).value=clock;}}));
  el('f-wakeups').addEventListener('change',()=>{if(val('f-wakeups')==='0'){const noWake=document.querySelector('input[name=fallback][value="無"]');noWake.checked=true;noWake.dispatchEvent(new Event('change',{bubbles:true}));}});
  el('f-date').addEventListener('change',()=>{el('wake-date-hint').textContent='最後醒來日期：'+val('f-date');if(!editingId&&val('f-date')){el('f-bed-date').value=previousDay(val('f-date'));el('f-lights-date').value=previousDay(val('f-date'));el('f-out-date').value=val('f-date');}});
  window.addEventListener('popstate',route);
  // Cloud 嵌入文件只管理自己的路由，不改寫 Streamlit 主文件的 /~/+/ 路徑。
  window.addEventListener('beforeunload',event=>{if(dirty){event.preventDefault();event.returnValue='';}});
  captureInvitation(new URLSearchParams(window.NSYSU_EMBED?window.NSYSU_EMBED.initial_query:location.search));
  el('auth-dialog').addEventListener('cancel',()=>{postAuthAction=null;el('auth-password').value='';});
  route();
 }catch(e){showPage('home-page');showToast('無法連線，請重新整理；若仍無法使用，請聯絡研究團隊','error');}finally{el('loading-screen').hidden=true;}
}
function updateAccount(){el('member-entry-help').innerHTML=session?'目前顯示已授權的受試者。選定後會保留選擇，專屬 QR Code 可直接進入睡眠日誌。':'請使用研究團隊提供的專屬 QR Code；研究人員可登入管理工作區選擇受試者。';el('account-chip').textContent=session?'管理者已登入':'';el('signout-btn').hidden=!session;el('admin-login-button').hidden=!!session;el('archived-filter-row').hidden=!session;}
function setRoute(view,member){const params=new URLSearchParams();if(view!=='home')params.set('view',view);if(member)params.set('member',member);if(member&&member===invitationMember&&invitationToken)params.set('invite',invitationToken);const target=new URLSearchParams(window.NSYSU_EMBED?window.NSYSU_EMBED.initial_query:location.search).get('date');if(target&&member)params.set('date',target);if(window.NSYSU_EMBED){window.NSYSU_EMBED.initial_query=params.toString();return;}const url=location.pathname+(params.size?'?'+params:'');if(location.pathname+location.search!==url)history.pushState({},'',url);}
function goHome(event){event?.preventDefault();if(saving)return;showPage('home-page');setRoute('home');}
function startDiary(){if(saving)return;if(session){showMemberEntry('diary');return;}postAuthAction='entry';setRoute('start');openAuth();}
function showMemberEntry(purpose){entryPurpose=purpose;clearParticipantSelection();el('entry-purpose').textContent=purpose==='history'?'歷史紀錄':'填寫睡眠日誌';el('entry-submit').textContent=purpose==='history'?'查看歷史紀錄 →':'在這台裝置填寫 →';el('member-entry').value='';el('entry-error').hidden=true;showPage('entry-page');setRoute(purpose==='history'?'history':'start');el('member-entry').focus();if(!directoryLoaded)loadParticipants();}
function enterMember(event){event.preventDefault();if(!selectedParticipant){const row=participants.find(p=>p.member_id===val('member-entry').trim().toLowerCase());if(row)selectParticipant(row.member_id);else{el('entry-error').textContent='請先從下拉清單選擇一位受試者，再繼續。';el('entry-error').hidden=false;return;}}const mid=selectedParticipant.member_id;closeParticipantOptions();if(entryPurpose==='history'){currentMember=mid;showHistory();}else openMember(mid);}
function showHistory(event){event?.preventDefault();if(saving)return;showPage('history-page');setRoute('history',currentMember);renderHistoryParticipants();loadHistoryParticipants();loadHistory();}
function openAuth(){if(!postAuthAction&&el('history-page').classList.contains('active'))postAuthAction='history';el('auth-status').textContent='';el('auth-title').textContent='管理者登入';el('auth-dialog').showModal();el('auth-email').focus();}
function closeAuth(){el('auth-dialog').close();el('auth-password').value='';postAuthAction=null;}
function startAnother(){if(saving)return;if(dirty&&!confirm('要清除尚未送出的內容，重新開始嗎？'))return;if(!currentMember){showMemberEntry('diary');return;}dirty=false;openMember(currentMember);}
function resetDiary(){if(!dirty||confirm('要清除尚未送出的內容嗎？'))cancelEdit();}
function setStep(step,focus=true){currentStep=step;document.querySelectorAll('[data-step]').forEach(panel=>panel.hidden=+panel.dataset.step!==step);document.querySelectorAll('[data-step-marker]').forEach(marker=>{const i=+marker.dataset.stepMarker;marker.classList.toggle('complete',i<step);if(i===step)marker.setAttribute('aria-current','step');else marker.removeAttribute('aria-current');});el('previous-step').hidden=step===0;el('next-step').hidden=step===3;el('submit-btn').hidden=step!==3;el('step-count').textContent=`第 ${step+1} 步，共 4 步`;el('form-error').hidden=true;document.querySelectorAll('[aria-invalid]').forEach(input=>input.removeAttribute('aria-invalid'));if(step===3)renderReview();window.scrollTo(0,0);if(focus)document.querySelector(`[data-step="${step}"] h2`).focus();}
function validateStep(step){
 if(step===0){if(!val('f-name').trim())fail('請填寫姓名','f-name');if(!val('f-date'))fail('請選擇最後醒來的日期','f-date');VTCA.anchored(val('f-date'),'12:00');integer('f-headphone',0,600);}
 if(step===1){for(const id of ['f-sleep-time','f-morning-wake-time','f-wake-time'])if(!VTCA.validClock(val(id)))fail('請使用 24 小時 HH:mm，例如 22:30 或 00:15',id);if(val('f-lights-out')&&!VTCA.validClock(val('f-lights-out')))fail('關燈時間請使用 HH:mm，或留空','f-lights-out');VTCA.diaryTimes({date:val('f-date'),bedDate:val('f-bed-date'),bed:val('f-sleep-time'),lightsDate:val('f-lights-date'),lights:val('f-lights-out'),wake:val('f-morning-wake-time'),outDate:val('f-out-date'),out:val('f-wake-time')});integer('f-sleep-onset',0,300);}
 if(step===2){const wakes=integer('f-wakeups',0,20);const fallback=document.querySelector('input[name=fallback]:checked');if(!fallback)fail('請選擇醒來後能否睡回去','rg-fallback');if((wakes===0)!==(fallback.value==='無'))fail('請核對夜醒次數與醒後能否睡回去的回答','f-wakeups');if(val('f-waso')!=='')integer('f-waso',0,1440);if(!document.querySelector('#cg-disturbance input:checked'))fail('請選擇干擾因素；若沒有，請選「無」','cg-disturbance');if(getScale('scale-disturbance')===null)fail('請選擇干擾程度','scale-disturbance');if(getScale('scale-quality')===null)fail('請選擇整體睡眠品質','scale-quality');}
}
function showFormError(error){el('form-error').textContent=error.message;el('form-error').hidden=false;const field=error.field&&el(error.field);if(field){const input=field.matches('input,select')?field:field.querySelector('input,button');input?.setAttribute('aria-invalid','true');input?.focus();}else el('form-error').scrollIntoView({block:'center'});}
function nextStep(){try{validateStep(currentStep);setStep(currentStep+1);}catch(error){showFormError(error);}}
function previousStep(){if(!saving&&currentStep>0)setStep(currentStep-1);}
function handleDiarySubmit(event){event.preventDefault();if(currentStep<3)nextStep();else submitRecord();}
function reviewList(pairs){return `<dl class="review-list">${pairs.map(([label,value])=>`<div><dt>${text(label)}</dt><dd>${text(value)}</dd></div>`).join('')}</dl>`;}
function renderReview(){const fallback=document.querySelector('input[name=fallback]:checked')?.value||'未填';const groups=[['基本資料',0,[['姓名',val('f-name')],['最後醒來日期',val('f-date')],['耳機使用',val('f-headphone')+' 分鐘'],['配戴手錶',boolLabel(VTCA.tri(val('f-wore-watch')))],['助眠藥物',boolLabel(VTCA.tri(val('f-sleep-medication')))],['飲酒',boolLabel(VTCA.tri(val('f-drank-alcohol')))]]],['睡眠時間',1,[['上床',val('f-bed-date')+' '+val('f-sleep-time')],['開始嘗試入睡',val('f-lights-out')?val('f-lights-date')+' '+val('f-lights-out'):'未填'],['自覺入睡所需時間',val('f-sleep-onset')+' 分鐘'],['最後醒來',val('f-date')+' '+val('f-morning-wake-time')],['實際離床',val('f-out-date')+' '+val('f-wake-time')]]],['夜間狀況',2,[['夜醒次數',val('f-wakeups')+' 次'],['醒後狀況',fallback],['夜間清醒總時間',val('f-waso')===''?'未填':val('f-waso')+' 分鐘'],['干擾因素',[...document.querySelectorAll('#cg-disturbance input:checked')].map(i=>i.value).join('、')],['干擾程度',getScale('scale-disturbance')+'／5'],['睡眠品質',getScale('scale-quality')+'／5']]]];el('review-area').innerHTML=groups.map(([title,step,pairs])=>`<div class="review-block"><div class="review-heading"><h3>${title}</h3><button type="button" class="btn btn-text" onclick="setStep(${step})">修改${title}</button></div>${reviewList(pairs)}</div>`).join('');}
function route(){const params=new URLSearchParams(window.NSYSU_EMBED?window.NSYSU_EMBED.initial_query:location.search),mid=params.get('member'),view=params.get('view');captureInvitation(params);const valid=mid&&/^ycc\d{8}$/.test(mid);if(valid)currentMember=mid;if(view==='workspace')goWorkspace();else if(view==='qr'){if(valid)currentMember=mid;goQR();}else if(view==='members'){if(session)goAdmin();else goWorkspace();}else if(view==='history'){currentMember=valid?mid:null;showHistory();}else if(valid&&view!=='submitted')openMember(mid);else if(view==='start')startDiary();else goHome();}
init();
