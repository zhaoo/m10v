// Candidate packaging only: delegates firmware generation to the web production pipeline.
import {mkdir,readFile,writeFile,stat} from 'node:fs/promises';
import {execFileSync} from 'node:child_process';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {readNativeOfficial,prepareNative,generateNative} from '../node/gr3-native-library.mjs';
import {defaultConfiguration,defaultHalo,defaultEffects} from '../web/gr3/native-library-state.mjs';
import {exportSdFilms,encodeZip} from '../node/gr3-sd-film-export.mjs';
import {SD_FILM_IDS} from '../node/gr3-sd-film-pack.mjs';

const [model,out]=process.argv.slice(2);
if(!['gr3','gr3x'].includes(model)||!out)throw Error('Usage: node scripts/export_square_film_candidate.mjs gr3|gr3x NEW_OUTPUT_DIRECTORY');
try{await stat(out);throw Error('Candidate output already exists');}catch(error){if(error.code!=='ENOENT')throw error;}
const sha=bytes=>createHash('sha256').update(bytes).digest('hex'),json=value=>Buffer.from(JSON.stringify(value,null,2)+'\n');
const configuration=defaultConfiguration(model);
configuration.slots=[34,35,37,33,314,76,66,317,299,290].map(film=>({film,grain:0,soft:0,halo:defaultHalo(),effects:defaultEffects()}));
const options={debug_mode:true,appended_slots:true,hdf_enabled:true,halation_enabled:true,
 extensions:{aspect:true,level:true,negativeGrain:true,rawNr:{mode:'stock'}}};
const source=await readNativeOfficial(model),plan=prepareNative(source,configuration,options);
const result=await generateNative(source,configuration,plan.configuration_sha256,options);
if(!result.manifest.appended_slots?.playback?.identity_enabled||!result.manifest.capture_lifecycle?.snapshot)throw Error('Recorded identity requires installed shot snapshot');
const cube='LUT_3D_SIZE 2\n0 0 0\n1 0 0\n0 1 0\n1 1 0\n0 0 1\n1 0 1\n0 1 1\n1 1 1\n';
const sd=await exportSdFilms({model,ids:[...SD_FILM_IDS],customFilms:[{name:'Identity Test',filename:'identity.cube',base64:Buffer.from(cube).toString('base64')}]});
const label=model==='gr3'?'GR III · 2.10':'GR IIIx · 1.60';
const readme=`M10V 正方形胶卷图标测试候选 / ${label}
状态：WAITING_FOR_USER_VALIDATION，尚未经相机验证，未发布。

本包用于核对正方形包装图标、机内小图辨识、回放胶卷身份和导入 LUT 名称。
固件文件：${plan.filename}；仅适用于 ${label}，不得用于其他机型。
保留有效机内存档；已有已选胶卷优先于本包的十款初始配置。
调试日志已启用，原有画幅、水平仪、HDF、原生颗粒和光晕入口保留；强度默认关闭。

手动安装：
1. 先备份个人 SD 数据和原厂恢复包；本任务未操作相机或 SD 卡。
2. 固件按本项目既有相应机型更新方法使用 ${plan.filename}。
3. 解压 M10V-SD-films.zip，将 SD/M10V 中的资源与卡上 M10V 目录合并；只替换 FILMS.M10，保留已有存档和其他文件。
4. 在机内胶卷库装入 Identity Test。若当前十款已满，先取消一款，再加入；该测试 LUT 为恒等颜色变换。

待相机核对：
- 胶卷库正方形卡片：文字、颜色、图案、选择框、翻页、返回。
- MENU/ADJ/取景中的小图和名称；Identity Test 在第一和第十个位置均显示实际名称。
- 分别使用两种胶卷拍新 JPEG 和 RAW+JPEG，随后更换当前胶卷、关机重启并回放，图标仍对应拍摄时胶卷。
- 旧照片只记录过槽位，无法补回实际胶卷身份，显示 FILM/?；不会借用当前胶卷。
- 首张、连拍、即时回放、相册、RAW 再开发及无卡/换卡的既有行为。
发生问题请保留本包 manifest/receipt 和 SD 上匹配的 M10V 调试日志，注明操作与照片。

恢复：使用对应机型的原厂恢复包及既有恢复流程；恢复个人备份，不清空用户存档。
固件 SHA-256：${sha(result.candidate)}
`;
const files={
 [plan.filename]:result.candidate,'M10V-runtime-arm.bin':result.runtime,
 'M10V-build-receipt.json':json(result.receipt),'M10V-runtime-manifest.json':json(result.manifest),
 'M10V-configuration.json':json(plan.configuration),'M10V-SD-films.zip':sd.zip,
 'README.txt':Buffer.from(readme),'LICENSE':await readFile('LICENSE'),
 'THIRD_PARTY_NOTICES.md':await readFile('THIRD_PARTY_NOTICES.md'),
 'evidence/source-diff.patch':execFileSync('git',['diff','--binary'],{maxBuffer:32*1024*1024}),
};
const sources={};
for(const [file,expected] of Object.entries(result.manifest.sources)){
 const bytes=await readFile(file);if(sha(bytes)!==expected)throw Error('Source changed during packaging: '+file);
 sources[file]=bytes;
}
files['evidence/source-snapshot.zip']=encodeZip(sources);
files['evidence/provenance.json']=json({candidate:'square-film-art-20261030-r1',model,status:'WAITING_FOR_USER_VALIDATION',camera_tested:false,
 revision:execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),
 branch:execFileSync('git',['branch','--show-current'],{encoding:'utf8'}).trim(),
 git_status:execFileSync('git',['status','--short'],{encoding:'utf8'}).trim(),
 options,source_sha256:plan.source_sha256,runtime_source_sha256:plan.runtime_source_sha256,
 configuration_sha256:plan.configuration_sha256,source_files:result.manifest.sources,
 candidate_sha256:sha(result.candidate),sd_receipt:sd.receipt,created_at:new Date().toISOString()});
files.SHA256SUMS=Buffer.from(Object.entries(files).map(([name,bytes])=>sha(bytes)+'  '+name).join('\n')+'\n');
await mkdir(out,{recursive:true});
for(const [name,bytes] of Object.entries(files)){const file=path.join(out,name);await mkdir(path.dirname(file),{recursive:true});await writeFile(file,bytes);}
const name=`m10v-${model}-square-film-20261030-r1.zip`,zip=encodeZip(files);
await writeFile(path.join(out,name),zip);
await writeFile(path.join(out,'SHA256SUMS'),Buffer.concat([files.SHA256SUMS,Buffer.from(sha(zip)+'  '+name+'\n')]));
console.log(JSON.stringify({out,zip:path.join(out,name),bin_sha256:sha(result.candidate),zip_sha256:sha(zip),camera_tested:false},null,2));
