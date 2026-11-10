import {createHash} from 'node:crypto';
import {readFileSync,readdirSync} from 'node:fs';
const root=new URL('../',import.meta.url),sha=b=>createHash('sha256').update(b).digest('hex');
export function validateCompanionIdentity(value){
 if(!value||typeof value!=='object'||Array.isArray(value)||Object.keys(value).sort().join(',')!=='buildId,catalogHash,rendererHash'||Object.values(value).some(v=>typeof v!=='string'||!/^[a-f0-9]{64}$/.test(v)||/^0+$/.test(v)))throw Error('invalid companion identity');
 return {buildId:value.buildId,catalogHash:value.catalogHash,rendererHash:value.rendererHash};
}
export function companionSourceFingerprint(){
 const names=[...readdirSync(new URL('native/companion/',root)).filter(n=>/\.[ch]$/.test(n)).map(n=>'native/companion/'+n),'native/gr3/m10v_companion_owner.c','native/gr3/m10v_companion_owner.h','native/gr3/m10v_companion_extensions.inc','native/gr3/m10v_torn_overlay.h','scripts/build_gr3_companion_owner.py','contracts/companion-v1.json','contracts/extensions-v1.json','node/gr3-companion-owner.mjs'].sort();
 return sha(JSON.stringify(names.map(n=>[n,sha(readFileSync(new URL(n,root)))])));
}
export function companionOwnerBytes(manifest,fallback){
 const c=manifest.companion;if(c===undefined)return fallback;
 const need=(ok,message)=>{if(!ok)throw Error('companion owner: '+message);};
 need(c?.enabled===true&&c.schema==='m10v-companion-owner/v2','explicit component required');
 validateCompanionIdentity(c.identity);
 need(c.descriptor_offset===0x6400&&c.descriptor_bytes===64&&c.owner_bytes===0x6440&&c.payloadBytes===1024,'layout differs');
 need(Number.isInteger(c.base)&&Number.isInteger(c.bytes)&&c.base%128===0&&c.bytes>0&&c.bytes<65536,'code bounds');
 for(const name of ['init','start','stop','timer']){const at=c.symbols?.['m10v_companion_ui_'+name];need(Number.isInteger(at)&&at%4===0&&at>=c.base&&at<c.base+c.bytes,'callback code bounds');}
 return c.owner_bytes;
}

// Exact RTOS compilation closure; Linux transport is separately fingerprinted.
export const companionNativeSources = ["native/companion/runtime.c", "native/companion/auth.c", "native/companion/operations.c", "native/companion/transaction.c", "native/companion/extensions.c", "native/companion/resident_bridge.c", "native/gr3/m10v_companion_owner.c", "native/companion/auth.h", "native/companion/http_parser.h", "native/companion/json.h", "native/companion/operations.h", "native/companion/transaction.h", "native/companion/extensions.h", "native/gr3/m10v_companion_extensions.inc", "native/gr3/m10v_torn_overlay.h", "native/gr3/m10v_zoom_camera.h", "native/gr3/m10v_zoom.h", "native/gr3/m10v_isp_effects_camera.h", "native/gr3/m10v_isp_effects_state.h", "native/companion/resident_bridge.h", "native/companion/generated_contract.h", "native/gr3/m10v_companion_owner.h", "native/gr3/m10v_library.h", "native/gr3/m10v_tone.h", "native/gr3/m10v_sd_library.h", "contracts/companion-v1.json", "contracts/extensions-v1.json", "scripts/build_gr3_companion_owner.py"];
