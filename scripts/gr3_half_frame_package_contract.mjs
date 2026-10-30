// Read-only acceptance gates for a local GR III half-pair test package.
// These establish artifact identity and offline evidence, never camera acceptance.
export const CANDIDATE_NAME='M10V-GR3-HalfFrame-TEST-20261030-r7-debug';
export const BASE_COMMIT='84caa3248477ecf36bc197420e4d5963ebab5693';
export const LOG_FILES=['M10VMN0.BIN','M10VMN1.BIN','M10VCP0.BIN','M10VCP1.BIN',
 'M10VIO0.BIN','M10VIO1.BIN','M10VAK0.BIN','M10VAK1.BIN'];
export function auditHalfPair(manifest,receipt,runtime){
 const p=manifest.half_pair,r=receipt.composition?.half_pair;
 const fields={backend:'native-IIP',frame_filesystem_calls:0,cpu_pixel_reads:0,cpu_pixel_writes:0};
 if(!p?.enabled||p.schema!=='m10v-half-pair/v1'||
 p.first_original_preserved!==true||p.camera_tested!==false||!r?.enabled||r.schema!==p.schema||
 r.first_original_preserved!==true||r.camera_tested!==false||
 Object.entries(fields).some(([key,value])=>p[key]!==value||r[key]!==value)||
 typeof p.storage!=='string'||!p.storage.trim()||r.storage!==p.storage||
 /HALFPAIR\.BIN|[\\/]/i.test(p.storage))
  throw Error('Native-IIP half-pair capability/provenance missing; CPU/SD frame path is not accepted');
 if(runtime.includes(Buffer.from('HALFPAIR.BIN','ascii')))throw Error('Native-IIP package contains the retired CPU/SD frame backend');
 const h=p.handoff;
 if(!h||!Number.isSafeInteger(h.callsite)||!Number.isSafeInteger(h.target)||
 h.callsite!==r.handoff?.callsite||h.target!==r.handoff?.target||
 h.callsite%4||h.target%4||h.callsite<manifest.base||h.callsite+4>manifest.base+runtime.length||
 h.target<manifest.base||h.target>=manifest.base+runtime.length)throw Error('Half-pair handoff extent differs');
 const word=runtime.readUInt32LE(h.callsite-manifest.base);
 if((word>>>24)!==0xeb)throw Error('Half-pair handoff is not an ARM BL');
 const displacement=(word<<8)>>6;
 if(h.callsite+8+displacement!==h.target)throw Error('Half-pair handoff target differs');
 return p;
}
export function auditHalfCaption(rtos){
 const start=0x540bc000-0x53000000,end=0x540be000-0x53000000;
 if(!Buffer.isBuffer(rtos)||rtos.length<end)throw Error('Half caption overlay extent missing');
 const overlay=rtos.subarray(start,end),text=Buffer.from('Half\0','utf16le'),at=overlay.indexOf(text);
 if(at<8||overlay.indexOf(text,at+1)!==-1||overlay.readUInt32LE(at-8)!==0x00000105||
 overlay.readUInt32LE(at-4)!==0x540bc000+at||overlay.includes(Buffer.from('Half 3:4\0','utf16le')))
  throw Error('Native Half menu caption must be exactly Half');
 return 0x540bc000+at-8;
}
export function validateChecks(validation){
 if(!Array.isArray(validation?.checks)||!validation.checks.length)throw Error('Current candidate validation evidence missing');
 const names=new Set();
 for(const c of validation.checks){
  if(!c||typeof c.name!=='string'||!c.name.trim()||names.has(c.name)||
   typeof c.log!=='string'||!c.log||!Number.isInteger(c.exit_code)||
   (c.required!==false&&c.exit_code!==0))throw Error('Invalid or failed required validation check');
  names.add(c.name);
 }
 return validation.checks;
}
export function packageReadme({buildId,binSha,officialSha,checks}){
 return `# GR III 半格双拍日志测试包 r7 · 2026-10-30

状态：WAITING_FOR_USER_VALIDATION。仅适用于 GR III / 官方 2.10。
这是新的离线验证候选，设备尚未验收；未发布至 GitHub 或生产环境。
用户已确认 r6 的取景闪烁修复；该反馈仅覆盖取景。r6 的双拼没有达到预期，回放慢，旧 SD 首帧暂存和 CPU 整图拼接方案不作为本次交付方案。
r7 保留已确认的取景修复，比例菜单和拍摄状态栏统一显示 Half。两张照片各自在原生 ISP 完成色彩处理后，由原生 IIP 空间处理组合双画面；双拼阶段不经 CPU 读写像素，也不经 SD 图像文件暂存。诊断日志仍会写入卡内。
离线构建门禁要求 manifest 与回执明确声明 native-IIP、图像文件调用为 0、CPU 像素读写为 0，并核验真实编码前 ARM 入口；这些检查不能替代实机性能和回放验收。

## 安装与验证

1. 先备份照片、原固件和 M10V 存档，保留已验证的恢复固件。
2. 按原有更新流程使用 gr3/fwdc239b.bin。SD/M10V/FILMS.M10 为胶卷库；保留自己的自定义胶卷和设置，避免直接覆盖。
3. 先关闭边框，用 3:2 和 16:9 各拍一张，检查菜单文字、取景颜色、半按对焦与回放。
4. 选择 Half，保持同一相机方向连续拍两张。第一张仍保存原始单张 JPEG；第二张应保存双画面 JPEG，并在即时回放、相册和导出照片中检查。
5. 再检查切回其他比例、35/50mm 裁切、RAW+JPEG、已有胶卷、HDF、水印和边框。组合效果未获得设备验收，遇到不兼容布局时应保留普通 JPEG 并记日志，不应损坏照片。

每次对照测试使用相同画幅、持机方向和尺寸。两张之间更改这些条件可能重新开始一组。
图像暂存仅由本次运行的原生内存所有者管理，不从旧 HALFPAIR.BIN 恢复帧；退出或重启后的组对行为以相机日志和实际结果为准。
请对照原厂正片或负片检查保存、即时回放和相册切换速度；本包仍含诊断日志，不以未经测量的“流畅”替代性能反馈。

## 问题回传

发现问题后尽快停止继续拍摄，将卡根目录实际生成的以下文件原样打包：

${LOG_FILES.map(f=>'- '+f).join('\n')}

文件未生成时不用补齐。附上两次拍摄的 JPEG/RAW、操作顺序、比例、裁切、持机方向、胶卷和边框设置。
日志每通道为 CRC 双页尾窗，继续操作会覆盖较早事件。请保留两页；事件缺失不等于未执行。
工具 tools/read_gr3_debug_log.py 可离线解码，无需自行处理后再回传。

诊断 build_id：${buildId}。
BIN SHA-256：${binSha}。
官方输入 SHA-256：${officialSha}。
基线 main：${BASE_COMMIT}。源码指纹与清单见 evidence/provenance.json。

## 当前离线检查

${checks.map(c=>'- '+c.name+'：exit '+c.exit_code+(c.required===false?'（非门禁，结果完整保留）':'')).join('\n')}

完整输出在 evidence/checks 中。ARM 模拟、像素测试与封包校验不能证明相机 AF、实际编码、回放、SD 写入或性能已通过。
仅构建 GR III 候选；IIIx/IV 未执行设备验证。r4 的对焦和画幅已收到设备通过反馈，取景与双拼失败；其离线通过日志不作为本包通过证据。

## 恢复

若取景、对焦或保存异常，停止测试，备份日志和照片。按原有恢复流程使用此前已验证固件；可先切回原有比例并关闭边框。
本压缩包不会自动刷机、重置存档或写入 SD。收到本候选明确设备通过反馈后，才进入发布流程。
`;
}
