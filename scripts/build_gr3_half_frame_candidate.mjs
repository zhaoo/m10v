// Reproducible local candidate through the same web preflight/compiler/auditor.
import {mkdir,writeFile,stat} from 'node:fs/promises';
import path from 'node:path';
import {readNativeOfficial,prepareNative,generateNative} from '../node/gr3-native-library.mjs';
import {defaultConfiguration} from '../web/gr3/native-library-state.mjs';
import {auditHalfPair} from './gr3_half_frame_package_contract.mjs';
const args=process.argv.slice(2),debug_mode=true,positional=args.filter(a=>a!=='--debug');
if(positional.some(a=>a.startsWith('--')))throw Error('Unknown candidate option');
const folder=path.resolve(positional[0]||'builds/gr3-half-frame-r4-debug-20261030');
if(positional.length>1)throw Error('usage: node scripts/build_gr3_half_frame_candidate.mjs [--debug] [new-output-directory]');
try{await stat(folder);throw Error('Candidate directory exists; choose a new directory');}catch(e){if(e.code!=='ENOENT')throw e;}
const configuration=defaultConfiguration(),options={appended_slots:true,hdf_enabled:true,halation_enabled:true,
 border_enabled:true,debug_mode,extensions:{aspect:true,level:true,negativeGrain:true,rawNr:{mode:'stock'}}};
const source=await readNativeOfficial('gr3'),plan=prepareNative(source,configuration,options);
const result=await generateNative(source,configuration,plan.configuration_sha256,options);
if(result.receipt.composition.half_frame.enabled!==true||!result.manifest.border.pixel_pipeline_enabled||
 !result.manifest.half_pair?.enabled||!result.receipt.composition.half_pair?.enabled)throw Error('Half-pair or border capability missing');
auditHalfPair(result.manifest,result.receipt,result.runtime);
await mkdir(folder,{recursive:false});
for(const[name,bytes]of Object.entries({'fwdc239b.bin':result.candidate,'runtime.bin':result.runtime,
 'plan.json':JSON.stringify(plan,null,2),'receipt.json':JSON.stringify(result.receipt,null,2),
 'manifest.json':JSON.stringify(result.manifest,null,2),'configuration.json':JSON.stringify(plan.configuration,null,2),
 'options.json':JSON.stringify(options,null,2)}))await writeFile(path.join(folder,name),bytes);
console.log(JSON.stringify({folder,sha256:result.receipt.candidate_sha256,verified_hooks:result.receipt.verified_hooks,camera_tested:false},null,2));
