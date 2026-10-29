# GR II：现行功能差距与 HDF 初始设置发布

2026-10-28 以线上和 GitHub main `84feaa97bf489b4ffde319c08b71c9750bded6f9`
为基线，新工作树 `daily/gr2-parity-20261028`；没有合并旧 GR1 工作树的未提交代码。
基线对应 Actions40658889263 的 DEPLOY_OK，公网 GR2 HTML 和 GR3 studio.js 与该提交逐字节相符。

用户本轮先要求 GR2 与 GR3 同步后发布，得知无 GR II 真机后，进一步明确指示
“你直接合并分支，发布github和宝塔好了”。本次据此发布**当前已完成的HDF增量**，
不等待机身测试，也不将该授权写成设备通过。`hardware_verified=false`、实验版说明保留。

## 当前差距

最新 main 的 GR3/GR2 目录都展示46款，但有24个不同ID，不能按数量认定同步。
GR3为十槽/v5/184字节；GR2仍为五槽/v4/104字节。GR2普通胶卷当前仍经过CPU色彩处理，
尚不满足现行GR3保存照片走本机ISP的性能合同。画幅/蒙版、RAW降噪、水平仪、
开关机图等接口也未完成对齐。上述均保持研究中，没有认定底层无法实现。
精确目录对照位于忽略目录 `data/research/gr2/parity-20261028/catalog-gap.json`。
本次没有更改旧胶卷ID、五槽ABI、FILMS.M10协议或GR3/IIIx/IV的原生实现。

## 公开项目核对

- [FRAME-GR2](https://github.com/Lyle-xub/FRAME-GR2/tree/9d8eba85b4eb6058bfaff4f54d03b5aefbd80a5b)：
  当前公开树只有 README、功能文档和图示，没有固件实现源码或根许可证。
  可作为原生拟合/LUT、画幅等功能线索，不能视为可以直接复制的开源实现。
- [GR2 boot-screen mod](https://github.com/lc2425150/ricoh-gr2-boot-screen-mod/tree/d99b561620973c29e86c65ea74aa12f777f4edeb)：
  公开了解包/图像转换和TTL研究，明确说明真机验证和修改固件校验仍有边界。
  本次只读参考，没有执行第三方脚本或复制缺少授权的实现，也没有把TTL候选当作设备证据。

## 本次实际改变

| 层次 | 实现/边界 |
| --- | --- |
| 页面 | HDF开关与首次强度0–3，JSON导入、撤销重做、构建摘要复用既有状态流程；不是远程覆盖机内当前值 |
| API/构建 | 接受并规范化0–3，将值加入来源/配置绑定，编译宏GR2_HDF_INITIAL_STRENGTH和回读报告/receipt一致 |
| 独立存档 | 仅在两个名字确证缺失时采用编译值；有效旧记录先返回，损坏/错误/未知不初始化 |
| 首次非零强度 | 原池prepare_pool先于写档；准入失败零写入。已有有效档不因编译初值不同而覆盖 |
| 保持 | 默认0的原生runtime SHA仍为9aa7c2e1195046f6bc85a59bfa85507c62a6f797796d8f04d8a8a675b5f4e03d；其他机型源码和部署控制不变 |

测试：相关Python56 PASS（264.817s），重点Node4 PASS（10.487s）。全套Node351 PASS/
52 FAIL/14 SKIP；相同官方样本及路径别名的干净main基线350 PASS/52 FAIL/14 SKIP，
52个失败名称集合完全一致，无新增失败。名称及对照记录见
`docs/testing/gr2-hdf-initial-validation-20261028.json`，不把全套写成通过。
独立只读审查无可确认P1/P2；浏览器验证强度、撤销/重做及构建回读。

本地HDF强档r1候选SHA：`6bb0dc7b63834264da58730c7696175bc91ad6ac22bbc632b35397be535b06a0`。
独立封包回读通过，原GR2更新校验函数执行该候选完整载荷后接受checksum2338688830。
测试ZIP、官方输入、组件和运行体二进制保持忽略，不进入公开Git。
实机启动、HDF效果、RAW/JPEG、回放、连拍和恢复仍需有GR II的测试者验证。
