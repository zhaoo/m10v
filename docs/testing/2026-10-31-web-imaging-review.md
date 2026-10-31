# M10V 网页与影像方案调整

基线：`a901016cd4f1ebfe917dbe195d2c5711af9309a1`。开始时已核对远端 main 与当前生产提交一致。开发和审核在独立工作树完成；用户随后明确要求合并并发布，版本为 `2026.10.31.3`。实际部署状态以该版本的 GitHub Actions 与线上提交为准。

## 改动范围

| 区域 | 调整 |
| --- | --- |
| 首页 | 简介、明确的功能列表、三步流程、机型入口；清理口号与装饰文案，修复宽屏右侧留白 |
| 影像方案 | GR III / IIIx 扩展默认关闭；功能卡片双列，手机单列；开启后展开设置 |
| 开关机画面 | 并入影像方案；关闭时保留图片草稿，构建请求不携带图片 |
| 草稿与历史 | 保留边框与 A/B 开关；隔离旧编辑器设置；修复 HDF 独立模式、重复撤销和水印显示值不同步 |
| 机型菜单 | 当前机型、适配状态、简短说明；支持方向键、Home/End、Escape |
| 胶卷库 | 导航统一命名；黑白分组更名 D76，ID 与顺序不变；手机双列，修正 IIIx 与 IV 的操作说明 |
| 说明 | 覆盖胶卷、本卷参数、全部扩展、机型差异、安装与存档优先级 |
| 精简入口 | 删除测试包页面；移除桥接入口、弹窗和引导，保留后端桥接接口 |
| GR II | 去掉不可操作的开关机画面步骤，保留实验功能和只读检查；修正首页与说明中的范围描述 |
| GR IV | 胶卷库明确五个位置、静态 JPEG 和原厂取景；参考工具链接到当前胶卷工作台 |

## 运行时影响与保留项

- A/B 开关进入预检、配置指纹、编译参数、manifest 和最终回读；关闭时拒绝选择与 DISP 快切，保留胶卷所需的共享生命周期挂钩。
- 普通胶卷 ISP 管线、原厂预设、胶卷身份、SD 格式、机型隔离、已有机内存档优先级保持不变。
- 网页扩展开关表示是否将功能或初始设置加入本次方案；已有机内记录的行为在说明中单独解释。焦距开关仅控制一次性预设写入。
- 桥接后端未删除；GR IIIx 单包版本适配仍是独立高级选项。

## 验证

- 页面、配置、草稿、导航、路由、GR II / IV 相关定向检查：53 通过。
- 当前 GR III 候选执行 A/B 关闭门禁与真实任务投递至 ISP / 编码桥检查：23 通过。普通胶卷零像素快速路径包含在该组检查中。
- 13 个公开页面或视图分别检查桌面与手机，共 26 个视图：无横向溢出、无脚本异常。LUT 工具页发现的缺省图标 404 已补齐。
- 浏览器实际操作覆盖：菜单键盘导航、图片上传与裁切、开关关闭后不发送图片、草稿恢复、HDF 独立模式及一次撤销、水印格式撤销、机型禁用项、说明锚点、删除页面返回 404。
- 全量 `npm test` 执行结果：373 通过、59 失败、34 跳过。没有将其记为全绿；失败包含本地固件样本缺失、旧目录数量／旧槽位合同和过时源码断言。对最新 main 的独立副本抽查，相关目录、旧胶卷、原生路由、SD 兼容与旧控制器检查也存在失败。未修改无关断言来掩盖失败。
- 独立代码审查发现的 HDF 状态、重复撤销、机型文案与水印显示问题均已修正并复查。

## 本地构建校验候选

| 机型 | 方案 | SHA-256 | 独立回读挂钩 |
| --- | --- | --- | --- |
| GR III 2.10 | 胶卷库，扩展默认关闭 | `b7b5acf6bb150998c9b0e16f4b0f99881c0ccbc96dc0e2e39248aa79ef97f01b` | 158 |
| GR IIIx 1.60 | 胶卷库，A/B 开启 | `1daf2d50ce0020cc4b7e436f2c32b770a3cda163bc84a6d6063c19157b3bd9e4` | 158 |

