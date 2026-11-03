// Dedicated, exact-source two-stage delivery. This does not broaden the normal
// importer or ordinary M10V patching ABI. Camera Flash/boot remain unverified.
import {createHash} from 'node:crypto';
import {inspectFirmwareImport, inspectOfficial} from './firmware.mjs';
import {decodeFrameMap, sum32} from './gr3-frames.mjs';
import {encodeZip} from './gr3-sd-film-export.mjs';

export const ANNIVERSARY_DOWNGRADE_PROFILES = Object.freeze({
  gr3: Object.freeze({model_label:'GR III', from_version:'2.20', to_version:'2.10',
    source_sha256:'5c53760b3b564c87239dbf7f5c94d0f6fd91accd156ec4ba672ebfd6b861793e',
    restore_sha256:'d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4',
    candidate_sha256:'3860d908a59aea82b0aede7a529bee002a31563605686ed310c75aed5a8615dc',
    project:588, version:0x0214141c, filename:'fwdc239b.bin', zip_filename:'M10V-GRIII-2.20-to-2.10.zip'}),
  gr3x: Object.freeze({model_label:'GR IIIx', from_version:'1.70', to_version:'1.60',
    source_sha256:'aa8e3ae1349d94e83be381c20530e41d5e57b75c27ef24ba81c7b017d6c11592',
    restore_sha256:'708e79f3b7b96a7e1581b4acf4c412233050a1832718ef7f06c8397db1b431c7',
    candidate_sha256:'6dcd6bb1954f3a316d804d368b47f4e50bfaaca1b54f20b656235b24e76e249a',
    project:609, version:0x01461412, filename:'fwdc243b.bin', zip_filename:'M10V-GRIIIx-1.70-to-1.60.zip'}),
});
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
const need = (ok, message) => {if (!ok) throw Error('Anniversary downgrade: '+message);};
const version = word => [24,16,8,0].map(shift => (word >>> shift)&255).join('.');
function repair(bytes) {
  bytes.writeUInt32LE(0, bytes.length-4);
  bytes.writeUInt32LE(-sum32(bytes) >>> 0, bytes.length-4);
}
function outside(before, after, ranges) {
  need(before.length === after.length, 'length changed');
  let at = 0;
  for (const [start, length] of [...ranges].sort((a,b)=>a[0]-b[0])) {
    need(before.subarray(at,start).equals(after.subarray(at,start)), 'non-target bytes changed');
    at = start+length;
  }
  need(before.subarray(at).equals(after.subarray(at)), 'non-target bytes changed');
}
function sections(decoded, report) {
  const result = new Map();
  let at = 0;
  for (const row of report.sections) {
    const end = at+row.size;
    need(at+16 <= end && end <= decoded.length-4 &&
      decoded.toString('ascii',at,at+8).split('\0')[0] === row.name, 'source section layout differs');
    result.set(row.name, {start:at+16, end, header:at});
    at = end;
  }
  need(at+4 === decoded.length && result.size === 14, 'source section trailer differs');
  return result;
}
function authenticate(newSource, oldSource, model) {
  need(Object.hasOwn(ANNIVERSARY_DOWNGRADE_PROFILES, model), 'unsupported model');
  const profile = ANNIVERSARY_DOWNGRADE_PROFILES[model];
  need(Buffer.isBuffer(newSource) && hash(newSource) === profile.source_sha256, 'requires exact new official source SHA-256');
  need(Buffer.isBuffer(oldSource) && hash(oldSource) === profile.restore_sha256, 'requires exact old official restore SHA-256');
  const report = inspectFirmwareImport(newSource);
  inspectOfficial(oldSource);
  need(report.model === profile.model_label && report.public_version === profile.from_version, 'source model/version differs');
  return {profile,report};
}
function load(newSource, oldSource, model) {
  const {profile,report} = authenticate(newSource,oldSource,model);
  const {decoded,frames} = decodeFrameMap(newSource);
  const rows = sections(decoded,report);
  const rtos = rows.get('RTOS'), cpu = rows.get('CPU');
  need(cpu.end-cpu.start === 131072 && decoded.readUInt32LE(cpu.start+0x80) === profile.project, 'CPU project/length differs');
  need(decoded.readUInt32BE(rtos.start+0x2038) === profile.version &&
    decoded.readUInt32BE(cpu.start+0x90) === profile.version &&
    newSource.readUInt32BE(0x38) === profile.version && newSource.readUInt32BE(0x50) === profile.version,
  'official component versions differ');
  need(decoded.subarray(rtos.start+0x6286cc,rtos.start+0x6286d0).equals(Buffer.from('e42103e3','hex')), 'updater instruction preimage differs');
  need(decoded.subarray(cpu.start+0x5132,cpu.start+0x5136).equals(Buffer.from('76310014','hex')), 'CPU getter preimage differs');
  return {profile,decoded,frames,rows,rtos,cpu};
}
function targetFor(state) {
  const target = Buffer.from(state.decoded);
  target.writeUInt32BE(state.profile.version+256, state.rtos.start+0x2038);
  Buffer.from('e6ffffea','hex').copy(target,state.rtos.start+0x6286cc);
  repair(target);
  return target;
}

