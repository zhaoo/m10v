# GR III 半格日志测试包 r3 · 2026-10-29

状态：`WAITING_FOR_USER_VALIDATION`，仅用于 **GR III / 官方2.10**。
这是开启诊断日志的新候选，不能沿用r2的BIN哈希或验收结果。
设备尚未安装/验证，未推送GitHub或部署生产。

## 安装和拍摄

1. 备份原有固件、照片、M10V目录和状态存档，保留此前已验证的固件包。
2. 按已有更新流程使用 `gr3/fwdc239b.bin`。胶卷库在 `SD/M10V/FILMS.M10`，已有自定义胶卷/状态文件不要直接覆盖。
3. 在原有画幅菜单选择 **Half 3:4**；横持时是竖向半格，最大2992×4000。一次快门保存一张照片。
4. 建议先用3:2拍一张对照，再切Half 3:4拍摄。保留边框、胶卷、水印及HDF等已有功能和设置。

日志默认已启用，无须另外放置开关文件或清除设置。
日志版增加SD写入开销，拍摄速度与保存等待不能直接作为无日志版本的性能结论。

## 遇到问题后回传什么

请尽快备份卡根目录中以下**实际生成**的文件，原样打包回传：

- `M10VMN0.BIN`、`M10VMN1.BIN`：菜单。
- `M10VCP0.BIN`、`M10VCP1.BIN`：拍摄、ISP完成、CPU残余阶段及阶段计时。
- `M10VIO0.BIN`、`M10VIO1.BIN`：处理任务、保存、边框交接。
- `M10VAK0.BIN`、`M10VAK1.BIN`：按键/A-B等独立诊断通道。

不一定每个通道都有文件；没有生成的文件不用补齐。附上对应问题照片（若保存成功）和简短操作顺序，例如：
「Half 3:4、35mm、RAW+JPEG、胶卷A、边框关闭；第二张回放黑屏」。

日志是四个通道各自的CRC双页环形尾窗，每通道最多63条记录；继续大量拍摄/操作会覆盖较早记录。
文件没出现某事件，不能单独证明相机没执行该步骤。分析时按本包build_id、CRC和原始文件关联，保留两页。

诊断build_id：`076e56a5`。
BIN SHA-256：`f31ca47f2433d8b0cf1ab04f230c8ab0ae90af18dceef672540d3622d34aa74e`。
官方输入SHA-256：`d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4`。
源码/配置指纹及日志文件清单见 `evidence/provenance.json`、`gr3/manifest.json`、`gr3/receipt.json`。
工具 `tools/read_gr3_debug_log.py` 可离线解码，回传时不需要自行解码。

## 本包验证范围

- 基于最新main `38a847b5871e2441a7934fafd38dcee50d4faef4`，生产成功部署日志已核对；保留半格分支已有实现。
- 保留原有六画幅、边框、十胶卷槽、HDF ADJ、通用光晕、水印、水平仪与负片颗粒。
- 本轮只开启现有诊断/计时链路，不新增成像算法或Hook实现，仅按既有构建规则启用诊断Hook。
- 诊断全功能RTOS增量实测1,170,620字节，比无日志候选增加8,624字节；空间上限在原基础上增加有界16KiB至1152KiB，原指令/整节/只读映射/非目标区域/最终封包检查保留。
- 本包专项执行结果见 `evidence/half-frame-final-artifact-r3-debug.log`、`half-frame-pipeline-r3-debug.log`、`half-frame-logger-r3-debug.log` 和 `half-frame-debug-plan-r3.log`。
- 实际诊断BIN：259个Hook，最终半格39项、当前拍摄链路/RAW归属23项、日志19项、诊断预检2项通过；超限产物拒绝检查通过。
- 从本包runtime直接执行ARM日志器，四通道8个文件可用正确build_id及CRC解码；此检查使用文件系统/堆测试边界，不代表真实SD已写入。
- 完整Node套件有历史配置/胶卷断言失败；本轮完整输出及失败名称在evidence中，不能报告全库通过。r2的历史功能验证记录另存于evidence，仅供对照。
- GR IIIx/IV未重建：此次为GR III诊断配置，未改变其机型入口。真实相机像素、AF、回放与SD写入仍需实测。

## 停用日志与恢复

日志为编译开关；停用日志需恢复此前无日志的r2测试包或此前已验证固件。
回退前将边框关闭并切回原有比例，再按既有更新流程恢复，保留卡上原有状态存档。
本包不自动写SD、不重置存档、不执行刷机。请对本包明确反馈测试结果后再进入发布流程。

重新构建与包装使用：

```sh
node scripts/build_gr3_half_frame_candidate.mjs --debug builds/gr3-half-frame-debug-rebuild
node scripts/package_gr3_half_frame_candidate.mjs builds/gr3-half-frame-debug-rebuild builds/gr3-half-frame-debug-repack
```
