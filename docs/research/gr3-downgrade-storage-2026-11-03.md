# GR III / IIIx 降级的存储路径静态核对

范围为精确官方 GR III 2.20→2.10、IIIx 1.70→1.60。仅在内存解码四个已固定 SHA 的官方文件，逐字节比较并反汇编限定范围；未修改固件、未生成 BIN/ZIP、未执行 Flash/文件系统替身或设备操作。`installation_allowed=false`、`camera_verified=false`、`stable=false`、`bin_emitted=false`。本报告没有把 `0x5362c218` 称为完整分区解析成功；该入口的外层校验、解压和 decoded 加和与后续更新消费路径须区分。

## 输入与可复现输出

| 输入 | SHA-256 |
| --- | --- |
| `bin/fwdc239b-gr3-official.bin`，GR III 2.10 | `d6a3c9c288d784080e7b283222ecdd8752adfeed6faa36dab44f73115354bfd4` |
| `/Users/zhaoo/Desktop/fwdc239b.bin`，GR III 2.20 | `5c53760b3b564c87239dbf7f5c94d0f6fd91accd156ec4ba672ebfd6b861793e` |
| `bin/fwdc243b-gr3x-official.bin`，IIIx 1.60 | `708e79f3b7b96a7e1581b4acf4c412233050a1832718ef7f06c8397db1b431c7` |
| `/Users/zhaoo/Desktop/fwdc243b.bin`，IIIx 1.70 | `aa8e3ae1349d94e83be381c20530e41d5e57b75c27ef24ba81c7b017d6c11592` |

```sh
mkdir -p builds/anniversary-downgrade-followup-20261103
.venv/bin/python scripts/analyze_gr3_downgrade_storage.py --report builds/anniversary-downgrade-followup-20261103/storage-evidence-v1.json
```

已执行，退出码2表示获得离线部分证据，JSON约359KB；拒绝覆盖已有报告。报告保存四个输入身份、每分区 SHA、CPU 精确差异、UserData 比较表 SHA、格式化矩阵、32个分区容量及限定范围的原指令和 preimage。脚本不写固件数据。

## 分区布局未改变的具体证据

两组旧/新官方文件的 BOOTPARA、DRAMPARA、PARTPARA、M0、BOOT、LINUX、INITFS、ICONBIN、FDRVPARA 分别完整字节相同；RTOS、SRIC、CPU、SHELLCMD、RES不同。新版两机型的 `RTOS+0x628c94..0x62aa8c` 更新消费代码也完整相同。

PARTPARA 为516字节，SHA `e13eb1c08cd0ea660aad7dc6e51032f9fa92798f6436ada58e254b9ce41f3c85`。`0x53629a94` 用首字 `0x600` 作初始扇区，随后32×16字节记录生成运行表；记录含 AreaSize、LoadAddr、第三字、JumpAddr。`0x53629b48→0x537fb2f8` 将容量按设备扇区大小向上取整并累计起点。`0x537fb31c` 对已识别的默认接口采用512字节，其他接口会调用其真实 getter；下表为512字节假设下的派生值，不是机身分区读回。

| 分区索引 | 容量 | 起始扇区 | 加载地址 |
| --- | --- | --- | --- |
| 0 | `0x70000` | `0x600` | `0x50b00000` |
| 1 | `0x4000000` | `0x980` | `0x53000000` |
| 10 | `0x20000` | `0x118a80` | `0x50b82100` |
| 11 | `0x2d0000` | `0x118b80` | `0x50ba2100` |
| 12 | `0x30000` | `0x11a200` | `0x50e72100` |
| 13 | `0x200` | `0x11a380` | `0x50ea2100` |
| 14 | `0x210000` | `0x11a381` | `0x50ea2300` |
| 21..25 | 各`0x100000` | `0x121300..0x123300`，步长`0x800` | 0 |
| 26..30 | 各`0x20000` | `0x123b00..0x123f00`，步长`0x100` | 0 |

结论限于：这四份输入没有提供“周年更新改变分区参数/容量”的证据。相同布局不能证明旧代码能解释当前机身已有数据。

