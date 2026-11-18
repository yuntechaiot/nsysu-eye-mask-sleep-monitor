'use strict';
const dashboardPeers=new Set(),dashboardFrames=new Set();
function researchOpener(){let frame=window;for(let depth=0;depth<8;depth++){try{if(frame.opener)return frame.opener;const next=frame.parent;if(!next||next===frame)break;frame=next;}catch{return null;}}return null;}
function researchWindowContains(root,source){for(let depth=0;source&&depth<8;depth++){if(source===root)return true;try{const next=source.parent;if(!next||next===source)break;source=next;}catch{return false;}}return false;}
function notifyResearchLogout(){if(config?.dashboard_url)for(const frame of dashboardFrames)frame.postMessage({type:'nsysu:logout'},new URL(config.dashboard_url,location.href).origin);}
function notifyResearchSession(){if(session&&config?.dashboard_url)for(const frame of dashboardFrames)frame.postMessage({type:'nsysu:session-update',session},new URL(config.dashboard_url,location.href).origin);}
async function restoreResearchSession(){
 const query=window.NSYSU_EMBED?window.NSYSU_EMBED.initial_query:location.search;
 if(!config?.dashboard_url)return;
 const origin=new URL(config.dashboard_url,location.href).origin;
 if(new URLSearchParams(query).get('auth_return')!=='1'&&sessionStorage.getItem('nsysu-research-return-origin')!==origin)return;
 const peer=researchOpener();
 if(!peer)return;
 const nonce=crypto.randomUUID(),generation=authGeneration;
 await new Promise(resolve=>{
  let pending=true;
  const finish=()=>{if(!pending)return;pending=false;clearTimeout(timer);removeEventListener('message',receive);resolve();};
  const receive=event=>{
   if(!pending||event.source!==peer||event.origin!==origin||event.data?.type!=='nsysu:return-session'||event.data.nonce!==nonce)return;
   if(generation!==authGeneration){finish();return;}
   const saved=event.data.session;
   if(saved===null){session=null;authGeneration++;sessionStorage.removeItem('vtca-session');sessionStorage.removeItem('nsysu-research-return-origin');}
   else if(saved?.user?.app_metadata?.diary_staff===true&&typeof saved.user.id==='string'&&typeof saved.access_token==='string'&&typeof saved.refresh_token==='string'){
    session=saved;authGeneration++;sessionStorage.setItem('vtca-session',JSON.stringify(saved));sessionStorage.setItem('nsysu-research-return-origin',origin);dashboardPeers.add(peer.parent||peer);dashboardFrames.add(peer);
   }
   finish();
  };
  const timer=setTimeout(finish,1500);addEventListener('message',receive);
  try{peer.postMessage({type:'nsysu:return-session-request',nonce},origin);}catch{finish();}
 });
}
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
 if(!config?.dashboard_url||event.origin!==new URL(config.dashboard_url,location.href).origin||![...dashboardPeers].some(peer=>researchWindowContains(peer,event.source)))return;
 if(event.data?.type==='nsysu:session-request'&&typeof event.data.nonce==='string'){dashboardFrames.add(event.source);event.source.postMessage({type:'nsysu:session',nonce:event.data.nonce,session},event.origin);}
 if(event.data?.type==='nsysu:logout')void signOut(true);
 if(event.data?.type==='nsysu:session-update'&&session&&event.data.session?.user?.app_metadata?.diary_staff===true&&event.data.session.user.id===session.user.id){session=event.data.session;sessionStorage.setItem('vtca-session',JSON.stringify(session));}
});
function lineNotice(){
 if((config.simulated||config.live_demo)&&!el('test-mode-notice')){const notice=document.createElement('p');notice.id='test-mode-notice';notice.className='info-box';notice.textContent=config.live_demo?'本機 LINE 實測：日誌僅保存於隔離測試資料庫。':'隔離驗收模式：合成資料，不發送真實 LINE 訊息。';document.getElementById('main').prepend(notice);}
 const info=config.line;const node=el('line-notice');if(!node||!info?.official_id||!info.join_url)return;
 node.hidden=false;node.replaceChildren();const p=document.createElement('p');p.textContent=`官方 LINE：${info.official_id}。加入後，請依 LINE 訊息完成帳號綁定，以接收睡眠日誌提醒。`;
 const a=document.createElement('a');a.href=info.join_url;a.textContent='加入官方 LINE';a.className='btn';a.target='_blank';a.rel='noopener noreferrer';node.append(p,a);
}
