# GR III 菜单、Instax 与显示修复 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans for integration and superpowers:dispatching-parallel-agents for independent bug domains. Steps use checkbox syntax.

**Goal:** 完成用户确认的五项变化并交付离线验证的候选。
**Architecture:** 延用原生 UI、状态和 ISP。独立 ADJ/回放问题可并行定位，目录与自定义 ISP 由集成者顺序修改。
**Tech Stack:** C / ARM、Python、Node.js。
**Spec:** `docs/superpowers/specs/2026-10-29-gr3-menu-instax-playback-adj-live-design.md`

**Execution:** 已按用户两次确认连续实施。Tasks1–5 完成；Task6 已完成两机型r4构建、BIN回读、当前链路/定向/完整npm和独立审查，测试包归档与本地提交作为交付收尾完成。详细证据及已知基线失败见 `docs/testing/gr3-menu-instax-adj-live-20261029.md`。终态为 WAITING_FOR_USER_VALIDATION，不合并/推送/部署。

**Rulings:** 自定义配方使用独立逐张 sidecar，保留原来的 RAW/HDF/颗粒/水印偏移；preview 改为 TopMenu inline 存储，避免额外 heap 的读/析构竞态。扩展采用 SD reserved 区的版本化记录，旧 zero-extension 保留；升级不自动改写旧用户配置。改动 owner extent 时同步工厂、构造器、HDF/border 消费者和独立 Node verifier。独立审查发现前版 renderer 漏验并修复；最终查询大小的 RED/GREEN 在真实 BIN 上执行。重定位失败时更改常量引用写法，不放宽 relocator 门槛。

## Global Constraints

- 基线 main `38a847b5871e2441a7934fafd38dcee50d4faef4`，保留原厂 ADJ、旧胶卷 ID、存档兼容与 RAW 安全。
- 拟合离线执行；普通胶卷关闭附加效果零 CPU 像素工作；不伪造 ISP 完成。
- 不合并、不推送、不部署；真机未测如实记录。

## Review Focus

- 相册照片切换/重启后不得由当前选择冒充历史身份。
- HDF 冷缓存与五槽、U 模式回读不能隐藏新 ID。
- 自定义旧包无 ISP 配方时保持兼容且不虚报精确预览。
- 带色黑白、强剪裁 LUT 不得静默改色或越界。
- 菜单退出和内存分配失败保持原厂返回与所有权。

### Task 1: 回放身份修复

**Files:** `scripts/build_gr3_film_slot_extension.py`, `node/gr3-m10v-native-build.mjs`, `tests/test_gr3_ui_polish.py` 及所需专属测试。
**Interfaces:** 消费原厂照片元数据/图标分派；产生经过真实调用链验证的回放 Hook。
- [x] 重现原厂相册图标路径，新增缺失入口/身份测试并观察失败。
- [x] 最小修复并同步封包校验与 IIIx 消费者。
- [x] 运行回放/原厂照片/切图与成像回归，记录结果。

### Task 2: HDF ADJ 可见性

**Files:** `scripts/build_gr3_hdf_adj.py`, `native/gr3/m10v_hdf_adj.c`, `node/gr3-hdf-adj.mjs`, `tests/test_gr3_hdf_adj.py`。
**Interfaces:** 消费原厂五槽设置，复用 HDF owner/cache/journal；输出独立 ID20。
- [x] 从原厂构造/显示入口复现已分配但未显示，测试先失败。
- [x] 补齐遗漏分派，保留原厂所有 ID、确认/取消和保存失败行为。
- [x] 运行五槽、冷缓存、原厂函数和保存测试。

### Task 3: 菜单样式

**Files:** `native/gr3/m10v_settings_view.c`, `native/gr3/m10v_hdf_menu.c`, UI 测试。
**Interfaces:** 延用控件所有权；整行黄色底、深色文字、灰底和分隔线。
- [x] 用实际控件创建/绘制记录验证样式、焦点和退出生命周期，先失败。
- [x] 修改设置/HDF 自绘页，保留胶卷卡片和控制器语义。
- [x] 运行设置视图、根菜单、HDF 和菜单只读检查。

### Task 4: Instax 彩色

**Files:** 胶卷目录生成器、Instax 目标/拟合脚本、派生资源、来源报告和目录/ISP 测试。
**Interfaces:** 追加稳定 ID 与创意组；原生 ISP 配方和可复现的数值/来源哈希。
- [x] 新增目录位置、旧 ID 不变和可编码配方用例，先失败。
- [x] 读取官方曲线与社区数据，固定输入与许可证，离线生成目标/ISP 拟合及误差。
- [x] 更新统一目录派生资源；验证真实投递/Still/完成/编码零像素工作。

### Task 5: 自定义 LUT ISP 预览与成片

**Files:** `node/gr3-custom-lut.mjs`, SD 打包器/解析器、相机 SD/缓存、`m10v_isp_native_look.c`, `m10v_isp_recipe_color.c` 及协议/ARM 测试。
**Interfaces:** 电脑拟合的版本化配方与源 LUT 身份；相机只读缓存，逐张冻结。
- [x] 新增非 identity LUT 预览/成片、旧记录、损坏配方和快照隔离用例，先失败。
- [x] 沿现有 SD/状态 ABI 提供可兼容配方记录；构建端拟合，预览和 Still 使用同一参数。
- [x] 运行 SD 导入/旧包/篡改、Live/Still、真实投递/零像素和 RAW 安全检查。

### Task 6: 整合和候选

**Files:** `docs/testing/2026-10-29-gr3-menu-instax-playback-adj-live.md`、独立构建目录。
**Interfaces:** 所有任务产出的原生 runtime/目录/配方，导出链的最终 BIN/receipt。
- [x] 执行相关跨模块回归与完整 npm test；基线差异明确记录。
- [x] 全分支独立 review，修复实际问题并重跑受影响检查。
- [x] 正常导出链构建受影响机型，回读最终 BIN，生成 ZIP/哈希与实机清单。
- [x] 本地提交可审阅改动，停在 WAITING_FOR_USER_VALIDATION。
