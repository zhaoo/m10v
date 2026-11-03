const MAX_PACKAGE_BYTES=70*1024*1024;
const OFFICIAL_SOURCE='d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4';
const FIRMWARE_CHECKS=['pinned_source','camera_declaration','strict_decode','receipt_binding','exact_rebuild'];
const PACKAGE_CHECKS=['firmware_proof','runtime_binding','independent_service_build','elf_and_pairing','archive_hashes'];
const IDENTITY_FIELDS=['buildId','catalogHash','rendererHash'];
const isRecord=value=>value!==null&&typeof value==='object'&&!Array.isArray(value);
const isHash=value=>typeof value==='string'&&/^[a-f0-9]{64}$/.test(value)&&!/^0+$/.test(value);
const sameHash=(value,expected)=>isHash(value)&&isHash(expected)&&value===expected;
function need(ok,message){if(!ok)throw new Error('GRemote 连接包安全验证未通过：'+message);}
const completeChecks=(value,names)=>isRecord(value)&&names.every(name=>value[name]===true);
function validIdentity(value){
 return isRecord(value)&&Object.keys(value).sort().join(',')==='buildId,catalogHash,rendererHash'&&IDENTITY_FIELDS.every(field=>isHash(value[field]));
}

/** Read bounded public evidence. Pairing keys belong only in the private ZIP. */
export function readGRemotePackageSafety(response){
 try{
  const encoded=response?.headers?.get('X-M10V-GRemote-Package-Receipt');
  if(typeof encoded!=='string'||!encoded.length||encoded.length>256*1024||!/^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(encoded))throw Error('invalid header');
  const binary=atob(encoded);
  if(btoa(binary)!==encoded)throw Error('noncanonical base64');
  const value=JSON.parse(new TextDecoder('utf-8',{fatal:true}).decode(Uint8Array.from(binary,char=>char.charCodeAt(0))));
  if(!isRecord(value))throw Error('invalid audit');
  return value;
 }catch{throw new Error('GRemote 连接包安全验证信息缺失或格式无效，已停止下载。');}
}

function verifyFirmwareEvidence(firmware,sourceSha256,configurationSha256){
 need(isRecord(firmware)&&firmware.schema==='m10v-web-firmware-safety/v1'&&firmware.status==='offline_verified_camera_unverified'
  &&firmware.artifact_kind==='firmware'&&firmware.download_allowed===true&&firmware.installation_allowed===false&&firmware.camera_tested===false
  &&completeChecks(firmware.checks,FIRMWARE_CHECKS),'缺少完整的原始固件离线验证证据。');
 need(firmware.model==='gr3'&&firmware.public_version==='2.10'&&firmware.filename==='fwdc239b.bin','原始固件机型、版本或文件名不匹配。');
 need(sourceSha256===OFFICIAL_SOURCE&&sameHash(firmware.source_sha256,sourceSha256),'原始固件来源摘要不匹配。');
 need(sameHash(firmware.configuration_sha256,configurationSha256),'原始固件配置摘要不匹配。');
 need(isHash(firmware.candidate_sha256)&&Number.isSafeInteger(firmware.candidate_bytes)&&firmware.candidate_bytes>0&&firmware.candidate_bytes<=MAX_PACKAGE_BYTES,'原始固件摘要或字节数无效。');
}

/** Verify ZIP bytes and their firmware binding; camera acceptance stays unverified. */
export async function verifyGRemotePackageBlob(blob,{audit,sourceSha256,configurationSha256,model,filename,receipt}={}){
 need(isRecord(audit)&&audit.schema==='m10v-gremote-delivery-safety/v1'&&audit.status==='offline_verified_camera_unverified'
  &&audit.artifact_kind==='gremote_connection_package'&&audit.download_allowed===true&&audit.installation_allowed===false&&audit.camera_tested===false
  &&completeChecks(audit.checks,PACKAGE_CHECKS),'缺少完整的连接包离线验证证据。');
 need(model==='gr3'&&audit.model==='gr3'&&audit.public_version==='2.10','连接包仅支持 GR III 2.10。');
 need(filename==='m10v-gr3-gremote.zip'&&audit.filename===filename,'连接包文件名不匹配。');
 need(audit.pairing_policy==='fresh-per-download'&&audit.apk_included===false&&typeof audit.film_pack_included==='boolean'&&isHash(audit.service_sha256),'独立服务、个人配对或组件回执无效。');
 verifyFirmwareEvidence(audit.firmware,sourceSha256,configurationSha256);
 need(isRecord(receipt)&&receipt.model==='GR III'&&receipt.camera_model==='gr3'&&receipt.public_version==='2.10'&&receipt.filename==='fwdc239b.bin','原始固件构建回执缺失或机型不匹配。');
 for(const field of ['source_sha256','configuration_sha256','candidate_sha256'])need(sameHash(receipt[field],audit.firmware[field]),`原始固件构建回执摘要不匹配（${field}）。`);
 need(receipt.candidate_bytes===audit.firmware.candidate_bytes,'原始固件构建回执字节数不匹配。');
 verifyFirmwareEvidence(receipt.safety,sourceSha256,configurationSha256);
 need(sameHash(receipt.safety.candidate_sha256,audit.firmware.candidate_sha256)&&receipt.safety.candidate_bytes===audit.firmware.candidate_bytes,'构建回执的固件安全证据不匹配。');
 need(validIdentity(audit.companion_identity)&&validIdentity(receipt.companion_identity)
  &&IDENTITY_FIELDS.every(field=>audit.companion_identity[field]===receipt.companion_identity[field]),'固件与连接包身份不匹配。');
 need(blob instanceof Blob,'下载文件不是有效的 Blob。');
 need(blob.size<=MAX_PACKAGE_BYTES,'ZIP 大小超过 70 MiB 安全验证上限。');
 need(Number.isSafeInteger(audit.candidate_bytes)&&audit.candidate_bytes>0&&audit.candidate_bytes===blob.size,'ZIP 字节数不匹配。');
 need(isHash(audit.candidate_sha256),'ZIP SHA-256 摘要缺失或无效。');
 need(typeof globalThis.crypto?.subtle?.digest==='function','当前浏览器无法执行 SHA-256 安全验证。');
 let digest;
 try{
  const bytes=await blob.arrayBuffer();
  if(bytes.byteLength!==audit.candidate_bytes)throw Error('invalid byte count');
  digest=Array.from(new Uint8Array(await globalThis.crypto.subtle.digest('SHA-256',bytes)),byte=>byte.toString(16).padStart(2,'0')).join('');
 }catch{throw new Error('GRemote 连接包 SHA-256 安全验证失败，已停止下载。');}
 need(sameHash(digest,audit.candidate_sha256),'ZIP SHA-256 摘要不匹配。');
 return audit;
}
