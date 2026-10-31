// Package only an already audited export; never writes a camera or publishes.
import {readFile,readdir,mkdir,writeFile} from 'node:fs/promises';
import {resolve,dirname,basename} from 'node:path';
import {createHash} from 'node:crypto';
import {execFileSync} from 'node:child_process';
import {buildSdFilmPack,auditSdFilmPack} from '../node/gr3-sd-film-pack.mjs';
import {encodeZip} from '../node/gr3-sd-film-export.mjs';

const [inputArg,outputArg,diagnosticsArg]=process.argv.slice(2);
if(!inputArg||!outputArg)throw Error('usage: node scripts/package_gr3_pure_isp_candidate.mjs export-directory NEW-output-directory');
const input=resolve(inputArg),out=resolve(outputArg),sha=b=>createHash('sha256').update(b).digest('hex');
const json=v=>Buffer.from(JSON.stringify(v,null,2)+'\n');
const receipt=JSON.parse(await readFile(resolve(input,'M10V-build-receipt.json')));
const manifest=JSON.parse(await readFile(resolve(input,'M10V-runtime-manifest.json')));
const model=manifest.camera_model;
if(!['gr3','gr3x'].includes(model)||receipt.camera_model!==model||manifest.pure_isp_effects?.enabled!==true||
 receipt.pure_isp_effects!==true||receipt.composition?.verified!==true||receipt.camera_tested===true)
 throw Error('not an unvalidated GR III/IIIx pure ISP candidate');
const filename=model==='gr3'?'fwdc239b.bin':'fwdc243b.bin';
if(receipt.filename!==filename)throw Error('receipt filename/model mismatch');
const binary=await readFile(resolve(input,filename)),runtime=await readFile(resolve(input,'M10V-runtime-arm.bin'));
if(sha(binary)!==receipt.candidate_sha256||binary.length!==receipt.candidate_bytes||sha(runtime)!==manifest.code_sha256)
 throw Error('export BIN/runtime identity mismatch');
const sources={};
for(const [p,expected]of Object.entries(manifest.sources)){
 const b=await readFile(p);
 if(sha(b)!==expected)throw Error('source changed since export: '+p);
 sources[p]=b;
}
sources['scripts/analyze_gr3_isp_effect_fidelity.py']=await readFile('scripts/analyze_gr3_isp_effect_fidelity.py');
for(const p of ['scripts/package_gr3_pure_isp_candidate.mjs','docs/superpowers/specs/2026-10-31-gr3-pure-isp-effects-design.md',
 'docs/superpowers/plans/2026-10-31-gr3-pure-isp-effects.md'])sources[p]=await readFile(p);
for(const p of await readdir('tests'))if(p.startsWith('test_gr3_isp_effect')||p.startsWith('test_gr3_pure_isp'))
 sources['tests/'+p]=await readFile('tests/'+p);
sources['node/gr3-pure-isp-effects.test.mjs']=await readFile('node/gr3-pure-isp-effects.test.mjs');
for(const p of ['tests/test_gr3_module_dispatch_trace.py','tests/test_gr3_debug.py',
 'tests/test_gr3_capture_lifecycle_integration.py','scripts/analyze_gr3_800t_mapping.py',
 'scripts/analyze_gr3_border_iip.py'])sources[p]=await readFile(p);
