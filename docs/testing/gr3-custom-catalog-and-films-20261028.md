# 2026-10-28 SD 自定义目录与胶卷更新

用户授权从 GitHub main 起步，对 GR III / GR IIIx 做定向检查后直接发布，无全量回归。本记录的 ARM、文件、封包和 HTTP 证据均不代表本次真机验收。

## 自定义 LUT 再次缺失

用户确认：在 SD 胶卷库导入 .cube，下载后复制 SD，GR III 今天重新刷机。

213cb7f 修正了固定内建目录过滤，但其测试分别替换 settings 和文件系统，没有贯通真实 settings 与 SD 代码。复查找到第二个确定缺陷：settings_open 逐项询问自定义列表，以首次返回 0 缓存目录结束；底层分配、读取、校验、关闭失败均返回 0，因此一次临时读取失败会使后续自定义项在本次菜单生命周期内不可达。尚不能断言这是用户现场的唯一原因。

修复：增加 directory_extent，单次读取并验证 4096 字节文件头，统计自定义 ID，明确区分“有效但没有自定义项”与读取失败。错误显示在菜单，用户再次按键可重试；恢复时重新定位有效项、更新 expected，重试本身不安装胶卷。返回键不受过期目录索引阻挡。CRC、记录身份、短读校验不放宽。

联合测试从 exportSdFilms 实际导出的 ZIP 提取 FILMS.M10，在链接的 ARM settings/SD 代码中模拟第一次短读及恢复，断言自定义 ID、数量、名称、索引与无浏览写入。文件系统服务为边界替身，不模拟实体 SD 时序。另有主机 ASan/UBSan 测试验证 OK 重试不误安装、过期索引恢复与返回。

## 胶卷与分组

- 312 OptiColour 200、313 NC500：C41。
- 314 ACROS II 100、315 Double-X 5222：黑白。原 D76 目录改为黑白，原 ID 保留。
- 316 LomoChrome Turquoise：创意。
- 306 Makoto Shinkai、307 Ghibli、308 1970s 停用；移除 CPU 漫画路径、编译资源和 Fn / ADJ 漫画控件。历史记录保持可解码，在既有安全迁移入口移除这些选择并保留其他胶卷和设置。

新增三卷的来源、假设、许可及逐文件 SHA 在 native/gr3/extra-films-reference.json。ACROS II 为厂商定性资料指导下的独立模型；Double-X 用仓库内 MIT 授权 spectral_film_lut 的 KODAK_5222（D96 曲线6）加 POLYMAX grade2 纸基解释；Turquoise 为依据 Lomography 2021 配方说明建立的独立换色模型。未复制受限制社区 LUT，不把独立系数写成官方测量数据。

全部新增卷使用原厂 ISP 色彩路径，无新增 CPU 全图调色。拟合误差仅相对离线显示目标，不是实体胶卷还原度；camera_validated 与 film_calibrated 保持 false。

32768 独立色点 holdout 的 ΔE00 P95：ACROS II 0.817、Double-X 2.192、Turquoise 0.520。Double-X 未达到既有 P95<=2 的拟合优选阈值，fidelity_pass 如实为 false，未放宽阈值；其模拟误差和扫描/纸基解释仍属限制，不宣称 100% 模拟。

## 发布与检查

6b395f6 的部署 run 40646235364 因 debug 组合包 RTOS 增长超限失败，服务器回退 213cb7f。此次删除已停用漫画资源，保持原预算及机型保护，重新检查 debug 组合包，不通过关闭 debug 或提高预算绕过。

最终检查命令与构建摘要见本次发布回执。仅运行自定义导入/目录、旧包兼容、漫画迁移、五款胶卷实际任务生产链路、网页分组/导出以及两机型构建相关检查。

最终定向检查结果：网页/API 19 项通过；最新目录联合/ASan 2 项通过；目录 extent 故障边界 1 项通过；漫画迁移及五卷任务链路已通过，目录尾卡片与旧包兼容 2 项通过；更新日志 4 项通过。未运行全量回归。

- gr3: bytes=32350352, sha256=62ca094379054c16b450973028d0c378c6fff737bdc656871ca1a24c15668db9, debug=True, RTOS growth=1114532, film_count=103, SD visible=46。
- gr3x: bytes=32474760, sha256=f395985be6c63a90def788fb5a94b2bb446d5591315b9bc6ad25f159f49ab0ff, debug=False, RTOS growth=1106756, film_count=103, SD visible=46。

6a4bb9c 的服务器 GR III debug 构建通过，随后 GR IV 发布构建因共享链接器新增 directory_extent、GR IV 缺少显式接口排除声明而失败，run 40652219088 回退 213cb7f。补齐 GR IV 的专用排除清单，保持该机型原有位置目录和不支持自定义 LUT 的边界，不削弱链接器必需接口检查。GR III / GR IIIx 功能代码保持不变。

补齐后执行与服务器相同的 `scripts/check_gr4_release.mjs`：完整编译、链接、固件封包及重新解码回读通过；GR IV SHA256=4ed9c8823796e2e8ac350d6b96e59474084b769cfb6eede96815b3264b417863，bytes=41191236，camera_tested=false。更新日志四项检查通过。此修正仅为保持已存在的 GR IV 发布构建边界。
