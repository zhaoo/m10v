import {createHash} from 'node:crypto';
import {existsSync} from 'node:fs';
import {readFile,writeFile,mkdtemp,rm} from 'node:fs/promises';
import {execFile} from 'node:child_process';
import {promisify} from 'node:util';
import os from 'node:os';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {inspectGr2,GR2_SHA256} from './gr2-firmware.mjs';
import {inspectGr1,GR1_SHA256} from './gr1-firmware.mjs';
import {inspectFirmwareImport,GR3_220_SHA256} from './firmware.mjs';

const root=fileURLToPath(new URL('..',import.meta.url)),run=promisify(execFile);
const profiles={
  gr2:['bin/rg2_v003.frm',GR2_SHA256],
  gr1:['bin/rg1_v051.frm',GR1_SHA256],
  gr4:['bin/fwdc248b-gr4-officical.bin','a2f664dfca034059eb0fd6e18ab08684c326b4a034d85c164dad7e1ec9b5655f'],
  gr3:['bin/fwdc239b-gr3-official.bin','d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4'],
  gr3x:['bin/fwdc243b-gr3x-official.bin','708e79f3b7b96a7e1581b4acf4c412233050a1832718ef7f06c8397db1b431c7'],
};
const hash=b=>createHash('sha256').update(b).digest('hex');
export async function readModelOfficial(model){
  if(!Object.hasOwn(profiles,model))throw new Error('unsupported model');
  const [file,expected]=profiles[model],data=await readFile(path.join(root,file));
  if(hash(data)!==expected)throw new Error('local official firmware identity differs');
  return data;
}
let inspectingGr4=false;
export async function inspectModelFirmware(data){
  if(!Buffer.isBuffer(data))throw new Error('firmware must be bytes');
  const identity=hash(data),model=identity===GR3_220_SHA256?'gr3':Object.keys(profiles).find(key=>profiles[key][1]===identity);
  if(!model)return {...inspectFirmwareImport(data),workspace_url:'/gr3/'};
  if(model==='gr2')return {...inspectGr2(data),workspace_url:'/gr2/'};
  if(model==='gr1')return {...inspectGr1(data),workspace_url:'/gr1/'};
  if(model==='gr3'||model==='gr3x')return {...inspectFirmwareImport(data),workspace_url:'/gr3/'};
  if(inspectingGr4)throw new Error('GR IV inspection is already running');
  inspectingGr4=true;let folder;
  try{
    folder=await mkdtemp(path.join(os.tmpdir(),'m10v-gr4-inspect-'));
    const input=path.join(folder,'official.bin');await writeFile(input,data,{mode:0o400});
    const bundled=path.join(root,'.venv/bin/python');
    const python=process.env.M10V_PYTHON|| (existsSync(bundled)?bundled:'python3');
    const {stdout}=await run(python,['-c',
      'import json,sys; from pathlib import Path; from scripts.analyze_model_firmware import inspect_gr4; print(json.dumps(inspect_gr4(Path(sys.argv[1]).read_bytes())))',input],
      {cwd:root,timeout:60000,maxBuffer:2*1024*1024});
    return {...JSON.parse(stdout),workspace_url:'/gr4/',capabilities:{
      inspect:{status:'verified_offline',can_read:true},
      reference_editor:{status:'reference_verified',can_build:true},
      native_film_library:{status:'not_ported',can_build:false},
    }};
  }finally{if(folder)await rm(folder,{recursive:true,force:true});inspectingGr4=false;}
}
