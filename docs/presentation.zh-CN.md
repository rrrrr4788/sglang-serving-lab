[English](presentation.md) | [简体中文](presentation.zh-CN.md)

# 项目展示与证据

## 产出

主要展示目标是快速部署，以及现有GPU池内的服务副本弹性。

部署带鉴权SGLang，选择TP2或独立TP1副本，经官方Gateway路由，在双GPU池内伸缩，
发布受限HTTPS，并从一次有界错误配置中恢复。真实证据来自双RTX A6000单节点VM，不是GPU集群。

| 本地日期 | 观察 | 来源和边界 |
| --- | --- | --- |
|2026-10-28|先TP2后双TP1，四请求归属2+2|[拓扑](reports/2026-10-28-real-gpu-topologies.md)，不证明TP加速|
|2026-10-28|mock伸缩24成功；指标故障→fallback2→恢复1|[Mock](reports/2026-10-28-mock-autoscaling.md)，仅CPU控制|
|2026-10-30|真实1→2→1、256个HTTP200、独立GPU、新副本接流、空闲GPU进程释放|[伸缩](reports/2026-10-30-real-gpu-autoscaling.md)，8 closed-loop/64输入/2048输出，不是容量/SLO证明|
|2026-10-30|可信TLS1.3、无/错key401、私有路径404/端口不可达、16token推理|[HTTPS](reports/2026-10-30-https-ingress.md)，单客户端，未测限流拒绝|
|2026-10-30|完整128token SSE、提前关闭、abort1、持续idle|[流式](reports/2026-10-30-stream-cancellation.md)，活动槽回收，不是VRAM池释放|
|2026-10-30|3500token在途完成、错误配置告警、回滚、resolved、16token恢复、KEDA恢复|[运维](reports/2026-10-30-operations-rollback.md)，观察238.37秒、计划503窗口，不是HA|
|实验后|用户确认VM销毁|首次提供方截图1.32小时/USD1.49；第二轮最终账单未独立核对|

原始JSONL私有保存，报告记录哈希。日期按America/Los_Angeles，部分文件名为次日UTC。
以上来源是原私有helper；后续公开参数化工具仅离线检查，不是新GPU运行验收。

## 工程决策

- TP共同计算模型，副本分流不同请求；Kubernetes整卡放置与SGLang token调度属于不同层。
- 创建副本不等于Ready，冷模型启动具有实际运维成本。
- 缺指标不等于零负载；本地fallback证据与真实负载伸缩不同。
- 无备用接流容量时单副本故障会停服，恢复流程验证归属、排空、通知和回滚。
- 取消释放活动任务，但预分配KV/cache显存可能保留。

## 边界与复现

未自动采购/加入GPU节点、未跨节点HA、无持续SLO或成本最优、无TP加速或多租户隔离证明。
限流拒绝、完整应用日志脱敏、证书续期/重启、云Grafana/DCGM、公网OpenAI请求格式未验证或不属本轮。
不承诺持续在线公网端点。

[架构](architecture.zh-CN.md) → [云端](cloud-rebuild.zh-CN.md) →
[验收](acceptance.zh-CN.md) → [HTTPS](https.zh-CN.md) → [运维](operations.zh-CN.md)。
历史报告是原始来源；两种展示语言保持相同事实与边界。
