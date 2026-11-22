# 刷后必做配置（OpenWrt 实测）

新系统起来后的顺序：**改密码 → 网络配置 → WiFi 配置**。以下命令均为 OpenWrt 19.07 实测，其他版本大同小异。

## 0. 改 root 密码（第一件事！）

```sh
passwd
```

> 新刷的 OpenWrt root 是**空密码**，且默认 SSH 对 LAN 开放。不改密码等于门户大开。

## 1. 网络配置

### LAN 地址

默认 `192.168.1.1`，与光猫同网段会冲突：

```sh
uci set network.lan.ipaddr='192.168.2.1'
uci commit network
/etc/init.d/network restart
```

改完电脑 `ipconfig /renew` 重新拿地址。

### VLAN（交换芯片 bcm53011）

K3 默认划分实测可用，一般不用动：

```sh
# /etc/config/network 中的默认值
# VLAN1（LAN）: ports '0 1 2 5t'
# VLAN2（WAN）: ports '3 5t'   ← 端口 3 是 WAN 口，5 是 CPU
```

## 2. WiFi 配置

### 固定信道（必做）

缺 `clm_blob` 的固件 `channel=auto` 会 ACS 失败（见 [pitfalls.md](pitfalls.md#8)），必须固定：

```sh
# 先扫描挑信道：iwinfo wlan0 scan（2.4G）/ iwinfo wlan1 scan（5G）
# 挑邻居信号最弱、同信道 AP 最少的
uci set wireless.radio0.channel='6'     # 2.4G，按扫描结果定
uci set wireless.radio1.channel='36'    # 5G 只支持 ch36–48（无 clm_blob）
uci commit wireless
wifi   # 完整重启无线；改信道别用 wifi reload，brcmfmac 会楔死（pitfalls#10）
```

### 频宽与 SSID 拆分（经验）

- 5G 在拥挤环境（同频段几十个邻居 AP）且信号一般时，**20/40MHz 窄频宽 + 干净信道** 比 80MHz 宽频宽更稳（[实测案例](pitfalls.md#11)）
- 双频合一在弱信号+干扰环境下会让手机反复横跳断连，**拆分 SSID** 立竿见影：

```sh
uci set wireless.default_radio1.ssid='<原SSID>_5G'
uci commit wireless
wifi
```

### 关于 clm_blob

缺 `clm_blob` 的影响：ACS 不可用、5G 只支持 ch36–48、部分场景射频表现弱。想解锁高频段：找同芯片（BCM4366）设备的板级 `brcmfmac4366c-pcie.clm_blob`，放入路由器 `/lib/firmware/brcm/` 后重启。效果与兼容性因来源而异，试完记得回坑清单更新记录。

## 3. 常用诊断命令

```sh
iwinfo                        # 无线接口一览
iwinfo wlan0 info             # 2.4G 状态（信道/速率/客户端数）
iwinfo wlan0 assoclist        # 已连客户端及信号
iwinfo wlan1 scan             # 5G 邻居扫描
wifi status                   # 无线配置生效状态（radio up/pending 等）
logread | grep -E "hostapd|brcmfmac"   # 无线日志（连断、扫描错误）
dmesg | grep brcmfmac         # 驱动日志（clm_blob 缺失在此可见）
uci show wireless             # 无线配置全量
```

## 4. 备一份配置

改完顺手备份，出问题时一键还原：

```sh
sysupgrade -b /tmp/backup.tar.gz   # 配置备份（不含固件）
```
