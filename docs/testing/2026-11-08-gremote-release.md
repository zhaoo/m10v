# M10V 2026.11.08.1 发布依据

状态：USER_VALIDATED。用户确认 GR III 配套固件实际连接成功，胶卷库和设置可用；后续 GRemote test30 修复版本误提示和装卷确认刷新，用户回复「没问题了，发布 m10v 和 gremote」。此反馈不扩大为其他机型、完整画质或量化性能验收。

本次基线与上次成功生产提交均为 `f05518cbd3c888798f746363b9a03c1b073c8f18`，生产证据为 Actions 42251434031 的 DEPLOY_OK。远端 main/develop 与基线一致，无需冲突整合。

验收候选为 GR III 2.10 全功能 r3，BIN SHA-256 `d7573c85a7699a2df94bf8124e28c53a871f7f5f2765e3db71e4590ae04e78a8`，服务 SHA-256 `c9241b8e6d721f745217203ef07ef291f65a4f62e888d2dbe46a61588d6a479d`。buildId `bbda50945d064c96d110650ef412a425edf0683137402f083a2f5e4b1ece8e6d`。

发布前重算并与验收回执一致：runtime_source_sha256 `6c803936920ff3a5a95873ff4f70626133350db5c35dd89b0cafc84fac511f36`，integration_source_sha256 `6522e1267cb5b7b198df12e3eb687a812506ff27a373c1d75e6c89f70778d08f`。仅新增 changelog 与本记录，不改验收后的 native 行为。

候选已有离线证据：协议与冷启动 ARM 30 项通过、最终 BIN 12 项通过、相关 Node 18 项通过及 1 项跳过。Node 全量 511 passed、79 failed、61 skipped，失败名称集合与既有基线一致，不能声称整库全部通过。GRemote 最终 709 passed、6 skipped，真实 C HTTP 联调另行 3 项通过。

影响范围包括共享目录、SD 兼容及 GR III/IIIx 共用构建，GR IV 也使用共享 SD 模块；保留部署现有三机型构建检查，不把 GR III 用户验收扩展到 IIIx/IV。网站导出按用户选项生成，不能认为每种配置与全功能候选逐字节相同。

固件及用户配置不提交公开 Git；脚本依然为联动必需。不变更现有签名、受限 SSH 或服务器授权。

发布复核：changelog 与配套选项 17 项通过，部署 Node 保护 36 项通过、1 项跳过。扩展、冷启动、最终 BIN 和目录合并运行 29 项，其中 27 通过、1 跳过、1 失败：旧 DeliveredPureIsp 冷原厂快照夹具按 per-film 标志期待阶段值 1，当前候选得到 2。该夹具绕过真实任务入口，未修改断言或运行体消除失败；另用当前十槽真实投递测试核对原厂旁路与普通胶卷零像素路径，连同最终 BIN 身份、新卷与印花冻结共 7 项通过。
