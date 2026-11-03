# 周年 CPU 28 字节差异：RX 指令、版本回复与20字节数据

本轮只读四份已固定 SHA 的原厂包，在内存解码CPU，无BIN/ZIP输出、无CPU模拟执行、无Flash/相机访问。没有修改现有存储分析脚本、报告或候选构造器。证据JSON为`builds/anniversary-downgrade-followup-20261103/cpu-rx-delta-evidence-v1.json`。

## 先给结论

`CPU+0x5135`不是未分类数据，已确定为 **Renesas RX 版本getter的一条OR指令的立即数字节**。新固件运行时CPU版本的第三段固定为20；只把CPU头`+0x92`从20提升为21，并不能把这条运行报号变为21。当前内存研究构造的“CPU头提高一段、其余运行指令保留”因此存在明确的**声明版本与已定位运行getter不一致**。

`CPU+0x12b..0x13e`确定是被按数据读取的20字节区；其前4字节会随CPU版本查询回复发给DSP。它的生成算法、完整20字节的其他消费者和是否存在外部验证机制仍未确定。没有证据将它称为SHA-1、签名或绑定CPU头的摘要，亦没有证据证明更改CPU头后无需其他验证。

## 输入、架构与工具身份

输入身份沿用`gr3-downgrade-storage-2026-11-03.md`的四份精确原厂包：GR III 2.10/2.20、IIIx 1.60/1.70。每个CPU镜像均为`0x20000`字节，最后4字节为`00 00 fe ff`，按小端reset vector指向`0xfffe0000`。

该地址起始原字节为：

```text
fffe0000 fd7302300c0000   MVTC #0x00000c30, control-register18
fffe0007 fd730a300f0000   MVTC #0x00000f30, control-register26
fffe000e fbe2440afeff     MOV.L #0xfffe0a44, r14
fffe0014 fd68ec           MVTC r14, control-register28
fffe0017 052d8b00         BSR.A 0xfffe8b44
```

这组可变长指令、控制寄存器操作、分支与reset vector形成一致的RX入口证据；本轮使用RX解码器，未把它误作ARM或Renesas SH。

使用GNU binutils上游RX decoder源码构建限定范围只读解码器：

