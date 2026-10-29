# GR III / IIIx 保存下载失败修复

基线：b41a768a6829d2e89db31cf654501b938e978336。用户明确授权本次修复后合并 main、发布 GitHub 和宝塔；发布授权不作为相机验收。

## 根因

2026-10-28 17:35:48、17:45:17（服务器日志时间）Nginx 对用户 IIIx 1.70 来源项目 `aa8e3ae1349d94e83be381c20530e41d5e57b75c27ef24ba81c7b017d6c11592` 的 `/native-library/build` 明确报 `upstream sent too big header while reading response header from upstream`。生产配置响应头缓冲为 16 KiB。完整原生胶卷构建回执、构建来源、版本适配记录都通过 Base64 响应头返回，组合超限导致 502。网页只尝试读取 JSON 错误，HTML 网关错误被隐藏成“操作失败”。上轮真实输入 HTTP 用例仅预检原生胶卷，实际导出走较小的原厂预设，未覆盖该问题。

## 修改范围

- GR III / IIIx 浏览器原生胶卷及原厂工具下载通过 `Accept: multipart/form-data` 协商，将完整校验记录放到响应正文 metadata 部分；firmware 部分保持原始 BIN 字节。服务端分段写出，不拼接额外完整固件 Buffer。
- 浏览器校验 multipart 格式、固件类型与长度，恢复原来的二进制 Response 和完整回执，保留原有配置/版本锁回读及下载逻辑；取消保持 AbortError。
- 网关错误显示 HTTP 状态；保留服务端 JSON 中的具体构建错误。旧二进制下载客户端兼容保留。
- 相机运行代码、补丁地址、ISP、胶卷目录、存档、机型基线、版本适配算法、GR II/IV 下载策略均未修改。

## 验证

- 回归测试先复现真实 HTTP 客户端 `HPE_HEADER_OVERFLOW`：40 KB 记录超过 8 KiB 头限制。修复后记录完整恢复，BIN 字节完全相同；覆盖畸形 multipart、取消、旧响应及网页 HTTP 错误。
- 专项网页/服务/发布保护：34 passed；部署 Python 检查：24 passed。独立代码复核无阻塞问题。
- 两个真实输入开启完整原生胶卷、HDF、光晕、画幅/水平仪/负片颗粒及 RAW NR，逐机型完整编译、版本适配、独立回读，经 8 KiB 响应头限制的真实 HTTP 客户端下载成功。回读型号、配置、长度、SHA-256 及包版本全部一致：GR III `2.20.21.28`、IIIx `1.70.21.18`。两个用例均 passed，未跳过。
- Chrome 实际接收 32,314,700-byte IIIx multipart 下载，恢复 BIN 文件名、完整回执与 1.70.21.18 版本，Web Crypto 计算 SHA-256 与回执一致。网络响应头不再携带大回执。
- 完整 npm test 首轮：318 passed、56 failed、32 skipped。其中 13 个新增失败名称为本地原厂 fixture 别名缺失导致的加载/输入错误；补齐忽略文件后单独复跑相关文件，29 passed、0 failed。其余失败名称均已在上一轮 main 对照报告 `gr3-version-compat-existing-failures-20261028.json` 中记录。完整明细和补跑结果位于本地 `builds/save-download-diagnostic/`；不将全套报告为通过。

## 边界

此轮证明构建及浏览器下载链路，不证明相机刷入、厂商更新器接受、恢复、菜单或拍摄。功能运行基线仍为 GR III 2.10、IIIx 1.60。测试固件和回执按机型存放在本地 `builds/save-download-diagnostic/candidates/`，不得混用 BIN。
