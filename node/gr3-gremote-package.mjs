import {createHash} from 'node:crypto';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import {existsSync} from 'node:fs';
import {mkdtemp,chmod,writeFile,readFile,rm,stat} from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {requireWebDownload} from './firmware-web-safety.mjs';
import {validateCompanionIdentity} from './gr3-companion-owner.mjs';

const root=fileURLToPath(new URL('../',import.meta.url)),run=promisify(execFile),issued=new WeakMap();
const maxBytes=70*1024*1024,official='d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4';
const hash=bytes=>createHash('sha256').update(bytes).digest('hex');
function need(ok,message){if(!ok)throw Object.assign(new Error('GRemote 连接包安全校验未通过：'+message),{code:'M10V_GREMOTE_PACKAGE_CHECK_FAILED'});}
const alive=signal=>signal?.throwIfAborted();
const sameIdentity=(a,b)=>['buildId','catalogHash','rendererHash'].every(k=>a?.[k]===b?.[k]);
export function requireGRemotePackageDownload(candidate,audit){
 const proof=issued.get(audit);
 need(proof&&Buffer.isBuffer(candidate)&&candidate.length===proof.bytes&&hash(candidate)===proof.digest,'下载缺少本次校验记录，或 ZIP 字节已变化。');
 return audit;
}
export async function createGRemotePackage(firmwareResult,{signal}={}){
 alive(signal);const original=firmwareResult?.candidate,audit=firmwareResult?.audit;
 requireWebDownload(original,audit);
 const candidate=Buffer.from(original),receipt=structuredClone(firmwareResult.receipt),manifest=structuredClone(firmwareResult.runtimeManifest);
 requireWebDownload(candidate,audit);
 need(firmwareResult.filename==='fwdc239b.bin'&&audit.model==='gr3'&&audit.public_version==='2.10'&&audit.artifact_kind==='firmware'&&audit.source_sha256===official,'仅支持精确官方 GR III 2.10；GR IIIx 暂不支持。');
 need(candidate.length<=maxBytes&&receipt?.model==='GR III'&&receipt.camera_model==='gr3'&&receipt.public_version==='2.10'&&receipt.filename==='fwdc239b.bin'&&receipt.source_sha256===official&&receipt.candidate_sha256===hash(candidate)&&receipt.candidate_bytes===candidate.length&&receipt.configuration_sha256===audit.configuration_sha256,'固件与完整构建回执不符。');
 need(receipt.safety&&JSON.stringify(receipt.safety)===JSON.stringify(audit),'构建回执缺少本次固件校验记录。');
 const identity=validateCompanionIdentity(manifest?.companion?.identity);
 validateCompanionIdentity(receipt.companion_identity);
 need(manifest.camera_model==='gr3'&&manifest.companion.enabled===true&&manifest.companion.schema==='m10v-companion-owner/v2'&&sameIdentity(identity,receipt.companion_identity),'GR III 运行体与回执 companion 身份不符。');
 need(manifest.companion.camera_tested===false&&manifest.companion.continuousCacheValidated===false,'机身验收状态必须保持未验证。');
 alive(signal);let folder,result;
 try{
  folder=await mkdtemp(path.join(os.tmpdir(),'m10v-gremote-download-'));await chmod(folder,0o700);alive(signal);
  for(const [name,data] of [['fwdc239b.bin',candidate],['M10V-build-receipt.json',JSON.stringify(receipt)],['M10V-runtime-manifest.json',JSON.stringify(manifest)]]){alive(signal);await writeFile(path.join(folder,name),data,{mode:0o600,flag:'wx'});}
  const compiler=process.env.M10V_LLVM_CLANG||['/opt/homebrew/opt/llvm/bin/clang','/usr/local/opt/llvm/bin/clang','/usr/bin/clang'].find(existsSync);
  const linker=[process.env.M10V_LLVM_LD,compiler&&path.join(path.dirname(compiler),'ld.lld'),'/opt/homebrew/opt/lld/bin/ld.lld','/usr/local/opt/lld/bin/ld.lld','/usr/bin/ld.lld'].find(p=>p&&existsSync(p));
  const env={...process.env,M10V_NODE:process.execPath,TMPDIR:folder,TMP:folder,TEMP:folder,PATH:[compiler&&path.dirname(compiler),linker&&path.dirname(linker),path.dirname(process.execPath),process.env.PATH].filter(Boolean).join(path.delimiter)};
  const output=path.join(folder,'m10v-gr3-gremote.zip');
  let stdout;
  try{({stdout}=await run(process.env.M10V_PYTHON||'python3',['scripts/package_gremote_connection.py','--candidate-dir',folder,'--out',output],{cwd:root,env,signal,timeout:120000,maxBuffer:1024*1024}));}
  catch(error){alive(signal);throw Object.assign(new Error('GRemote 连接包独立校验或服务构建失败，未签发下载。'),{code:'M10V_GREMOTE_PACKAGE_BUILD_FAILED'});}
  alive(signal);need((await stat(output)).size<=maxBytes,'ZIP 超过 70 MiB 限制。');
  const zip=await readFile(output);alive(signal);const metadata=JSON.parse(stdout);
  need(metadata.schema==='m10v-gremote-connection-package/v1'&&metadata.model==='GR III'&&metadata.public_version==='2.10'&&metadata.status==='offline_verified_camera_unverified'&&metadata.camera_tested===false&&metadata.installation_allowed===false&&metadata.apk_included===false&&metadata.pairing_policy==='camera-hotspot-per-boot'&&metadata.firmware_sha256===hash(candidate)&&metadata.sha256===hash(zip)&&metadata.bytes===zip.length&&sameIdentity(metadata.companion_identity,identity),'ZIP 与独立服务构建回执不符。');
  const packageAudit=Object.freeze({schema:'m10v-gremote-delivery-safety/v1',status:'offline_verified_camera_unverified',artifact_kind:'gremote_connection_package',download_allowed:true,installation_allowed:false,camera_tested:false,model:'gr3',public_version:'2.10',filename:'m10v-gr3-gremote.zip',candidate_sha256:hash(zip),candidate_bytes:zip.length,firmware:audit,service_sha256:metadata.service_sha256,companion_identity:Object.freeze({...identity}),pairing_policy:'camera-hotspot-per-boot',apk_included:false,film_pack_included:metadata.film_pack_included,checks:Object.freeze({firmware_proof:true,runtime_binding:true,independent_service_build:true,elf_and_pairing:true,archive_hashes:true})});
  issued.set(packageAudit,{digest:packageAudit.candidate_sha256,bytes:zip.length});
  result={candidate:zip,filename:packageAudit.filename,audit:packageAudit,headers:{'Cache-Control':'private, no-store','X-M10V-GRemote-Package-Receipt':Buffer.from(JSON.stringify(packageAudit)).toString('base64')}};
 }finally{if(folder)await rm(folder,{recursive:true,force:true});}
 alive(signal);return result;
}
