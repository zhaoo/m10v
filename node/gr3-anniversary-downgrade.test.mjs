import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {spawnSync} from 'node:child_process';
import {inspectFirmwareImport} from './firmware.mjs';
import {decodeFrameMap,sum32} from './gr3-frames.mjs';
import {ANNIVERSARY_DOWNGRADE_PROFILES as profiles,prepareAnniversaryDowngrade,buildAnniversaryDowngrade,
  verifyAnniversaryDowngrade,exportAnniversaryDowngrade} from './gr3-anniversary-downgrade.mjs';
const hash=b=>createHash('sha256').update(b).digest('hex');
function repair(b){b.writeUInt32LE(0,b.length-4);b.writeUInt32LE(-sum32(b)>>>0,b.length-4);return b;}
function rows(d){const rows={};let at=0;for(let i=0;i<14;i++){
  const name=d.toString('ascii',at,at+8).split('\0')[0];
  const size=name==='RES'?d.length-4-at-16:d.readUInt32LE(at+12);
  rows[name]={header:at,start:at+16,end:at+16+size};at+=16+size;
}assert.equal(at+4,d.length);return rows;}
// A separate test-only repacker creates checksum-valid malicious containers.
function repack(candidate,changed,{replaceFirst=false}={}){
  const {decoded,frames}=decodeFrameMap(candidate),chunks=[];
  for(const frame of frames){const start=frame.decoded_start,end=frame.decoded_end;
    if(!(replaceFirst && frame===frames[0]) && changed.subarray(Math.max(0,start-8191),end).equals(decoded.subarray(Math.max(0,start-8191),end)))
      chunks.push(candidate.subarray(128+frame.encoded_start,128+frame.encoded_end));
    else for(let at=start;at<end;at+=0x6000){const b=changed.subarray(at,Math.min(at+0x6000,end)),h=Buffer.alloc(2);h.writeUInt16BE(0x8000|b.length);chunks.push(h,b);}
  }
  chunks.push(Buffer.alloc(2));const payload=Buffer.concat(chunks),footer=Buffer.from(candidate.subarray(-24));footer.writeUInt32LE(payload.length,12);
  return repair(Buffer.concat([candidate.subarray(0,128),payload,Buffer.alloc(-(128+payload.length)&3),footer]));
}
function unzipStored(zip){const result={};let at=0;while(zip.readUInt32LE(at)===0x04034b50){
  assert.equal(zip.readUInt16LE(at+8),0);const size=zip.readUInt32LE(at+18),n=zip.readUInt16LE(at+26),extra=zip.readUInt16LE(at+28);
  const name=zip.toString('utf8',at+30,at+30+n),start=at+30+n+extra;result[name]=zip.subarray(start,start+size);at=start+size;
}assert.equal(zip.readUInt32LE(at),0x02014b50);return result;}

test('anniversary builder rejects unsupported models before reading input',()=>{
  for(const model of ['gr4','GR III','__proto__',undefined])
    assert.throws(()=>prepareAnniversaryDowngrade(Buffer.alloc(0),Buffer.alloc(0),model),/unsupported model/);
});

