# M10V 本地安全核查工具

下列检测和研究脚本只读检查，不写 SD、不控制相机。另有独立网页二阶降级构建器，可生成完整两阶段ZIP；普通2.10/1.60生成链保持不变。源码不包含官方固件、相机照片、配置、虚拟环境或密钥。本次开发基线为 GitHub main `711ce5163ef2eb5ba690c1abdfadbd8a94529c43`，是否已部署以官网更新日志和确切提交为准。

## 1. 核验官方原包

无需编译器即可用 Python 运行基础身份检查。可用 Node 时加 `--repo` 执行严格解码。把路径替换为自己保存的文件和源码目录：

```sh
python3 skills/m10v-firmware-safety/scripts/verify_source.py /path/to/official.bin --model gr3 --repo /path/to/m10v
```

GR IIIx 使用 `--model gr3x`。只允许精确官方 2.10 / 1.60 作为构建来源；识别到官方 2.20 / 1.70 也会以退出码 2 拒绝使用。不能用这个原包检查器验证已修改的候选。

## 2. 检查 M10V 候选

要求 Node 20+、候选对应的已审查源码与原构建工具、完整回执、独立保存的下载 SHA-256，以及确切官方基线。现有构建链会使用 Python/LLVM 和相关验证库；缺少依赖时停止，不绕过。官方基线放到项目约定的 `bin/fwdc239b-gr3-official.bin` / `bin/fwdc243b-gr3x-official.bin`；它们不随源码包分发。

```sh
node scripts/check_gr3_flash_safety.mjs --help

node scripts/check_gr3_flash_safety.mjs \
  --source /path/to/official-2.10.bin \
  --candidate /path/to/candidate/fwdc239b.bin \
  --receipt /path/to/candidate/M10V-build-receipt.json \
  --expected-sha256 REPLACE_WITH_INDEPENDENT_DOWNLOAD_SHA256 \
  --model gr3 --camera-version 2.10 --camera-origin official
```

IIIx 使用对应 1.60、`--model gr3x` 和 `fwdc243b.bin`。如果机身已经装的是 M10V，只有此前确实实测过且保留原包 SHA 记录时，才填写 `--camera-origin m10v-verified --installed-sha256 PREVIOUS_INSTALLED_BIN_SHA256`。这些仍是人的声明，并没有从相机读取内容；不应为了通过检查把未知/第三方来源写成官方来源。

检查会严格解码候选，再按回执配置重建，要求整个 BIN 逐字节一致。临时编译/缓存不修改输入文件，也不导出新的候选。未知版本、第三方机身固件、缺少完整回执、与当前源码不符的历史候选、版本伪装、摘要或字节不同均拒绝。未知固件不能通用叠加 patch。

退出码 1 是拒绝/错误；2 是离线一致但仍未通过设备验证。`installation_allowed` 始终为 false，没有“保证安全、可以刷入”的成功码。整个重建通过也不能验证机内持久化设置、供电、SD 健康、完整启动或硬件恢复。

## 3. 研究新的二阶降级思路

该探针仅执行真实原厂更新器的局部门禁和 CPU 校验。需要安装 Unicorn 和 Capstone 的 Python 环境及 Node。以当前项目已经使用的 `.venv/bin/python` 为例：

```sh
.venv/bin/python scripts/probe_gr3_anniversary_downgrade.py \
  --new /path/to/official-2.20.bin \
  --old /path/to/official-2.10.bin --model gr3
```

IIIx 可对照 1.70 / 1.60，使用 `--model gr3x`。可加 `--report /path/to/new-report.json` 写出新的 JSON 报告，已有文件不覆盖；不接受 BIN 输出。探针通过仍退出 2，代表安装被阻断。

研究思路是先保留新版官方运行代码，只修改最少的版本元数据和一条拒绝分支，再由该更新器接受精确旧官方包。探针在内存里使用合成包字段，没有完整更新 BIN，没有模拟 Flash 写入、完整启动或机内设置迁移。不是救砖程序，不能用于 MENU/回放启动均不可用的故障机，也不能证明店内服务固件适用。

