# Xray TUN 透明网关（K3 + OpenWrt 19.07）

在刷好的 OpenWrt 19.07 K3 上部署 Xray，实现**全屋透明代理**：所有连入的家庭设备无需任何代理设置，国内流量直连、国外流量自动走节点，DNS 按国内外分流。

- 实测环境：斐讯 K3（BCM4709C Cortex-A9）+ OpenWrt 19.07.10（内核 4.14）+ Xray v26.11.9（arm32-v5 软浮点版）
- 部署文件在 [tools/xray/](../tools/xray/)

## 架构

```
                          ┌──────────────────────── K3 ────────────────────────┐
 LAN 客户端 ──(br-lan)──▶ │ mangle 打 mark 0x2 ──▶ ip rule fwmark 0x2          │
                          │        └──────────▶ table 100: default dev tun0    │
                          │                        │                           │
                          │                   tun0 (10.0.0.1/16)                │
                          │                        │                           │
                          │                  Xray tun-in inbound                │
                          │       routing: geoip:cn/private → direct            │
                          │                 其余 → proxy (vmess 节点)           │
                          │                        │                           │
                          │   direct 流量: Xray 回注 tun0（带 mark 0x1）        │
                          │        └─▶ ip rule fwmark 0x1 → main 表 → WAN       │
                          └────────────────────────────────────────────────────┘

 DNS: dnsmasq ──▶ 10.0.0.2:53 ──▶ tun-in:53 ──▶ dns-out ──▶ Xray DNS 模块
                           223.5.5.5（expectIPs geoip:cn）→ 国内直连
                           回退链 → 8.8.8.8（经 proxy 出站）→ 国外解析
```

核心思想：**只有被 mangle 标记（mark 0x2）的客户端流量进入 TUN**；路由器自身流量不标记、走主路由表直连，杜绝"本地回包被劫进 TUN 死循环"。Xray 回注的包带 mark 0x1 走主表，防环。

## 部署步骤

1. **二进制与数据文件**（空间紧张，注意 overlay 余量）：
   - `xray`：GitHub releases 的 `Xray-linux-arm32-v5.zip`（**必须 v5 软浮点**，armv6/v7 构建在 Cortex-A9 上 Illegal instruction），UPX 压缩后放 `/usr/bin/xray`
   - `geoip.dat`：全量版，放 `/usr/share/xray`（init 脚本里设 `XRAY_LOCATION_ASSET`）
2. **安装文件**（见 [tools/xray/](../tools/xray/)）：
   - `/etc/init.d/xray`（procd 托管，开机自启 + respawn）
   - `/etc/xray/config.json`：用 `gen_config.py` 从订阅生成（节点域名会自动写进 `dns.hosts` 静态映射——没有它，解析节点地址要经代理，形成引导死循环）
   - `/etc/xray-tun-routes.sh`：等 tun0 出现后配置策略路由（幂等，可重复跑）
   - `/etc/firewall.user`：mangle 打标 + FORWARD 放行（**tun0 不在任何 fw3 zone，不加这两条 FORWARD 规则客户端流量全部被 DROP**）
3. **dnsmasq**：`uci add_list dhcp.@dnsmasq[0].server='/#/10.0.0.2#53'` + `uci set dhcp.@dnsmasq[0].noresolv='1'`（DNS 全部交给 TUN 网关分流）
4. **开机链路**：`/etc/rc.local`（见 tools/xray/rc.local.example）加执行位并调用 tun-routes 脚本；再加 cron 自愈（xray 崩溃 respawn 后 tun0 重建会丢 table 100 路由）：
   ```
   */5 * * * * sh /etc/xray-tun-routes.sh >/dev/null 2>&1
   ```
5. **kmod-tun**：`opkg install kmod-tun`，确认 `/etc/modules.d/` 里有 tun 模块（否则重启后 /dev/net/tun 消失、TUN 起不来）

## 已实测的坑（每条都真实踩过）

