[English](deployment.md) | [简体中文](deployment.zh-CN.md)

# 部署与操作

Compose要求Ubuntu/WSL2、Docker Compose2.30+、兼容NVIDIA GPU/驱动及Docker GPU支持。
先确认已有GPU/端口归属；首次下载模型/镜像需要网络和磁盘，不承诺固定显存门槛。
CPU kind是独立模拟环境，不运行真实LLM。

## Compose基线

```bash
git clone https://github.com/rrrrr4788/sglang-serving-lab.git
cd sglang-serving-lab
cp .env.example .env
# Edit .env and set separate, private random values for both required secrets.
# Generate each with: python3 -c 'import secrets; print(secrets.token_hex(32))'
chmod 600 .env
# Use hex secrets; the examples below load this private file as trusted shell input.
set -a; . ./.env; set +a
python3 scripts/validate.py
docker compose up -d --wait --wait-timeout 300
docker compose ps
python3 scripts/smoke.py
```

SGLANG_API_KEY与GRAFANA_ADMIN_PASSWORD使用不同随机私密值。加载完成后smoke检查无/错key拒绝并做一次小生成。端口仅loopback30000/9090/3001。Grafana自动配置SGLang Lab → SGLang Serving Overview，datasource UID为prometheus。看板改动进入版本化JSON；无流量分位数可能为空，显存面板是SGLang分配而非DCGM整卡利用率。

## 创建独立CPU kind集群

```bash
mkdir -p .private
kind create cluster \
  --name sglang-platform \
  --config deploy/kind/cluster.yaml \
  --image kindest/node:v1.36.1@sha256:3489c7674813ba5d8b1a9977baea8a6e553784dab7b84759d1014dbd78f7ebd5 \
  --kubeconfig .private/kubeconfig \
  --wait 180s
```

固定kind0.32.0/Kubernetes1.36.1拓扑是共享宿主的三个容器，不是独立物理机器/GPU。kubeconfig保持独立并忽略，不影响其他集群。使用kubectl1.36.1；云工具固定Helm3.22.1，不再使用旧Helm4要求。

## 核对节点Ready

```bash
kubectl --kubeconfig .private/kubeconfig --context kind-sglang-platform \
  wait --for=condition=Ready node --all --timeout=60s
kubectl --kubeconfig .private/kubeconfig --context kind-sglang-platform get nodes -o wide
```

## 命名空间与配额

```bash
kubectl --kubeconfig .private/kubeconfig --context kind-sglang-platform \
  -n sglang-platform apply -f deploy/kind/namespace.yaml
kubectl --kubeconfig .private/kubeconfig --context kind-sglang-platform \
  -n sglang-platform describe resourcequota local-budget
```

## 配置与操作

必需SGLANG_API_KEY和GRAFANA_ADMIN_PASSWORD；GRAFANA_ADMIN_USER默认admin，
MODEL_PATH默认Qwen/Qwen3-0.6B。引擎内部0.0.0.0服务Compose网络，宿主绑定仍为127.0.0.1。
固定版本豁免health/metrics鉴权，须保持私有。Compose本身无TLS、多租户隔离、入口限流或HA；
Docker管理员可查看env。

docker compose stop停止本项目，docker compose up -d --wait --wait-timeout 300恢复。
命名卷保留缓存/监控，删卷是独立破坏性操作。改Grafana密码env不会重置已有数据库。
编辑后运行scripts/validate.py；smoke须已有授权运行服务及导出的私有key。

CPU配额约束工作负载requests/limits，不限制kind容器或系统服务。
Mock/Gateway生命周期见[展示](presentation.zh-CN.md)。
保留证据后kind delete cluster --name sglang-platform仅删除对应实验；
已报告的本地验收未执行此删除。

## 云profile

按[云初始化](cloud-rebuild.zh-CN.md)、[HTTPS](https.zh-CN.md)及[验收](acceptance.zh-CN.md)执行。
要求NVIDIA RuntimeClass/device plugin、两张allocatable GPU、local-path及私有sglang-engine-auth Secret。
TP2、双TP1和autoscale都指向sglang-worker，须明确选一个；换profile前停流并终止旧profile。
Autoscale省略replicas交给HPA。不能apply整个目录。
单节点结果不证明TP性能、前后端独立凭据或节点/存储HA。
