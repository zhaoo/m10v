# 自定义 LUT → SD 原生 ISP 配方（2026-10-29，Node 部分）

本记录只说明电脑拟合、SD 记录与报告；相机运行、取景与成片链路由同次集成的 C/ARM 验证记录覆盖。尚无本候选相机验收。

## 配方 ABI

保持 `M10VREC2`/kind4、原始 13³ RGB、原来的名称+RGB 摘要和外层 CRC。无 `film.ispProfile` 时 `customFilmRecord` 的输出行为不变。存在该字段时，它是 1572 字节 payload：9 个 int16 matrixQ13、9 个 int16 postQ512、3×256 个 uint16 曲线。

记录偏移 `6688..8448` 的可选扩展：

| 偏移 | 内容 |
| --- | --- |
| 6688 | uint32 `0x5053494d`，ASCII `MISP` |
| 6692 | uint32 version 1 |
| 6696 | uint32 payload_bytes 1572 |
| 6700 | payload 的标准 CRC32 |
| 6704..8276 | 1572 字节 payload |
| 8276..8448 | 172 字节零保留 |

纯数据 codec 不导入 `.runtime`。编码与独立 audit 都检查矩阵长度/有符号范围/中性保持行和，以及每条曲线的 14-bit 范围与单调性。audit 另查魔数、版本、长度、内部 CRC、外层 CRC 和全部保留字节；修好外层 CRC 不能让损坏扩展通过。全零扩展仍作为历史记录读取。

## 拟合与相对矩阵边界

`exportSdFilms` 改为 async，生产 HTTP 路由与 GR IV 共享调用者都已 await。仅导出内置卷不加载或运行 GRLife 拟合器。自定义卷先检查名称/身份/重复，再用既有 `fitCube` worker 的 tone/gamut 拟合器、独立样本和灰阶/肤色保护；没有另写一套近似求解器。

拟合目标是实际 SD 携带的量化 13³ RGB 表；原始上传源 SHA-256 与采样后目标 SHA 都进入报告。没有自动降低原始风格强度；超出原生可编码范围的 LUT 拒绝导出。有效结果明确标注 ISP 近似，manifest 包含真实参数、源身份和独立误差。

关键修正：GRLife 的 `matrixQ13` 是绝对 look，而 `m10v_isp_frame_apply` 左乘当前原厂 CCA。导出必须先计算 `relative = absolute × inverse(StandardLook)` 再量化 Q13，并精确保留每行 8192；不能将绝对矩阵直接塞入 frame target，造成 Standard 作用两次。post 保持相对输出矩阵，原生 writer 右乘当前 CSP。

新增 `assessFit(frameRelative:true)` 在实际 payload 上重新评估并重新绑定报告：

- 按 C writer 的整数舍入模拟 `CCA=(relativeQ13×stockCCA+4096)>>13`、`CSP=(stockCSP×postQ512+256)>>9`，检查 signed12/signed9 溢出。
- 使用原始 BASE_GAMMA 的整数 `baseQ14/64` 索引与 correction 曲线映射，先映射 256 项表，再插值。
- 将合成后的矩阵转换回同一个显式 Standard 模型评估独立样本；源报告的绝对参数哈希保留在 provenance。
- 在相对参数评估后再次使用既有灰阶/肤色/P95 guard 选择候选。报告记录候选、实际选择、guard 原因和原厂基线字段。

`StockISP` 原厂 make11 本轮回读确认 CCA `[436,-184,4,-48,400,-96,1,-104,359]`、CSP `[77,150,29,-43,-85,128,128,-107,-21]`；gamma 全部 256 项与现有 GRLife 常量逐项相等。该模型及 `MID_INDEX` 仍是显式离线模型，不能宣称物理相机色彩标定或像素等价；运行时各张的原厂调整仍由真实 frame composer 检查。

## 测试与 RED 证据

修改前的新增测试确实失败：扩展魔数实际为零；坏 profile 未抛错；重算外层 CRC 后的扩展修改未被拒绝。另一个实际拟合导出测试证明绝对 Standard look 被错误写入 payload（identity 应为近 identity 相对矩阵），在矩阵基底转换前失败。

最终专属检查：

```sh
node --test --test-reporter=spec node/gr3-custom-lut.test.mjs node/gr3-custom-isp.test.mjs node/gr3-sd-film-export.test.mjs node/gr3-fit-quality.test.mjs node/gr3-lut-fit.test.mjs node/gr3-sd-film-routes.test.mjs node/gr4-native-routes.test.mjs
node --test --test-reporter=spec node/gr3-custom-isp-fit.test.mjs
git diff --check
```

结果：前一组 29 项通过，后一组 2 项通过，diff whitespace 检查通过。覆盖真实 GR3/IIIx worker 拟合、非 identity 暖色 LUT、profile 与报告参数逐项相等、报告绑定、identity 相对矩阵、实际原厂矩阵字段保持、硬件字段溢出、反相 LUT 明确拒绝、历史无配方记录、扩展篡改、真实 HTTP ZIP 与 GR IV async 调用者。

本工作树最初没有 GRLife/full BIN fixture；验证使用忽略的 symlink 指向主目录缓存。没有把这些运行时或官方固件加入 Git。早期关联 `gr3-sd-film-pack.test.mjs` 的四项失败保留：30 款硬编码数量、56 项哈希表硬编码、用当前记录伪造上一版 v1 renderer 的预期、含退役 ID 的上一版 47 款测试；均不改断言掩盖。集成者统一处理完整套件/成品回读。

## 可复查离线样本

`builds/gr3-custom-isp-validation/` 下保存真实导出的暖色 `warm.cube`、`FILMS.M10`、`warm.zip`、`warm-receipt.json`，用于 C/ARM 消费相同 payload 的链路检查。矩阵合成后的预期 CCA 保持上述 Standard；CSP 为 `[75,155,26,-42,-73,115,115,-96,-19]`。这些 ignored 样本不代表相机已验收。最终生产导出需在全部 runtime 修改完成后重建，以绑定最后 renderer 合同。

最后一次样本 `FILMS.M10` SHA-256：`2bb0b86897469a5b0bd7bf38b6ec5657cc3232508a191da05173d7604ea2ca54`。独立 805 样本的 CIEDE2000 mean/P95/max 为 `0.118916 / 0.293002 / 0.481882`；这是上述显式模型结果，非实拍测量。
