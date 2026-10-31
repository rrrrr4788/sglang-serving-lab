[English](cloud-rebuild.md) | [简体中文](cloud-rebuild.zh-CN.md)

# 重建单节点 GPU 环境

整合入口见[单命令部署](one-command.zh-CN.md)。本页保留底层分阶段流程，不要对已有部署混用两条路径。

使用WSL/Linux、Python3.10+、OpenSSH、kubectl和**新的专用完整VM**。
要求Ubuntu22.04/24.04 amd64、systemd、免密sudo、恰好两张完整NVIDIA GPU、
可用580+驱动、nvidia-container-runtime、curl、UFW及足够磁盘/内存/下载能力。
仅GPU容器/Notebook不满足此路径；脚本不装驱动、不升级OS、不采购或销毁资源。

## 租用前准备

固定Helm3.22.1与KEDA2.21.0。逐条执行下载/校验，校验失败立即停下，成功后才解压。
私有工具下载是运行产物，不是缺少的私有源码。

```bash
mkdir -p .private/bin .private/vendor
curl -fL https://get.helm.sh/helm-v3.22.1-linux-amd64.tar.gz \
  -o .private/vendor/helm-v3.22.1-linux-amd64.tar.gz
printf '%s  %s\n' 896cf63684a42a723d61c980369d6e588330927deb13676ca0d85006dd6da0ea \
  .private/vendor/helm-v3.22.1-linux-amd64.tar.gz | sha256sum -c -
tar -xOf .private/vendor/helm-v3.22.1-linux-amd64.tar.gz linux-amd64/helm > .private/bin/helm
chmod 700 .private/bin/helm
curl -fL https://kedacore.github.io/charts/keda-2.21.0.tgz \
  -o .private/vendor/keda-2.21.0.tgz
printf '%s  %s\n' a7da56bf41a33dad9d2fc82a6fdecee552fff947d80bf1e1dbcf4db0f9e26dee \
  .private/vendor/keda-2.21.0.tgz | sha256sum -c -
```

填写新租主机，先建立SSH信任，有条件时通过提供方核对指纹；不关闭host-key检查。

```bash
export GPU_HOST='NEW_VM_IP'
ssh -i ~/.ssh/sglang_lab_ed25519 "ubuntu@$GPU_HOST" true
python3 scripts/cloud/cloud.py host --host "$GPU_HOST"
python3 scripts/cloud/cloud.py deploy --host "$GPU_HOST"
```

host检查前置条件，启用UFW前允许实际SSH端口，允许Pod10.42/16和Service10.43/16网络，
禁止公网6443；安装已校验的K3s v1.36.5+k3s1，先等Node创建再等Ready。
NVIDIA device-plugin v0.20.1须报告两张allocatable GPU。
归属标记允许安全复查，不重装/重启；发现无关K3s、任务或防火墙策略则拒绝。
--user/--key/--ssh-port/--api-port可改SSH/API默认设置。

deploy自建127.0.0.1临时隧道，通过SSH和隧道比对kube-system UID后，
才以0600备份/替换私有kubeconfig。端口占用、项目Deployment已存在或外部指标API已有归属时拒绝。
不改全局context；引擎key私下生成/复用并作为Secret发送，不打印。

依次创建namespace/PVC/Secret、operations规则/Alertmanager/接收器、一个TP1 worker、
Gateway/RBAC、Prometheus与KEDA，等待Ready及外部指标API可用。
**不启用ScaledObject**，不发布HTTPS，不发推理/负载；Ready须另验收。
不要apply整个deploy/k3s：多个worker文件互斥且指向同一Deployment。

## 单独终端继续

deploy完成/失败会关闭临时隧道。另开终端保持前台隧道：

```bash
python3 scripts/cloud/cloud.py tunnel --host "$GPU_HOST"
```

工作终端执行：

```bash
python3 scripts/acceptance/ready.py --host "$GPU_HOST" --run-inference
```

之后依[验收流程](acceptance.zh-CN.md)启用伸缩并跑有界负载，
按[HTTPS](https.zh-CN.md)开放入口，按[运维](operations.zh-CN.md)练习恢复。
worker-tp2.yaml为单Pod两GPU、禁用副本伸缩；worker-replicas.yaml为双TP1；
worker-autoscale.yaml不写replicas，让HPA管理。双GPU主机切换profile前停流并结束旧profile。
本地local-path RWO缓存不是存储HA。

## 失败、时间与释放

失败保留资源，无自动重试/切profile/卸载；重新deploy前检查部分初始化状态。
不分享kubeconfig、Secret、完整Pod参数或含凭据的启动日志。

可按首次模型Ready20–40分钟估算，主要冷下载；不是测得脚本耗时。
先保留本地证据，再在提供方明确销毁并确认；关隧道或缩为0不停止计费。

早期host/deploy及后续运行实验通过，见[展示/证据](presentation.zh-CN.md)；
operations扩展是后续单独安装。当前参数化工具和扩展后的完整初始化仅离线检查，
未在新GPU上端到端重跑。原VM均已报告销毁，不能复用旧地址。
