import {expandEncodedKnots} from './gr3-fit-binding.mjs';
// Scalar ranges only, independently read from exact supported official inputs.
import {inspectOfficial} from './firmware.mjs';
import {decodeFrameMap} from './gr3-frames.mjs';
import {readFile} from 'node:fs/promises';
const cache=new Map();
export function deriveFitEnvelope(source){
 const identity=inspectOfficial(source);if(!['GR III','GR IIIx'].includes(identity.model)||!['2.10','1.60'].includes(identity.public_version))throw Error('fit envelope needs pinned official firmware');
 if(cache.has(identity.sha256))return structuredClone(cache.get(identity.sha256));
 const {decoded}=decodeFrameMap(source);let offset=0;for(const section of identity.sections){if(section.name==='RTOS')break;offset+=section.size;}const rtos=decoded.subarray(offset+16,offset+identity.sections.find(s=>s.name==='RTOS').size);
 const load=rtos.readUInt32LE(0x450),ram=rtos.readUInt32LE(0x454),size=rtos.readUInt32LE(0x458);
 const at=(address,n)=>{if(address>=ram&&address+n<=ram+size)address=address-ram+load;const pos=address-0x53000000;if(pos<0||pos+n>rtos.length)throw Error('factory envelope pointer outside RTOS');return pos;};
 const matrices=[];for(let i=11;i<=25;i++){const record=rtos.readUInt32LE(at(0x55018d94+i*4,4)),matrix=rtos.readUInt32LE(at(record+4,4)),p=at(matrix,18);matrices.push(Array.from({length:9},(_,i)=>rtos.readInt16LE(p+i*2)));}
 const curves=[];for(let i=0;i<12;i++){const ptr=rtos.readUInt32LE(at(0x55037604+i*4,4)),p=at(ptr,512);curves.push(Array.from({length:256},(_,i)=>rtos.readUInt16LE(p+i*2)));}
 const steps=curves.flatMap(c=>c.slice(1).map((v,i)=>v-c[i]));
 const bounds={schema:'m10v-factory-fit-envelope/v1',source_sha256:identity.sha256,model:identity.model,look_min:Math.min(...matrices.flat()),look_max:Math.max(...matrices.flat()),look_row_abs_max:Math.max(...matrices.flatMap(m=>[0,1,2].map(i=>m.slice(i*3,i*3+3).reduce((s,v)=>s+Math.abs(v),0)))),post_min:-8191,post_max:8191,post_col_abs_max:8191,curve_step_min:Math.min(...steps),curve_step_max:Math.max(...steps),curve_first_min:Math.min(...curves.map(c=>c[0])),curve_first_max:Math.max(...curves.map(c=>c[0])),curve_last_min:Math.min(...curves.map(c=>c.at(-1))),curve_last_max:Math.max(...curves.map(c=>c.at(-1))),post_provenance:'schema bound, no comparable factory Q512 post matrix',factory_arrays_retained:false};cache.set(identity.sha256,bounds);return structuredClone(bounds);
}
export async function loadFitEnvelope(model){const source=await readFile(new URL(model==='gr3x'?'../bin/fwdc243b-gr3x-official.bin':'../bin/fwdc239b-gr3-official.bin',import.meta.url));return deriveFitEnvelope(source);}
export function envelopeViolations(look,env){if(!env)return [];const errors=[];const check=(label,v,min,max)=>{if(v<min||v>max)errors.push(label+': '+v+' outside '+min+'..'+max);};
 for(const v of look.matrixQ13)check('look coefficient',v,env.look_min,env.look_max);for(let i=0;i<3;i++)check('look row absolute sum',look.matrixQ13.slice(i*3,i*3+3).reduce((s,v)=>s+Math.abs(v),0),0,env.look_row_abs_max);
 for(const v of look.postQ512)check('post coefficient (schema)',v,env.post_min,env.post_max);for(let c=0;c<3;c++)check('post column absolute sum (schema)',[0,1,2].reduce((s,r)=>s+Math.abs(look.postQ512[r*3+c]),0),0,env.post_col_abs_max);
 for(const curve of [...look.curves,...(look.knots||[]).map(expandEncodedKnots)]){check('curve first',curve[0],env.curve_first_min,env.curve_first_max);check('curve last',curve.at(-1),env.curve_last_min,env.curve_last_max);for(let i=1;i<curve.length;i++)check('curve step',curve[i]-curve[i-1],env.curve_step_min,env.curve_step_max);}return [...new Set(errors)];
}
