# 平台视觉稿 R3 与本地功能核查 · 2026-11-03

本地源码 HEAD：`711ce5163ef2eb5ba690c1abdfadbd8a94529c43`，含本会话已有未提交修改。本报告区分视觉预览、网页修复、离线测试及相机验证。

## 用户要求与视觉稿

- 桌面和手机均直接展示工作台、胶卷库、技能、更新日志、说明、打赏；GitHub 单独常显。删除“更多”折叠菜单。
- 免责声明位于独立说明页面内，不作为一级导航项。
- 恢复独立胶卷库视图，读取原目录快照，原胶卷图标逐文件复制。保留全选、清空、导出全部和导出所选。
- 全量资源选择与工作台最多十卷的方案选择互相独立。GR III 显示 56 款，IIIx 过滤四款 GR III 专属资源后显示 52 款。
- 原自定义 LUT 工具入口保留；视觉稿导出确认会打开本地现有导出工具，并传递所选机型。视觉稿本身不构建固件、不生成替代固件文件。
- 视觉稿的本地草稿使用独立键 `m10v-design-preview-v3`，不覆盖原工作台配置。机型、已选卷、颗粒、光晕和标记开关经刷新持久化核查。
- 320px 与 390px 无横向溢出，一级导航全部可见。桌面 1440px 截图已检查。

