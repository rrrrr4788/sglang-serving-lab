[English](https.md) | [简体中文](https.zh-CN.md)

# 复现 HTTPS 入口

仅用于按[云端初始化](cloud-rebuild.zh-CN.md)准备的当前专用VM。保持API隧道运行。
在WSL/Linux仓库根目录使用Python3.10+、Bash、curl、kubectl、SSH、
已校验的Helm依赖和私有引擎密钥。

CURRENT_HOSTNAME选择自有域名A记录或sglang-IP用横线连接.sslip.io。
生成工具隐藏输入ACME邮箱，以0600写入**新的**忽略目录，不访问网络。
Git中的IngressRoute使用无效示例域名，必须先生成。
可用--contact-file传已有私有overlay。签发时CA会收到邮箱；
不要导出联系信息、ACME/TLS私钥或Helm Secret。

```bash
export GPU_HOST='NEW_VM_IP'
export INFERENCE_HOST='CURRENT_HOSTNAME'
python3 scripts/cloud/prepare_https.py --host "$GPU_HOST" \
  --hostname "$INFERENCE_HOST" --output-dir .private/https-current
curl -fL https://traefik.github.io/charts/traefik/traefik-42.1.3.tgz \
  -o .private/vendor/traefik-42.1.3.tgz
printf '%s  %s\n' 10ec2b032fd7ec9fa04a8816872e20ba0fafc47231f6394b5cb5d522f3b0ef50 \
  .private/vendor/traefik-42.1.3.tgz | sha256sum -c -
getent ahostsv4 "$INFERENCE_HOST"
```

仅在校验和通过、DNS指向当前VM后继续。换IP必须重新生成。
本版假设IPv4和唯一DNS目标；安装前检查宿主80/443空闲。

```bash
.private/bin/helm upgrade --install sglang-edge .private/vendor/traefik-42.1.3.tgz \
  --kubeconfig .private/cloud-kubeconfig --kube-context k3s-sglang-platform \
  --namespace sglang-platform --values deploy/k3s/traefik-values.yaml \
  --values .private/https-current/traefik-contact.json --wait --timeout 5m
ssh -i ~/.ssh/sglang_lab_ed25519 "ubuntu@$GPU_HOST" \
  'sudo -n ufw allow 80/tcp && sudo -n ufw allow 443/tcp'
kubectl --kubeconfig .private/cloud-kubeconfig --context k3s-sglang-platform \
  -n sglang-platform apply -f .private/https-current/inference-ingress.yaml
python3 scripts/acceptance/https.py --host "$GPU_HOST" \
  --base-url "https://$INFERENCE_HOST" --run-inference
```

顺序是安装Traefik、开放80/443、再挂路由，让HTTP-01在防火墙就绪后启动。
80只用于ACME，不传模型key。HTTPS只允许POST /generate、/v1/chat/completions、
/v1/completions。脚本检查可信TLS、无/错key拒绝、私有路径/端口隔离及一次16token原生生成；
拒绝重定向，先检查集群/DNS与主机一致。

Traefik单Pod、host80/443和本地持久ACME存储仍是单点；16活动请求、8/s、burst16不是测得容量。
续期/重启、两种OpenAI请求格式、限流拒绝和完整应用日志脱敏尚未实测，见[证据](presentation.zh-CN.md)。

路由有误时恢复上次验收的生成文件/Helm值，不扩大白名单或暴露后端端口来排障。
删除IngressRoute不销毁付费VM：保留证据后在提供方明确销毁并确认状态。
