[English](one-command.md) | [简体中文](one-command.zh-CN.md)

# 新 GPU VM 单命令部署

这是已实现的**单节点双GPU**架构统一入口，部署serving系统，不跑负载/故障实验，
也不创建GPU集群。入口及续跑逻辑已离线测试，**尚未在新GPU VM端到端执行完整命令**；
已有阶段和能力分别有[历史证据](presentation.zh-CN.md)。

## 前置条件

本地：Linux/WSL amd64、Python3.10+、OpenSSH、kubectl、SSH私钥。
远端：新的专用完整Ubuntu22.04/24.04 amd64 VM、systemd、免密sudo、恰好两张完整NVIDIA GPU、
可用580+驱动、nvidia-container-runtime、curl、UFW及足够网络/磁盘/内存。
仅Notebook/GPU容器或单卡不适配该profile；不安装驱动或采购资源。

脚本本地自动下载并校验Helm3.22.1、KEDA2.21.0、Traefik42.1.3，无需再手工准备。
已有缓存或二进制不匹配时拒绝覆盖。首次SSH须核对指纹并建立信任，不关闭host-key检查。
宿主80/443须空闲，DNS/CA/镜像仓库/模型下载须可达；不重启本地Docker或已有lab服务。

## 无副作用预览

```bash
python3 scripts/cloud/launch.py --host NEW_VM_IP --plan
```

预览不创建文件、不下载、不连接VM。真实launch会修改防火墙/K3s/应用，
开放HTTPS并发少量鉴权验收请求，不跑自动伸缩负载、流式取消或停服故障实验。

## 部署

NEW_VM_IP替换成当前VM。首次SSH有条件时按提供方核对指纹，退出远端会话后，
在本地运行第二条命令；脚本隐藏输入ACME联系邮箱。

```bash
ssh -i ~/.ssh/sglang_lab_ed25519 ubuntu@NEW_VM_IP
python3 scripts/cloud/launch.py --host NEW_VM_IP
```

默认域名为sglang-IP用横线连接.sslip.io，无需购买域名，但必须唯一解析到当前IPv4。
若使用自有A记录及非交互私有联系文件：

```bash
python3 scripts/cloud/launch.py --host NEW_VM_IP \
  --hostname inference.example.com --contact-file .private/acme-contact.json
```

私有overlay结构为：
```json
{"certificatesResolvers":{"le":{"acme":{"email":"YOUR_CONTACT_EMAIL"}}}}
```

签发时CA会收到邮箱，不要提交该overlay或ACME/TLS材料。
输入文件可选，默认本地隐藏提示。--user/--key/--ssh-port/--api-port可调整访问，
其余见--help。

## 自动顺序

1. 本地生成当前主机路由/私有0600邮箱配置，下载并校验工具。
2. 检查驱动/双GPU，配置UFW，安装固定K3s及NVIDIA集成。
3. 打开临时loopback API隧道，比对集群身份，以本轮owner标记专用项目namespace。
4. 部署私有Secret、TP1 worker、Gateway、Prometheus、Alertmanager/接收器和KEDA；
   不接管其他项目或已有无关KEDA namespace。
5. 内网鉴权/TP1/指标/16token preflight通过后，启用唯一HPA，min1/max2。
6. 安装Traefik、在SSH之外仅开放80/443，挂受限路由；API/后端保持私有，先验鉴权后开放入口。
7. 等待可信TLS、做外网鉴权/隔离/16token验收，要求Gateway、规则、伸缩器健康；
   给启动期间告警留出恢复时间。

成功后打印HTTPS地址。密钥只留.private/cloud-engine.key，不打印值。
临时API隧道结束；后续kubectl用cloud.py tunnel。域名/路径白名单及Gateway/worker
共用Secret的限制与[HTTPS](https.zh-CN.md)、[架构](architecture.zh-CN.md)一致。
Grafana仍是Compose看板，本入口不新增云Grafana/DCGM。

## 失败后继续

阶段记录在.private/deployments/VM_IP/state.json。失败不自动删除，资源仍可能计费。
修复提示的前置条件、最后阶段、DNS或连接后执行：

```bash
python3 scripts/cloud/launch.py --host NEW_VM_IP --resume
```

原命令有自定义hostname/SSH身份时须重复传入；--api-port可换成本地空闲端口。
续跑核对源码/配置哈希、私有HTTPS输入、chart/Helm缓存、集群UID、namespace UID与owner。
历史鉴权/TLS/服务通过不代表当前健康，会重新检查。每主机文件锁阻止并发执行。

只有本轮未完成的应用阶段可重放同一固定清单，已完成阶段跳过；
原独立cloud.py deploy仍拒绝重复覆盖。不是迁移/任意协调工具：
代码/配置不同、namespace归属不同、集群被换或IP复用都拒绝。
不要编辑/删除state来强行接管。未记录哈希前的局部生成失败可能留下私有临时目录供检查。

## 检查与释放

```bash
python3 scripts/check_repository.py
python3 -m unittest discover -s tests -v
```

测试模拟下载、SSH、K8s、续跑与失败，不使用付费主机，
不宣称此新入口已完成云端端到端验收。需要有界运行实验时另用[验收工具](acceptance.zh-CN.md)。

首次加载受冷下载影响很大，原20–40分钟是规划估算，不是新入口实测耗时。
保留证据后，在提供方明确销毁VM并确认状态。关脚本、隧道或Pod不停止计费。
不采购资源、不自动删VM、不保证HA，也不做节点扩容。
