# GR III 撕纸叠映：ISP 路线与协议证据

日期：2026-11-10。研究／实现基线：M10V `develop`，起点 `9796cc688342abb7bccd6e8ab3daa6af97e753eb`；本文件对应工作树中的实验实现，不代表该提交已经包含新功能。尚未操作相机、写卡或完成真机验收。

## 固件身份与复核入口

| 输入 | SHA256 |
| --- | --- |
| 官方 GR III 2.10 BIN | `d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4` |
| 解码 RTOS，基址 `0x53000000`，17,520,064 bytes | `8a4eafcad2716e0b21e9909264e1242e534f0e39e05cba82a53546ceb4070b67` |

使用仓库 `node/firmware.mjs` 的 `readOfficialSection(firmware, 'RTOS')` 解码，并重新计算哈希。下面地址均为这份 RTOS 的 ARM 地址；固件偏移为地址减 `0x53000000`。不把其他公开版本或 IIIx 同名函数直接视为可用。

Granulation 原厂代码、曲线、提交／释放及等待路径的分段哈希与五个 Hook preimage 记录在 `scripts/build_gr3_isp_effect_granulation.py`。构建器在生成代码前复核原厂字节；`scripts/build_gr3_torn_overlay.py` 记录独立组件来源与导出；`tests/test_gr3_torn_build_gate.py`、`node/gr3-torn-overlay.test.mjs` 覆盖 opt-in 和 manifest 边界。

## 排除原厂多重曝光：它包含 CPU 图像运算

原厂 `MultiBlendProcess` 不是纯 ISP 合成入口：

| 原厂位置 | 可见行为 |
| --- | --- |
| `0x53c601b4`、`0x53c601c8` | `MultiBlendProcess`／`MultiBlendProcess.cpp` 字符串；构造器 `0x53504c44` 及执行断言引用这些字符串。 |
| `0x53c62ab0` | 原生 vtable 指向执行函数 `0x53504e44`。 |
| `0x535050f4..0x5350511c` | `vld1.16`、`vqshl.u16`、`vqadd.u16`、`vmin.u16`、`vst1.16`，按向量递增图像指针。 |
| `0x5350504c..0x53505070` | `vld1.16`、`vqshl.u16`、`vmax.u16`、`vst1.16`，逐向量取亮值。 |
| `0x53504c68..0x53504e40` | 依据曝光张数计算权重，两条行循环执行 `vld1.16`／`vsub`／`vqrdmulh`／`vadd`／`vst1.16`。 |

这些是 ARM CPU 的 NEON 像素运算；后续 cache helper 不会改变这一事实。本功能不接入该合成路线，也不使用手机或 CPU 蒙版作为回退。

原厂 UI 确有合成参数与控制命令：`StillMultiExposureCompositeType` 位于 `0x53b27bcc`；参数解析 `0x53306bc4` 将 `Additive→0`、`Average→1`、`Bright→2` 传给 setter `0x53252284`。`next/retry/finish` 表 `0x538effe0` 对应 `0/1/2`，命令 handler `0x5328ecac` 经 `0x532288b0` 投递事件 `0xb6/0xb7/0xb8`。这些控制能力不满足本次像素处理硬约束，因此没有作为新功能实现。UI 参数值与 MultiBlendProcess 内部派生模式不是同一枚举，不互相套用。

## 采用的原厂 IIP 单平面路线

现有 Granulation 入口 `0x5367ad3c` ABI：`r0=context`、`r1=dst descriptor`、`r2=src descriptor`、`r3=strength`，栈参数为 prepared plane 和容量／归属信息。

- 目标宽高来自 descriptor `+0x10/+0x12`，原厂读点 `0x5367ad58/0x5367ad74`。
- `0x5367af78/0x5367af7c` 读取独立源平面地址和 stride；`0x5367afcc/0x5367afd0` 读取独立目标地址和 stride。该原语不读取 descriptor 的第二照片平面。
- `0x5367b010/0x5367b040` 构建 Loader，`0x5367b070` 配置 LUT，`0x5367b144` 配置 Blend，`0x5367b15c` 配置 Store。
- `0x5367b404` 提交原生 graph；`0x5367b410` 等待 context event mask `0x400`；`0x5367b41c` 释放 graph。

`native/gr3/m10v_isp_effect_granulation.c` 的 owned 路径用私有返回地址、nonce、context、prepared plane 和 graph/service 归属认证调用。只替换768个 int16 曲线系数；跳过原厂 CPU RNG `0x5368a92c`。等待必须取得真实完成；释放还核对嵌套 service 和原厂 driver 状态，不能用超时作为成功、释放 DMA 缓冲或进入 CPU 回退的理由。

新增 `m10v_isp_effect_granulation_plane()` 验证整个 plane span、descriptor、pitch、curve、对象别名和源／目标／蒙版关系。CPU 复制的是少量 descriptor 和曲线元数据；不读写整幅照片像素。`tests/test_gr3_isp_effect_granulation.py` 执行原厂控制流和认证 Hook，硬件叶子由边界替身承载；这不证明真实混合公式或照片颜色。

两拍实验序列由 `native/gr3/m10v_torn_overlay.c` 实现：

1. 第一张 Y 经 IIP 写入独占蒙版平面。上下端点采用相同曲线：Y≤48为0、Y≥208为255、中间线性过渡，避免依赖目标旧值。
2. 第二张 Y 原位经 IIP 使用上端点255、下端点 identity 和保留蒙版。
3. 第二张 UV 作为独立单平面，经 IIP 使用上端点128、下端点 identity 和同一蒙版。