| # | 现象 | 原因 | 解法 |
|---|---|---|---|
| 1 | WiFi 能连但全家"上不了网"；LAN 互访正常、路由器 IPv6 正常、IPv4 全灭 | `ip rule add from all lookup 100`（无 fwmark 条件）把路由器**本地回包**也劫进 tun0，Xray 回注又命中同一规则 → 循环丢弃 | 只劫持打了 mark 的流量：`ip rule add fwmark 0x2 lookup 100`，本地流量走主表 |
| 2 | 修好规则后客户端仍不通，但路由器 DNS 测试正常 | fw3 的 FORWARD policy DROP，tun0 不属于任何 zone；DNS 回包走 INPUT（ACCEPT）所以路由器自测正常，客户端流量走 FORWARD 全被拒 | firewall.user 加 `FORWARD -i br-lan -o tun0 -j ACCEPT` 和反向各一条 |
| 3 | 国外域名解析不了（"No answer"），国内正常 | Xray v26 中 `skipFallback: true` 的 DNS 服务器**不参与回退链**，8.8.8.8 永远不被查询 | 回退服务器不要带 skipFallback |
| 4 | 配了 `tcp://8.8.8.8:53` 但查询链里根本没有它 | v26 不支持 `tcp://` DNS 前缀，服务器被静默丢弃 | 用纯地址（UDP）；UDP over vmess mux 实测可用 |
| 5 | DoH（dns.google）全部 "context deadline exceeded" | 双重死循环：DoH 域名解析经 dnsmasq→TUN→DoH 自身；且 dns.google 被墙需经代理、代理节点的域名解析又依赖 DNS | 弃 DoH，用 223.5.5.5/8.8.8.8 明文双链 + 节点域名 hosts 静态映射 |
| 6 | 重启后 ip rule 不出现 | `cat > /etc/rc.local` 推送文件会**丢掉执行位**（644），而 19.07 只在 `-x` 时才执行 rc.local；另外 `exit 0` 写在脚本调用之后也会吞掉调用 | 推送后 `chmod +x`；`exit 0` 放最后 |
| 7 | Go ≥1.21 的 armv7/armv6 二进制全部 Illegal instruction | Cortex-A9 无 udiv/sdiv 指令 | 只用 arm32-v5（GOARM=5）构建 |
| 8 | 客户端测试结果诡异（时好时坏） | PC 同时有 USB tether（跃点低抢默认路由）或本机 Clash 劫持流量，测试流量根本没进 K3 | 测试前拔 tether、退出本机代理，确认默认路由唯一指向 192.168.2.1 |
| 9 | v26 移除了 loadbalancer 协议 / dokodemo 隐式 DNS 拦截等 | v26 配置与网上旧教程不兼容 | 以 `xray run -test` 校验配置为准；节点切换 = 重新生成配置（首个 outbound 即默认路由） |
| 10 | Git Bash 调 ssh 时 /etc 等路径被转成 Windows 路径 | MSYS 路径转换 | 加 `MSYS_NO_PATHCONV=1` |
| 11 | 某个国外网站突然打不开，但 curl 能连上（或只看到它的"地区封锁"提示页） | **网站自己按地区/机房封锁出口 IP**，与墙无关。实测 javdb.com 封锁大陆与日本机房出口（"Due to copyright restrictions"），港/新/台出口正常；CloudFront 类站点（如 platform.deepseek.com）会对无 JS 客户端发 WAF challenge（202/403），真实浏览器可通过 | 换出口地区合适的节点；先 `curl -x 代理 https://站点/cdn-cgi/trace` 看出口 `loc=` 再下结论 |
| 12 | 视频一卡一卡、下载龟速，但网页能打开 | 同一订阅各节点吞吐差距可达 **50 倍以上**（实测深夜机场 CDN 拥塞时：台湾节点 23KB/s、新加坡节点 1.2MB/s）；网页加载只暴露 RTT，不暴露带宽 | 用 `speed.cloudflare.com/__down?bytes=N` 实测**单连接吞吐**选节点（见下 auto_select.py），别只看 ping/网页 |
| 13 | 华为等 IoT 设备（音箱/家庭云存储）在 App 里批量显示"设备已离线"，但设备在线、PC 上网正常、国内网站直连无感 | tun-in 的 sniffing `destOverride:["http","tls"]` 把 TLS(443) 连接的目的地**改写为 SNI 域名**；geoip:cn 规则匹配要解析域名，而华为 IoT 域名（如 `whiomplatform.hwcloudtest.cn`）公网 DNS 全 NXDOMAIN → 拿不到 IP → geoip 匹配落空 → CN 流量掉进默认 proxy（海外节点）→ 华为云拒绝海外 IP → 设备反复重连失败。非 443 流量无 SNI 改写仍走直连，所以"网络全通但设备离线"极具迷惑性 | sniffing 一律加 `routeOnly: true`（域名只用于域名分流规则，连接保持原 IP）；诊断实锤：`logread` 里 `taking detour [proxy] for [tcp:<CN-IP>:443]` 与 `app/dns ... rcode: 3` 同时出现 |
| 14 | 给 7890/7891 显式代理配置了域名分流规则但不生效 | http/socks inbound **默认不开 sniffing**，路由规则拿不到域名，按 IP 匹配走了默认节点；只有 tun-in 天然有 sniffing | 给 http-in/socks-in 加 `"sniffing": {"enabled": true, "destOverride": ["http","tls"]}` |
| 15 | 域名分流指向的节点连不通/不稳定 | 只有主节点 outbound 带 `sockopt.mark=1`；分流目标节点不带 mark 时其出站 socket 可能被策略路由劫持进 tun0 造成环路 | 域名规则指向的节点 outbound 也要 `sockopt: {mark: 1}`（gen_config.py 已自动处理） |
| 16 | 想要 Clash 式"自动选最快节点"，但 v26 没有 url-test/loadbalancer | v26 移除 loadbalancer，且运行时无法动态改路由 | 每节点挂一个测试入站（`17900+i` → `node-i`），一个配置测全部节点，PC 侧脚本测 RTT+吞吐后重生成配置（见下 auto_select.py） |
| 17 | 修复坑 13 后音箱恢复，但家庭云存储 NAS 仍显示离线——`/proc/net/nf_conntrack` 里 XMPP 5223/CoAP 5683/MQTT 1883/TLS 443 全部 ESTABLISHED 且有来有回 | 故障期反复重连失败后 NAS 的云注册状态机卡死：传输层会话能重建，但不再向华为云重新注册，云端一直认为设备离线（音箱 SDK 会自愈，NAS 不会） | 设备断电重启；仍不行再抓开机注册握手流量深挖 |

