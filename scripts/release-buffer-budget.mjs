// Release checks run in a private process. Collect dead decoded containers
// before allocating another firmware-sized buffer, including synchronous audits.
export function installReleaseBufferCollection(collect=global.gc,threshold=32*1024*1024){
 if(typeof collect!=='function')throw new TypeError('release buffer collection requires exposed GC');
 const original=new Map(),names=['alloc','allocUnsafe','from'];
 let collecting=false,restored=false;
 function before(bytes){
  if(bytes>=threshold&&!collecting){
   collecting=true;try{collect();if(process.env.M10V_RELEASE_MEMORY_AUDIT==='1')console.error(JSON.stringify({phase:'buffer-allocation',bytes,...process.memoryUsage(),stack:new Error().stack.split('\n').slice(2,6)}));}finally{collecting=false;}
  }
 }
 for(const name of names){
  const fn=Buffer[name];original.set(name,fn);
  Buffer[name]=function(...args){
   const value=args[0];
   before(name==='from'?(value?.byteLength??0):value);
   return Reflect.apply(fn,this,args);
  };
 }
 return ()=>{
  if(restored)return;
  restored=true;
  for(const [name,fn] of original)Buffer[name]=fn;
 };
}
