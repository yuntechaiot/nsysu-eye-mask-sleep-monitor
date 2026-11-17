'use strict';
// Invitation codes are public; names are supplied only through the caller's RLS.
let participants=[], canManageParticipants=false, selectedParticipant=null;
let participantOptions=[], participantOptionIndex=-1, directoryRequest=0, directoryLoaded=false;
let qrReady=null;
function participantLabel(row){return (row.display_name?`${row.member_id} · ${row.display_name}`:row.member_id)+(row.archived_at?'（已移除）':'');}
function participantURL(mid){const token=invitationCache.get(mid)?.invite;if(!token)return '';const url=new URL(VTCA.diaryLink(window.NSYSU_EMBED?config.diary_url:location.origin+location.pathname,config.diary_url,mid));url.searchParams.set('invite',token);return url.href;}
function ensureQRCode(){
 if(typeof QRCode!=='undefined')return Promise.resolve();
 if(qrReady)return qrReady;
 qrReady=new Promise((resolve,reject)=>{
  const script=document.createElement('script');script.src='/web/qrcode.min.js';script.dataset.qr='true';
  script.onload=()=>resolve();script.onerror=()=>{script.remove();qrReady=null;reject(Error('QR Code 載入失敗，請重新載入頁面；仍可複製填寫連結。'));};document.head.appendChild(script);
 });return qrReady;
}
function setDirectoryStatus(message,failed=false){
 ['directory-status','admin-directory-status'].forEach(id=>el(id).textContent=message);
 ['directory-retry','admin-directory-retry'].forEach(id=>el(id).hidden=!failed);
}
async function loadParticipants(){
 const requestId=++directoryRequest,generation=authGeneration;
 setDirectoryStatus('正在載入受試者清單…');
 try{
  const headers=await authHeaders();
  const response=await fetch('/api/participants'+(session&&el('show-archived').checked?'?include_archived=1':''),{headers:headers.Authorization?{Authorization:headers.Authorization}:{}});
  const result=await response.json();if(!response.ok)throw Error(result.error||'無法載入受試者清單');
  if(generation!==authGeneration||requestId!==directoryRequest)return false;
  participants=result.participants;canManageParticipants=result.can_manage===true;directoryLoaded=true;
  setDirectoryStatus(`共 ${participants.length} 位受試者${session?' · 姓名依帳號授權顯示':' · 公開清單僅顯示編號'}`);
  el('stat-participants').textContent=participants.length;
  if(selectedParticipant){const row=participants.find(p=>p.member_id===selectedParticipant.member_id);if(row)selectParticipant(row.member_id,false);else clearParticipantSelection();}
  if(el('member-entry').getAttribute('aria-expanded')==='true')renderParticipantOptions();
  buildAdminGrid();return true;
 }catch(error){
  if(generation!==authGeneration||requestId!==directoryRequest)return false;
  setDirectoryStatus(error.message,true);return false;
 }
}
function clearParticipantSelection(){selectedParticipant=null;el('participant-share').hidden=true;el('selected-member-label').textContent='';el('selected-qr').replaceChildren();el('participant-link').value='';el('qr-network-hint').hidden=true;}
function clearParticipantNames(){
 directoryRequest++;canManageParticipants=false;participants=participants.map(p=>({member_id:p.member_id,display_name:null}));
 if(selectedParticipant){const mid=selectedParticipant.member_id;selectParticipant(mid,false);}
 renderParticipantOptions();buildAdminGrid();el('new-member-name').value='';closeParticipantDialog();
}
function searchParticipants(){clearParticipantSelection();el('entry-error').hidden=true;openParticipantOptions();}
function openParticipantOptions(){el('participant-options').hidden=false;el('member-entry').setAttribute('aria-expanded','true');renderParticipantOptions();}
function closeParticipantOptions(){el('participant-options').hidden=true;el('member-entry').setAttribute('aria-expanded','false');el('member-entry').removeAttribute('aria-activedescendant');participantOptionIndex=-1;}
function toggleParticipantOptions(){if(el('participant-options').hidden){el('member-entry').focus();openParticipantOptions();}else closeParticipantOptions();}
function renderParticipantOptions(){
 const query=selectedParticipant&&val('member-entry')===participantLabel(selectedParticipant)?'':val('member-entry');
 participantOptions=participants.filter(row=>VTCA.participantMatches(row,query));participantOptionIndex=-1;el('member-entry').removeAttribute('aria-activedescendant');
 const list=el('participant-options');list.replaceChildren();
 if(!participantOptions.length){const empty=document.createElement('div');empty.className='option-empty';empty.textContent=directoryLoaded?'找不到符合的受試者，請改用其他關鍵字。':'清單尚未載入，請稍候或按「重新載入清單」。';list.appendChild(empty);return;}
 participantOptions.forEach((row,index)=>{
  const option=document.createElement('div');option.id='participant-option-'+index;option.className='participant-option';option.setAttribute('role','option');option.setAttribute('aria-selected',String(row.member_id===selectedParticipant?.member_id));option.textContent=participantLabel(row);
  option.addEventListener('mousedown',event=>event.preventDefault());option.addEventListener('click',()=>selectParticipant(row.member_id));list.appendChild(option);
 });
}
function participantKeydown(event){
 if(event.key==='Escape'){closeParticipantOptions();return;}
 if(event.key==='ArrowDown'||event.key==='ArrowUp'){
  event.preventDefault();if(el('participant-options').hidden)openParticipantOptions();if(!participantOptions.length)return;
  participantOptionIndex=(participantOptionIndex+(event.key==='ArrowDown'?1:-1)+participantOptions.length)%participantOptions.length;
  [...el('participant-options').children].forEach((option,i)=>option.classList.toggle('option-active',i===participantOptionIndex));
  const option=el('participant-option-'+participantOptionIndex);el('member-entry').setAttribute('aria-activedescendant',option.id);option.scrollIntoView({block:'nearest'});
 }else if(event.key==='Enter'&&!el('participant-options').hidden){event.preventDefault();const row=participantOptions[participantOptionIndex<0?0:participantOptionIndex];if(row)selectParticipant(row.member_id);}
 else if(event.key==='Tab')closeParticipantOptions();
}
async function selectParticipant(mid,focus=true){
 const row=participants.find(p=>p.member_id===mid);if(!row)return;
 const generation=authGeneration;
 currentMember=mid;sessionStorage.setItem('nsysu-selected-member',mid);if(new URLSearchParams(window.NSYSU_EMBED?window.NSYSU_EMBED.initial_query:location.search).get('view')==='qr')setRoute('qr',mid);
 selectedParticipant=row;el('member-entry').value=participantLabel(row);el('selected-member-label').textContent=participantLabel(row);el('entry-error').hidden=true;
 el('entry-submit').disabled=!!row.archived_at;
 closeParticipantOptions();el('participant-share').hidden=entryPurpose==='history';
 el('participant-link').value='';el('copy-participant-link').disabled=true;el('selected-qr').replaceChildren();
 el('participant-manage-actions').hidden=!canManageParticipants;
 el('archive-participant').hidden=!!row.archived_at;el('restore-participant').hidden=!row.archived_at;
 if(row.archived_at){el('selected-qr').textContent='此受試者已移除，固定 QR Code 已停用。';el('invitation-status').textContent='還原後會恢復原固定 QR Code，既有歷史資料保留。';return;}
 el('qr-network-hint').hidden=true;
 if(focus){el('member-entry').focus({preventScroll:true});closeParticipantOptions();}
 if(entryPurpose==='history')return;
 if(!session){el('selected-qr').textContent='登入後顯示固定 QR Code';el('invitation-status').textContent='請使用上方「登入」管理資料；登入後會自動顯示，不必手動產生。';return;}
 el('selected-qr').textContent='正在載入固定 QR Code…';el('invitation-status').textContent='正在取得這位受試者的固定連結…';
 try{
  if(!invitationCache.has(mid))await loadFixedInvitation(mid);
  if(generation!==authGeneration||!session||selectedParticipant?.member_id!==mid)return;
  const url=participantURL(mid);el('participant-link').value=url;el('copy-participant-link').disabled=!url;
  el('invitation-status').textContent='每次使用相同 QR Code，不會在 30 天後到期；請只提供給這位受試者本人。';
  const local=['localhost','127.0.0.1','[::1]'].includes(new URL(url).hostname);
  el('qr-network-hint').hidden=!local;el('qr-network-hint').textContent='目前是本機網址，手機無法使用這個 QR Code。請從正式網站提供專屬填寫連結。';
  await ensureQRCode();if(generation!==authGeneration||!session||selectedParticipant?.member_id!==mid||participantURL(mid)!==url)return;
  el('selected-qr').replaceChildren();new QRCode(el('selected-qr'),{text:url,width:164,height:164,colorDark:'#3C3489',correctLevel:QRCode.CorrectLevel.M});
 }catch(error){if(generation===authGeneration&&selectedParticipant?.member_id===mid){el('selected-qr').textContent='固定 QR Code 尚未載入';el('invitation-status').textContent=error.message+' 請重新選擇受試者後重試。';}}
}
async function copyParticipantLink(){
 try{await navigator.clipboard.writeText(val('participant-link'));showToast('已複製受試者填寫連結');}
 catch{el('participant-link').focus();el('participant-link').select();showToast('請按 Ctrl+C 或長按複製上方連結。');}
}
async function openParticipantDialog(){
 el('participant-create-status').textContent='';el('participant-form').hidden=true;el('participant-access-help').hidden=false;
 el('participant-login').hidden=!!session;
 if(!el('participant-dialog').open)el('participant-dialog').showModal();
 if(session){
  const loaded=await loadParticipants();if(!el('participant-dialog').open)return;
  if(!loaded){el('participant-create-status').textContent='請先確認受試者清單載入成功後重試。';return;}
  el('participant-form').hidden=!canManageParticipants;el('participant-access-help').hidden=canManageParticipants;
  if(canManageParticipants)el('new-member-id').focus();else el('participant-create-status').textContent='目前帳號尚未開通受試者管理權限，請聯絡專案管理員。';
 }
}
function closeParticipantDialog(){el('participant-dialog').close();}
function loginForParticipants(){closeParticipantDialog();postAuthAction='participants';openAuth();}
async function createParticipant(event){
 event.preventDefault();const button=el('create-participant');button.disabled=true;el('participant-create-status').textContent='正在新增…';
 try{
  const headers=await authHeaders();const generation=authGeneration;
  const response=await fetch('/api/participants',{method:'POST',headers:{...headers},body:JSON.stringify({member_id:val('new-member-id').trim(),display_name:val('new-member-name').trim()||null})});
  const result=await response.json();if(!response.ok)throw Error(result.error||'新增未完成，請重試');
  if(generation!==authGeneration)return;
  el('new-member-id').value='';el('new-member-name').value='';closeParticipantDialog();
  const loaded=await loadParticipants();if(generation!==authGeneration)return;
  if(!loaded&&!participants.some(p=>p.member_id===result.participant.member_id))participants.push(result.participant);
  showMemberEntry('diary');selectParticipant(result.participant.member_id);showToast('受試者已新增，固定 QR Code 會自動顯示');
 }catch(error){el('participant-create-status').textContent=error.message;}finally{button.disabled=false;}
}
document.addEventListener('click',event=>{if(!el('participant-combobox')?.contains(event.target))closeParticipantOptions();});