if(diagnosticsArg){sources[diagnosticsArg]=await readFile(diagnosticsArg);sources['scripts/read_gr3_debug_log.py']=await readFile('scripts/read_gr3_debug_log.py');}
const pack=buildSdFilmPack();auditSdFilmPack(pack);
const label=model==='gr3'?'GR III 2.10':'GR IIIx 1.60';
const readme=`M10V 纯 ISP 效果测试候选 — ${label}\n\n仅用于 ${label}，禁止跨机型刷入。尚未实机验收，不是正式发布。\n新增“效果”菜单：漏光（强度、位置、范围）、颗粒（模式、粒径）、模糊（强度、范围）。\n颗粒“继承”使用当前胶卷颗粒档位；“关闭”覆盖胶卷档位。默认新增效果关闭。\n新增效果的像素操作均走原生 ISP，CPU 仅处理参数和同步。Pixel/Charmera/HDR 等未接入路径保留原行为。\n\n安装：备份 SD 卡与机内配置，确认机型和电量充足。将 ${filename} 放 SD 卡根目录，按现有 M10V 固件更新流程安装。\nSD/M10V/FILMS.M10 为匹配胶卷资源；只合并所需文件，不覆盖其他设置或存档。已有机内设置优先。\n安装前记录当前可用固件，保留已验证的同机型恢复包。恢复使用原有同机型更新流程。\n\n验证：\n1. 冷启动、原厂菜单返回、五槽切换、关闭全部新增效果拍摄和回放。\n2. 漏光三档强度、左右/双侧、三档范围；横向、左右竖拍、倒置和裁切。\n3. 颗粒关闭/弱/中/强与三档粒径，检查真实照片细节、阴影及亮部。\n4. 模糊三档强度和范围，与 HDF 关闭/各档组合。\n5. 三效果组合、RAW+JPEG、连续拍摄、回放和重启设置持久化。\n6. 对比关闭/开启的存片耗时，记录机型、分辨率、卡型号及操作步骤。\n\n异常处理：若 ISP 出错或无法确认任务资源安全，程序保留等待以阻止释放活跃缓冲或编码半成品。\n如长时间无响应，停止操作，等待卡写入指示停止后正常关机重启；仍无法操作时按相机既有恢复流程处理。\n不要在卡写入时拔卡或移除电池。回传异常前后的步骤、照片和 M10V 调试文件（如产生）。\n\n验证界限：已执行离线 ARM 控制路径、构建及最终 BIN 回读检查；未实测 ISP 输出、物理 DMA、画质、连拍及性能。\n固件 SHA-256: ${sha(binary)}\n状态: WAITING_FOR_USER_VALIDATION\n`;
const git=args=>execFileSync('git',args,{encoding:'utf8'}).trim();
const provenance={status:'WAITING_FOR_USER_VALIDATION',model,firmware:label,
 git_revision:git(['rev-parse','HEAD']),git_branch:git(['branch','--show-current']),git_status:git(['status','--short']),
 candidate_sha256:sha(binary),runtime_sha256:sha(runtime),source_files:Object.fromEntries(Object.entries(sources).map(([p,b])=>[p,sha(b)])),
 camera_tested:false,performance_measured:false};
const files={[filename]:binary,'README.txt':Buffer.from(readme),'SD/M10V/FILMS.M10':pack,
 'evidence/M10V-build-receipt.json':json(receipt),'evidence/M10V-runtime-manifest.json':json(manifest),
 'evidence/M10V-configuration.json':await readFile(resolve(input,'M10V-configuration.json')),
 'evidence/provenance.json':json(provenance),'evidence/source-snapshot.zip':encodeZip(sources),
 'evidence/validation.md':await readFile('docs/testing/gr3-pure-isp-effects-20261031.md'),
 'LICENSE':await readFile('LICENSE'),'THIRD_PARTY_NOTICES.md':await readFile('THIRD_PARTY_NOTICES.md')};
for(const p of ['third_party/curated-film-luts/LICENSE','third_party/spectral-film-lut/LICENSE',
 'third_party/style-filter-luts/street-license','third_party/style-filter-luts/film-luts-license',
 'third_party/style-filter-luts/README.md'])files['licenses/'+p.replaceAll('/','-')]=await readFile(p);
files['evidence/final-validation.log']=await readFile(resolve(input,'final-validation.log'));
for(const p of ['host-comparison.png','host-fit.json']){
 try{files['evidence/host-model/'+p]=await readFile(resolve(input,'visual-audit',p));}
 catch(error){if(error.code!=='ENOENT')throw error;}
}
if(diagnosticsArg){
 files['evidence/validation.md']=sources[diagnosticsArg];
 files['README.txt']=Buffer.concat([files['README.txt'],Buffer.from('\n'),sources[diagnosticsArg]]);
}
if(manifest.debug_mode){
 const d=manifest.debug_log;
 if(!d?.build_id||!Array.isArray(d.files))throw Error('debug candidate lacks diagnostic identity');
 files['README.txt']=Buffer.concat([files['README.txt'],Buffer.from('\n诊断 build_id: '+d.build_id+'\n本测试包启用存片诊断，发生异常时回传 SD 卡根目录的 '+d.files.join('、')+'（如存在）。\n日志为环形窗口；没有某条事件不能证明事件从未发生。性能计时也包含诊断开销。\n')]);
}
files.SHA256SUMS=Buffer.from(Object.entries(files).map(([p,b])=>sha(b)+'  '+p).join('\n')+'\n');
await mkdir(out,{recursive:false});
for(const[p,b]of Object.entries(files)){await mkdir(dirname(resolve(out,p)),{recursive:true});await writeFile(resolve(out,p),b);}
const zip=encodeZip(files),zipname=basename(out)+'.zip';
await writeFile(resolve(out,zipname),zip);
await writeFile(resolve(out,'SHA256SUMS'),files.SHA256SUMS.toString()+sha(zip)+'  '+zipname+'\n');
console.log(JSON.stringify({out,zip:resolve(out,zipname),zip_sha256:sha(zip),bin_sha256:sha(binary),status:provenance.status},null,2));
