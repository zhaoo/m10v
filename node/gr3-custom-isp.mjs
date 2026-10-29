// Optional data-only custom SD profile. No fitter/runtime dependency here.
export const CUSTOM_ISP_OFFSET=6688;
export const CUSTOM_ISP_BYTES=1760;
export const CUSTOM_ISP_PAYLOAD_BYTES=1572;
export const CUSTOM_ISP_MAGIC=0x5053494d;
export function decodeCustomIspPayload(bytes){
 if(!Buffer.isBuffer(bytes)||bytes.length!==CUSTOM_ISP_PAYLOAD_BYTES)throw Error('自定义 ISP 配方长度无效');
 const matrixQ13=Array.from({length:9},(_,i)=>bytes.readInt16LE(i*2));
 const postQ512=Array.from({length:9},(_,i)=>bytes.readInt16LE(18+i*2));
 for(const [values,unit] of [[matrixQ13,8192],[postQ512,512]])
  if([0,1,2].some(r=>values.slice(r*3,r*3+3).reduce((s,v)=>s+v,0)!==unit))throw Error('自定义 ISP 矩阵行和无效');
 const curves=Array.from({length:3},(_,c)=>Array.from({length:256},(_,i)=>bytes.readUInt16LE(36+(c*256+i)*2)));
 if(curves.some(curve=>curve.some((v,i)=>v>16383||(i>0&&v<curve[i-1]))))throw Error('自定义 ISP 曲线无效');
 return {matrixQ13,postQ512,curves};
}
export function encodeCustomIspPayload(look){
 const bytes=Buffer.alloc(CUSTOM_ISP_PAYLOAD_BYTES);
 for(const [values,at] of [[look?.matrixQ13,0],[look?.postQ512,18]]){
  if(!Array.isArray(values)||values.length!==9||values.some(v=>!Number.isInteger(v)||v< -32768||v>32767))throw Error('自定义 ISP 矩阵无效');
  values.forEach((v,i)=>bytes.writeInt16LE(v,at+i*2));
 }
 if(!Array.isArray(look?.curves)||look.curves.length!==3||look.curves.some(curve=>!Array.isArray(curve)||curve.length!==256||curve.some(v=>!Number.isInteger(v)||v<0||v>16383)))throw Error('自定义 ISP 曲线无效');
 look.curves.flat().forEach((v,i)=>bytes.writeUInt16LE(v,36+i*2));
 decodeCustomIspPayload(bytes);return bytes;
}