视觉稿：[交互预览](http://127.0.0.1:49861/m10v-studio-visual.html?v=3#library)。

## 核查发现与修复

1. **独立胶卷库未区分 IIIx。** 原 `sd-library.js` 仅按路径选择 GR III，无法表达 IIIx；全选会包含四款仅支持 GR III 的胶卷。新增配套机型选择、目录能力过滤与导出模型绑定。未知机型阻止导出，打包期间禁用机型选择。模型通过 `#model=gr3x` 传递，保留服务端拒绝未知查询参数的限制。
2. **自定义 LUT 导入后无法移除。** 原按钮在忙碌期间创建为禁用，结束后没有恢复。修复结束后的按钮状态同步。IIIx 导出同时携带自定义 LUT，不静默丢弃。
3. **当前工作树缺失拟合依赖。** 从用户本机已有 M10V checkout 恢复三个浏览器拟合模块，每个文件先核对仓库同步脚本锁定的 SHA-256。一致后复制至 Git 忽略的 `.runtime/grlife/web`。未替换拟合算法，未放宽校验。此项仅说明本地依赖已恢复，不代表服务器部署已更新。

生产源码修改仅涉及 `web/gr3/sd-library.js`、`sd-library.html`、`sd-library.css`，并新增 `node/gr3-sd-library-model.test.mjs`。视觉稿位于仓库外。未修改相机运行体、固件生成器、封包协议或稳定基线。

## 实际验证

| 检查 | 本地结果 |
|---|---|
| GR III 全量资源 HTTP 导出 | 200；56 条；695080 字节 ZIP；全部配方审计通过 |
| GR IIIx 全量资源 HTTP 导出 | 200；52 条；645892 字节 ZIP；全部配方审计通过 |
| ZIP 内容 | `SD/M10V/FILMS.M10`、`README.txt`、`manifest.json` |
| 原网页浏览器导出链路 | III / IIIx 的请求模型、实际数量、Blob 大小及成功状态核查通过；拦截保存动作，未写存储卡 |
| IIIx 自定义 identity LUT | 原网页导入并导出成功；模型 gr3x；自定义名称保留；ZIP 52319 字节 |
| 自定义移除按钮 | 先复现禁用问题，修复后原网页实测可移除；自动测试覆盖 |
| 最终定向回归 | 49 项通过，0 失败，0 跳过 |
| 全量 `npm test` | 563 项：423 通过、88 失败、52 跳过 |
| 与此前已核对 main 的失败名称集合比较 | 无新增失败名称；此前 10 个失败在恢复依赖后不再出现 |
| `git diff --check` / JS 语法检查 | 通过 |

全量运行后对移除按钮又做了最后的状态修正；最终定向 49 项在该修正之后重新执行。不能把全量结果称为全绿，也不能把浏览器或离线检查称为相机实测通过。

## 仍存在的限制

胶卷打包旧测试仍有四项失败：两项包含旧目录数量 / 哈希表结构假设，两项涉及旧资源包兼容。本轮没有删断言或放宽配方身份校验以让这些测试通过。旧包不能凭新包导出成功推断兼容，应使用匹配版本重新导出。除此之外，全量中的其余既有失败见下列完整名称。

本轮没有刷机、没有向相机或真实 SD 卡写入，没有合并、推送或上线。当前 GR III 2.10 的固件运行体未因本轮网页核查而改变；离线检查无法保证所有机身状态下零风险。

原始日志与对比数据在 `builds/platform-ui-check-20261103/`。

## 本次全量仍失败的完整名称（88 项）

- `<repo>/node/candidate-verify.test.mjs`
- `candidate analysis returns a report without exposing firmware bytes`
- `verified GR III shutdown modification exports a same-version firmware package`
- `GR2 HTTP import, authenticated preparation, native download and SD pack`
- `old web configuration migrates into v4 and validates effect ranges`
- `legacy effects serialize as neutral and resetting preserves film and special controls`
- `all six film icons and five FN enum resources have independent immutable readback`
- `GR III preflight preserves factory choices and binds the new slot layout to approval`
- `actual builder component independently produces twenty patches and permits border-only Effects`
- `missing hook, partial table, source and central-symbol tampering are rejected`
- `code, guard subrange and independent full-context shim readback reject tampering`
- `aborted firmware request terminates its child and cleans the owned temporary folder`
- `Charmera has an independent identity without stealing existing custom ID 79`
- `four colors persist per slot, texture reset preserves color and switching film clears it`
- `requested groups retain stock identities`
- `<repo>/node/gr3-customization.test.mjs`
- `D76 adds the seven exact requested identities after T-Max and preserves all groups`
- `new monochrome and experimental films have correct groups and stable IDs`
- `real GR III build stores correct grain strengths and preserves Positive shared branch`
- `diffusion hook, frozen code and per-tone levels are read back independently of receipt`
- `linked fit workbench and modules are reachable over HTTP`
- `<repo>/node/gr3-frames.test.mjs`
- `actual separately linked native IIP and guard yield exactly18 independently checked patches`
- `retired SD frame storage, CPU compositor and inaccurate zero-pixel declarations reject`
- `source, model, worker ABI, original word and target forgeries reject`
- `guard and native IIP binary subranges must match declared hashes and distinct export bounds`
- `full border runtime reuses the exact same checked guard with zero duplicate patches`
- `Harman films append stable IDs and shared 40px icon records`
- `old effects upgrade and film-specific bounds accept bounded integer simulated EI`
- `schema4 packs EI in each effects reserved byte and common reset preserves EI and disables extra effects`
- `all 46 prior display identities and group order stay unchanged`
- `final joined firmware contains all selected components and rejects repaired-checksum tampering`
- `native RAW NR export independently reads back off and threshold together with old extensions`
- `workbench effects selection visibly includes dependencies and removing either dependency removes effects`
- `<repo>/node/gr3-jpeg.test.mjs`
- `M10V native library builds from official bytes without a compatibility runtime and audits every patch`
- `both models expose the same two editable crop controls with correct lens units`
- `IIIx web export downloads the complete shared ISP ten-film HDF and halation bundle`
- `III and IIIx share ISP film 306`
- `III and IIIx share ISP film 307`
- `III and IIIx share ISP film 308`
- `legacy retired effects migrate to neutral without losing other slot settings`
- `web debug export uses the running Node when the service PATH contains no node`
- `original M10V web workflow binds all five slots and timestamp into audited firmware`
- `fresh defaults and every film selection leave extra effects off`
- `switching away from a manually enabled effect resets extras, selecting same film preserves them`
- `<repo>/node/gr3-patch-plan.test.mjs`
- `Phoenix EI120 persists independently per slot and resets on a different stock`
- `real border component admits exactly the added Resize status helper`
- `actual pure reservation builder preserves the complete exact reset shim`
- `<repo>/node/gr3-raw-nr.test.mjs`
- `backend exposes exactly the requested forty-four identities, names and group order`
- `default SD export and every record retain the requested names and order`
- `deleting texture processing retains all55 previous-revision film records`
- `prior renderer custom LUTs remain accepted while repaired-CRC tampering is rejected`
- `SD pack contains every current platform recipe, independent of five active slots`
- `new builtin LUT records retain names icons and source contract identity`
- `v1 built-in pack from the preceding release remains readable`
- `last delivered 47-film and named custom packs remain readable after opt-in defaults`
- `<repo>/node/gr3-stock-audit.test.mjs`
- `<repo>/node/gr3-stock-presets.test.mjs`
- `five retained style filters keep their identities and requested group names`
- `fresh journals preserve independent timestamp corner and colour bytes`
- `one catalogue exposes only requested legacy simulations`
- `four halo controls and grain/soft are packed in each version4 slot`
- `film name stamp migrates off and packs independently from date`
- `both colour views edit a single native configuration and do not restore the legacy film builder`
- `universal halation is explicit GR III film capability, bound into plan and defaults off`
- `web draft preserves the independent halation write toggle`
- `<repo>/node/gr3-update-evidence.test.mjs`
- `GR IIIx ports audited legacy recipe, timestamp, aspect and level composition with stock edits`
- `GR IV actual native capabilities and custom prepare are model-specific`
- `GR IV custom API has independent route and authorization`
- `GR IV uses the shared five-slot workbench and retains the reference editor`
- `HTTP serves isolated product workspaces and authorizes GR IV mutations`
- `the same import handler accepts both models and updates target labels from official identity`
- `2.20 upload shows the uploaded version as its actual build source`
- `local sample selection does not override the loaded target until import completes`
- `GR IIIx extension tab retains the native workflow`
- `opening imaging settings preserves an HDF-only selection`
- `product home exposes GR IV native workbench and GR II inspection with truthful limits`
- `<repo>/node/version-candidate.test.mjs`
- `<repo>/node/version-verify.test.mjs`
- `custom film drafts migrate supported selections and block unresolved slots without custom tools`
- `native draft and history retire leak while preserving active per-slot settings`
- `legacy undo snapshots cannot restore custom recipe or preset modes`
- `combined HDF and film drafts retain film and preserve global HDF separately`
- `imaging switches survive draft and undo normalization, including border and A/B`
