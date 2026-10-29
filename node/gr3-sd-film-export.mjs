import {sha256} from './gr3-fit-binding.mjs';
import {buildSdFilmPack,auditSdFilmPack,sdCrc} from "./gr3-sd-film-pack.mjs";
import {parseCustomCube} from './gr3-custom-lut.mjs';
export function encodeZip(rows) {
  const local = [];
  const central = [];
  let offset = 0;
  for (const name of Object.keys(rows)) {
    const bytes = rows[name];
    const filename = Buffer.from(name);
    const checksum = sdCrc(bytes);
    const header = Buffer.alloc(30);
    header.writeUInt32LE(0x04034b50);
    header.writeUInt16LE(20, 4);
    header.writeUInt16LE(0x800, 6);
    header.writeUInt32LE(checksum, 14);
    header.writeUInt32LE(bytes.length, 18);
    header.writeUInt32LE(bytes.length, 22);
    header.writeUInt16LE(filename.length, 26);
    local.push(header, filename, bytes);
    const record = Buffer.alloc(46);
    record.writeUInt32LE(0x02014b50);
    record.writeUInt16LE(0x0314, 4);
    record.writeUInt16LE(20, 6);
    record.writeUInt16LE(0x800, 8);
    record.writeUInt32LE(checksum, 16);
    record.writeUInt32LE(bytes.length, 20);
    record.writeUInt32LE(bytes.length, 24);
    record.writeUInt16LE(filename.length, 28);
    record.writeUInt32LE((0o100644 << 16) >>> 0, 38);
    record.writeUInt32LE(offset, 42);
    central.push(record, filename);
    offset += header.length + filename.length + bytes.length;
  }
  const centralSize = central.reduce((size, part) => size + part.length, 0);
  const ending = Buffer.alloc(22);
  ending.writeUInt32LE(0x06054b50);
  ending.writeUInt16LE(Object.keys(rows).length, 8);
  ending.writeUInt16LE(Object.keys(rows).length, 10);
  ending.writeUInt32LE(centralSize, 12);
  ending.writeUInt32LE(offset, 16);
  return Buffer.concat([...local, ...central, ending]);
}

export function exportSdFilms(input){
 if(!input||typeof input!=='object'||Array.isArray(input)||!Object.hasOwn(input,'ids')||Object.keys(input).some(k=>!['ids','model','customFilms'].includes(k))||(input.model!==undefined&&!['gr3','gr3x'].includes(input.model)))throw Error('请选择 GR III / GR IIIx 胶卷');
 const files=input.customFilms??[];
 if(!Array.isArray(files)||files.length>216)throw Error('自定义 LUT 数量超限');
 let total=0;const sourceHashes=[];
 const custom=files.map(file=>{
  if(!file||typeof file!=='object'||Object.keys(file).some(k=>!['name','filename','base64'].includes(k))||typeof file.base64!=='string'||!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(file.base64))throw Error('LUT 文件编码无效');
  const bytes=Buffer.from(file.base64,'base64');total+=bytes.length;
  if(total>16*1024*1024)throw Error('LUT 文件总量不能超过 16 MiB');
  sourceHashes.push(sha256(bytes));
  return parseCustomCube(bytes,file.filename,file.name);
 });
 const pack=buildSdFilmPack(input.ids,custom),receipt={...auditSdFilmPack(pack),...(custom.length?{custom_lut_assessment:{status:'legacy-unassessed',isp_fit:false,path:'13-cubed RGB table; existing CPU colour path',source_sha256:sourceHashes,camera_verified:false}}:{})};
 const instructions='M10V SD 胶卷库 / GR III 2.10 / GR IIIx 1.60\n'+
 '需要配套的 M10V SD 胶卷库固件；旧内置胶卷库固件不读取此文件，GR III 与 GR IIIx 共用此配方包。\n'+
 '解压，将 SD/M10V 目录复制到 SD 卡根目录，与 DCIM 并列。更新时只替换 FILMS.M10，保留其他文件。\n'+
 '机内：MENU > 设置 > 胶卷库，管理已选胶卷，进入卡上的胶卷列表添加喜欢的胶卷。\n'+
 '按机内中文提示选择或取消胶卷，已选胶卷按顺序显示。GR III 最多十款；GR IIIx 保持五款上限。MENU 返回上一级，卡上可存全部当前平台胶卷。\n'+
 '时间水印：MENU > 设置 > 时间水印，分别设置日期时间、胶卷名称、日期格式、位置、颜色；名称可单独开启。OK 保存，MENU 取消当前编辑。\n'+
 '装入成功后重启或换卡仍保留。无卡、损坏或不兼容文件不替换原槽。失败提示后请保留原配置重试。\n'+
 '内置胶卷通过固件内配方身份校验；自定义胶卷携带压缩采样的 13 级 RGB LUT，仅由配套新版固件读取。\n'+
 '离线验证候选，尚未通过真机 SD 换卷验收。胶卷仅作用于保存的静态 JPEG，实时取景尚不随换卷变化。800T 已合入新版能量扩散与原厂 FN 五项中文调节，旧版胶卷包需重新导出。\n';
 return {receipt,zip:encodeZip({'SD/M10V/FILMS.M10':pack,'README.txt':Buffer.from(instructions),'manifest.json':Buffer.from(JSON.stringify(receipt,null,2)+'\n')})};
}