## Clash 式自动选优（auto_select.py）

K3 的 arm32-v5 环境跑不了任何 Go 程序（含 Clash/mihomo），Xray v26 又没有 url-test。等价的实现（`tools/xray/auto_select.py`，PC 上运行）：

1. 生成一个**带测试口的配置**：每个订阅节点一个 HTTP 测试入站（`0.0.0.0:17900+i`），路由规则 `test-in-i → node-i`。一份配置即可测全部节点，**不用逐个重启 xray**；
2. 部署后逐节点测：RTT（google 204，并发）+ 单连接吞吐（CF 2MB 下载，串行——并发测会让节点抢共享 CDN，结果失真）；
3. 选优：默认出口 = 吞吐最快（top 25% 内取 RTT 最低）；`javdb.com` 域名规则分流到最快的新加坡节点（订阅序号 6/7/8，可改脚本常量）；
4. 部署最终配置（测试口保留，方便下次复测），验证 google + javdb 出口。

用法：`python tools/xray/auto_select.py`（自动从同目录 update_k3.sh 读订阅 URL）。机场拥塞时段复测一次即可，全程约 5-10 分钟。

## 验证清单

```sh
# 路由器侧
ip rule show                     # 应有 fwmark 0x1→main、fwmark 0x2→table 100
ip route show table 100          # default dev tun0
iptables -L FORWARD -n | grep tun0   # 两条 ACCEPT 且有计数
nslookup www.baidu.com 10.0.0.2  # 国内域名有答案
nslookup www.google.com 10.0.0.2 # 国外域名有答案（经节点）

# 客户端侧（无 tether/无本机代理）
curl -I https://www.baidu.com    # 200，直连
curl -I https://www.google.com   # 经节点
```

## 降级行为

- xray 进程崩溃、procd respawn 后：table 100 路由随 tun0 重建丢失 → 客户端退回直连（国内正常、国外不可用），5 分钟内 cron 自愈
- 节点失效：国外站点与国外 DNS 不可用（国内直连不受影响）；`update_k3.sh <序号>` 切换节点，或 `auto_select.py` 全量复测自动换最快