## DSP-only 与组合包的实际写入差别

`0x53628db0` 的类型跳表：0/1走DSP；2/3/4先CPU、成功后DSP；6只CPU。CPU失败时组合路径不进入DSP；CPU已经成功后再发生DSP失败，当前函数没有把CPU写回旧版的分支。未解析驱动内部是否另有恢复机制。

这里 DSP对象`+0x34`的值可以追溯到 footer kind，不能把它当作独立未知模式：`0x53628d74`取主对象`+0x2c`→`0x53628d8c`压栈→`0x53629a30`保存；组合入口`0x5362aa60..0x5362aa80`也把组合对象`+0x3c`传给同一 setter。因此，下述 `cmp ..., #2` 对应组合kind2，来源已追踪。

DSP `0x5362a5b0` 消费分区头的低16位 section kind：2（PARTPARA）建分区表；3记录M0；4经`0x53629e48→0x5362c91c→0x5362c7b8`写入分区（高16位为分区索引）；8（FDRVPARA）保存驱动参数；6（RES）经`0x53629f50`配置/格式化资源驱动，再调用`0x5362a314`写资源文件。这里的 section kind 与外层 footer kind 是不同字段。随后依次调用`0x53629c4c`写分区表、`0x53629cbc`写boot header、`0x53629db4`写M0，再更新版本/计数字段。原诊断字符串明确为 `write partition table`、`write boot header`、`write boot image`。

`0x5362c7b8`按设备扇区大小补齐最后一块；非整块分配临时缓冲、以`0xff`填充、复制源数据，最终通过存储对象 vtable `+0x28`写入。未替换该写入为成功，也未执行硬件回读。

新增且不能忽略的区别是**DSP-only 并非仅仅少刷一次CPU**。`0x53629f50`的格式化矩阵位于`0x53d3400c`，寻址是`base + drive_index*8 + footer_kind`；驱动名表`0x540516c8`依次为 J,A,B,E,F,G,H,I。矩阵中开启的驱动如下：

| footer kind | 进入格式化分支的驱动 |
| --- | --- |
| 0（DSP） | J,A,F,G,H,I |
| 1（DSP） | J,A,B,E,F,G,H,I |
| 2（组合） | J,A,G,H |
| 3（组合） | J,A,F,G,H,I |
| 4（组合） | J,A,B,E,F,G,H,I |

非J启用驱动在`0x5362a13c..0x5362a150`调用`0x5362d7a8`和`0x5362dfc8`；对应日志是`format resource drive`。J路径在`0x5362a1d4`按分区索引派发：10..14调用`0x5362c3f8`，21调用`0x536b9e8c`循环21..25，26调用`0x536c1c0c`循环26..30；后两组在kind2时跳过。`0x5362c3f8`为非零容量分区分配整区缓冲、填`0xff`，再通过 vtable `+0x28`覆盖对应区域；成功后清运行表DataSize/SectorNum。它不是只清RAM标记。

这些分支只有在相应 FDRVPARA 参数和 RES section 被消费、设备初始化及前置操作成功后才可达。它们是静态可达条件和原始数据矩阵，不是已经发生的格式化记录。DSP-only第一阶段跳过CPU Flash路径，却会进入kind2原本跳过的F/I及额外原始分区清空路径；不能仅凭省去CPU写入宣布更安全。

## 持久化 UserData 的新证据与限度

新版 `0x5324b35c` 附近的 UserDataModel 初始化从 DomainData 索引9/10取得已存名称/格式列表。在`0x5324b650..0x5324b668`循环比较`0x413`个32位字；不匹配会跳往`0x5324b74c`，传入日志 `Invalid user FwUp!!!!! Clear UserData`，随后存在释放读入表、构造默认UserData及复制到运行缓冲的路径。`0x536ba00c`本身为错误/诊断处理，不应冒称专用“清设置”函数；本轮没有运行错误分支或证明默认数据已写回存储。

最重要的收窄证据：四份输入**真正逐字比较的完整4172字节表相同**，SHA为`d17ff94346b67560bd7f10bedcfb3626f5d19438283a72b3c4c678c649a534a8`。

