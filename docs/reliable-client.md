# 非流式客户端：总预算与有限重试

入口是 `examples/reliable_client.py`。它不修改服务端配置，不启动网关，不处理流式恢复。

## 使用

主机安装方式（Python 3.10+，使用独立虚拟环境）：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r examples/requirements.txt
set -a; source .env; set +a
.venv/bin/python examples/reliable_client.py 'Say hello.' --budget 15 --retries 2
.venv/bin/python -m unittest discover -s examples -p 'test_*.py' -v
```

当前固定 SGLang 镜像已包含相同版本 HTTPX；也可以直接在现有容器中执行，避免安装主机依赖。
下面的调用从容器环境读取密钥，密钥不会放入命令参数；源码通过标准输入执行：

```bash
docker compose exec -T sglang python3 - 'Say hello.' --budget 15 --retries 2 < examples/reliable_client.py
```

容器内默认地址是 `127.0.0.1:30000`，不受主机映射端口改变影响。
只使用自己的可信服务地址；私有 `.env` 不提交到 Git。输出是响应 JSON 与实际尝试次数。

## 策略与工程取舍

| 情况 | 行为 |
| --- | --- |
| HTTP 503 | 在剩余预算和次数允许时重试 |
| 建立连接失败 | 有限重试 |
| HTTP 400/401 或其他未明确允许的状态 | 立即停止，不重试 |
| 写入/读取失败、结果不确定 | 不自动重发，避免重复请求 |
| 总预算耗尽 | 取消当前客户端等待并停止，不开始下一轮 |

默认 15 秒总预算、最多 2 次重试，即最多 3 次尝试，是可调整的教学示例默认值，不是 SLA。
退避上限从 0.5 秒开始翻倍，并加入随机抖动；如有 `Retry-After`，遵守其等待下限。
如果等待下限超过剩余预算，预算到期后就停止。不会为了重试重新获得完整预算。

关键代码是外围的 `asyncio.wait_for(run(), timeout=total_timeout)`：整个请求循环、
响应读取及退避等待都在同一个截止时间内。HTTPX 的单次读写超时不能单独替代这个总预算。
异步取消和资源关闭是协作式操作，不是操作系统级硬实时保证。

取消客户端等待不保证 GPU 已取消服务端工作；客户端不提供 exactly-once 保证。
即使是 HTTP 503，也可能代表运行中断而非入队前拒绝，重试仍可能带来额外计算。
这也是只做有限重试、对结果不确定的传输错误不重发的原因。

## 验证边界

本地模拟覆盖短暂 503 后成功、401 不重试、持续 503 的次数上限、请求期间预算耗尽、
Retry-After 期间预算耗尽、读取失败不重放。真实服务只做一次短的非流式调用。
不通过停止服务、故障注入或额外负载制造错误。实际检查结果以学习计划中的记录为准。

实现参考：[HTTPX AsyncClient](https://www.python-httpx.org/async/)、
[Python asyncio.wait_for](https://docs.python.org/3.10/library/asyncio-task.html#asyncio.wait_for)。
