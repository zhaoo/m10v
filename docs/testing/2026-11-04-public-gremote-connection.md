# GRemote 连接公开开关候选

状态：**WAITING_FOR_USER_VALIDATION**。未发布新固件运行体，未操作相机或 SD。

用户确认本次先支持 GR III，IIIx 的 GRemote 开关置灰。普通固件仍限定精确官方 GR III 2.10 / IIIx 1.60。2026-11-03 旧桥的实测反馈不视为本候选的设备验收。

## 行为

- 影像工具新增默认关闭的「GRemote 连接」。依赖十槽胶卷库；关闭胶卷库、切换 IIIx/IV 或恢复不兼容草稿会取消选择。
- 服务端严格验证布尔值、精确来源、机型、原生管线；拒绝客户端注入私有身份和 `preserve_existing`。公开 `gremote_preserve_settings` 是独立布尔选择；身份同时绑定当前配置、保留策略、源码、目录、渲染器和开关机图片。
- 开启后输出私有 ZIP，包含匹配固件、独立编译的 SD 服务、每次下载新生成的配对、匹配 FILMS、校验清单和人工说明。不复用旧用户密钥，不嵌入 APK，不自动刷机或开启 SD 脚本。
- 原有完整重建、执行线程、排队、取消、失效、下载证明保留。父进程核验固件后才打包；浏览器分别绑定 ZIP 摘要与内层固件回执，不能把两种摘要混用。
- 普通 OFF 网页初次应用编译选卷的策略保持不变。启用 GRemote 后有独立「保留机内设置」选项，默认开启；关闭才应用网页选卷。本 RC2 启用保留策略，保留有效当前 journal 中的槽位和全局参数，`zoom_seed=null`。记录缺失或损坏仍走原初始化；SD 文件备份不等于机内 AppData/Flash 备份。RC1 是旧的非保留检查产物，**不用于此次刷入**。
- M10V 与 GRemote 导流菜单是独立纯网页提交，不夹带本候选运行体。

## 最终候选

私有包：`m10v-gremote-gr3-210-20261104-rc2.zip`，34,898,932 字节。

- ZIP SHA-256：`5470c7e0e4a33dace7e9b32f9e85a99b0c5118285eb4c85d73ee8ca3ad743de5`
- BIN SHA-256：`bd14384feb6885807137ade77795bba49e0c4caf1ef5258f3c0e16059cb4924a`
- buildId：`8eb3de47ce1f49316f3aa81fcde09c401c96eb39140131d67ffcac4693fc6a8a`
- 目录：`5d3ec9b649a410b0ec988d09d7107872ce8fa67520a9502fc6ef840318d8f9fb`
- renderer：`7595208a0cf061d661fd90ab0b8233fd0cf5d5090a2209dff38c9c47a7f21995`

ZIP 含个人配对材料，不进入公开 Git/GitHub Release。`builds/public-gremote-20261104/` 保留私有来源、回执与日志，公开文档只记录非秘密身份。

## 本轮验证

- GR III 2.10、IIIx 1.60 官方输入的身份及完整解码通过。
- 两款 OFF 固件以同样默认配置、`--pure-isp-effects --ab-compare` 分别对比干净 main `6e77769619ee9dc952e6b3993d052d53e0807a94`，完整 BIN 逐字节相同。GR III：`e6fa707d4f94394939da835afb21c280ef554cca9ed2d082bca99010e6a3871e`；IIIx：`3f3f5d82dc23b43124bfb26aafec27d920206a219a529987263a0fd75f7c88cc`。各 14 个分区相同，13 个非 RTOS 分区保持官方字节。
- 新增与相关开关、模型迁移、导航、浏览器验证、下载、任务队列检查 63 项通过。公开 HTTP → 线程 → 两次完整固件构建 → 新服务 → 队列 → multipart → 浏览器 SHA 真实链路，在最终打包修复后再次通过 1/1。
- 最终 RC2 交付 BIN 的真实 pure-ISP producer/快照/原生执行/编码零像素访问验证 15 项通过，覆盖新增五卷；同一交付 BIN 的 journal 保留、首次初始化和策略标记 3 项通过，共 18 项。只增加按实际 ROM 大小且严格不越 RTOS RAM 的测试映射，不放宽原有 hook 或状态断言。不代表物理 DMA、成像质量或相机速度。
- 实际私有打包 Node 3/3；Python 打包及服务相关 19 项，12 通过、7 个既有 APK 条件跳过。两次服务使用不同 key/instance，取消删除含密钥编译临时文件，伪造证明或改 ZIP 拒绝。
- 评审发现同时篡改 manifest/receipt 的三个身份可能生成不匹配服务，已补 RED→GREEN：从最终 BIN 的具名 ELF 常量精确位置读回身份，验证完整重定位 owner 对象；不做任意字节搜索。复审无剩余可操作问题，BIN/native 源码未因此改变。
- 全量 Node：干净 main 598 项，444 pass / 83 fail / 71 skip；最终 RC2 628 项，477 pass / 78 fail / 73 skip。规范化绝对 checkout 前缀后无新增失败；全量仍红，不能称全套通过。完整失败及差异记录在私有 evidence 目录。
- 保留设置相关 Node 34 项通过；复审未发现可操作问题。本地实际浏览器 1440/390：GR III 开关默认关闭，开启后保留选项默认勾选，取消/撤销/重做/草稿恢复正确；IIIx 禁用且无法点击激活。导航外链一次，无横向溢出。仅导入内置来源，未在该视觉检查中生成固件。

## 发布门槛与未验证项

真实启动、保存/装卷读回、冷启动焦距缓存、重启持久化、拍摄/RAW/JPEG/回放/连续拍摄、重复 owner 生命周期和恢复仍未验收。桥保留冷焦距缓存未就绪时 fail-closed；不能从离线结果推断不会变砖。当前 ADB 没有设备，未安装或传入新固件包。用户反馈已安装 GRemote 正式 App，尚未由本轮工具核验。

按 `skills/grkit-development/references/release-workflow.md`，当前候选明确验收后，才将固件功能合并 main、推送并部署；不得把已上线的纯导航提交当作固件功能已上线。IIIx 桥接仍未移植，不承诺支持。
