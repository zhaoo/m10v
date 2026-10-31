// Reproducible local camera-test export; does not flash or deploy.
import {readFile,mkdir,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {prepareNative,generateNative,readNativeOfficial} from '../node/gr3-native-library.mjs';
import {resolveIspEffectOptions} from '../node/gr3-isp-effect-options.mjs';
const root=fileURLToPath(new URL('..',import.meta.url));
const args=process.argv.slice(2),modelAt=args.indexOf('--model');
const model=modelAt<0?'gr3':args[modelAt+1];
if(!['gr3','gr3x'].includes(model)||args.some(v=>v.startsWith('--')&&!['--model','--release','--dsp-version-unlock'].includes(v)))throw Error('usage: build_gr3_device_candidate.mjs [out] [configuration.json] [--model gr3|gr3x] [--release] [--dsp-version-unlock]');
const positional=args.filter((v,i)=>!v.startsWith('--')&&(modelAt<0||i!==modelAt+1));
const out=path.resolve(positional[0]||path.join(root,'builds/gr3-integrated-device-test'));
const configuration=positional[1]?JSON.parse(await readFile(positional[1],'utf8')):{
 slots:[298,77,75,37,33].map((film,i)=>({film,grain:i===4?2:0,soft:0,halo:{gain:3,spread:3,threshold:5,profile:2}})),
 stamp:2,format:0,corner:3,color:1};
const extensions={aspect:true,level:true,negativeGrain:true},debug_mode=!process.argv.includes('--release');
const version_unlock=process.argv.includes('--dsp-version-unlock')?{enabled:true,mode:'dsp-package-only'}:{enabled:false};
const source=await readNativeOfficial(model);
const options=resolveIspEffectOptions(source,{extensions,debug_mode,version_unlock,pure_isp_effects:true,hdf_enabled:true,border_enabled:true},model==='gr3x'?'GR IIIx':'GR III');
const plan=prepareNative(source,configuration,options);
const result=await generateNative(source,configuration,plan.configuration_sha256,options);
if(!result.manifest.pure_isp_effects?.enabled)throw Error('已核验机型的纯 ISP 效果未进入部署构建');
await mkdir(path.join(out,'fw'),{recursive:true});await mkdir(path.join(out,'evidence'),{recursive:true});
await writeFile(path.join(out,'fw',plan.filename),result.candidate);
for(const [name,value] of Object.entries({'M10V-configuration.json':{configuration,extensions,debug_mode,version_unlock},'M10V-build-receipt.json':result.receipt,'M10V-preparation.json':plan,'evidence/M10V-runtime-manifest.json':result.manifest}))await writeFile(path.join(out,name),JSON.stringify(value,null,2)+'\n');
await writeFile(path.join(out,'evidence/M10V-runtime-arm.bin'),result.runtime);
await writeFile(path.join(out,'evidence/native-only.bin'),result.nativeCandidate);
if(result.component)await writeFile(path.join(out,'evidence/aspect-level.bin'),result.component);
await writeFile(path.join(out,'SHA256SUMS'),result.receipt.candidate_sha256+'  fw/'+plan.filename+'\n');
console.log(JSON.stringify({file:path.join(out,'fw',plan.filename),bytes:result.candidate.length,sha256:result.receipt.candidate_sha256,build_id:result.receipt.debug_log?.build_id??null,extensions},null,2));
