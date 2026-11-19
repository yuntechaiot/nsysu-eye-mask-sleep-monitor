/* One copy catalog for the cloud sender and the isolated Python preview. */
import copy from './messages.json' with {type:'json'};

export function lineText(name,values={}){
 return copy[name].replace(/\{(\w+)\}/g,(_,key)=>{
  if(values[key]===undefined)throw new Error('Missing LINE message context');
  return String(values[key]);
 });
}
export function reminderText(member,day,slot){
 return lineText(slot==='09:00'?'morning':'follow_up')+'\n'+lineText('diary_context',{member,day:day.replaceAll('-','/')});
}
export function bindingText(member,start,day){
 const values={member,start:start.replaceAll('-','/')};
 return day?lineText('binding_test',{...values,day:day.replaceAll('-','/')}):lineText('binding_success',values);
}
