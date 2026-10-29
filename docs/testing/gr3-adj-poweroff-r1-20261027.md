# GR III ADJ 关机与 A/B 胶卷名称修复 R1

状态：USER_REPORTED_EXIT_FAILURE。用户确认胶卷名称已正常，但普通 ADJ 电源退出及 DISP 打开的 A/B 选卷页退出仍卡死。R1 不通过，不发布；继续见 R2 记录。

## 基线与范围

- GitHub main：`87cc28ae876643d82566bdd2eda6b78193af8c64`。开始和交付前均 fetch 核对。
- 生产同 SHA：[Deploy Baota 40498799324](https://github.com/zhaoo/m10v/actions/runs/40498799324) 日志含该 SHA 的 `DEPLOY_OK ... service=active`。
- 目标：GR III / 官方 2.10 输入。IIIx 共用源码消费者由完整 Node 回归中的真实导出及机型检查覆盖；本次不交付 IIIx 测试包。GR IV 未修改。
- 用户故障：普通 ADJ 影像控制中按电源，会退出到拍摄取景并卡死；A/B 风格选择页六款漫画/E6胶卷误显示“槽位 1…5 / 页面验证（只读）”。“快拍”指正常拍摄界面，不是 SNAP 对焦。

## 修复与证据边界

| 路径 | 旧代码 | 本候选 | 保留行为 |
| --- | --- | --- | --- |
| ADJ 电源返回取景 | LiveView enter 无条件创建 TopMenu 并执行存档迁移/加载 | 在原厂分发前记录 ADJ MAIN phase2/value0；过渡取景只执行原厂 enter | 原厂事件、返回值、关机调度；正常启动与非 ADJ 输入不锁存 |
| 原厂 enter 释放旧 owner | 返回后才检查会丢失关闭状态 | 调用前保存标志，返回后重新获取 owner | 不跨原厂调用解引用旧 owner |
| A/B 页电源/原生 close | host 仍有效，adj_exit 再刷新及重定位列表 | 转交原厂前撤销自定义列表所有权，退出时不重建 | 原厂 native close/destroy 及普通 MENU/DISP 返回 |
| 漫画/E6 名称 | 缺少 306..311 映射，回退到旧槽位/诊断文字 | 映射到 1142..1147 正确胶卷名称 | 原厂风格、其他胶卷及自定义 LUT 名称与图标 |

电源标志只保存在现有 RAM 控制器预留区中，新 owner 构造归零；不修改 M10V6 存档格式或胶卷数据。原厂代码 `5322342c..454` 确认 MAIN 仅在 phase2/value0 映射为逻辑键1；`53219aec` 的 ADJ 映射把 MAIN/S1/S2 转为 0x35；`531a4db8` 原厂处理仍保留 0xb8 退出请求。phase2/value1 不解释成重新开机，它不会清除关闭标志。

离线检查证明旧代码在关闭路径进行了自定义初始化/刷新，以及候选消除了这些调用；**未通过实机复现死机，也未证明物理关机已恢复**。关机是否彻底修复须按下面步骤验收。

## 产物身份

- BIN SHA-256：`3b61382944b3087fadbfd30063198a65495f3acd28e218c14e5dfe0b1e61eb44`。
- BIN：32,352,744 bytes；157 个 Hook 独立封包回读通过。
- Runtime source fingerprint：`b56d2f75ce3b6671922f792ad48488cccf0cfafa108c118a0da106b9fd54fb29`，构建后与当前源码重新比较一致。
- 源码为上述 main 加本地补丁；包中 evidence/source.patch 包含完整差异，receipt/manifest 保留源与配置摘要。
- 新建存档默认选择六款漫画/E6卷；已有有效机内配置优先，不覆盖用户存档。保留画幅、水平仪、负片颗粒、HDF 菜单（默认强度0）、实时色调和原生 ISP。

## 检查结果

- 新增回归先在旧代码上失败，修复后通过：胶卷名称、关闭后不重建、关机过渡不建菜单/读存档、原厂 enter 内失去 owner 仍不初始化。
- 最终专项 ARM：56 项通过，包含旧五槽和追加槽；MAIN press/hold/坏包不误处理，非 ADJ 启动不误锁存，重建 owner 恢复正常初始化，原厂 dispatch 内重入及非零返回值保留。
- 最终 BIN smoke：从实际封包解码并执行生产 ARM Hook；原厂 UI/OS 是显式边界；reentrant dispatch -> enter、owner retirement、return=0x73；自定义 factory/存档调用0。
- 最终 BIN 原生拍摄/ISP 管线：18 项通过。
- Node 全量：400 项，358 通过、33 失败、9 跳过。其中32项在独立 main 源码副本及相同本地依赖上重现；剩余1项是本轮边测试边修改源码触发 fingerprint 保护，冻结源码后单独重跑已通过（1通过、6按名称过滤），结果见包中 raw-nr-recheck.log。不能称全库全绿。
- 扩展旧 ARM 集：main 与本候选各21个相同失败（18断言、3错误），没有新增失败；为过时的 owner/view/state 布局断言，完整用例名及日志随包保存，不修改这些断言绕过失败。
- 未执行：实机更新、物理关机/拍摄/重启验收、GitHub 推送、生产发布。

Node 基线失败的用例名见 evidence/node-current-failures.json 与 node-baseline-failure-names.json；旧 ARM 失败名见 evidence/baseline-arm-tests.log 与 current-arm-tests.log。

## 用户验证

1. 保留存储卡现有 M10V 存档；按现有更新方法使用包内 fw/fwdc239b.bin。需要更新胶卷库时，仅复制 SD/M10V/FILMS.M10；不要删除或覆盖自己的 M10V6A/B.bin 等配置。
2. 普通 ADJ → 影像控制，不按 DISP，直接按电源。确认镜头正常收回、关机完成；重开后可正常取景。重复3次。
3. ADJ 影像控制 → DISP → A/B 选择页：六款漫画/E6显示正确名称，不再出现“槽位/页面验证”；原厂风格仍存在。分别在 A 与 B 选择阶段直接关机，再重开。
4. 验证普通 ADJ 的 OK/MENU 返回，A/B 两次 OK 启用及 DISP 快切；拍摄 JPEG/RAW+JPEG、即时回放、再次关机；Fn 及原来配置保留。
5. 如仍卡死，记录发生在普通 ADJ 还是 A/B 页、A/B阶段、是否收镜头及重开结果，并绑定本包哈希反馈。

恢复：先取出更新卡并断电重开；删除卡根的测试更新 BIN。需要恢复固件时，沿既有官方固件恢复/更新流程使用已备份的原厂文件；不要删除用户胶卷存档。此包不覆盖相机或存储卡上的任何文件，安装步骤由用户执行。