for(const [model,fixtureEnv,oldFile] of [
  ['gr3','M10V_GR3_220_FIXTURE','fwdc239b-gr3-official.bin'],
  ['gr3x','M10V_GR3X_170_FIXTURE','fwdc243b-gr3x-official.bin'],
]){
  const fixture=process.env[fixtureEnv],profile=profiles[model];
  test(`${model}: exact two-stage package, independent known hash, CPU preservation and immutable inputs`,{skip:!fixture},()=>{
    const source=readFileSync(fixture),old=readFileSync(new URL('../bin/'+oldFile,import.meta.url));
    const sourceHash=hash(source),oldHash=hash(old),plan=prepareAnniversaryDowngrade(source,old,model);
    assert.equal(plan.status,'ready');assert.equal(plan.model,model);assert.equal(plan.from_version,profile.from_version);assert.equal(plan.to_version,profile.to_version);
    const {candidate,receipt}=buildAnniversaryDowngrade(source,old,model);
    assert.equal(hash(candidate),profile.candidate_sha256);assert.equal(receipt.changed_decoded_bytes,9);
    assert.equal(candidate.length,model==='gr3'?30509128:30509144);
    assert.equal(receipt.camera_verified,false);assert.equal(receipt.stable,false);assert.equal(receipt.cpu_entirely_preserved,true);
    assert.equal(receipt.combined_footer_kind,2);assert.equal(candidate.readUInt32BE(0x50),source.readUInt32BE(0x50));
    const a=decodeFrameMap(source).decoded,b=decodeFrameMap(candidate).decoded,r=rows(a);
    assert.ok(a.subarray(r.CPU.start,r.CPU.end).equals(b.subarray(r.CPU.start,r.CPU.end)));
    assert.equal(b.readUInt32BE(r.RTOS.start+0x2038),profile.version+256);
    assert.equal(b.subarray(r.RTOS.start+0x6286cc,r.RTOS.start+0x6286d0).toString('hex'),'e6ffffea');
    assert.equal(sum32(candidate),0);assert.equal(sum32(b),0);
    assert.deepEqual(verifyAnniversaryDowngrade(source,old,model,candidate),receipt);
    assert.throws(()=>inspectFirmwareImport(candidate),/component copies differ/,'normal importer retains its original component version boundary');
    const input={accepted_plan_id:plan.plan_id,acknowledge_instructions:true};
    const exported=exportAnniversaryDowngrade(source,old,model,input),files=unzipStored(exported.zip);
    assert.equal(exported.filename,profile.zip_filename);
    assert.deepEqual(Object.keys(files),['stage-1-bridge/'+profile.filename,'stage-2-official/'+profile.filename,'receipt.json','README.txt','SHA256SUMS']);
    assert.ok(files['stage-1-bridge/'+profile.filename].equals(candidate));assert.ok(files['stage-2-official/'+profile.filename].equals(old));
    assert.deepEqual(JSON.parse(files['receipt.json']),receipt);
    assert.match(files['README.txt'].toString(),/待相机验证/);assert.match(files['README.txt'].toString(),/第一阶段.*正常重启/);
    for(const line of files.SHA256SUMS.toString().trim().split('\n')){const [sha,name]=line.split('  ');assert.equal(hash(files[name]),sha);}
    assert.equal(hash(source),sourceHash);assert.equal(hash(old),oldHash);
  });
  test(`${model}: tampered sources, stale plans and unknown configuration are refused`,{skip:!fixture},()=>{
    const source=readFileSync(fixture),old=readFileSync(new URL('../bin/'+oldFile,import.meta.url));
    const plan=prepareAnniversaryDowngrade(source,old,model);
    const badSource=Buffer.from(source);badSource[512]^=1;repair(badSource);
    const badOld=Buffer.from(old);badOld[512]^=1;repair(badOld);
    assert.throws(()=>buildAnniversaryDowngrade(badSource,old,model),/exact new official/);
    assert.throws(()=>buildAnniversaryDowngrade(source,badOld,model),/exact old official/);
    assert.throws(()=>prepareAnniversaryDowngrade(old,source,model),/exact new official/);
    assert.throws(()=>prepareAnniversaryDowngrade(source,old,model==='gr3'?'gr3x':'gr3'),/exact new official/);
    for(const input of [null,[],{}, {accepted_plan_id:plan.plan_id,acknowledge_instructions:false},
      {accepted_plan_id:'stale',acknowledge_instructions:true},
      {accepted_plan_id:plan.plan_id,acknowledge_instructions:true,features:['film']},
      Object.create({accepted_plan_id:plan.plan_id,acknowledge_instructions:true}),
      {[Symbol('unexpected')]:true,accepted_plan_id:plan.plan_id,acknowledge_instructions:true}])
      assert.throws(()=>exportAnniversaryDowngrade(source,old,model,input),/preflight and acknowledge/);
  });
  test(`${model}: repaired checksums cannot authorize non-target payload, CPU, sections or container changes`,{skip:!fixture},()=>{
    const source=readFileSync(fixture),old=readFileSync(new URL('../bin/'+oldFile,import.meta.url)),{candidate}=buildAnniversaryDowngrade(source,old,model);
    const d=decodeFrameMap(candidate).decoded,r=rows(d);
    const verify=b=>verifyAnniversaryDowngrade(source,old,model,b);
    for(const at of [0x30,0x50,0x78,0x7c,candidate.length-24,candidate.length-16,candidate.length-8]){
      const bad=Buffer.from(candidate);bad[at]^=1;repair(bad);assert.throws(()=>verify(bad));
    }
    const badSum=Buffer.from(candidate);badSum[badSum.length-1]^=1;assert.throws(()=>verify(badSum),/checksum/);
    assert.throws(()=>verify(candidate.subarray(0,candidate.length-4)));
    const tail=candidate.length-24,payloadEnd=128+candidate.readUInt32LE(tail+12);
    if(payloadEnd<tail){const bad=Buffer.from(candidate);bad[payloadEnd]=1;repair(bad);assert.throws(()=>verify(bad),/padding/);}
    for(const at of [r.RTOS.start+0x10000,r.RTOS.start+0x6286cc,r.CPU.start+0x90,r.RTOS.header+8,r.RES.header+12]){
      const changed=Buffer.from(d);changed[at]^=1;
      // Repair CPU too: payload equality must reject even a self-consistent CPU.
      if(at>=r.CPU.start&&at<r.CPU.end){changed.writeUInt32BE(0,r.CPU.start+0x7c);let sum=0;
        for(let p=r.CPU.start;p<r.CPU.end;p+=4)sum=(sum+changed.readUInt32BE(p))>>>0;
        changed.writeUInt32BE(-sum>>>0,r.CPU.start+0x7c);}
      repair(changed);const bad=repack(candidate,changed);
      assert.equal(sum32(bad),0);assert.equal(sum32(decodeFrameMap(bad).decoded),0);
      assert.throws(()=>verify(bad),/non-target|target versions|section/);
    }
    const alternative=repack(candidate,d,{replaceFirst:true});
    assert.ok(decodeFrameMap(alternative).decoded.equals(d));
    assert.throws(()=>verify(alternative),/non-canonical/);
  });
  test(`${model}: existing independent Python preserved-CPU ARM probe reproduces the exact candidate SHA`,{
    skip:!fixture||process.env.M10V_ANNIVERSARY_PYTHON_CROSSCHECK!=='1',timeout:120000},()=>{
    const script=`import hashlib,json,sys\nimport scripts.probe_gr3_anniversary_preserved_cpu as p\noriginal=p.strict_decode\ndef capture(raw,*args):\n print(json.dumps({'candidate_sha256':hashlib.sha256(raw).hexdigest()}),flush=True)\n return original(raw,*args)\np.strict_decode=capture\nr=p.probe(sys.argv[1],sys.argv[2],sys.argv[3])\nprint(json.dumps({'changed':r['changed_decoded_bytes'],'cpu':r['cpu_entirely_preserved'],'camera_verified':r['camera_verified']}))\n`;
    const result=spawnSync(process.env.M10V_PYTHON||'.venv/bin/python',['-c',script,fixture,new URL('../bin/'+oldFile,import.meta.url).pathname,model],
      {cwd:new URL('..',import.meta.url),encoding:'utf8',timeout:110000,maxBuffer:1024*1024});
    assert.equal(result.status,0,result.stderr||String(result.error));
    const [identity,evidence]=result.stdout.trim().split('\n').map(line=>JSON.parse(line));
    assert.equal(identity.candidate_sha256,profile.candidate_sha256);assert.deepEqual(evidence,{changed:9,cpu:true,camera_verified:false});
  });
}
