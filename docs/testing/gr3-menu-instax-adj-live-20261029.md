# GR III / IIIx 菜单、Instax、回放与自定义 ISP 候选

状态：**WAITING_FOR_USER_VALIDATION**。2026-10-29 基于 GitHub main `38a847b5871e2441a7934fafd38dcee50d4faef4` 开发；本轮只读核对宝塔提交同为此 SHA。开发分支 `daily/gr3-menu-instax-playback-adj-live-20261029`；未合并、推送或部署。正式交付为 **r4**，早期构建均不作为当前候选。

后续状态（2026-10-29）：**USER_VALIDATED / RELEASE_AUTHORIZED**。用户反馈“别的没问题了”，明确要求删去 HDF 底部单句说明后合并 main 并发布 GitHub/宝塔。接受的 r4 身份及授权边界见 `gr3-menu-instax-adj-live-user-acceptance-20261029.json`；下文保留原候选交付记录。最终只移除正常状态说明和对应资源文字，保留错误提示及资源编号；用户明确授权此项调整后直接发布，无额外实机计时或机型测量结论。

## 改动和源码证据

- 菜单：时间/名称水印、A/B、焦距设置和效果/HDF/边框页使用整行黄色选中底、原厂 enum28 深色字和分隔线。保持胶卷卡片、控件顺序及返回/确认/取消。HDF 样式资源独立归属，缓存尾部不重叠；覆盖分配失败、重入和销毁。
- Instax Color：追加 ID317 到「创意」，原来 46 个目录项和数值不变；无默认边框。富士官方 AF3-076E 特性/光谱/染料曲线及 MIT Spectral Film LUT 数字化模型为参考；来源、许可证和复现见 [Instax 记录](gr3-instax-20261029.md)。32768 个软件留出样本量化 ΔE00 mean/P95/max 为 **3.458 / 6.779 / 21.047**，严格 fidelity gate 未过，不能称 100% 模拟或实体胶片标定。
- 回放图标：原厂 `0x535c24ec` 的 ImageTone 解析将 `0x10c..0x115` 清为 0，旧绘制 Hook 因而看不到私有身份。补齐有 preimage 校验的解析桥，保留原厂/未知值；按照片自身记录显示通用胶卷标记，不以当前槽位冒充历史胶卷名。缺少原始身份的旧照片不能凭空恢复具体胶卷。见 [回放记录](gr3-playback-icon-20261029.md)。
- HDF ADJ：原厂记录 `+0x3c` 是“非零排除”的谓词，原实现方向反了；现在有 owner 时可见。覆盖五槽真实图标显示、初始导航、冷缓存启动、设置存档和 U 模式回读，复用同一 HDF journal，不借用原厂编号。见 [HDF 记录](gr3-hdf-adj-20261029.md)。
- 自定义 LUT：电脑离线拟合，SD 记录 6688 处增加 MISP v1 扩展，payload1572 字节，长度/CRC/中性矩阵行和/单调14位曲线均校验。绝对 look 转为相对 Standard 矩阵，并按实际 CCA/CSP 舍入和原厂 gamma 重新评估误差。报告及源/配方哈希随 ZIP 输出，超范围拒绝。见 [导出记录](gr3-custom-isp-export-20261029.md)。
- 相机端：TopMenu 在原 `0x213c` 后拥有 `0x4000` 的 inline 配方缓存，设置 owner 变为 `0x613c`，HDF/border 尾部随构建统一移动。存储重入后重新检查 owner 身份和 version；不另持可被提前释放的 profile heap。拍摄从缓存复制到本张 `0x5150` 的1576字节 sidecar，完整 recipe 为 `0x5778`；保留 RAW token、HDF、方向水印和原厂颗粒原偏移。取景和 Still 写同一配方，已曝光照片不读后来的 UI 配方；普通关闭附加效果的新配方走真实完成交接和零像素 CPU 快路。
- 完成 ISP 调色后，即使需要水印/光晕残余处理也不再重复应用原始自定义 LUT。旧零扩展记录继续读，上一版 renderer 身份也被覆盖；未知 renderer/损坏记录仍拒绝。**旧自定义胶卷要重新导出并重新装入，才能获得 ISP 预览；不会自动重写已有配置。**

## 最终 BIN 身份

两包均使用现有 `scripts/export_gr3_m10v_native.mjs --with-hdf` 公共导出链；HDF 功能包含但默认强度0，调试关闭，正常五款初始配置，有效已有存档优先。每款239个 Hook 核验。当前候选不包含边框功能开关，边框与其他效果的原代码/回归保留，不改用户旧配置。

| 机型 | 固件基线 | BIN 字节 | SHA256 |
| --- | --- | ---: | --- |
| GR III | 2.10 | 32178328 | `981852373ab67f9646008a9b4546daeddfe16781db9d2d5fd5e59edbb78ef6e3` |
| GR IIIx | 1.60 | 32320924 | `e77e78e9508d3fce9ba05fc3335c6964d729005a252ff3323d2614ab603ffc2e` |

