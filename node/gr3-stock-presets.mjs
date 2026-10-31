// GR III resource layout independently decoded here. Slot metadata from
// Darkslide GR 9913169, GPL-2.0-only; see vendor/darkslide/LICENSE.
import {readFileSync} from 'node:fs';
import {inspectFirmwareImport} from './firmware.mjs';
import {decodeFrameMap} from './gr3-frames.mjs';
const template=JSON.parse(readFileSync(new URL('../vendor/darkslide/gr3_v210.json',import.meta.url)));
const cache=new WeakMap();
const need=(ok,message)=>{if(!ok)throw new Error(message);};
export function officialResources(source){
  if(cache.has(source))return cache.get(source);
  const report=inspectFirmwareImport(source),{decoded}=decodeFrameMap(source);
  let cursor=0;const sections={};
  for(const row of report.sections){sections[row.name]={offset:cursor+16,size:row.size-16};cursor+=row.size;}
  const r={decoded,sections};cache.set(source,r);return r;
}
function reader(source){
  const {decoded,sections}=officialResources(source),start=sections.RTOS.offset;
  const copySource=decoded.readUInt32LE(start+0x450);
  const copyDestination=decoded.readUInt32LE(start+0x454);
  const copyLength=decoded.readUInt32LE(start+0x458);
  need(copyLength>0&&copySource>=0x53000000&&copySource-0x53000000+copyLength<=sections.RTOS.size,
    '原厂启动复制范围无效');
  const off=(address,size=4)=>{
    if(address>=copyDestination&&address<copyDestination+copyLength){
      need(address+size<=copyDestination+copyLength,'原厂资源跨越启动复制范围');
      address=address-copyDestination+copySource;
    }
    const at=address-0x53000000;
    need(at>=0&&at+size<=sections.RTOS.size,'原厂资源地址越界');return start+at;
  };
  const word=a=>decoded.readUInt32LE(off(a));
  // Find the language directory in initialized RAM. Newer firmware inserts
  // image descriptors before it; its old absolute address is not a format field.
  const languageDirectories=[];
  for(let at=copyDestination;at+21*4<=copyDestination+copyLength;at+=4){
    const pointers=Array.from({length:21},(_,language)=>word(at+language*4));
    if(!pointers.every(p=>p%4===0&&p>=copyDestination&&p+4*279<=copyDestination+copyLength))continue;
    try{
      const names=template.slots.slice(0,12).map(slot=>{
        const record=off(word(pointers[1]+slot.string_id*4),8),count=decoded[record];
        if(count<2||decoded[record+1]!==1||decoded.readUInt16LE(record+2)!==0)return null;
        const text=off(decoded.readUInt32LE(record+4),count*2);
        return decoded.readUInt16LE(text+(count-1)*2)===0?decoded.toString('utf16le',text,text+(count-1)*2):null;
      });
      if(names.every((name,i)=>name===template.slots[i].factory_en))languageDirectories.push(at);
    }catch{/* This word run is not a resource directory. */}
  }
  need(languageDirectories.length===1,'原厂语言目录无法唯一定位');
  const languageDirectory=languageDirectories[0];
  // The existing icon table has an independent checked boundary; discovery of
  // the language directory determines the descriptor count, including additions.
  const iconDirectory=copyDestination+0x20fc,descriptorCount=(languageDirectory-iconDirectory)/4;
  need(Number.isInteger(descriptorCount)&&descriptorCount>548&&descriptorCount<=4096,'原厂图标目录范围无效');
  let iconCount=descriptorCount;
  for(let id=0;id<descriptorCount;id++){
    const descriptor=off(word(iconDirectory+id*4),8),width=decoded.readUInt16LE(descriptor),height=decoded.readUInt16LE(descriptor+2);
    const location=decoded.readUInt32LE(descriptor+4),size=width*height*4;
    if(location*4+size<=sections.ICONBIN.size){
      need(id<iconCount,'原厂图标和外部图片目录交错');
    }else{
      // The same pointer array ends with JPEG descriptors. Their last word is
      // a firmware path pointer, not an ICONBIN word offset (13 in the old
      // release, 15 in the supplied release). Never scan them as RGBA aliases.
      const at=off(location,1),path=decoded.toString('ascii',at,Math.min(at+128,start+sections.RTOS.size)).split('\0')[0];
      need(width>0&&height>0&&/^[AB]:\\Resource\\Jpeg\\[A-Za-z0-9_]+\.jpg$/.test(path),'原厂图片描述符类型无效');
      iconCount=Math.min(iconCount,id);
    }
  }
  need(iconCount>548,'原厂 ICONBIN 图标目录缺失');
  const languageTables=Array.from({length:21},(_,language)=>word(languageDirectory+language*4)).sort((a,b)=>a-b);
  const stringCount=(languageTables[1]-languageTables[0])/4;
  need(stringCount>278&&stringCount<=4096&&languageTables.every((value,i)=>value===languageTables[0]+i*stringCount*4)&&
    languageTables.at(-1)+stringCount*4<=copyDestination+copyLength,'原厂语言表范围无效');
  const string=(id,language)=>{
    need(Number.isInteger(id)&&id>=0&&id<stringCount&&Number.isInteger(language)&&language>=0&&language<21,'原厂名称索引无效');
    const record=off(word(word(languageDirectory+language*4)+id*4),8);
    const count=decoded[record],address=decoded.readUInt32LE(record+4),at=off(address,count*2);
    need(count>=2&&decoded[record+1]===1&&decoded.readUInt16LE(record+2)===0&&
      decoded.readUInt16LE(at+(count-1)*2)===0,'原厂名称记录无效');
    return {record,at,count,address,text:decoded.toString('utf16le',at,at+(count-1)*2)};
  };
  const icon=id=>{
    need(Number.isInteger(id)&&id>=0&&id<iconCount,'原厂图标索引无效');
    const desc=off(word(iconDirectory+id*4),8),width=decoded.readUInt16LE(desc),height=decoded.readUInt16LE(desc+2);
    const offset=decoded.readUInt32LE(desc+4)*4,size=width*height*4;
    need(offset+size<=sections.ICONBIN.size,'图标范围越界');
    return {offset,size,width,height,pixels:decoded.subarray(sections.ICONBIN.offset+offset,sections.ICONBIN.offset+offset+size)};
  };
  return {decoded,sections,start,off,word,string,icon,languageDirectory,iconDirectory,iconCount,descriptorCount,stringCount};
}
export function stockResourceLayout(source){
  const {languageDirectory,iconDirectory,iconCount,descriptorCount,stringCount}=reader(source);
  return {languageDirectory,iconDirectory,iconCount,descriptorCount,stringCount};
}
function lendable(r,id){
  const spans=[],candidates=[];
  for(let language=0;language<21;language++){
    const table=r.word(r.languageDirectory+language*4);
    for(let other=1;other<r.stringCount;other++){
      const address=r.word(table+other*4);if(!address)continue;
      const at=r.off(address,8),count=r.decoded[at],textVa=r.decoded.readUInt32LE(at+4);
      spans.push([textVa,textVa+count*2]);
      if(other===id&&![0,1,18,19].includes(language)&&count>=2&&r.decoded[at+1]===1&&r.decoded.readUInt16LE(at+2)===0)
        candidates.push({...r.string(id,language),language});
    }
  }
  candidates.sort((a,b)=>b.count-a.count||a.language-b.language);
  return candidates.find(c=>spans.filter(([a,b])=>a<c.address+c.count*2&&b>c.address).length===1);
}
export function stockPresetCapabilities(source){
  const r=reader(source);
  return template.slots.slice(0,12).map(s=>{
    const en=r.string(s.string_id,1);need(en.text===s.factory_en,'原厂名称与槽位不符');
    const loan=s.name_max&&s.name_max>en.text.length?lendable(r,s.string_id):null;
    return {slot:s.no,name:s.name,factoryName:en.text,canRename:s.rename!=='closed',
      nameMax:Math.min(s.name_max??en.text.length,loan?loan.count-1:en.text.length),
      iconPixelsBase64:r.icon(s.icon_id).pixels.toString('base64'),
      affectedLanguages:loan?[1,19,loan.language]:[1,19]};
  });
}
export function createStockEdits(source,{negativeGrainMenu=false,presets=[]}={}){
  need(typeof negativeGrainMenu==='boolean','颗粒开关无效');need(Array.isArray(presets),'预设列表无效');
  const r=reader(source),edits=[],seen=new Set();
  const write=(section,offset,value,owner,meta={})=>{
    const base=r.sections[section];need(offset>=0&&offset+value.length<=base.size,'补丁范围越界');
    const before=r.decoded.subarray(base.offset+offset,base.offset+offset+value.length);
    if(before.equals(value))return;
    need(!edits.some(e=>e.section===section&&offset<e.offset+e.replacementHex.length/2&&e.offset<offset+value.length),'补丁范围重叠');
    edits.push({section,offset,expectedHex:before.toString('hex'),replacementHex:value.toString('hex'),owner,...meta});
  };
  if(negativeGrainMenu){
    need(r.word(0x53b348bc)===0x53b3500c&&r.word(0x53b348c0)===9,'负片菜单前像不符');
    need(r.decoded.subarray(r.off(0x53b3500c,28),r.off(0x53b3500c,28)+28).toString('hex')==='0200020102020203020402050206020d000e00004f6e537461727400','负片菜单内容不符');
    write('RTOS',0xb348c0,Buffer.from('0a000000','hex'),'negative-grain');
    write('RTOS',0xb3501e,Buffer.from('020f','hex'),'negative-grain');
  }
  for(const item of presets){
    need(item&&typeof item==='object'&&!Array.isArray(item)&&Object.keys(item).every(k=>['slot','name','iconPixelsBase64'].includes(k)),'预设包含未知字段');
    need(Number.isInteger(item.slot)&&item.slot>=1&&item.slot<=12,'预设槽位无效');
    need(!seen.has(item.slot),'重复预设槽位');seen.add(item.slot);
    const s=template.slots[item.slot-1],owner=`stock-${item.slot}`;
    if(item.name!==undefined){
      need(s.rename!=='closed','该预设名称不可修改');
      const en=r.string(s.string_id,1),zh=r.string(s.string_id,19),name=item.name;
      need(typeof name==='string'&&name.length>0&&name.length<=(s.name_max??en.text.length),'预设名称长度无效');
      need(/^[\x20-\x7e]+$/.test(name)&&name===name.trim()&&!name.includes('  '),'名称仅支持可打印英文字符且无多余空格');
      need(en.text===s.factory_en,'原厂名称不匹配');
      const target=name.length<=en.text.length?en:lendable(r,s.string_id);
      need(target&&name.length<target.count,'预设名称超过实际存储长度');
      const value=Buffer.alloc(target.count*2);value.write(name+'\0',0,'utf16le');
      const record=Buffer.alloc(8);record[0]=name.length+1;record[1]=1;record.writeUInt32LE(target.address,4);
      const meta={affectedLanguages:target===en?[1,19]:[1,19,target.language]};
      write('RTOS',target.at-r.start,value,owner,meta);
      if(target!==en)write('RTOS',target.record-r.start,Buffer.from([name.length+1]),owner,meta);
      write('RTOS',en.record-r.start,record,owner,meta);write('RTOS',zh.record-r.start,record,owner,meta);
    }
    if(item.iconPixelsBase64!==undefined){
      need(typeof item.iconPixelsBase64==='string'&&/^[A-Za-z0-9+/]{8534}==$/.test(item.iconPixelsBase64),'图标编码无效');
      const pixels=Buffer.from(item.iconPixelsBase64,'base64'),icon=r.icon(s.icon_id);
      need(pixels.length===6400&&icon.width===40&&icon.height===40,'图标须为40×40 RGBA');
      for(let i=0;i<1600;i++){
        const x=i%40,y=Math.floor(i/40),alpha=pixels[i*4+3],visible=x>=1&&x<39&&y>=2&&y<38;
        need((alpha===0||alpha===255)&&!!alpha===visible&&alpha===icon.pixels[i*4+3],'图标透明边不符合原厂规则');
      }
      for(let id=1;id<r.iconCount;id++){if(id===s.icon_id)continue;const other=r.icon(id);
        need(!(other.offset<icon.offset+icon.size&&icon.offset<other.offset+other.size),'图标与其他资源共享');}
      write('ICONBIN',icon.offset,pixels,owner);
    }
  }
  return edits;
}