第一张保存轮廓原图；第二张候选 JPEG 使用上述合成结果。只接受 YC422；不把 NV12 跳行近似当作正确色度采样。交错色度共享邻接亮度时可能出现窄彩边；真实 alpha 方向、权重、舍入、色度中心和画面效果均需真机确认。

## 冻结 SI 的单拍身份

开始会话时可以检查当前设置，已曝光照片必须使用本张冻结数据。`native/gr3/m10v_torn_bindings.c` 将二者分开；enqueue／执行不调用当前 UI getter 来替代冻结身份。

| 位置 | 证据 |
| --- | --- |
| `0x53245190` | 当前设置 getter 读取 model payload `+0x472`；`0x53366698` 的读命令按枚举0输出 `Single`。 |
| `0x533068bc`、`0x5330698c` | 参数解析 `Single` 后以 `r1=0` 调用 `0x5327b744(model, mode)`。 |
| `0x5327b76c`、`0x5327b7b8` | native setter 保存请求模式到设置 payload `+0x472`，并把原值传给 `0x5354c640`。 |
| `0x5354c640..0x5354c668` | 将该 byte 参数放入消息 `0xc7`，由 `0x5354b564` 提交。 |
| `0x53542050..0x5354209c` | service handler 从 payload 读 byte，以不变值调用 `0x5355e31c`；handler 表指针位于 `0x54093668`。 |
| `0x5355e348` | 写入请求模式到 settings/SI 内容 `+0xfb9`。 |
| `0x5355e224..0x5355e26c`、`0x5355e140..0x5355e16c` | 从 `+0xfb9` 推导 normalized `+0x799`；请求0保留两者为0。一些非单拍请求在原厂限制下也会归一化成0，因此只检查 `+0x799` 不充分。 |
| `0x53510800..0x53510830` | 将传入 SI 复制到 recipe `+0x44c8` 指向的独立存储，长度 `0x74270`。 |
| `0x5351b55c/0x5351b568`、`0x5351cf9c/0x5351cfac` | 调用者从自己的 owner `+0x9a8` 读取源 SI，再传入上述复制入口；两个字段均落在复制范围内。 |

实验 eligibility 同时要求冻结 `SI[0xfb9]==0` 与 `SI[0x799]==0`，拒绝 Half `SI[0x7b6]==6` 和 HDR tone14；胶卷槽状态来自已有逐张 recipe 快照，拒绝未知／自定义以及 Charmera／像素世界 CPU renderer289/290。`tests/test_gr3_torn_bindings.py` 对这些冻结字段逐一改变并验证拒绝，且不映射原生 live getter 路径。

溯源尚有一段没有闭合：service wrapper `+4` 的设置 backing 与调用者 owner `+0x9a8` 源 SI 之间的更早赋值链，本轮没有完整追踪。不能只因两个结构存在相同偏移就宣称指针归属已证明；特别不能把通用 IIP graph wrapper `+4` 当作 SI。本表分别记录已确认的模式语义和真实 recipe 复制链；ARM eligibility 测试不能替代该段原厂溯源或设备观察。

## 所有权、菜单与无线合同

会话放在 TopMenu owner `+0x6d00` 的独立尾部，完整 owner extent `0x6e00`；recipe 追加 `+0x57d8..+0x57f8` 的32字节快照。蒙版使用原厂池分配 `align64(6144)×4096+63` bytes，保存准确 allocation token。owner、generation、recipe、SI、phase 共同约束执行。pending recipe 或 graph lease 未解除时不得取消后释放正在使用的 plane。关闭路径零 plane 分配和像素工作。

机身菜单「效果 → 撕纸叠映」使用可滚动四行窗口和1218..1225新文字资源；既有 HDF、边框、印花、暗角编号与行为保留。开始／取消经过 companion 本地 storage gate，未决远程事务不能被本地动作越过。

独立扩展合同 `contracts/extensions-v1.json` 增加 runtime 字段24 `tornSession`：读0关闭／1待拍轮廓／2待拍素材／3已完成／4失败；只写0取消或1开始／重新开始，2..4由 parser 和 portable 事务层共同拒绝。generation 参加 revision 防止相同阶段 ABA；同值的新开始请求仍执行，重复 requestId 不重放动作。新 canonical SHA256：`c5e4a67763f11333c72f40ceee652919b280ab83235b21a535bc9145b73a224d`。旧 App／固件须保持合同门禁，不能仅按字段名试写。

`scripts/package_companion_debug.py` 对原生 feature mask、合同源文件、service ELF 和 APK 的扩展 schema／hash 分别核对；保留私密配对与原固件／catalog／renderer 审计。只有已编译 bit24 的交付说明增加实验两拍步骤。完成阶段不单独证明 SD 保存成功。

## 验证边界

本轮实际离线检查包括 ARM 会话／几何／RAW归属拒绝、实际 AppMain mailbox 的新合同与 CAS／去重、实际 portable JSON parser 的只写0/1，以及机身菜单滚动和未决事务拒绝。具体最终通过数、候选 buildId、完整构建和交付哈希以本次交付 manifest 与测试日志为准，不能从本研究文档推导设备通过。

部分 macOS 宿主测试执行新链接的 C 程序时收到 SIGKILL9；该环境问题未被当作通过。对应生产 parser 和事务链有独立 ARM 执行覆盖。未执行的完整交付／设备步骤必须单列，不以模拟器代替真机结论。

待真机验收：原厂同条件拍摄对照、白底与暗部素材、撕纸纤维和彩边、横竖拍、RAW+JPEG、即时回放与相册、至少连续三张、取消恢复、断线／重启核对，以及额外蒙版分配与真实缓存一致性。没有实测数值，不声明帧率、耗时、内存兼容性或成片效果达标。