| 固件 | 比较循环入口 | LDR literal | 实际首个比较字 |
| --- | --- | --- | --- |
| 旧GR III/IIIx | `0x5324b578` | `0x5324b714`→`0x53b593a8` | `0x53b593ac` |
| 新GR III/IIIx | `0x5324b650` | `0x5324b7ec`→`0x53b58cd0` | `0x53b58cd4` |

这里 literal 指针会先加4再读取；报告刻意从`pointer+4`取4172字节，没有把前一字算进表。计数指令preimage为`135400e3`（`movw r5,#0x413`），循环核心preimage为`04c0b2e5013083e20400b1e500005ce1`。这意味着该**特定UserData格式等同性检查**没有因这两组周年更新而改变；不能继续笼统断言“新旧UserData格式完全未知”。但这张尺寸/布局比较表不证明各字段语义、默认值、其他domain、机内现有损坏数据或特殊服务版兼容。

DomainDataFactory构造器`0x53827f18..0x53827f30`从`0x54056460`格式化`F:\KB%ld.DOM`，另有`C:\KB%ld.DOM`路径。因此kind0/1额外格式化F，与已定位的domain数据文件驱动存在直接静态联系；尚未完整证明普通开机每一个domain的路径选择，不将两条证据直接升级为“kind0必定丢全部用户设置”。

`0x5362a558`在更新成功后向CommonProperty对象写`+0xf0`版本和`+0x100`加一计数。这是可见RAM字段写，未追到持久化提交，不能称已证明不可逆版本/防回退熔丝。`0x5362cc5c`另有 sector0偏移`0x30..33`写`0x5aa5a55a/ffffffff`，但诊断明确名为macro mode、尚无直接调用者，不把它错误命名成更新标记。

## CPU 28字节差异的确切范围

两款CPU都131072字节，分别只有28个不同字节，全部集中在：

- `0x7c..0x7f`：原已知大端加和补数。
- `0x91..0x93`：版本字段三个字节。
- `0x12b..0x13e`：20字节不透明区，两款同样从`e0fa6b7cd97d3ac48861f0afa1afd27bf9869394`变为`af9e161465792721a2f23d5e930c2579c701df07`。
- `0x5135`：GR III `15→14`，IIIx `0b→14`。

除此之外131044字节逐字相同。后续独立GNU RX解码已确认`0x5135`位于运行版本getter的 `OR #0x1400,r1` 常量；20字节区也有读取前4字节并返回的路径，但仍未证明它属于哪种签名/元数据。因此不能把CPU差异全部称作元数据或宣布CPU执行代码完全相同，详见 [CPU后续报告](gr3-cpu-anniversary-delta-2026-11-03.md)。

## 仍需解决的条件

后续在同一脚本加入独立的原厂 ARM 表比较循环：把对侧官方包的4172字节编译表作为合成输入，分别交给四份 RTOS 的原循环。16个场景中，4个完整相同表通过；首项、521号项、1042号末项各翻转1位的12个负例均进入原错误分支边界，末项负例实际比较到1043个字。执行在错误/默认路径之前停止，没有读取机身实际设置，没有执行默认值写回。`storage-evidence-v2.json` 为包含这些场景的后续输出；两个新增行为回归通过。真实设置文件及字段语义仍未被该表比较测试覆盖。

没有执行CPU通信Flash状态机、eMMC驱动vtable、格式化、写后回读、第一阶段/第二阶段冷启动或恢复。尚未确认所有domain持久化ABI及字段语义，也没有未知店内服务版身份。分区表相同和特定UserData表相同降低了两项具体未知范围，但没有消除真实写入顺序、格式化副作用与启动兼容的设备证据缺口。

已检查的原始更新调用链中没有获得OTP写入、熔丝烧录或单调防回退计数器提交的正面证据；也没有证明这些机制不存在。CommonProperty的RAM版本/计数、macro-mode扇区magic与CPU/Flash写入不能被合并成一个假想的防降级标记。驱动、CPU固件及未覆盖启动路径仍可能有额外持久化行为，本轮没有据此给出“可任意回退”的保证。