目录：`builds/gr3-menu-instax-adj-live-20261029-r4/` 与 `builds/gr3x-menu-instax-adj-live-20261029-r4/`。各自 receipt/manifest 包含官方输入、源文件/配置指纹与最终 runtime hash。以这些完整身份识别候选，不以版本名替代。

## 验证结果和边界

- 最终 GR III BIN 解包、runtime SHA/receipt 核对后运行 `tests.test_gr3_film_pipeline_current`：**21 项通过**。真实原厂任务生产者 → 本张快照 → Still Make → 完成校验 → 编码；24MP planes 未映射，访问像素/分配/文件服务即失败。覆盖 Instax stage0/1、自定义冻结、原厂全部 tone、普通参数变化、关闭 Live 色彩仍有拍摄缓存、重复 Make、错误身份拒绝、FP/寄存器保护及独立篡改审计。
- 最终 IIIx BIN 同样解包核验；owner size、自定义真实生产者/零像素编码、真实离线导出配方 → Live 回调/Still、Instax stage0/1 共 **4 项通过**。没有把 GR III 结果直接记作 IIIx 结果。
- 真实导出的非 identity 暖色 LUT，原厂 Still 与 Live vtable 回调写入的 CCA/CSP 与报告一致，四通道 gamma bank 逐字节相同。Live 用 stage1-shaped metadata；**未模拟传感器 stage0 的 AWB/黑电平标定**，不能据此声称真实实景预览像素一致或帧率通过。
- 菜单/HDF/ADJ/回放/Instax/SD 兼容定向45项通过；最终 custom ISP 再核验9项通过，含原 main renderer 旧记录、CRC 修复后越界、存储重入、残余水印不重复调色。Node 拟合/codec/HTTP/机型调用者、对应新增测试见本目录子记录；生成合同 `--check` 和 `git diff --check` 通过。
- 完整 npm 的 baseline 与最终对照日志在 `builds/npm-main-baseline-20261029.log`、`builds/npm-final-verified-20261029.log`。原 main：437项，330通过、65失败、42跳过；最终：449项，342通过、65失败、42跳过。按归一化测试名对比新增失败为0；结果在 `builds/npm-final-baseline-comparison.json`。基线使用独立 `git archive origin/main`，原样保留1872个源文件；缺失的旧固件根目录 fixture、历史目录/104字节状态/资源断言等不通过，本次不改无关断言掩盖。UI 旧“尚未迁移为 ISP”文案断言随实际功能更新，现要求说明近似与重导入，并复跑通过。
- 未执行全量历史 Python/ARM 套件。额外尝试的旧 `test_gr3_appended_slots`、`test_gr3_capture_released_raw` 有旧5槽/104字节 fixture 失败；独立 NativeLook 套件被 main 自带 Phoenix fitter 来源哈希过时阻断。这些不计为通过，也不扩大最终21项当前 ABI 的证明范围。
- 独立 whole-change review 发现并验证旧 renderer 兼容遗漏，修复后独立 host probe 认可旧记录、拒绝未知记录。随后 bounded review 确认无剩余 Critical/Important；owner size 查询也已修正并经真实 BIN 回归验证。最终 ABI/封包不放松原有重定位门槛。

## 用户实机验收

1. 备份卡上原配置/胶卷包，使用对应机型 r4 BIN 与配套 SD/M10V/FILMS.M10，不跨机型。保留已有存档；候选不自动改五个 ADJ 槽或激活新胶卷。
2. MENU 的时间/名称水印、焦距、效果/HDF：检查整行黄底/深色字、值与焦点、取消、错误和返回，拍照/回放返回后重复打开。
3. 胶卷库添加「创意」Instax Color；同曝光/白平衡对照肤色、灰阶、红蓝和暗部。分别拍 JPEG、RAW+JPEG，切卷后首张和连续至少3张，观察即时回放/相册及处理等待。实体 Instax 对照另记，不把软件误差当作实拍色差。
4. ADJ 设置任选一槽分配“HDF 模拟”，检查 ADJ 中实际显示；更改档位后与 MENU 一致，取消不保存，重启/U模式回读正确，所有原厂 ADJ 功能保留。
5. 可先使用包内 `ISP Warm Test` 验证色彩取景；自己的 LUT 需用本分支本地服务重新导出并在相机重新装入。切回原厂再切回 LUT，比较预览/首张/后续 JPEG，半按、Fn、DISP/A-B、回放返回均检查；颗粒/光晕/水印只按各自成片合同验收。
6. 新拍和带 m10v 私有记录的旧照片切图/详情检查胶卷标记；原厂照片不得误标，修改当前胶卷不改变旧照片的图标身份。

回退：先在所有使用的普通/U1–U3 配置中将五个 ADJ 槽改回原厂选项，再按已有方法恢复先前已验证固件/胶卷包。不要在不支持扩展 ID20 的固件中保留该分配。不会自动覆盖卡上配置，设备动作由用户执行。
