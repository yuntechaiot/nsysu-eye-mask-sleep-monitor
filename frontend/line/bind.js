'use strict';
const byId=id=>document.getElementById(id);let idToken=null;
async function identity(){
 byId('bind-button').disabled=true;byId('retry').hidden=true;
 try{
  const response=await fetch('/api/line/config');const cfg=await response.json();if(!response.ok)throw Error(cfg.error||'暫時無法連線，請稍後重試。');
  byId('test-label').hidden=!(cfg.simulated||cfg.live_demo);
  if(cfg.live_demo)byId('test-label').textContent='本機 LINE 實測：LINE 身分與訊息為真實，日誌使用隔離測試資料。';
  if(cfg.simulated){const r=await fetch('/acceptance/identity');if(!r.ok)throw Error('請先在隔離驗收工具模擬加入好友。');idToken=(await r.json()).id_token;}
  else{
   if(new URLSearchParams(location.search).get('error'))throw Error('LINE 授權已取消，請按「重新確認 LINE 身分」再試。');
   if(!cfg.liff_id)throw Error('綁定服務尚未開通，請聯絡研究團隊。');
   if(!window.liff)await new Promise((resolve,reject)=>{const script=document.createElement('script');script.src='https://static.line-scdn.net/liff/edge/2/sdk.js';script.onload=resolve;script.onerror=()=>reject(Error('無法載入 LINE，請檢查連線後重試。'));document.head.appendChild(script);});
   await liff.init({liffId:cfg.liff_id});
   if(!liff.isLoggedIn()){liff.login({redirectUri:location.origin+'/line'});return;}
   idToken=liff.getIDToken();if(!idToken)throw Error('LINE 授權已取消或到期，請回到 LINE 重新開啟「開始綁定」。');
  }
  byId('identity-status').textContent='請填寫研究團隊配發的帳號。';byId('bind-button').disabled=false;
 }catch(error){byId('identity-status').textContent=error.message;byId('retry').hidden=false;}
}
byId('retry').onclick=()=>{history.replaceState({},'',location.pathname);identity();};
byId('bind-form').onsubmit=async event=>{
 event.preventDefault();byId('error').hidden=true;byId('bind-button').disabled=true;byId('bind-button').textContent='正在確認並綁定…';
 try{
  const response=await fetch('/api/line/bind',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({id_token:idToken,account:byId('account').value.trim(),password:byId('password').value})});
  const result=await response.json();if(!response.ok)throw Error(result.error||'連線未完成，請重試。');
  if(result.status!=='bound'||!result.first_reminder_at)throw Error('尚未確認綁定成功，請重試。');
  byId('password').value='';byId('bind-form').hidden=true;byId('identity-status').hidden=true;byId('success').hidden=false;
  const formatted=new Intl.DateTimeFormat('zh-TW',{timeZone:'Asia/Taipei',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',hour12:true}).format(new Date(result.first_reminder_at));
  byId('first-reminder').textContent='首次睡眠日誌提醒：'+formatted+'。';byId('success').focus();
 }catch(error){byId('error').textContent=error.message==='Failed to fetch'?'網路中斷，尚未確認成功；請恢復連線後重試。':error.message;byId('error').hidden=false;}
 finally{byId('bind-button').disabled=false;byId('bind-button').textContent='確認綁定';}
};
identity();
