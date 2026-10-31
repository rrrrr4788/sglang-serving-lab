[English](acceptance.md) | [简体中文](acceptance.zh-CN.md)

# 公开验收工具

Python3.10+标准库工具，在WSL/Linux仓库根目录执行，要求已授权的当前专用VM及API隧道。
不依赖私有lab源码；key、kubeconfig、生成配置与证据继续忽略。
工具不采购节点、不删除VM、不自动启用ScaledObject。

每个工具必传--host。Kubeconfig/context/namespace显式指定，节点地址须匹配传入IPv4。
外部检查还要可信HTTPS根地址--base-url，DNS须唯一匹配主机。namespace固定sglang-platform。
默认只有项目context及私有key/kubeconfig，没有默认主机。--help列出
--context/--kubeconfig/--node/--key-file/--evidence-dir；
证据须在.private内，key权限须0600。

先初始化并通过preflight，再启用伸缩；外部/流式检查前先完成[HTTPS](https.zh-CN.md)：

```bash
export GPU_HOST='NEW_VM_IP'
export INFERENCE_URL='https://CURRENT_HOSTNAME'
python3 scripts/acceptance/ready.py --host "$GPU_HOST" --run-inference
kubectl --kubeconfig .private/cloud-kubeconfig --context k3s-sglang-platform \
  -n sglang-platform apply -f deploy/k3s/sglang-scaledobject.yaml
python3 scripts/acceptance/autoscaling.py --host "$GPU_HOST" --run-load
python3 scripts/acceptance/https.py --host "$GPU_HOST" \
  --base-url "$INFERENCE_URL" --run-inference
python3 scripts/acceptance/stream_cancel.py --host "$GPU_HOST" \
  --base-url "$INFERENCE_URL" --run-inference
python3 scripts/acceptance/ready.py --host "$GPU_HOST" --snapshot-only
```

| 工具 | 上限与解释 |
| --- | --- |
| ready --run-inference | 鉴权拒绝、TP1/DP1、Gateway、16token生成、一个空闲守卫指标 |
| autoscaling --run-load | 8个closed-loop客户端，最多256请求或300秒接新请求，64输入/2048输出；观察900秒；1→2→1、独立GPU、双后端接流、空闲进程退出 |
| https --run-inference | 可信TLS、鉴权/私有路径/端口、一次16token原生生成 |
| stream_cancel --run-inference | 完整128token SSE，再提前关闭3500token请求；总150秒；abort信号和两次idle |
| ready --snapshot-only | 只读Gateway/规则/Alertmanager/接收器，不生成 |
| operations --run-maintenance | 单副本计划停服；见[恢复手册](operations.zh-CN.md) |

伸缩还通过SSH检查GPU进程，--ssh-user/--ssh-key/--ssh-port可改初始化默认值。
专用宿主不能运行其他GPU任务。停止观察器不证明远端有界客户端已停止。
不要并发验收、负载期间手动scale或用python -O。生成、负载、维护均需显式执行开关。

JSONL/恢复文件进入.private/evidence；preflight/HTTPS输出选定结果，保存时用私有tee及pipefail。
不输出key、原始K8s错误或生成正文。即使恢复成功，缺观察仍FAIL。

历史报告用原lab脚本和已记录硬件。公开参数化工具由其整理，仅**离线**验证，
未在新GPU VM重跑。CLI/目标/DNS/SSE/恢复测试不代替运行验收；
新环境须记录日期和证据，原始哈希不变。
