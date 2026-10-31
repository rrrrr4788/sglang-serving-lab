[English](README.md) | [简体中文](README.zh-CN.md)

# SGLang Serving Lab

可快速部署、支持GPU副本弹性的SGLang推理平台参考实现。
新专用双GPU VM通过统一入口配置，在线架构提供鉴权路由、监控和有边界的恢复。
保留单GPU Compose基线；定位工程展示作品，不承诺生产SLA，也不自动采购GPU节点。

## 已演示能力

- 固定SGLang0.5.21/Qwen3-0.6B、鉴权、Prometheus/Grafana、有界队列/客户端。
- 双A6000单节点K3s，先单TP2后双TP1，并确认路由归属。
- 真实1→2→1、256个HTTP200、独立GPU、新副本接流、空闲进程释放。
- 可信HTTPS、无/错key拒绝、管理路径/端口私有。
- 完整128token SSE、取消后abort信号及持续idle。
- 3500token在途完成、错误配置告警、回滚、resolved、推理及KEDA恢复，有计划停服。

见[双语展示/证据](docs/presentation.zh-CN.md)与[已实现架构](docs/architecture.zh-CN.md)。
原VM均已报告销毁，不承诺持续在线demo。公开参数化工具仅离线检查，未在新GPU上重跑。

客户端→Traefik→官方Gateway→worker。Prometheus驱动KEDA唯一HPA及Alertmanager私有接收器。
云验收控制面和GPU共置单VM，不证明采购节点、HA、无中断更新、容量/SLO收益、多节点TP或租户隔离。

## 启动本地单GPU基线

要求Ubuntu/WSL2、Docker Compose2.30+、兼容NVIDIA GPU/驱动及Docker GPU支持。
先确认资源/端口归属，阅读[部署说明](docs/deployment.zh-CN.md)。

```bash
git clone https://github.com/rrrrr4788/sglang-serving-lab.git
cd sglang-serving-lab
cp .env.example .env
# Set distinct private SGLANG_API_KEY and GRAFANA_ADMIN_PASSWORD values in .env.
# Generate each with: python3 -c 'import secrets; print(secrets.token_hex(32))'
chmod 600 .env
set -a; . ./.env; set +a
python3 scripts/validate.py
docker compose up -d --wait --wait-timeout 300
python3 scripts/smoke.py
```

端口仅绑定127.0.0.1：推理30000、Prometheus9090、Grafana3001。
Grafana自动配置SGLang Lab → SGLang Serving Overview；凭据/缓存私有。
云初始化可能比本地快速启动慢得多。

## 单命令云部署

首次建立SSH信任后，一个入口部署固定单节点双GPU架构：隐藏输入ACME邮箱、小请求验收并启用min1/max2副本伸缩。--resume仅续跑同一归属环境。新整合入口已离线测试，未在新GPU实跑。

```bash
python3 scripts/cloud/launch.py --host NEW_VM_IP
```

[前置条件、预览与续跑](docs/one-command.zh-CN.md)。

## 复现云端路径

[初始化新专用双GPU VM](docs/cloud-rebuild.zh-CN.md) →
[Preflight和有界伸缩](docs/acceptance.zh-CN.md) →
[HTTPS](docs/https.zh-CN.md) → [流式与恢复](docs/operations.zh-CN.md)。
之后保存证据并在提供方明确销毁VM。阶段由操作者执行，不采购节点或自动销毁。
不要apply整个deploy/k3s目录。

## 离线检查

```bash
python3 scripts/check_repository.py
python3 -m unittest discover -s tests -v
python3 scripts/cloud/cloud.py --help
python3 scripts/acceptance/operations.py --help
```

检查覆盖仅公开文件CLI、目标/DNS保护、SSE解析、私有配置生成和恢复回放，不重跑云服务。

## 文件与文档

deploy/kind和services/mock-worker用于CPU模拟；deploy/k3s包含固定云profile、
路由、伸缩、入口和告警。scripts/cloud用于初始化/HTTPS生成，scripts/acceptance含公开有界工具/payload。
monitoring含Compose看板，tests含离线检查，docs/reports保留历史证据。

[文档](docs/README.zh-CN.md) · [路线](docs/platform-roadmap.zh-CN.md) ·
[双语规范](docs/documentation.zh-CN.md)。
展示/操作文档有英文与简体中文版本；历史报告保留原始语言，通过双语摘要统一展示。
API key、kubeconfig、ACME材料和个人笔记不进Git。
