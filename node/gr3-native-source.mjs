// Public version numbers are metadata, not an executable compatibility test.
// Match every dependency against the reviewed target, ignoring only the two
// component version fields and the CPU checksum that covers its version.
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {inspectOfficial,inspectFirmwareImport} from './firmware.mjs';
import {decodeFrameMap} from './gr3-frames.mjs';

const references=new Map();
function dependencies(source,report){
  const {decoded}=decodeFrameMap(source),sections=new Map();let offset=0;
  const header=Buffer.from(source.subarray(0,128));header.fill(0,0x38,0x3c);header.fill(0,0x50,0x54);
  sections.set('HEADER',createHash('sha256').update(header).digest('hex'));
  for(const row of report.sections){
    const payload=decoded.subarray(offset,offset+row.size);
    const bytes=['RTOS','CPU'].includes(row.name)?Buffer.from(payload):payload;
    if(row.name==='RTOS')bytes.fill(0,16+0x2038,16+0x203c);
    if(row.name==='CPU'){bytes.fill(0,16+0x7c,16+0x80);bytes.fill(0,16+0x90,16+0x94);}
    sections.set(row.name,createHash('sha256').update(bytes).digest('hex'));offset+=row.size;
  }
  return sections;
}
export function inspectNativeSource(source){
  const report=inspectFirmwareImport(source),model=report.model==='GR IIIx'?'gr3x':'gr3';
  if(!references.has(model)){
    const file=model==='gr3x'?'fwdc243b-gr3x-official.bin':'fwdc239b-gr3-official.bin';
    const bytes=readFileSync(new URL('../bin/'+file,import.meta.url));
    const reference=inspectOfficial(bytes);
    const expected=model==='gr3x'?'708e79f3b7b96a7e1581b4acf4c412233050a1832718ef7f06c8397db1b431c7':'d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4';
    if(reference.model!==report.model||reference.sha256!==expected)throw Error('原生构建参考身份不一致');
    references.set(model,dependencies(bytes,reference));
  }
  const reference=references.get(model),actual=dependencies(source,report);
  const changed=[...reference].filter(([name,digest])=>digest!==actual.get(name)).map(([name])=>name);
  if(changed.length){
    const error=Error(`${report.model} ${report.public_version} 的原生 ABI 尚未适配（${changed.join('、')} 已变化）；已保留上传固件，不会改用旧版固件或改写版本号。`);
    error.code='M10V_NATIVE_ABI_NOT_PORTED';throw error;
  }
  return report;
}
