'use strict';
let participantQRGeneration=0;
function clearParticipantQR(){
 participantQRGeneration++;el('self-qr-password').value='';el('self-qr-link').value='';el('self-qr-open').removeAttribute('href');el('self-qr-title').textContent='';el('self-qr-image').replaceChildren();el('self-qr-image').removeAttribute('title');el('self-qr-result').hidden=true;el('self-qr-form').hidden=false;el('self-qr-submit').disabled=false;el('self-qr-status').textContent='';
}
function openParticipantQR(event){event?.preventDefault();clearParticipantQR();el('self-qr-account').value='';el('self-qr-dialog').showModal();el('self-qr-account').focus();}
function closeParticipantQR(event){event?.preventDefault();clearParticipantQR();el('self-qr-dialog').close();}
async function submitParticipantQR(event){
 event.preventDefault();const generation=++participantQRGeneration,account=val('self-qr-account').trim(),password=val('self-qr-password');el('self-qr-password').value='';
 el('self-qr-submit').disabled=true;el('self-qr-status').textContent='正在核對帳號…';
 try{
  const response=await fetch('/api/participant/diary-access',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({account,password})});
  const result=await response.json();if(generation!==participantQRGeneration||!el('self-qr-dialog').open)return;
  if(!response.ok)throw Error(result.error||'研究帳號或密碼不正確，請核對後重試。');
  const url=new URL(result.diary_url),expected=new URL(config.diary_url,location.href);
  if(result.status!=='verified_research_account'||result.member_id!==account||url.origin!==expected.origin||url.searchParams.get('member')!==account||!/^[a-f0-9]{64}$/.test(url.searchParams.get('invite')||''))throw Error('日誌入口核對未完成，請稍後再試。');
  await ensureQRCode();if(generation!==participantQRGeneration||!el('self-qr-dialog').open)return;
  el('self-qr-title').textContent=account+' 的睡眠日誌填寫入口';el('self-qr-link').value=url.href;el('self-qr-open').href=url.href;
  el('self-qr-image').replaceChildren();new QRCode(el('self-qr-image'),{text:url.href,width:256,height:256,colorDark:'#172033',correctLevel:QRCode.CorrectLevel.M});
  el('self-qr-form').hidden=true;el('self-qr-result').hidden=false;el('self-qr-status').textContent='已取得本人的日誌 QR Code 與連結。';
 }catch(error){if(generation===participantQRGeneration)el('self-qr-status').textContent=error.message==='Failed to fetch'?'連線未完成，請稍後重試。':error.message;}
 finally{if(generation===participantQRGeneration)el('self-qr-submit').disabled=false;}
}
async function copySelfDiaryLink(){try{await navigator.clipboard.writeText(val('self-qr-link'));el('self-qr-status').textContent='已複製日誌連結。';}catch{el('self-qr-link').focus();el('self-qr-link').select();el('self-qr-status').textContent='請長按或按 Ctrl+C 複製連結。';}}
