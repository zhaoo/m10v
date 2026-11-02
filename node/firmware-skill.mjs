import {readFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import {encodeZip} from './gr3-sd-film-export.mjs';

// Fixed allowlist: never archive a skill directory recursively or include BINs.
const names=['SKILL.md','references/firmware-safety.md','scripts/verify_source.py'];
export async function firmwareSkillArchive(){
 const rows={},files={};
 for(const name of names){
  const bytes=await readFile(new URL('../skills/m10v-firmware-safety/'+name,import.meta.url));
  rows['m10v-firmware-safety/'+name]=bytes;
  files[name]=createHash('sha256').update(bytes).digest('hex');
 }
 rows['m10v-firmware-safety/manifest.json']=Buffer.from(JSON.stringify({schema:'m10v-firmware-safety-skill/v1',version:'2026.11.03.1',includes_firmware:false,files})+'\n');
 return encodeZip(rows);
}
