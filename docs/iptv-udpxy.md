# IPTV 组播转单播（广东电信 + udpxy）

利用 K3 多余的 LAN 口接入运营商 IPTV 专网，用 udpxy 把组播流转成 HTTP 单播，局域网内任意设备（电视 VLC、手机等）无需机顶盒即可看直播。

- 实测环境：广东电信（PPPoE 拨号、账号形如 `<市话号码>@iptv.gd`）+ K3 OpenWrt 19.07.10 + udpxy 1.0-23.10
- 频道表（316 个频道，已转 udpxy 单播格式）：[tools/iptv/iptv-udpxy.m3u](../tools/iptv/iptv-udpxy.m3u)

## 拓扑

```
光猫 iTV 口 ──网线──▶ K3 LAN3（交换机 port 2）
                        │  VLAN 3（tagged，CPU 侧 eth0.3）
                        ▼
              itv 接口: PPPoE 拨号（IPTV 专网，拿到 10.x 地址）
                        │  eth0.3 挂虚拟 IP 192.168.77.1/24（udpxy 组播源）
                        ▼
              udpxy 监听 192.168.2.1:4022
                        │
         http://192.168.2.1:4022/rtp/<组播地址>:<端口>  ← 局域网设备直接播放
```

## 配置

**1. 交换机 VLAN + 网络接口**（`/etc/config/network`）：

```
config switch_vlan
	option device 'switch0'
	option vlan '3'
	option ports '2 5t'        # LAN3 接光猫 ITV 口；5t = CPU tagged
	option vid '3'

config interface 'itv'
	option ifname 'eth0.3'
	option proto 'pppoe'
	option username '<市话号码>@iptv.gd'
	option password '<ITV密码>'
	option defaultroute '0'     # 绝不能抢默认路由
	option peerdns '0'          # 不能用 ITV 专网的 DNS
```

> 本机示例的 ITV 口在 LAN3；不同路由器端口布局不同，先 `swconfig dev switch0 show` 确认端口号与物理口的对应关系。

**2. udpxy**（19.07.10 的 2016 版有三个必踩的坑）：

```sh
uci set udpxy.@udpxy[0].enabled='1'
uci set udpxy.@udpxy[0].bind='192.168.2.1'
uci set udpxy.@udpxy[0].port='4022'
uci set udpxy.@udpxy[0].source='192.168.77.1'   # 必须是接口 IP，不是接口名
uci delete udpxy.@udpxy[0].verbose              # init 脚本把 verbose 映射成 -V，这个版本不认，必崩
uci delete udpxy.@udpxy[0].status               # status → -S 同理，必崩
uci delete udpxy.@udpxy[0].buffer_size          # 按字节算 2048 太小，删掉用默认
uci commit udpxy
```

eth0.3 的虚拟 IP 写进 `/etc/rc.local`（记得 `chmod +x`，见 xray 文档坑 #6）：

```sh
ip addr add 192.168.77.1/24 dev eth0.3
```

**3. 防火墙**：itv 划在 wan zone，放行 IGMP 与组播入站：

```sh
uci add firewall rule; uci set firewall.@rule[-1].name='ITV-IGMP'
uci set firewall.@rule[-1].src='wan'; uci set firewall.@rule[-1].proto='igmp'
uci set firewall.@rule[-1].target='ACCEPT'
uci add firewall rule; uci set firewall.@rule[-1].name='ITV-Multicast'
uci set firewall.@rule[-1].src='wan'; uci set firewall.@rule[-1].proto='udp'
uci set firewall.@rule[-1].dest_ip='224.0.0.0/4'
uci set firewall.@rule[-1].target='ACCEPT'
uci commit firewall
```

**4. 频道表**：从运营商组播地址表（可向宽带装维要或网上搜）转成 udpxy 单播 URL 并去重：

```
http://192.168.2.1:4022/rtp/<组播IP>:<端口>
```

成品见 [tools/iptv/iptv-udpxy.m3u](../tools/iptv/iptv-udpxy.m3u)，上传到 K3 `/www/iptv.m3u`，局域网访问 `http://192.168.2.1/iptv.m3u`。

## 验证

```sh
# 拨号状态
ifstatus itv | grep '"up"'            # true = PPPoE 已连上
ip -4 addr show pppoe-itv             # 10.117.x.x 之类的 ITV 专网地址

# 拉流（广东卫视高清，~8.7Mbps 属正常）
curl -o /tmp/test.ts -m 12 'http://192.168.2.1:4022/rtp/239.77.0.4:5146'
# 13MB 左右 + 文件头 0x47（TS 同步字节）即成功

# 播放：VLC 打开 http://192.168.2.1/iptv.m3u
```

## 排障

| 现象 | 原因 | 解法 |
|---|---|---|
| 拨号一直 "pending"，`tcpdump -i eth0.3 ether proto 0x8863` 只看到 PADI 没有 PADO | 光猫 ITV 口没接线/对端没响应（**不是路由器问题**） | 检查光猫 ITV 口物理连接；线接上后 pppd 会自动重拨成功 |
| udpxy 崩溃循环 | verbose/status 选项被映射成该版本不认的 -V/-S | 删掉这两个 uci 选项 |
| "Invalid multicast address" | `-m` 参数给了接口名而不是 IP | `-m 192.168.77.1`（挂虚拟 IP 后） |
| 拨号永远无回应、DHCP 拿不到地址 | ITV 专网是 **PPPoE** 不是 DHCP | 用 pppoe 协议拨号 |
| 拉流正常但速度只有几百 K | 组播没进 eth0.3（防火墙/VLAN 问题） | 检查 igmp + 224.0.0.0/4 放行、VLAN 端口映射 |

## 说明

- 组播地址表为运营商公开资源；**PPPoE 账号密码为个人凭据，勿提交到公开仓库**（本仓库示例均为占位符）
- B700 机顶盒方案已退役：电视装 VLC 直接播放 `iptv.m3u`，与 [透明网关](proxy-transparent-gateway.md) 互不影响（ITV 专网流量不经过代理）
