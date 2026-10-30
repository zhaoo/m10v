# GR IV 共享构建接口兼容修复

部署 `c0b53312afcada7b74b818d880669f9d0cf489aa` 的 Actions [40884149571](https://github.com/zhaoo/m10v/actions/runs/40884149571) 已通过 GR III 构建和 IIIx guard，随后 GR IV 构建失败。脚本自动回滚至 `38a847b5871e2441a7934fafd38dcee50d4faef4`；已通过 SSH 确认该提交及服务 active。未把失败记作上线成功。

GR III 新增 `m10v_camera_library_custom_profile` 导出，严格共享 ELF 链接器因此更新必需 API。GR IV 有独立相机适配器，原来的 `omitted_exports` 已明确排除 GR III 专用接口，但遗漏新项，导致真实 `check_gr4_release.mjs` 在链接 camera 模块时失败。修复只在 GR IV 的既有排除清单追加该专用接口；不改链接器、不放宽 GR IV 指令/模型/封包检查，也不为 GR IV 启用未经适配的 GR III 预览功能。

回归 `test_gr4_runtime_links_every_ui_and_capture_entry` 使用确切官方 RTOS 完成实际编译/链接，并确认新增 GR III 接口没有泄漏到 GR IV 导出；测试通过。另执行与服务器一致的 `node scripts/check_gr4_release.mjs`，核对完整构建与候选回读，日志保存在 `builds/gr4-release-interface-fix.log`。GR III/IIIx 原已核验固件的 runtime source fingerprint 在修复后逐项保持一致；此次构建修复不改变它们的已验收行为。

重发使用新 changelog 版本 `2026.10.29.3`；上一失败版本归档为 source 证据，不标记 deployment。最终 Actions 与线上 SHA 在发布结束时核对。上述为离线/发布检查，不增加物理相机验收范围。