- [`opcodes/rx-decode.c`](https://raw.githubusercontent.com/RTEMS/sourceware-mirror-binutils-gdb/master/opcodes/rx-decode.c)，SHA `b91eccac0169ccf82fcb03ac218730fa23bcd476eae211ab26db9ffba4ddf24d`。
- [`include/opcode/rx.h`](https://raw.githubusercontent.com/RTEMS/sourceware-mirror-binutils-gdb/master/include/opcode/rx.h)，SHA `d71efde07b79636f6dce40b024dc4788221e2418618428dbabcb026ef11deeec`。

源码、最小编译头和读stdin的解码包装器在忽略目录`builds/anniversary-downgrade-followup-20261103/rx-tool/`。包装器读取131072字节stdin，只输出文本；没有把CPU保存为文件。源码SHA与先前`gr3-anniversary-version-unlock.md`记录一致。

## `0x5135`的确切语义

四份CPU中的getter在同一地址，入口`0xfffe512b`：

```text
fffe512b fbee9300fe    MOV.L  #0xfffe0093, r14
fffe5130 58e1          MOVU.B [r14], r1
fffe5132 763100XX      OR     #0xXX00, r1
fffe5136 02            RTS
```

| 镜像 | `0x5132..0x5135` | OR立即数 | 返回字 |
| --- | --- | --- | --- |
| GR III 2.10 | `76 31 00 15` | `0x1500` | `0x151b` |
| GR III 2.20 | `76 31 00 14` | `0x1400` | `0x141c` |
| IIIx 1.60 | `76 31 00 0b` | `0x0b00` | `0x0b11` |
| IIIx 1.70 | `76 31 00 14` | `0x1400` | `0x1412` |

该函数从Flash头只读取第四段`CPU+0x93`。第三段来自OR指令，不读取`CPU+0x92`。

另一个getter`0xfffe5121`读取Flash`0xfffe0091`，然后`0xfffe5128`执行BSET。GR III字节`78 91`置bit9，形成`0x02xx`；IIIx字节`78 81`置bit8，形成`0x01xx`。第一段因此也有机型代码常量来源，第二段读取头`+0x91`。

## 完整回复映射与研究构造的缺口

命令表`CPU+0x454`为`4e 00 00 00`，`+0x458`为处理器`0xfffe401b`。处理器的原始链为：

1. `0xfffe401d → 0xfffe5121`取得第一、二段；`0xfffe4021`右移8位；`0xfffe402a/402c`拆成两字节写RAM`0xa28+2/+3`。
2. `0xfffe402e → 0xfffe512b`取得第三、四段；`0xfffe403b`右移8位；`0xfffe4044/4046`拆成两字节写RAM`0xa28+4/+5`。
3. 后面还写`+6/+7`和20字节区前4字节至`+8..+11`，见下一节。

新版ARM接收端`0x53572570..0x535725c0`从回复对象分别取第0、第1个版本字，并在`0x535725b0`组合`word1 + (word0 << 16)`，随后提交CPU版本属性。该已定位路径没有从CPU头重新读取第三段，也没有在接收端把20改成21。

本轮按这些直线原指令语义做静态求值，四份官方CPU头与getter结果一致：

| 输入 | 官方CPU头 | 原指令getter结果 | 当前研究拟提高的CPU头 | 保留原指令后的getter |
| --- | --- | --- | --- | --- |
| GR III 2.20 | `02 14 14 1c` | `2.20.20.28` | `02 14 15 1c`（2.20.21.28） | **2.20.20.28** |
| IIIx 1.70 | `01 46 14 12` | `1.70.20.18` | `01 46 15 12`（1.70.21.18） | **1.70.20.18** |

这里“getter结果”是反汇编语义的静态求值，没有运行RX CPU或整机。精确指令、回复写址和头读取来源是确定的；因此当前内存构造器只修改CPU头第三段后，不能描述成CPU运行报号也提高了第三段。这个事实本身不证明会黑屏，也不能代替整条更新/启动验证。

组件包声明可分别研究，但不得混淆字段：既有原厂ARM证据的DSP外层字段为`+0x38`，CPU为`+0x50`。保留整个新版CPU、只提高DSP声明、继续使用组合footer kind2及RTOS版本分支补丁，是另一项尚待离线验证的研究假设；本轮没有构造该包、改变严格导入规则或给出安装许可。

## 20字节区的可证实用途

后续进展：独立的 `scripts/probe_gr3_anniversary_preserved_cpu.py` 已在内存中验证“官方 CPU 完整保留、DSP 包字段单独提高、footer kind2 保持”的受限模型。原厂局部门禁按独立 DSP/CPU 字段作比较；通用生产导入器仍按原规则拒绝该混合版本容器，未被修改。具体结果见 `gr3-anniversary-downgrade-followup-2026-11-03.md`。这不改变本报告关于真实 CPU 通信、写入和冷启动尚未验证的边界。

头部附近实际布局：

```text
CPU+0x100..0x129  FirmwareLoaderService_UpdateCpuDspFirmware
CPU+0x12a        00
CPU+0x12b..13e   20字节数据
CPU+0x13f        00
CPU+0x140        00 01 fe ff  （指针0xfffe0100）
```

旧两款20字节相同：`e0fa6b7cd97d3ac48861f0afa1afd27bf9869394`；新两款20字节相同：`af9e161465792721a2f23d5e930c2579c701df07`。

版本处理器存在明确的数据指针与读取：

```text
fffe403e fbe22b01feff  MOV.L #0xfffe012b, r14
fffe404b c4e608        MOV.B [r14],   8[r6]
fffe404e c5e60109      MOV.B 1[r14],  9[r6]
fffe4052 c5e6020a      MOV.B 2[r14], 10[r6]
fffe4056 c5e6030b      MOV.B 3[r14], 11[r6]
```

`r6`在`0xfffe4024`设为RAM回复缓冲`0xa28`。因此，该区至少含有一个**随版本回复导出的4字节标识前缀**。该已定位路径把它作为常量数据读取；本轮没有取得从该区取指执行的证据。紧邻ASCII服务名、长度恰20字节均不足以证明摘要算法。

对两款新版CPU逐字节搜索该20字节区每一个地址的24/32位小端直接地址编码，只找到指向起点`0xfffe012b`的这一处`CPU+0x4040`。这不覆盖指针运算、间接表和外部启动器，不能据此宣布其余16字节没有消费者或不存在验证。

两款机型的CPU头项目号/公开版本和版本getter的机型指令并不全相同，却共享同一20字节值。这至少阻止了把它未经验证就解释为“对未归一化整块CPU的常规摘要”。本轮没有找到它与CPU头`+0x90`之间的计算/比较链，不能为研究构造器省略任何未知真实性校验作保证。

## 复现与边界

下面的只读命令以现有精确输入加载器将CPU经stdin送给已固定SHA的RX decoder，未写CPU镜像：

```sh
.venv/bin/python - <<'PY'
import sys, subprocess
sys.path.insert(0, 'scripts')
from analyze_gr3_downgrade_storage import load
for label in ('gr3_old','gr3_new','gr3x_old','gr3x_new'):
    cpu = load(label)['sections']['CPU']
    assert len(cpu) == 0x20000
    assert cpu[-4:] == bytes.fromhex('0000feff')
    print(label, 'header', cpu[0x90:0x94].hex(), 'data20', cpu[0x12b:0x13f].hex())
    for start, end in ((0x401b,0x405d),(0x5121,0x5137)):
        print(subprocess.check_output([
            'builds/anniversary-downgrade-followup-20261103/rx-tool/read_rx',
            hex(start), hex(end)], input=cpu).decode())
PY
```

已执行四输入加载、reset vector与getter/回复拷贝指令preimage断言、限定RX反汇编及静态求值。JSON逐输入保留CPU SHA、头`0x80..0x17f`、三个限定反汇编范围和版本求值结果。没有完整CPU控制流证明，没有SHA/签名验真、RX执行、Flash写入、安装、冷启动或恢复验证。20字节区的完整语义仍为明确未解决项；`0x5135`及声明/运行版本差异已从未知项收窄为具体证据。

## 补充：RX CPU loader是否另设独立降级门禁

已进一步限定追踪命令`0x7f`到RX原始接收/编程路径，证据为`builds/anniversary-downgrade-followup-20261103/cpu-loader-admission-evidence-v1.json`（71642字节，SHA `7b74cf48dcab5df6e65159183db157c9cc413706ef3c0a5cef9c456dd310df35`）。下述五段代码在GR III旧/新、IIIx旧/新四份CPU中**完整逐字相同**，JSON包含各段SHA与限定反汇编。

| 已覆盖原范围 | 作用 |
| --- | --- |
| `0xfffe3de8..0xfffe3e04` | 命令参数setter及回调跳转 |
| `0xfffe36d0..0xfffe36e4` | loader复制到RAM |
| `0xfffe4d2b..0xfffe4f08` | 更新控制器、握手、模式派发 |
| `0xfffe4fc7..0xfffe5009` | CPU/DSP更新包装和RAM loader调用 |
| `0xfffe9a68..0xfffe9f12` | FCU辅助、原始收包/擦写、硬件IO |

准确链路为：

- `CPU+0x348`命令表原字为`7f000000 e83dfeff 013efeff`，对应setter`0xfffe3de8`及回调`0xfffe3e01`。setter只把请求缓冲RAM`0xa3c+2/+3`拷到状态RAM`0x2d8/+0x2d9`；回调直接跳`0xfffe4d2b`。这里没有传入四字节候选版本。
- 控制器`0xfffe4d5f→0xfffe36d0`将原地址`0xfffe9a68`起`0x4ab`字节复制到RAM`0xf30`。这解释了Flash写入代码在RAM执行的来源。原始入口`0xfffe9c53`复制后为RAM`0x111b`。
- 控制器`0xfffe4eda..0xfffe4ee9`对状态模式分支：模式0或3走`0xfffe4f09`，其他模式走`0xfffe4fc7`；后者在`0xfffe5001`调用RAM`0x111b`。原字节`0xfffe4ede:14`为B.EQ，`0xfffe4ee1:18`为B.NE；GNU RX条件定义为`RXC_eq=0`、`RXC_ne=1`。该CPU侧模式来自请求，不能把它未经追踪就等同于外层footer kind。
- 原始入口将块号和写入偏移初始化为0；`0xfffe9cc9..0xfffe9ce8`每次接收完整`0x400`字节到RAM`0x7800`，对收到字节累加；`0xfffe9d18`取累加低8位并在`0xfffe9d1a`发回发送方。它是传输块校验回复，不能当作全CPU镜像的真实性或版本校验。
- 随后的`0xfffe9d46..0xfffe9d8a`计算`0xfffe0000+offset .. 0xfffe03ff+offset`，依次调用擦除范围、编程范围和`0xfffe9b12`写入完整`0x400`字节；`0xfffe9d96`将偏移加`0x400`。收到第一块后并没有另走读取`RAM0x7800+0x90`与当前CPU版本比较的分支。

**限定结论**：在上述已枚举的`0x7f`参数/控制器/原始接收→编程链中，没有候选CPU头`+0x90`版本解析、与当前版本getter比较、项目号比较或全镜像32位加和检查；可见的是传输字节校验回复、握手及FCU状态处理。原先ARM侧`0x536291b8`的型号/magic/CPU加和校验与ARM版本gate仍是不同的已知层次，不能用RX块校验替代它们。

这项静态结果没有找到“新版CPU loader自己拒绝旧CPU版本”的独立比较器；它收窄了该特定疑问，不等于实际CPU loader已接受第二阶段。完整命令派发的运行状态、硬件握手/FCU、写后启动校验和恢复仍未执行；未知店内服务CPU亦不在四个固定输入内。因此不能把未见该比较分支扩大为所有启动器/服务固件不存在防回退机制。
