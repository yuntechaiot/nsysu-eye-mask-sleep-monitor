/* Visible feedback for application requests, including concurrent requests. */
(function(root){
 'use strict';
 const doc=root.document,status=doc.getElementById('request-status');
 if(!status)return;
 const message=status.querySelector('[data-request-message]'),network=root.fetch.bind(root);
 let pending=0,slowTimer=null,lastControl=null;
 doc.addEventListener('pointerdown',event=>{lastControl=event.target.closest?.('button,a,[role="button"]')||null;},true);
 function place(){
  const control=lastControl?.isConnected&&lastControl.getClientRects().length?lastControl:doc.activeElement;
  if(control?.matches('button,a,input,select,textarea')&&control.getClientRects().length){
   const anchor=control.closest('.step-actions,.form-row')||control;
   anchor.insertAdjacentElement('beforebegin',status);
  }else{
   const host=doc.querySelector('dialog[open] form,.page.active')||doc.getElementById('main');
   host?.prepend(status);
  }
 }
 root.fetch=async function(...args){
  if(pending++===0){
   place();message.textContent='正在處理，請稍候…';status.hidden=false;
   slowTimer=root.setTimeout(()=>{message.textContent='連線較慢，仍在處理中，請稍候並避免重複送出。';},8000);
  }
  try{return await network(...args);}
  finally{if(--pending===0){root.clearTimeout(slowTimer);slowTimer=null;status.hidden=true;}}
 };
})(window);
