# 推送 main 后自动部署宝塔

当前生产入口为 GitHub Actions [Deploy Baota](https://github.com/zhaoo/m10v/actions/workflows/deploy-baota.yml)。只响应 main 推送，可手动 Run workflow 重试；develop 不会重复发布。并发任务按顺序执行。

Actions 先运行部署保护测试，再创建相对已确认成功上线版本 725e2bf15f7e01caa4f26ffaaa48d41c068d2f74 的 Git bundle，通过受限 SSH 传入服务器；服务器无需拉取 GitHub。发送前及接收端均检查24 MiB上限，基线只能推进至有DEPLOY_OK证据的生产提交。远端核验 bundle 前置对象、完整目标 SHA 和 fast-forward 关系，然后以 www 构建完整 GR III 组合包，并实际构建 GR IIIx 全功能候选，独立核验 IIIx 型号与完整 CPU 保留，以 www 运行 GR IV 全功能构建与独立封包回读（需要 clang、llvm、lld 和官方 GR IV BIN），再重启 m10v 并检查健康状态。只有本次 SHA 的 DEPLOY_OK 返回后，Actions 才显示绿色。构建或健康检查失败会尝试回退。

专用公钥在 root authorized_keys 中使用 restrict 和固定 command；拒绝交互 shell、PTY、端口转发、agent 转发及任意远端命令，仅接受 `deploy <40位SHA>`。新服务器为 Ubuntu 24.04（47.96.158.25）；目标地址由仓库变量 `M10V_DEPLOY_HOST` 指定。私钥存储于仓库 Actions Secret `M10V_DEPLOY_SSH_KEY`，不写入 Git。服务器 Ed25519 指纹通过用户提供的 Workbench 终端指纹核对，固定于仓库变量 `M10V_DEPLOY_KNOWN_HOSTS`，SSH 严格验证。

服务器入口 `/usr/local/lib/m10v-deploy/receive-ssh.sh` 与 update-server.sh 均由 root 持有；日志 `/var/log/m10v-deploy-ssh.log`。站点服务仍由 www 运行，监听 loopback 3000；未新增公网端口。增量包上限 24 MiB，超限明确失败。

常规业务推送无需重新配置。修改受控入口脚本后，应在服务器核验并安装相应文件。停用自动发布：在 GitHub 禁用 Deploy Baota 工作流；撤销服务器访问：从 root authorized_keys 移除注释为 m10v-github-actions-20261015 的专用公钥。

HTTPS Webhook 方案因 GitHub Actions 到本站 TLS 连接重置暂不启用，原生 Webhook 和 m10v-deploy 接收服务均应保持停用。历史实现见 WEBHOOK.md，不是当前生产入口。

### 发布构建资源隔离

服务器仅约 1.6 GiB 可用物理内存；Node 的 `--max-old-space-size` 不限制固件 Buffer、Python 或 clang。每个机型现在在独立 systemd transient service 内顺序执行：`MemoryHigh=600M`、`MemoryMax=700M`、`MemorySwapMax=384M`、`CPUQuota=100%`、`TasksMax=64`、`RuntimeMaxSec=600`。600 MiB 以上先回收内存，700 MiB 为构建物理内存硬限；有限交换空间缓冲固件封包峰值，给主机与服务保留更多物理内存。2026-10-20 两次 GR III 构建期间 SSH 失联，失联前全机 available 最低约 73 MiB，尚未取得内核 OOM 证据，因此不将内存压力写成唯一根因。OOM 或超时终止整个控制组；SSH 中断也显式停止当前单元并回滚。Actions 总窗口为 35 分钟，以覆盖三个各 10 分钟的阶段。不要通过取消三机型检查或无限扩大交换来绕过失败。

2026-10-20 第三次尝试拿到内核 `global_oom` 记录：网站服务与发布构建的 Python 进程先后被杀，构建峰值约 626.5 MiB、swap 峰值仍为 0。主机 `/etc/sysctl.conf` 将 `vm.swappiness` 设为 0；已备份该配置并改为 60，同时用 `sysctl -w vm.swappiness=60` 生效。1 GiB swap 仍保留原大小，不无限扩容。重新建机时核对 `sysctl vm.swappiness` 和 `swapon --show`，不要把“已配置 swap”当作它正在参与回收的证据。

查看 `FIRMWARE_BUILD_START` 对应 unit 的 `journalctl -u UNIT` 和 `systemctl show UNIT -p MemoryPeak -p Result`；成功仍必须以确切 SHA 的 `DEPLOY_OK` 为准。修改脚本后先通过既有管理员连接更新 `/usr/local/lib/m10v-deploy/update-server.sh` 的 root 拷贝并校验摘要。

GR IV 重打包的校验和按 64 KiB 分块计算；已核验的来源解码、重放缓冲在独立回读前释放。`tests.test_gr4_codec_memory` 对校验和额外分配设定回归预算，避免重新引入整幅固件复制。900 MiB 限制保持不变。
