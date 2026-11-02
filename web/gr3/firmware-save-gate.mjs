// Acceptance is scoped to one save attempt and its exact source/configuration.
export function createFirmwareSaveGate({dialog,trigger,cancel,confirm,readSnapshot,save,canSave=()=>true,onOpen=()=>{}}) {
 let snapshot=null,busy=false,focusTarget=trigger;
 const current=()=>snapshot&&JSON.stringify(readSnapshot())===JSON.stringify(snapshot);
 const dismiss=()=>{snapshot=null;if(dialog.open)dialog.close();focusTarget.focus({preventScroll:true});};
 cancel.addEventListener('click',dismiss);
 dialog.addEventListener('cancel',()=>{snapshot=null;focusTarget.focus({preventScroll:true});});
 dialog.addEventListener('close',()=>{snapshot=null;});
 confirm.addEventListener('click',async()=>{
  if(busy||!dialog.open||!current())return dismiss();
  if(!canSave())return;
  const accepted=snapshot;busy=true;confirm.disabled=true;dialog.close();snapshot=null;
  try{await save(accepted);}finally{busy=false;confirm.disabled=false;focusTarget.focus({preventScroll:true});}
 });
 const refresh=()=>{confirm.disabled=busy||!canSave();};
 return {refresh,open(sourceTrigger=trigger){if(busy||dialog.open||sourceTrigger.disabled)return;focusTarget=sourceTrigger;snapshot=readSnapshot();onOpen();refresh();dialog.showModal();cancel.focus({preventScroll:true});dialog.scrollTop=0;}};
}
