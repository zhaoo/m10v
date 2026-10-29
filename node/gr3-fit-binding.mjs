import {createHash} from 'node:crypto';
const canonical=value=>Array.isArray(value)?value.map(canonical):value&&typeof value==='object'?Object.fromEntries(Object.keys(value).sort().map(k=>[k,canonical(value[k])])):value;
export const sha256=value=>createHash('sha256').update(typeof value==='string'||Buffer.isBuffer(value)?value:JSON.stringify(canonical(value))).digest('hex');
export function encodedParameters(look){
 const out={};for(const [key,unit] of [['matrixQ13',8192],['postQ512',512]]){
 const a=look?.[key];if(!Array.isArray(a)||a.length!==9||a.some(v=>!Number.isInteger(v)||v< -32768||v>32767)||[0,1,2].some(r=>a.slice(r*3,r*3+3).reduce((s,v)=>s+v,0)!==unit))throw Error('invalid encoded '+key);out[key]=[...a];}
 for(const [key,n] of [['curves',256],['knots',33]]){const a=look?.[key];if(!Array.isArray(a)||a.length!==3||a.some(c=>!Array.isArray(c)||c.length!==n||c.some((v,i)=>!Number.isInteger(v)||v<0||v>16383||(i>0&&v<c[i-1]))))throw Error('invalid encoded '+key);out[key]=a.map(c=>[...c]);}return out;
}
export const parameterHash=look=>sha256(encodedParameters(look));
export function validateQualityBinding(look,report){
 encodedParameters(look);if(!report)return false;
 const {report_sha256,...body}=report;
 if(report.schema!=='m10v-gr3-fit-quality/v1'||report.parameter_sha256!==parameterHash(look)||report_sha256!==sha256(body)||report.camera_verified!==false||!['gr3','gr3x'].includes(report.model)||report.official_firmware!==(report.model==='gr3'?'2.10':'1.60')||!/^[0-9a-f]{64}$/.test(report.source_sha256))throw Error('fit quality report binding mismatch');return true;
}
export function sealReport(body){return {...body,report_sha256:sha256(body)};}

export const expandEncodedKnots=knots=>Array.from({length:256},(_,i)=>knots[i>>3]+(((knots[(i>>3)+1]-knots[i>>3])*(i%8))>>3));
