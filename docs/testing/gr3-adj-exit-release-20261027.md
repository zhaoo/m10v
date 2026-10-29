# ADJ 退出修复发布验收记录

状态：USER_VALIDATED。2026-10-27用户针对D2回复：“没问题了，合并main并发布宝塔和github”。按该授权完成main/develop与宝塔发布，不再重复索取批准。

## 验收身份和范围

- 已验收：GR III，D2 build_id=a26bd087。
- D2 BIN SHA-256：9149872492fd73d8d6ca324b7f7c98ab0fc973053886c974df5b1460ac1f7fa1。
- ZIP SHA-256：d6b7f63a3c38e3d9bcec2d32f7961a1db646df7328501f9bd93e1dd9c643b405。
- runtime source fingerprint：42c9ae8d5c3be45d7c14d4f3f4e2069120792515bdb0f900ffa6a882db25ac56。
- base_commit：87cc28ae876643d82566bdd2eda6b78193af8c64；上一轮生产Actions40498799324成功。
- 用户此前明确的两条故障：普通ADJ影像控制中按电源、DISP打开A/B选卷页后退出。胶卷名称在R1已获用户确认，R1/R2退出失败不作验收。
- 不扩大为GR IIIx/IV设备验收、JPEG/RAW画质或新增性能测量。

## 最终代码

在原厂导航关闭期间阻止迟到DISP重新开页，真实进入取景或控制器销毁后释放关闭状态；直接接管ADJ列表不伪造pending导航；仅菜单源实际等待挂接时才允许一次同源旧A1拦截。保留名称映射、原厂列表恢复、原厂事件、十槽和存档兼容。

代码与D2验收包的native源集合/摘要完全一致，之后只更新测试记录和changelog。专项诊断默认关闭，显式debug+--adj-exit-trace仍可用于后续取证。

为核验去除专项日志的普通路径，使用D2相同配置、debug=true及完整功能选项重新构建，唯一编译参数差异为M10V_ADJ_EXIT_TRACE=1→0；所有native sources字典逐项相同，158个Hook独立回读通过。

该普通构建BIN SHA-256：02102f3cfb9e16ae80b86ab9f8990fba6fddfb53c4e25aec128704e971ebfbc8。它与D2并非相同二进制，物理机身确认来自D2带日志版本；普通路径有离线构建、trace-off ARM和共享导出检查，未另作无日志版物理验收。生产保持原有默认关闭专项日志，不用同一版本名冒充同一产物。

## 发布前检查

- D2最终专项ARM114项通过、logger19项通过；独立复核42项核心用例通过。
- 最终BIN重放用户同序列：D1 reopened=true/A1 handled=1；D2 reopened=false/A1 handled=0，UI/存储为离线边界。机身通过来自后续用户反馈，不来自模拟器。
- Node全量400项：359通过、32项与独立main基线一致的既有失败、9跳过，无新增失败；保留失败断言，不称全库全绿。
- 发布检查：changelog2026.10.27.7；12项Node部署/changelog控制通过，24项Python部署/封包控制通过。
- GitHub main/develop远端同基线；普通fast-forward原子推送，不覆盖其他工作树本地main/develop或其脏文件。

## 部署边界

本次共享运行时实际消费者为GR III和IIIx；完整Node导出检查覆盖IIIx，未声称IIIx机身确认。当前生产受限部署入口仍执行已有三机型检查，沿用该入口，不在本次修复中修改部署/内存/权限配置。GitHub推送不等于部署完成，须以本次完整SHA的DEPLOY_OK、service=active及公网首页/机型页/指南/changelog核验为准。实际SHA及Actions可从本条changelog所在提交与其Deploy Baota运行定位。
