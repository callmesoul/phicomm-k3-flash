# tools/xray — K3 透明网关部署文件

按 [docs/proxy-transparent-gateway.md](../../docs/proxy-transparent-gateway.md) 部署透明网关所需的全部文件。

| 文件 | 安装位置 | 说明 |
|---|---|---|
| `xray.initd` | `/etc/init.d/xray` | procd 托管服务（开机自启、崩溃 respawn），记得 `chmod +x` + `enable` |
| `gen_config.py` | PC 任意位置 | 从订阅（base64 的 vmess:// 列表）生成 config.json；节点域名自动解析写入 `dns.hosts`（防引导环）；支持 `--domain=站点=序号` 域名分流与 `--test-ports` 每节点测试口 |
| `update_k3.sh` | PC 任意位置 | 一条命令完成：拉订阅 → 生成 → 局域网 HTTP 传送 → 校验 → 重启 xray → 恢复 TUN 路由 |
| `auto_select.py` | PC 任意位置 | Clash 式自动选优：部署测试口配置 → 逐节点测 RTT+吞吐 → 默认出口选最快、`javdb.com` 分流到最快新加坡节点 → 部署最终配置（见 [proxy-transparent-gateway.md](../../docs/proxy-transparent-gateway.md)） |
| `firewall.user` | `/etc/firewall.user` | mangle 打 mark 0x2 + FORWARD 放行 tun0↔br-lan（缺了它客户端流量全被 DROP） |
| `xray-tun-routes.sh` | `/etc/xray-tun-routes.sh` | 策略路由配置（幂等，可重复跑），`chmod +x` |
| `rc.local.example` | 参考 `/etc/rc.local` | 开机调用 tun-routes 脚本；**推送后必须 `chmod +x`**（无执行位则开机不执行） |

## 使用

```sh
# 生成配置（<订阅文件> = 网页导出的 base64 文本；序号 = 主节点）
python gen_config.py sub.txt config.json 0

# 一键更新（含传送到 K3 + 重启 + 自愈）
./update_k3.sh 0

# Clash 式自动选优（全节点测速，默认出口最快 + javdb.com 走最快新加坡节点）
python auto_select.py
```

`update_k3.sh` 首次使用前需改三处：

1. `SUB_URL`：替换成你的订阅地址（token 属于个人凭据，**不要提交进公开仓库**）
2. `SSH_ASKPASS`：指向你的 askpass 脚本（Windows OpenSSH + dropbear 密码认证用，见下）
3. `PC_IP` 自动从 ipconfig 探测，无需改

## SSH 密码（Windows + dropbear 坑）

K3 的 dropbear 只支持 ssh-rsa，且 Windows OpenSSH 的密码从控制台读取、不接受 stdin 管道——`printf 'password\n' | ssh` 会静默失败。可用 askpass 方案：

```bat
:: k3-askpass.bat
@echo off
type "C:\Users\<你>\.ssh\k3-pass.txt"
```

```sh
export SSH_ASKPASS='C:\Users\<你>\.ssh\k3-askpass.bat'
export SSH_ASKPASS_REQUIRE=force
ssh -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedKeyTypes=+ssh-rsa \
    -o PreferredAuthentications=password -o PubkeyAuthentication=no root@192.168.2.1
```

## 二进制获取

- `xray`：GitHub releases → `Xray-linux-arm32-v5.zip`（**必须 arm32-v5**，armv6/v7 在 Cortex-A9 上 Illegal instruction；UPX 压缩后约 10MB）
- `geoip.dat`：Xray 官方 release 附带的 geoip.dat，放 `/usr/share/xray/`
- 直连 GitHub 慢的话走镜像（先核对 sha256）
