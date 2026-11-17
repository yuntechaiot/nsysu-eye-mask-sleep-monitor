'use strict';
const dashboardPeers=new Set(),dashboardFrames=new Set();
function notifyResearchLogout(){if(config?.dashboard_url)for(const frame of dashboardFrames)frame.postMessage({type:'nsysu:logout'},new URL(config.dashboard_url,location.href).origin);}
async function workspaceAuth(action='workspace'){
 if(session){
  try{const allowed=await diaryRPC('diary_staff_status',{});if(allowed===true)return true;}
  catch(error){if(!/到期|權限/.test(error.message)){showToast(error.message,'error');return false;}}
  await signOut(true);
 }
 postAuthAction=action;openAuth();return false;
}
async function goWorkspace(event){event?.preventDefault();setRoute('workspace');if(!await workspaceAuth())return;showPage('workspace-page');}
async function goQR(event){
 event?.preventDefault();setRoute('qr',currentMember||sessionStorage.getItem('nsysu-selected-member'));
 if(!await workspaceAuth('qr'))return;
 const prior=currentMember||sessionStorage.getItem('nsysu-selected-member');
 showMemberEntry('diary');setRoute('qr',prior);
 if(await loadParticipants()&&prior&&participants.some(p=>p.member_id===prior))await selectParticipant(prior,false);
}
async function openResearch(event){
 event?.preventDefault();if(!await workspaceAuth('research'))return;
 const url=new URL(config.dashboard_url,location.href);const mid=currentMember||sessionStorage.getItem('nsysu-selected-member');if(mid)url.searchParams.set('member',mid);
 const peer=window.open(url.href,'nsysu-research');if(peer)dashboardPeers.add(peer);else showToast('請允許此網站開啟研究資料分頁。','error');
}
addEventListener('message',event=>{
 if(!config?.dashboard_url||event.origin!==new URL(config.dashboard_url,location.href).origin||![...dashboardPeers].some(peer=>peer===event.source||peer===event.source?.parent))return;
 if(event.data?.type==='nsysu:session-request'&&typeof event.data.nonce==='string'){dashboardFrames.add(event.source);event.source.postMessage({type:'nsysu:session',nonce:event.data.nonce,session},event.origin);}
 if(event.data?.type==='nsysu:logout')void signOut(true);
 if(event.data?.type==='nsysu:session-update'&&event.data.session?.user?.app_metadata?.diary_staff===true&&(!session||event.data.session.user.id===session.user.id)){session=event.data.session;sessionStorage.setItem('vtca-session',JSON.stringify(session));}
});
function lineNotice(){
 if((config.simulated||config.live_demo)&&!el('test-mode-notice')){const notice=document.createElement('p');notice.id='test-mode-notice';notice.className='info-box';notice.textContent=config.live_demo?'本機 LINE 實測：日誌僅保存於隔離測試資料庫。':'隔離驗收模式：合成資料，不發送真實 LINE 訊息。';document.getElementById('main').prepend(notice);}
 const info=config.line;const node=el('line-notice');if(!node||!info?.official_id||!info.join_url)return;
 node.hidden=false;node.replaceChildren();const p=document.createElement('p');p.textContent=`官方 LINE：${info.official_id}。加入後，請依 LINE 訊息完成帳號綁定，以接收睡眠日誌提醒。`;
 const a=document.createElement('a');a.href=info.join_url;a.textContent='加入官方 LINE';a.className='btn';a.target='_blank';a.rel='noopener noreferrer';node.append(p,a);
}