// Preserve the final original compressed frame, changing only its four direct
// checksum literals. No recompressor, frame flags or backreferences are changed.
function compressedTrailer(source, original, target, frame) {
  need(!frame.literal && frame.decoded_end === target.length, 'last original frame shape differs');
  const start = frame.decoded_start;
  need(original.subarray(Math.max(0,start-8191),original.length-4)
    .equals(target.subarray(Math.max(0,start-8191),target.length-4)), 'trailer dictionary or body changed');
  const block = Buffer.from(source.subarray(128+frame.encoded_start,128+frame.encoded_end));
  const literals = new Map();
  let at = 2, used = start, terminated = false;
  while (at < block.length && !terminated) {
    need(at+2 <= block.length, 'truncated trailer flags');
    const flags = block.readUInt16BE(at); at+=2;
    for (let bit=15;bit>=0;bit--) {
      if (!(flags & (1<<bit))) {
        need(at < block.length, 'truncated trailer literal');
        if (used >= target.length-4) literals.set(used,at);
        used++; at++; continue;
      }
      need(at+2 <= block.length, 'truncated trailer reference');
      const first = block[at++], second = block[at++];
      const offset = ((first&0xf8)<<5)|second;
      let count = first&7;
      if (count === 7) {need(at < block.length, 'truncated trailer extension'); count+=block[at++];}
      if (offset === 0) {
        need(at === block.length, 'trailing compressed trailer bytes'); terminated=true; break;
      }
      if (count === 262) {
        let extra = 255;
        while (extra === 255) {need(at < block.length, 'truncated long trailer reference'); extra=block[at++]; count+=extra;}
      }
      need(offset <= used && used+count+3 <= target.length, 'invalid trailer reference');
      used+=count+3;
    }
  }
  need(terminated && used === target.length && literals.size === 4 &&
    [0,1,2,3].every(i=>literals.has(target.length-4+i)), 'trailer checksum is not four direct literals');
  for (const [position,encoded] of literals) block[encoded]=target[position];
  return block;
}
function replay(source, state, target) {
  const chunks = [];
  let reused=0, replaced=0;
  for (const frame of state.frames) {
    const start=frame.decoded_start, end=frame.decoded_end, history=Math.max(0,start-8191);
    if (target.subarray(history,end).equals(state.decoded.subarray(history,end))) {
      chunks.push(source.subarray(128+frame.encoded_start,128+frame.encoded_end)); reused++;
    } else {
      replaced++;
      if (frame === state.frames.at(-1)) chunks.push(compressedTrailer(source,state.decoded,target,frame));
      else for (let at=start;at<end;at+=0x6000) {
        const part=target.subarray(at,Math.min(at+0x6000,end)), prefix=Buffer.alloc(2);
        prefix.writeUInt16BE(0x8000|part.length); chunks.push(prefix,part);
      }
    }
  }
  chunks.push(Buffer.alloc(2));
  const payload=Buffer.concat(chunks), footer=Buffer.from(source.subarray(-24));
  footer.writeUInt32LE(payload.length,12); footer.writeUInt32LE(target.length,16); footer.writeUInt32LE(0,20);
  const candidate=Buffer.concat([source.subarray(0,128),payload,Buffer.alloc(-(128+payload.length)&3),footer]);
  candidate.writeUInt32BE(state.profile.version+256,0x38); repair(candidate);
  return {candidate,reused,replaced};
}
function planFor(profile, model) {
  return {schema:'m10v-anniversary-downgrade-plan/v1',status:'ready',model,model_label:profile.model_label,
    from_version:profile.from_version,to_version:profile.to_version,
    source_sha256:profile.source_sha256,restore_sha256:profile.restore_sha256,
    plan_id:hash(['m10v-anniversary-cpu-preserved-kind2/v1',model,profile.source_sha256,profile.restore_sha256,
      'DSP+256:CPU-unchanged:6286cc-e6ffffea:trailer-literals'].join(':')),
    filename:profile.filename,zip_filename:profile.zip_filename,
    dsp_package_version:version(profile.version+256),cpu_package_version:version(profile.version),
    download_available:true,camera_verified:false,stable:false,
    scope:'Exact public official source only; file verification does not verify Flash, boot or recovery.'};
}
export function prepareAnniversaryDowngrade(newSource, oldSource, model) {
  return planFor(authenticate(newSource,oldSource,model).profile,model);
}

