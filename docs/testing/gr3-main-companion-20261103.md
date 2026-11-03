# GR III 2.10 最新 main + App 桥接候选

状态：WAITING_FOR_USER_VALIDATION。未刷机、未写 SD、未推送 GitHub、未部署。

用户确认仍是同一台 GR III 街拍版 M10V 2.10，没有升级 2.20、降级或换其他固件；原 App 装卷和扩展设置均可用。当前声明尚未用手机只读确认，旧设备记录不能外推为新包通过。

## 身份

- main/生产基线：6e77769619ee9dc952e6b3993d052d53e0807a94；交付前再次 fetch 未推进。
- 运行时代码提交：4a9bc5c；参考旧桥 5804896，基线 a24ccc2。
- 官方输入：d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4。
- 原厂内部版本保持 2.10.21.27。
- 新 BIN：1b55f822ea70422f613b794884ecab9df7f441b355c15e6825b10a6b49691c9e；46,032,800 bytes；274 hooks。
- buildId：246b91ea5a94bcd3abc344650f127f54605a03949f1180c96b78586c22362b40。
- 旧实机记录 BIN：7efe513bdc6954201b97d90cfb0c571740941e5484abe92149ab842dda505a70。
- App：develop 7c6d3a3，arm64 debug v17；APK SHA 4eab5ebf5e44697673b8c8654fddce70ae3455409afad15a0a0d08426eb37436。

## 变更

移植既有签名邮箱桥、UI owner 和正式机内 setter。保留最新 main 的 C41、原生 ISP、十槽装卷和扩展能力。编号 322–326 进入桥协议及 App 相机目录，目前 56 卷；手机修图渲染器继续使用原固定版本。

本候选显式启用 preserve_existing：有效 184B/v5 当前 journal 不因编译默认 receipt 缺失或变化被覆写。沿用旧 seed，zoom_seed=null；普通网页及关闭 bridge 的默认行为不变。旧存档迁移和退役 anime 清理沿用 main。

## 验证

- 官方输入严格全解码、型号、校验和；新 BIN 严格组件版本、RTOS/MMU 扩展、指令 preimage、重定位、分区和最终封包回读。相同源码配置逐字节精确重建通过。安全报告仍为 offline_verified_camera_unverified、installation_allowed=false。
- 缺失/篡改身份、策略和修复校验和后的篡改 BIN 拒绝：6 pass、3 skip（其他型号/版本输入未提供）。
- main 与 bridge-off BIN 相同：2d8b93b1e9e4eb1df3941fc517f6961ec23df23e3e08fb06690c2c27ac34d8ce。
- 保留当前 journal 的 ARM 检查 3 pass。实际 APK/BIN/service/配对/协议/owner/打包检查 79 pass、0 skip。
- 服务栈上界 2632B，静态 staging 61173B，既有配对材料逐字节相同。
- 实际交付 BIN 的 pure-ISP 检查 15 pass，含新增五卷 24MP 真实 producer、原生查询/执行和 JPEG 零像素访问；普通 main 成像 25 pass。
- Half、border、旧 SD 协议 34 项中 33 pass，另一项使用了不同组件编译器，按实际 AppleClang 组件工具链单独重跑通过；未修改 BIN。
- App 全量 616 pass、3 skip；当前 C 服务回环装入 326、激活及未知结果路径 1 pass。flutter analyze 无问题，v17 构建通过。
- Node 全量：main 571 项，378 pass、117 fail、76 skip；候选 574 项，381 pass、117 fail、76 skip。失败名称集合完全一致，完整清单附于包内 node-suite-comparison.json。全量仍红，不视为全套通过。
- 历史 ctypes 五槽 fixture 为 104B，却被当前 184B 原生初始化写入；未执行此不安全家族，不记为通过。IIIx、IV、2.20、1.70 和降级链不在本次范围。

## 评审和裁定

独立评审未发现固件或 App 产品实现缺陷，指出 326 已受支持而旧 UI 测试仍断言不可用；已修正为 326 可用、327 不可用，并完成 App 全量回归。

1. 冷焦距缓存未初始化时，旧桥会拒绝整份扩展快照；保留 fail-closed，不在 GET 中加载、播种或修复。冷启动仍需实机核对。
2. 普通 native-only 成像夹具未走完整效果入口，直接测试 pure-ISP 候选会触发 encoder 的保护性等待。使用对应真实入口夹具后通过，不放宽保护、不伪造完成 mask；失败探索日志保留。
3. Half 符号比较必须使用与构建一致的 AppleClang 组件工具链。LLVM 默认测试编译器造成符号位置变化；显式同工具链重跑通过。
4. C 回环服务原硬编码旧目录 hash；仅测试 fixture 改为显式公共 hash 环境绑定当前相机目录，覆盖 326 装卷。不是硬件验收。
5. 保留有效 journal 不代表备份了 Flash。损坏或缺失存档仍走原初始化；未知写入不重放。
6. 物理启动、持久化、DMA/缓存、成片、速度、重复 owner 重建内存及硬件恢复均未验证。本次只交付候选，保留开发分支，不进行集成发布。

## 设备验收

手机连接 USB 和相机 Wi-Fi，先停止后台请求，签名只读核对当前身份、十槽及扩展字段并备份；再人工核对满电、SD 备份和唯一型号 BIN。由用户手动更新固件及匹配服务。

更新后先读取，再做单项改值、读回、恢复；装入用户选定的槽位并启用；核对机内同步；正常关机重启后核对持久性；最后实测拍摄、回放、Half、连拍并与原厂流程对比。结果未知时不重放原请求。

若能正常启动而服务不可用，关机后恢复备份的脚本和服务。固件回退只在机身原更新入口仍可用时手动使用已保留旧包；两种启动入口均失效时没有已验证的 SD 救砖路径，不承诺恢复，不用抬高版本或二阶降级补救。