候选及 receipt、manifest、配置位于本地 `builds/imaging-options-20261031/`；网页截图与浏览器审查结果同目录保存。候选均保留 `camera_tested=false`。本轮没有刷写相机，未执行物理设备验收；离线通过不代表相机接受、拍摄、回放或连拍已经验证。


## 全量回归失败项索引

此索引来自上述全量运行；后续网页审核修正另由定向回归与浏览器操作验证，不将以下失败隐藏为通过。

- node/candidate-verify.test.mjs
- candidate analysis returns a report without exposing firmware bytes
- verified GR III shutdown modification exports a same-version firmware package
- old web configuration migrates into v4 and validates effect ranges
- legacy effects serialize as neutral and resetting preserves film and special controls
- all six film icons and five FN enum resources have independent immutable readback
- GR III preflight preserves factory choices and binds the new slot layout to approval
- actual builder component independently produces twenty patches and permits border-only Effects
- missing hook, partial table, source and central-symbol tampering are rejected
- code, guard subrange and independent full-context shim readback reject tampering
- bridge entry and instructions are removed while backend capability remains
- aborted firmware request terminates its child and cleans the owned temporary folder
- Charmera has an independent identity without stealing existing custom ID 79
- four colors persist per slot, texture reset preserves color and switching film clears it
- requested groups retain stock identities
- node/gr3-customization.test.mjs
- D76 adds the seven exact requested identities after T-Max and preserves all groups
- new monochrome and experimental films have correct groups and stable IDs
- real GR III build stores correct grain strengths and preserves Positive shared branch
- diffusion hook, frozen code and per-tone levels are read back independently of receipt
- node/gr3-frames.test.mjs
- Harman films append stable IDs and shared 40px icon records
- old effects upgrade and film-specific bounds accept bounded integer simulated EI
- schema4 packs EI in each effects reserved byte and common reset preserves EI and disables extra effects
- all 46 prior display identities and group order stay unchanged
- node/gr3-jpeg.test.mjs
- IIIx web export downloads the complete shared ISP ten-film HDF and halation bundle
- III and IIIx share ISP film 306
- III and IIIx share ISP film 307
- III and IIIx share ISP film 308
- legacy retired effects migrate to neutral without losing other slot settings
- web debug export uses the running Node when the service PATH contains no node
- original M10V web workflow binds all five slots and timestamp into audited firmware
- fresh defaults and every film selection leave extra effects off
- switching away from a manually enabled effect resets extras, selecting same film preserves them
- node/gr3-patch-plan.test.mjs
- Phoenix EI120 persists independently per slot and resets on a different stock
- node/gr3-raw-nr.test.mjs
- backend exposes exactly the requested forty-four identities, names and group order
- default SD export and every record retain the requested names and order
- deleting texture processing retains all55 previous-revision film records
- prior renderer custom LUTs remain accepted while repaired-CRC tampering is rejected
- SD pack contains every current platform recipe, independent of five active slots
- new builtin LUT records retain names icons and source contract identity
- v1 built-in pack from the preceding release remains readable
- last delivered 47-film and named custom packs remain readable after opt-in defaults
- node/gr3-stock-audit.test.mjs
- node/gr3-stock-presets.test.mjs
- five retained style filters keep their identities and requested group names
- fresh journals preserve independent timestamp corner and colour bytes
- one catalogue exposes only requested legacy simulations
- four halo controls and grain/soft are packed in each version4 slot
- film name stamp migrates off and packs independently from date
- both colour views edit a single native configuration and do not restore the legacy film builder
- node/gr3-update-evidence.test.mjs
- GR IIIx extension tab retains the native workflow
- opening imaging settings preserves an HDF-only selection
- node/version-candidate.test.mjs
- node/version-verify.test.mjs
