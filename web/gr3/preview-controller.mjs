import {renderPreviewPixels} from './film-preview.mjs';
const sourcePromises=new Map();
function loadSource(width,height){
 const key=width+'x'+height;
 if(!sourcePromises.has(key))sourcePromises.set(key,new Promise((resolve,reject)=>{
  const image=new Image();image.onload=()=>{const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
   const context=canvas.getContext('2d',{willReadFrequently:true});context.drawImage(image,0,0,width,height);
   resolve(context.getImageData(0,0,width,height));};image.onerror=()=>{sourcePromises.delete(key);reject(new Error('样张载入失败'));};
  image.src='/gr3/film-street-source.png';
 }));return sourcePromises.get(key);
}
export function createFilmPreview({width=620,height=413}={}){
 if(!Number.isSafeInteger(width)||!Number.isSafeInteger(height)||width<1||height<1||width>2048||height>2048||width*height>4*1024*1024)throw new RangeError('预览尺寸无效');
 let worker=null,source=null,latest=0,pending=null,tick=0,destroyed=false,inFlight=0;
 try{worker=new Worker(new URL('./preview-worker.mjs',import.meta.url),{type:'module'});}catch{}
 function dispatch(){
  if(destroyed||!pending||!source||inFlight)return;
  cancelAnimationFrame(tick);
  tick=requestAnimationFrame(()=>{
   if(destroyed||!pending?.canvas.isConnected)return;
   const {canvas,look}=pending,id=latest;
   if(worker){inFlight=id;worker.postMessage({kind:'render',id,look});}
   else {inFlight=id;renderPreviewPixels(source.data,look,source.width,source.height).then(pixels=>{if(!destroyed&&id===latest&&canvas.isConnected)canvas.getContext('2d').putImageData(new ImageData(pixels,width,height),0,0);}).catch(error=>{if(id===latest)pending?.onError?.(error.message);}).finally(()=>{inFlight=0;if(id!==latest)dispatch();});}
  });
 }
 if(worker){
  worker.onmessage=({data})=>{
   if(destroyed)return;
   inFlight=0;
   if(data.id===latest&&pending?.canvas.isConnected){
    if(data.error)pending.onError?.(data.error);
    else pending.canvas.getContext('2d').putImageData(new ImageData(new Uint8ClampedArray(data.pixels),width,height),0,0);
   }
   if(data.id!==latest)dispatch();
  };
  worker.onerror=()=>{worker?.terminate();worker=null;inFlight=0;dispatch();};
 }
 return {async request(canvas,look,onError){
  const id=++latest;pending={canvas,look,onError};
  try{source??=await loadSource(width,height);if(destroyed||id!==latest)return;
   if(worker&&!worker.sourceSent){worker.postMessage({kind:'source',width:source.width,height:source.height,pixels:source.data.buffer.slice(0)});worker.sourceSent=true;}
   dispatch();
  }catch(error){if(id===latest)onError?.(error.message);}
 },destroy(){destroyed=true;cancelAnimationFrame(tick);worker?.terminate();}};
}
