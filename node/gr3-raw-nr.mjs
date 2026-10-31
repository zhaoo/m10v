// RAW/Bayer NR layout independently checked against GR III 2.10.
// Reference: gr3-film-mods 04d5d5d raw_nr.py / FINDINGS section 21, MIT.
import {createHash} from 'node:crypto';
import {inspectNativeSource as inspectOfficial} from './gr3-native-source.mjs';
import {officialResources} from './gr3-stock-presets.mjs';
import {normalizeRawNr,rawNrThresholds} from '../web/gr3/native-library-state.mjs';
const need=(v)=>{if(!v)throw new Error('RAW 降噪配置或原厂表无效（仅 GR III 2.10）');};
const sha=b=>createHash('sha256').update(b).digest('hex');
const LOAD=0x53000000,POINTERS=0x107b540+0x375ec;
const tables=[
 {address:0x53ef9720,sha256:'d0f6f8ad9e5781c46eece7ea11bd22c5d28abaf60487dff37e4c353879eed2d6'},
 {address:0x53ef6868,sha256:'4c8250c16bb2efd882be719a508917f5fb7c84afd8edb69689cc29f0eb1c41a7'},
];
const instructions=[[0x43326c,0x02266001,0xe3a06000],[0x433284,0x02277001,0xe3a07000],[0x642ac4,0x13834018,0x13834010]];
export function rawNrCapabilities(){return {modes:['stock','off','threshold'],thresholds:[...rawNrThresholds],jpegNr:'stock',models:['gr3'],version:'2.10'};}
function baseline(source){
 need(inspectOfficial(source).model==='GR III');
 const {decoded,sections}=officialResources(source),rtos=decoded.subarray(sections.RTOS.offset,sections.RTOS.offset+sections.RTOS.size);
 for(const [offset,expected] of instructions)need(rtos.readUInt32LE(offset)===expected);
 tables.forEach((t,v)=>{
  need(rtos.readUInt32LE(POINTERS+v*4)===t.address);
  const table=rtos.subarray(t.address-LOAD,t.address-LOAD+144*20);
  need(table.length===144*20&&sha(table)===t.sha256);
  for(let i=0;i<144;i++)need(table[i*20]===(i<36?0:1));
 });
 return rtos;
}
export function rawNrEvidence(source,config={mode:'stock'}){
 const c=normalizeRawNr(config),report=inspectOfficial(source);
 if(report.model!=='GR III'){need(c.mode==='stock');return {source_sha256:report.sha256,jpeg_nr:'stock',live_view_nr:'stock',model_verified:false};}
 baseline(source);
 return {source_sha256:report.sha256,jpeg_nr:'stock',live_view_nr:'stock',model_verified:true,
  mechanism:c.mode==='off'?'still-ppu-unit-and-parameters-off':c.mode==='threshold'?'still-mode0-b-enable-table':'stock',
  first_enabled_index:c.mode==='threshold'?Math.round(8*(Math.log2(c.iso/3.125)-1)):c.mode==='stock'?36:null,
  table_entries:144,table_stride:20,tables:tables.map(t=>({...t}))};
}
export function planRawNr(source,config={mode:'stock'}){
 const c=normalizeRawNr(config);
 if(c.mode==='stock')return [];
 const rtos=baseline(source),edits=[];
 const put=(offset,expected,replacement)=>{need(rtos.subarray(offset,offset+expected.length).equals(expected));
  edits.push({section:'RTOS',offset,expectedHex:expected.toString('hex'),replacementHex:replacement.toString('hex'),owner:'raw-nr'});};
 if(c.mode==='off'){
  for(const [offset,expect,repl] of instructions){
   const a=Buffer.alloc(4),b=Buffer.alloc(4);a.writeUInt32LE(expect);b.writeUInt32LE(repl);put(offset,a,b);
  }
 }else{
  const first=Math.round(8*(Math.log2(c.iso/3.125)-1));need(first>=36&&first<144);
  for(const table of tables)for(let index=36;index<first;index++)put(table.address-LOAD+index*20,Buffer.from([1]),Buffer.from([0]));
 }
 return edits;
}
