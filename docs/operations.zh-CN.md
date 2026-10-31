[English](operations.md) | [简体中文](operations.zh-CN.md)

# 告警、排空与配置回滚

一次真实GPU演练已通过，见[报告](reports/2026-10-30-operations-rollback.md)。
后续公开工具通过离线恢复回放，未在新GPU上重跑。

## 安装与检查

新云初始化包含operations。已有部署先创建规则ConfigMap，再更新会挂载它的Prometheus。
保持隧道，GPU_HOST为当前VM：

```bash
kubectl --kubeconfig .private/cloud-kubeconfig --context k3s-sglang-platform \
  -n sglang-platform apply -k deploy/k3s/operations
kubectl --kubeconfig .private/cloud-kubeconfig --context k3s-sglang-platform \
  -n sglang-platform rollout status deployment/sglang-alertmanager --timeout=180s
kubectl --kubeconfig .private/cloud-kubeconfig --context k3s-sglang-platform \
  -n sglang-platform rollout status deployment/sglang-alert-receiver --timeout=180s
kubectl --kubeconfig .private/cloud-kubeconfig --context k3s-sglang-platform \
  -n sglang-platform apply -f deploy/k3s/prometheus.yaml
kubectl --kubeconfig .private/cloud-kubeconfig --context k3s-sglang-platform \
  -n sglang-platform rollout status deployment/sglang-prometheus --timeout=180s
python3 scripts/acceptance/ready.py --host "$GPU_HOST" --snapshot-only
```

Prom换Pod重置emptyDir历史，不影响本地证据。基线为Gateway200/单健康URL、
规则inactive/ok、Alertmanager200、KEDA Ready/无fallback；首次投递前events为空正常。

SGLangNoReadyWorker每5秒计算，连续15秒没有采集确认的Ready worker即触发。
**此告警**把缺指标视为不健康，伸缩器不将其视为零负载。发现/采集失败也能触发，
应结合Pod、发布、事件和指标排障。Prometheus→Alertmanager→私有ClusterIP接收器投递
firing/resolved，初始分组等待5秒。只在内存保留选定字段/128事件，重启丢历史。
不宣称邮箱/聊天投递、持久事件管理或NetworkPolicy隔离。

## 计划停服

要求[HTTPS](https.zh-CN.md)、一个Ready TP1 worker、健康告警基线和启用的ScaledObject，
没有其他流量/并发操作者。maxSurge0/maxUnavailable1会**暂时移除全部接流容量**，
恢复期间新请求应503。

```bash
python3 scripts/acceptance/operations.py --host "$GPU_HOST" \
  --base-url "$INFERENCE_URL" --run-maintenance
```

脚本保存原revision/template及恢复记录，带owner暂停KEDA为1，发起3500token流，
发布无效CLI而不换镜像；需观察旧health503/running1后原流完整完成、新实例启动失败、
真实firing、公网503。再恢复原revision，检查新UID/Gateway/resolved/16token推理，
移除本轮暂停。沿用180秒grace与SGLang0.5.21正常SIGTERM排空。

本项证明计划停服下有界正常终止/配置故障，不是换镜像、硬崩溃、HA或无错误更新。
空闲HPA缩容是另一项证据，本轮未直接触发有在途流量的HPA缩容。

## 恢复与释放

.private/evidence保存recovery-<UTC>.json和operations-<UTC>.jsonl。
发命令前记录可能变更，丢回执仍清理；外来owner/template会阻止覆盖。
中断后先核对恢复记录及归属再重试。对确认属于本轮的变更，使用**捕获的原revision**：

```bash
kubectl --kubeconfig .private/cloud-kubeconfig --context k3s-sglang-platform \
  -n sglang-platform rollout undo deployment/sglang-worker --to-revision=CAPTURED_REVISION
kubectl --kubeconfig .private/cloud-kubeconfig --context k3s-sglang-platform \
  -n sglang-platform rollout status deployment/sglang-worker --timeout=1200s
```

确认Ready Pod/Gateway及推理后，才移除本轮annotation：
autoscaling.keda.sh/paused-replicas及sglang.lab/ops-run。不得解别人的暂停。
恢复失败保留暂停；即使恢复成功，证据不完整仍FAIL。

历史238.37秒不是SLO；规则语法、离线回放、实际firing/resolved已通过，没有另跑amtool。
用户确认VM销毁，最终账单未独立核对。关闭隧道/Pod不停止计费：
保留证据，再在提供方明确销毁VM并确认状态。