export function verifyAnniversaryDowngrade(newSource, oldSource, model, candidate) {
  const state=load(newSource,oldSource,model), {profile,decoded,rtos,cpu,rows}=state;
  need(Buffer.isBuffer(candidate) && candidate.length>=152 && candidate.length<=newSource.length+1024*1024 && !(candidate.length&3), 'invalid candidate size');
  const tail=candidate.length-24, encoded=candidate.readUInt32LE(tail+12), end=128+encoded;
  need(end<=tail && ((end+3)&~3)===tail && candidate.subarray(end,tail).every(b=>b===0), 'container padding/layout differs');
  outside(newSource.subarray(0,128),candidate.subarray(0,128),[[0x38,4]]);
  outside(newSource.subarray(-24),candidate.subarray(-24),[[12,4],[20,4]]);
  need(candidate.readUInt32LE(48)===profile.project && candidate.readUInt32LE(tail+8)===2 &&
    candidate.readUInt32LE(tail+16)===decoded.length && sum32(candidate)===0, 'container project/kind/size/checksum differs');
  need(candidate.readUInt32BE(0x38)===profile.version+256 && candidate.readUInt32BE(0x50)===profile.version, 'outer DSP/CPU versions differ');
  const fresh=decodeFrameMap(candidate,decoded.length);
  need(sum32(fresh.decoded)===0, 'decoded checksum differs');
  const ranges=[[rtos.start+0x2038,4],[rtos.start+0x6286cc,4],[decoded.length-4,4]];
  outside(decoded,fresh.decoded,ranges);
  const expected=targetFor(state);
  need(fresh.decoded.equals(expected), 'target versions/branch/checksum differ');
  // The comparison includes every section header, flags, size and resource count.
  for (const row of rows.values()) need(decoded.subarray(row.header,row.start).equals(fresh.decoded.subarray(row.header,row.start)), 'section header differs');
  const cpuBytes=fresh.decoded.subarray(cpu.start,cpu.end);
  need(cpuBytes.equals(decoded.subarray(cpu.start,cpu.end)), 'CPU payload changed');
  let cpuSum=0;
  for(let at=0;at<cpuBytes.length;at+=4) cpuSum=(cpuSum+cpuBytes.readUInt32BE(at))>>>0;
  need(cpuSum===0, 'CPU checksum differs');
  // Exact canonical encoded bytes also bind original frame reuse, dependency
  // handling and compressed trailer. Equivalent alternative encodings are refused.
  const canonical=replay(newSource,state,expected);
  need(candidate.equals(canonical.candidate), 'non-canonical frame replay differs');
  need(hash(candidate)===profile.candidate_sha256, 'independently reproduced candidate SHA-256 differs');
  const changes=[];
  for(const [start,length] of ranges) for(let at=start;at<start+length;at++)
    if(decoded[at]!==fresh.decoded[at]) changes.push('0x'+at.toString(16));
  return {...planFor(profile,model),schema:'m10v-anniversary-downgrade-receipt/v1',status:'offline_verified',
    candidate_sha256:hash(candidate),candidate_bytes:candidate.length,decoded_sha256:hash(fresh.decoded),
    candidate_authenticity:'modified_unverified',cpu_payload_sha256:hash(cpuBytes),cpu_entirely_preserved:true,
    combined_footer_kind:2,changed_decoded_bytes:changes.length,changed_decoded_offsets:changes,
    original_frames_reused:canonical.reused,original_frames_replaced:canonical.replaced,
    updater_patch:{address:'0x536286cc',before:'e42103e3',after:'e6ffffea',destination:'0x5362866c'},
    checks:{exact_source_hashes:true,outer_sum32:0,decoded_sum32:0,cpu_sum32_be:0,fresh_decode:true,
      section_layout_unchanged:true,non_target_unchanged:true,cpu_byte_exact:true,canonical_frame_replay:true,
      compressed_trailer_preserved:true},
    limitations:['hardware_decompression_not_verified','complete_original_parser_not_executed',
      'flash_write_readback_not_verified','two_stage_boot_not_verified','settings_downgrade_not_verified',
      'hardware_recovery_not_verified','unknown_service_firmware_not_supported']};
}
export function buildAnniversaryDowngrade(newSource, oldSource, model) {
  const state=load(newSource,oldSource,model), target=targetFor(state);
  const {candidate}=replay(newSource,state,target);
  return {candidate,receipt:verifyAnniversaryDowngrade(newSource,oldSource,model,candidate)};
}
function instructions(profile) {
  return `M10V ${profile.model_label} 两阶段降级套件 ${profile.from_version} → ${profile.to_version}
待相机验证 / Camera-unverified. 文件级检查通过不等于刷写、开机或恢复成功。
只针对精确公开官方 ${profile.from_version}，不适用未知服务固件、第三方固件或其他机型。
本包保留新版官方 CPU 全部 131072 字节，组合更新 kind2；仅提高 DSP 包/RTOS 元数据第三段并修改更新器一条分支。
第一阶段 CPU 包版本保持 ${version(profile.version)}；DSP 包版本 ${version(profile.version+256)}，运行版本或菜单显示不能证明阶段成功。

1. 备份照片和设置，准备充足电量。核对 receipt.json 和 SHA256SUMS，确认机型及两个官方输入摘要。
2. 只将 stage-1-bridge/${profile.filename} 复制到 SD 卡根目录，按该机型官方固件更新流程操作。更新中不要断电、取卡或操作相机。
3. 第一阶段只有在相机明确提示更新完成且正常重启后，才继续第二阶段。失败、卡住或异常时停止，保留屏幕原文、阶段与进度；不要重复尝试或盲目继续。
4. 移除 SD 根目录上的第一阶段文件，替换为 stage-2-official/${profile.filename}。两个同名文件不能同时放在卡根目录。按官方流程安装精确官方 ${profile.to_version}，确认完成并重启。
5. 第二阶段完成后移除更新文件，验证启动、拍摄、RAW/JPEG、回放和设置。此后才按普通 ${profile.to_version} 流程生成 M10V 功能包。

第一阶段不是长期使用固件；第二阶段将覆盖临时更新器分支。不要通过版本菜单单独判断桥接成功。
本包包含精确官方还原文件，但不包含相机 Flash/NAND 备份，不是救砖程序，也不保证硬件恢复。
未执行真实硬件解压、Flash 写入/回读、两阶段启动、持久化设置迁移或设备恢复测试。
需要反馈时附 receipt.json、每阶段屏幕提示、能否开机拍摄及新拍摄的原始 JPEG/DNG。
`;
}
export function exportAnniversaryDowngrade(newSource, oldSource, model, input) {
  const plan=prepareAnniversaryDowngrade(newSource,oldSource,model);
  need(input && typeof input==='object' && !Array.isArray(input) &&
    Reflect.ownKeys(input).length===2 &&
    Reflect.ownKeys(input).every(key=>['accepted_plan_id','acknowledge_instructions'].includes(key)) &&
    input.accepted_plan_id===plan.plan_id && input.acknowledge_instructions===true,
  'preflight and acknowledge the exact two-stage plan/instructions first');
  const {candidate,receipt}=buildAnniversaryDowngrade(newSource,oldSource,model);
  const profile=ANNIVERSARY_DOWNGRADE_PROFILES[model];
  const files={['stage-1-bridge/'+profile.filename]:candidate,['stage-2-official/'+profile.filename]:oldSource,
    'receipt.json':Buffer.from(JSON.stringify(receipt,null,2)+'\n'),'README.txt':Buffer.from(instructions(profile))};
  files.SHA256SUMS=Buffer.from(Object.entries(files).map(([name,bytes])=>`${hash(bytes)}  ${name}`).join('\n')+'\n');
  return {zip:encodeZip(files),receipt,filename:profile.zip_filename};
}
