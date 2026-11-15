# GR III 开关机图片：实现与证据边界

当前实现针对完整 SHA-256 锁定的 GR III Street 2.10 官方 BIN。GR IIIx、GR IV 和 GR II 未启用此替换器。

网页「影像方案」支持分别上传开机和关机图片、缩放和移动 3:2 裁切、应用裁切后的最终压缩预览、分别恢复原厂默认。配置随原生胶卷工作台的同一个 BIN 导出；图片参与配置哈希，改图后必须重新预检。恢复默认表示下次由官方原包重新构建时省略对应补丁，不会远程更改已经刷入的相机。

## 两个独立资源

|用途|原生资源|固定容量|RTOS 路径地址|描述符|JPEG 请求|
|---|---|---:|---|---|---|
|开机|`B:\Resource\Jpeg\StartUp.jpg`|16,687 bytes|`0x53b22adc`|`0x53b5f520`|1|
|关机|`B:\Resource\Jpeg\GB_Diary.jpg`|112,509 bytes|`0x53b2298c`|`0x53b5f508`|2、3、10、11、12 共用该描述符|

两个描述符均为 `{u16 width=720, u16 height=480, u32 path}`。JPEG table 的装载地址是 `0x5407e0bc`（request 1 对应的槽），经启动初始化数据复制后在 RAM 中使用。原生 renderer 的锚点是 `0x55002b78`，request 0 为 LcdAdj，request 1 为 StartUp。关机补丁仅将 request 2、3、10、11、12 指向 Diary；**不更改 request 1**。

正常 type-2 更新器跳过 B-drive RES 记录，因此每个选中资源必须同时把 RES 记录名和 RTOS 字符串中的盘符改成 `A:`。只替换 B: 中的 JPEG 不构成可安装的资源替换。Darkslide 的四 request 别名不含 Street 的 Collabo 请求 3；本实现通过关机入口 `0x5319f270: mov r7,#3` 独立确认并覆盖第五种请求。分区参数、资源数量、各资源长度、RTOS 和总解码长度保持不变。此路径参考 Darkslide 的 `shared_shutdown.py`、`a_shutdown.py`；坐标和前像由本仓库官方样本重新校验，未使用 GR II BRP 地址。

## JPEG 和导出验证

浏览器先输出裁切后的 720×480 JPEG。服务端 Pillow 完整解码，确定性编码为 baseline JPEG、4:2:2，逐步降低质量直到固定槽能容纳；使用 JPEG comment segments 填满容量，EOI 位于最后两字节。然后再次完整熵解码。开机槽较小，复杂图片会显著降低质量；网页展示的是服务端最终压缩预览。

图片变换按输入哈希、容量与编码器脚本哈希缓存，缓存最多八项；预览、预检与构建使用相同结果。完整导出在已有原生构建结果上施加等长补丁，重新封装帧、修复内外层校验和，再从新 BIN 独立解码，逐字节验证预定目标及全部非目标间隙。回执包含最终 BIN 哈希、图片 JPEG 哈希和 `camera_tested:false`。

## 开机显示调用图仍未闭环

原生 `StartUp.jpg`、720×480 描述符与 request 1 已确认。当前静态分析找到的 JPEG renderer `0x5322e4a8` 直接调用如下：

```text
0x5319f234 → renderer(r1 = 2/3/10/11/12)  关机选择
0x531aae5c → renderer(r1 = 0)           LcdAdj
0x531da74c → renderer(r1 = 4/5/6/7/8/9) 键盘资源
request 1 → StartUp 描述符             尚未确认正常开机调用者
```

在官方 RTOS 中未找到 renderer 函数地址的直接数据指针引用。以上不排除通过其他入口或参数间接调用，但也不能证明每次正常开机都会显示这张图片。本实现提供**已离线验证的开机原生资源替换**，没有增加猜测的开机 hook、延时或显示调用；`startup.display_verified` 明确为 `false`。关机的相机显示和 A: 安装也仍需实机验收。

运行 `python3 scripts/analyze_gr3_startup.py` 可对锁定 RTOS 重现路径、描述符、table、renderer 指令前像和全部直接调用者检查。运行 `node --test node/gr3-power-images.test.mjs node/gr3-power-images-http.test.mjs` 验证独立图片、默认恢复、错误输入、HTTP 配置绑定与统一导出。

## GR III 2.10 机内关机图相册

「开关机画面」可加入 1 至 3 张 720 × 480 JPEG。固件设置菜单显示「关机图」，提供「原厂画面」和已写入的图片。选项通过两份带校验的相机 AppData 记录保存，关机渲染只读取内存里的已确认选项。调试固件在保存成功后记录事件 `140`，含选择编号与存档序号。

相册使用私有请求 13–15。原厂请求 2、3、10、11、12 继续指向 B 盘原有资源，自选图作为对应 A 盘资源写入。撕纸叠映在构建时共用字节完全相同的 ISP 曲线行，五组曲线展开后的系数和掩模保持原样。三张关机图、撕纸叠映与纯 ISP 已在同一份 GR III 2.10 调试 BIN 中构建并回读。该 BIN 通过 23 项撕纸叠映 ARM 回归及 RAW ISP 显影入口回归。相册请求透传、三张图和越界回退已有 ARM 仿真覆盖。r2 修复了关机图和边框共用菜单路由的问题。用户确认 GR III 2.10 修正版测试通过。