旧 2.10.22.27 两阶段包曾有特定服务固件下的成功反馈；其包版本低于公开 2.20，因此不能直接用于这次公开版本降级。现有历史文档也包含其他安装失败反馈，必须绑定具体包和机身，不能把某一次成功扩展为通用安全保证。

## 当前交付状态

来源和候选检测器、独立二阶构建器及网页下载链均已完成文件级本地验证。用户明确授权先上线、上线后实机验证；本次同时交付新版真实工作台、严格校验、队列和二阶入口。二阶页面为 `/gr3/downgrade.html`，分别生成 GR III 2.20→2.10 / IIIx1.70→1.60 两阶段套件及回执。真实安全结论仍需专用设备验证，正常2.10/1.60机身不需要降级。当前实现见 `docs/research/gr3-anniversary-delivery-builder-2026-11-03.md`；早期 `combined-release-readiness-20261103.md` 为交付实现前的缺口快照。

## 网页集成候选

网页已在本地加入严格校验和任务队列。正常准备好两个约定官方基线及原构建工具后，可在源码根目录运行 `npm start` 打开本地工作台。默认一个执行线程运行、最多4项排队；每个任务包括完整生成和第二次完整重建。页面支持进度和取消，首次/再次下载均验证实际文件 SHA-256。

普通生成仍要求匹配的2.10/1.60机身声明；2.20/1.70使用独立二阶入口，不叠加胶卷或其他作者的修改包。机身来源不明确、第三方固件和普通入口抬版本继续拒绝。生成与二阶套件都在统一队列中执行完整重建，浏览器再次核对实际下载摘要。结果仍仅为文件级验证，不能替代相机验收。普通链实现与前序回归见 `docs/testing/web-firmware-safety-queue-20261103.md`；旧研究记录不代表当前完整交付状态。

## 后续二阶研究：保留 CPU 与组合更新类型

已确认早期“只提高 CPU 头第三段”的假设不会同步提高 RX 运行 getter。当前离线研究保留官方 CPU 的全部字节，保留原组合 `kind2`，分别核对 DSP/CPU 准入；没有调整生产导入规则。下面只生成新的 JSON 研究记录，不生成降级包：

```sh
.venv/bin/python -m scripts.probe_gr3_anniversary_preserved_cpu \
  --new /path/to/official-2.20.bin --old /path/to/official-2.10.bin --model gr3 \
  --report /path/to/new-preserved-cpu-report.json
```

IIIx 对照使用精确 1.70 / 1.60 和 `--model gr3x`。该混合 DSP/CPU 版本内存模型被当前通用生产导入器拒绝是预期结果；不能据研究局部门禁通过去删除或绕过该门禁。

`scripts/probe_gr3_anniversary_decompress_contract.py` 只执行原解压驱动配置前缀并在真实硬件等待前停止，不合成完成中断或解压成功。`scripts/analyze_gr3_downgrade_storage.py` 对比四份官方分区与设置结构表，并执行有限的表比较循环，不执行 Flash/文件系统。不能把减少 CPU 改动或切换包类型等同于安全；DSP-only 类型可能比原 kind2 多进入设置相关格式化路径。详细证据见 `docs/research/gr3-anniversary-downgrade-followup-2026-11-03.md`。

## 后续二阶研究：派发失败分支与旧官方 CPU 准备

```sh
.venv/bin/python -m scripts.probe_gr3_anniversary_dispatch \
  --new /path/to/official-2.20.bin --old /path/to/official-2.10.bin --model gr3 \
  --report /path/to/new-dispatch-report.json
```

IIIx 使用精确1.70/1.60和 `--model gr3x`。脚本只输出新JSON，退出2表示仍未通过设备验收。原路由执行到写入函数入口即停止，或只注入CPU失败返回0；不模拟写入成功。另在显式提供的解码RAM中执行原CPU提取/校验/标志设置，以及512字节设备类假设下的原分区表RAM构造。它不执行完整解压、CPU通信、存储写入或相机启动。已确认CPU标志来自内容校验，不能将“保留同版本CPU”当作“不会刷写CPU”。详见 `docs/research/gr3-anniversary-dispatch-2026-11-03.md`。
