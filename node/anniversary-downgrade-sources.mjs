import {readFile,writeFile,mkdir} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {inflateRawSync} from 'node:zlib';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {ANNIVERSARY_DOWNGRADE_PROFILES as profiles} from './gr3-anniversary-downgrade.mjs';

const run=promisify(execFile),pending=new Map();
const hash=b=>createHash('sha256').update(b).digest('hex');
const files={gr3:{new:'fwdc239b-gr3-220-official.bin',old:'fwdc239b-gr3-official.bin',zip:'gr3_v220.zip'},
 gr3x:{new:'fwdc243b-gr3x-170-official.bin',old:'fwdc243b-gr3x-official.bin',zip:'gr3x_v170.zip'}};
const need=(ok,message)=>{if(!ok)throw Error('降级官方来源：'+message);};

// Read only the named firmware entry; never extract archive paths to disk.
export function officialFirmwareFromZip(zip,filename,expectedSha){
 need(Buffer.isBuffer(zip)&&zip.length>=22&&zip.length<=34*1024*1024,'下载归档大小无效');
 let end=-1;
 for(let at=zip.length-22;at>=Math.max(0,zip.length-65557);at--)
  if(zip.readUInt32LE(at)===0x06054b50&&at+22+zip.readUInt16LE(at+20)===zip.length){end=at;break;}
 need(end>=0&&zip.readUInt16LE(end+4)===0&&zip.readUInt16LE(end+6)===0,'归档目录无效');
 const count=zip.readUInt16LE(end+10),size=zip.readUInt32LE(end+12),start=zip.readUInt32LE(end+16);
 need(count>0&&count<1000&&zip.readUInt16LE(end+8)===count&&start+size===end,'归档目录边界无效');
 let at=start,found;
 for(let i=0;i<count;i++){
  need(at+46<=end&&zip.readUInt32LE(at)===0x02014b50,'归档条目无效');
  const names=zip.readUInt16LE(at+28),extra=zip.readUInt16LE(at+30),comment=zip.readUInt16LE(at+32),next=at+46+names+extra+comment;
  need(next<=end,'归档名称越界');
  const name=zip.toString('utf8',at+46,at+46+names);
  if(name.split('/').at(-1)===filename){
   need(!found,'归档包含重复固件');
   const flags=zip.readUInt16LE(at+8),method=zip.readUInt16LE(at+10),compressed=zip.readUInt32LE(at+20),uncompressed=zip.readUInt32LE(at+24),local=zip.readUInt32LE(at+42);
   need(!(flags&1)&&[0,8].includes(method)&&uncompressed>=152&&uncompressed<=34*1024*1024,'固件压缩方式或长度无效');
   need(local+30<=start&&zip.readUInt32LE(local)===0x04034b50,'固件本地头无效');
   const nameLength=zip.readUInt16LE(local+26),data=local+30+nameLength+zip.readUInt16LE(local+28);
   need(data+compressed<=start&&zip.toString('utf8',local+30,local+30+nameLength)===name,'固件本地边界无效');
   const payload=zip.subarray(data,data+compressed);
   found=method===0?Buffer.from(payload):inflateRawSync(payload,{maxOutputLength:34*1024*1024});
   need(found.length===uncompressed&&hash(found)===expectedSha,'官方固件SHA-256与固定来源不符');
  }
  at=next;
 }
 need(at===end&&found,'归档没有对应机型固件');return found;
}

export async function readAnniversarySources(model){
 need(Object.hasOwn(files,model),'机型无效');
 if(pending.has(model))return pending.get(model);
 const task=(async()=>{
  const p=profiles[model],f=files[model],oldUrl=new URL('../bin/'+f.old,import.meta.url),newUrl=new URL('../bin/'+f.new,import.meta.url);
  const cacheDirectory=new URL('../data/anniversary-official/',import.meta.url),cacheUrl=new URL(f.new,cacheDirectory);
  const oldSource=await readFile(oldUrl);need(hash(oldSource)===p.restore_sha256,'目标官方原包不符');
  let newSource;
  try{newSource=await readFile(newUrl);}catch(error){
   if(error.code!=='ENOENT')throw error;
   try{newSource=await readFile(cacheUrl);}catch(cacheError){if(cacheError.code!=='ENOENT')throw cacheError;}
  }
  if(!newSource){
   need(process.env.M10V_DOWNGRADE_AUTO_FETCH!=='0','缺少对应新版官方原包');
   const url='https://www.ricoh-imaging.co.jp/resources/japan/support/download/digital/FIRMWARE/'+f.zip;
   const {stdout}=await run('curl',['-fLsS','--proto','=https','--max-redirs','0','--max-time','120',url],
    {encoding:'buffer',maxBuffer:34*1024*1024,timeout:125000});
   newSource=officialFirmwareFromZip(stdout,p.filename,p.source_sha256);
   await mkdir(cacheDirectory,{recursive:true});
   try{await writeFile(cacheUrl,newSource,{flag:'wx',mode:0o644});}
   catch(writeError){if(writeError.code!=='EEXIST')throw writeError;newSource=await readFile(cacheUrl);}
  }
  need(hash(newSource)===p.source_sha256,'新版官方原包不符');return {newSource,oldSource};
 })();
 pending.set(model,task);
 try{return await task;}finally{pending.delete(model);}
}
