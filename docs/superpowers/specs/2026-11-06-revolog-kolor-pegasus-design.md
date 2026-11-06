# SHD50、Revolog KOLOR 与 Pegasus：原生 ISP 胶卷

用户确认新增三个独立胶卷：SHD50、Revolog KOLOR、Pegasus；彩虹胶卷选择“逐张自动变化、效果为胶卷固有特性”的原生 ISP 方案。相机保存链路不得使用 CPU LUT、CPU 随机数或 CPU 像素处理。三个胶卷先完成离线拟合并用同一基准图展示示例，用户确认视觉方向后再进入最终相机测试包阶段。

## 身份与目录

- 基线为 GitHub `origin/main` `49d63c0d6be9ffbd52e0532a1eec3bd1ed353f60`；实现分支 `daily/revolog-pegasus-isp`。
- 稳定 ID 328 为 `SHD50`，追加到 D76 分组；稳定 ID 329 为 `Revolog KOLOR`，稳定 ID 330 为 `Pegasus`，按此顺序追加到 C41 分组；既有 ID、显示顺序、十槽、184-byte 状态和历史存档不重排。
- 追加图标资源 888/889/890、名称资源 1203/1204/1205；冻结当前 85 条 SD 配方为新的兼容快照，再追加三个闭合 renderer 记录。
- 支持范围沿用纯 ISP 效果管线：GR III 2.10 与 GR IIIx 1.60。GR IV 和其他固件版本拒绝新 ID，不获得未经证明的兼容性。

## 视觉模型与来源

- SHD50 按用户提供的说明和可核实社区实拍拟合：极高反差、极细颗粒、窄宽容度、亮部快速漂白，红光响应较弱。公开资料对实际有效感光度存在 ISO 6–25 的显著分歧，因此只在名称中保留 SHD50，不伪造精确显影配方；成片以高反差中性黑白 ISP 曲线和红光权重降低表达，颗粒仍使用现有原生 ISP 颗粒。
- Revolog 官方将 KOLOR 描述为红、蓝、橙、绿、粉、青等颜色在整卷中变化的色调与渐变；实现为四组有机多色曝光场，逐张选择、平移和改变强度，不重复固定蒙版。
- Yodica 创始人公开描述 Pegasus 为每帧都有的 rainbow beam；公开规格为 ISO 400、35mm、C-41。实现为四组横贯胶片画幅的彩虹光带，逐张改变高度、宽度、相位和强度。
- Pegasus 基础负片复用现有 Kodak ColorPlus 200 的 ISP 配方；公开零售资料称 Yodica 使用 ColorPlus 基底。KOLOR 使用同一中性 C41 基底，但不宣称其真实乳剂就是 ColorPlus。SHD50 使用独立单色矩阵、曲线和多轴响应，不从现有 D76 胶卷改名复用。
- 未找到来源、输入色域和许可均可验证的 KOLOR/Pegasus 专用社区 LUT，因此不伪造“社区 LUT”。官方及社区样片只用于离线统计颜色顺序、覆盖率、边缘柔度和强度范围；仓库记录 URL、获取日期、派生参数和生成器哈希，不分发样片。
- “100%”不作为可伪造的离线数值。拟合器必须报告合成参考与量化 ISP 场的逐分量误差、覆盖率和边缘误差；最终还原度由绑定候选哈希的实机样张对照验收。

## ISP 架构

- 构建主机生成低分辨率、平滑、可缩放的有符号 Y/Cb/Cr 调制场。每个分量拆成正负场，由原生 Resize/Granulation ISP 图执行；CPU 只冻结和校验少量元数据，不读取照片平面。
- 两个彩虹胶卷各提供四个基础场。拍摄入口从本张已冻结的 film identity generation、recipe、SI 和 sequence 生成确定性 variant/phase/strength，并写入 shot snapshot 的带 tag 内部字段；后来的换卷或 UI 更新不能改变已排队照片。SHD50 不启用彩虹场。
- Pegasus 场固定在物理胶片/传感器坐标中，不随 EXIF 方向旋转；横拍为水平光带，竖拍回放时自然呈竖向，符合预曝光胶片行为。KOLOR 为二维有机场，无方向语义。
- 新增独立 native completion bit。真实 ISP 六分量全部成功后才能完成；任一提交、空间、所有权或完成校验失败都使照片任务失败，不得退回 CPU 调色。
- 资源包继续保持不可变、64-byte 对齐、哈希绑定和低于 `0x55000000` 的既有边界。所有场复用一个工作区；资源数量、代码区和最坏工作区在构建时硬校验。
- 基础色彩仍由 ISP frame gamma/matrix/multiaxis 执行。网页预览可以用同一生成参数做说明性模拟，但必须标注不是相机输出，且不进入固件成片链路。

## 行为与兼容

- 两个彩虹胶卷的彩虹场默认且始终开启，不复用用户可调的“漏光”开关，避免关闭全局漏光时意外丢失胶卷身份；SHD50 无彩虹场；现有颗粒、光晕、HDF、水印和画幅仍可独立组合。
- 关闭颗粒、光晕、HDF、水印等残余效果时，编码桥仍保持零像素访问；彩虹场在 Still Make 原生 ISP 阶段完成，不计作 CPU residual。
- 保存、重启、换卷首张、多张排队、关闭取景色彩、RAW-only、RAW+JPEG、即时回放和相册路径沿用现有合同。RAW 像素不应用彩虹场。
- 不修改现有全局漏光纹理、其菜单和历史 journal；不扩展异常回退为正常路径。

## 验证与交付

- 第一阶段把 `web/gr3/film-street-source.png` 作为共同输入，输出原图、SHD50、Revolog KOLOR、Pegasus 四联预览和三张独立示例；同时输出拟合/量化指标。预览只使用构建期同源模型，并明确不是相机实拍。用户查看后暂停等待视觉确认。
- TDD 覆盖目录/资源/SD 兼容、基础配方复用、四变体确定性、跨拍摄变化、排队冻结、方向、边界、失败拒绝及无 CPU 像素访问。
- 必须执行真实生产者投递 → 快照冻结 → Still Make 色彩与空间场 → 原生完成校验 → JPEG 编码，并用未映射 24MP 平面证明 CPU 快速路径不读写像素。
- 运行相关 Node、Python、host-C/ARM、最终 BIN 回读和完整 Node 基线对照；既有失败单独在 clean main 复现，不改断言掩盖。
- 交付 GR III / GR IIIx 可识别测试包、BIN/ZIP SHA-256、build_id、源码/配置指纹、匹配 FILMS.M10、恢复方法和实机检查表。状态停在 `WAITING_FOR_USER_VALIDATION`；未经当前候选验证不合并 main、不推送 GitHub、不部署宝塔。

## 来源

- Revolog KOLOR 官方产品页：<https://www.revolog.net/fr/products/kolor>
- Yodica 创始人采访与 Atlas/Pegasus 区别：<https://kosmofoto.com/2018/07/new-film-maker-yodica-offers-saturated-special-films/>
- Pegasus 规格汇总：<https://stingphotography.com/film/yodica/pegasus/>
- Yodica 基底零售资料：<https://www.revelab.es/comprar/yodica-pegasus/>
- SHD50 社区实拍与曝光讨论：<https://www.reddit.com/r/AnalogCommunity/comments/1rok0tc/lucky_shd50_is_a_weird_film/>
- SHD50 社区测试：<https://www.talkphotography.co.uk/threads/lucky-shd50-35mm-film.774288/>
