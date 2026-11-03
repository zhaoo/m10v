// Read-only to supplied files; temporary compilation never exports a BIN.
import {readFileSync} from 'node:fs';
import {parseArgs} from 'node:util';
import {auditFlashInputs} from '../node/gr3-flash-safety.mjs';

try{
 const {values}=parseArgs({options:{source:{type:'string'},candidate:{type:'string'},receipt:{type:'string'},
  'expected-sha256':{type:'string'},model:{type:'string'},'camera-version':{type:'string'},
  'camera-origin':{type:'string'},'installed-sha256':{type:'string'},help:{type:'boolean'}}});
 if(values.help){
  console.log('Usage: node scripts/check_gr3_flash_safety.mjs --source official.bin --candidate candidate.bin --receipt M10V-build-receipt.json --expected-sha256 <download-record-sha256> --model gr3|gr3x --camera-version 2.10|1.60 --camera-origin official|m10v-verified [--installed-sha256 <previous-installed-bin-sha256>]\nRequires the exact reviewed checkout and its normal build tools. Only temp compilation/cache is written. Exit 2 means installation remains blocked, including after exact offline reproduction. Exit 1 means rejected input/check failure. No exit code certifies camera safety.');
 }else{
  const report=await auditFlashInputs({source:values.source?readFileSync(values.source):undefined,
   candidate:values.candidate?readFileSync(values.candidate):undefined,
   receipt:values.receipt?JSON.parse(readFileSync(values.receipt,'utf8')):undefined,
   expectedSha256:values['expected-sha256'],camera:{model:values.model,version:values['camera-version'],
    origin:values['camera-origin'],...(values['installed-sha256']?{installedSha256:values['installed-sha256']}:{})}});
  console.log(JSON.stringify(report,null,2));
  process.exitCode=report.status==='rejected'?1:2;
 }
}catch(error){
 console.log(JSON.stringify({status:'rejected',installation_allowed:false,camera_tested:false,reasons:[error.message]},null,2));
 process.exitCode=1;
}
