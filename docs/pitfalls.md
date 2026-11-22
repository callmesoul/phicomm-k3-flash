# K3 刷机坑清单

每条按「现象 → 原因 → 解决」组织，均为实测记录。刷机前通读一遍，能避开 90% 的弯路。

## 刷机阶段

### 1. CFE 网页上传固件必跳 `f2.htm` 失败

- **现象**：CFE 管理页选固件上传后跳转到 `f2.htm`，刷写从不开始
- **原因**：CFE 上传页对现代浏览器兼容性差；后期 CFE 版本封堵了网页直传
- **解决**：放弃上传框，改用 [flashing-guide.md](flashing-guide.md) 的 `do.htm` + TFTP 方法

### 2. TFTP 传输到最后一块"卡住"

- **现象**：固件传到最后不动了，CFE 干等，直到超时
- **原因**：RFC 1350 规定：文件大小恰为 512 字节块大小的整数倍时，必须**补发一个 0 字节结束块**。OpenWrt 19.07.10 的 K3 固件是 7,995,392 = 512 × 15,616 字节，正好整块，不补块客户端就一直等
- **解决**：本项目 `tftpd.py` 已自动处理；若用其他 TFTP 服务器（tftpd64 等），确认其支持该行为，否则换 tftpd.py

### 3. 刷完 TTL=100 一直挂着，不重启

- **现象**：`do.htm` 执行后 ping 一直 `TTL=100`，路由器不自动重启，以为卡死了
- **原因**：**CFE 刷完不会自动重启，这是正常行为**
- **解决**：手动断电，等几秒重新上电。首次启动需 2~5 分钟

### 4. CFE 页面显示 "Command completed. Continue."

- **现象**：`do.htm` 执行后页面显示 "Command completed. Continue."，以为是报错
- **原因**：这是 CFE 命令执行成功的**正常回应**
- **解决**：不用管，按第 3 条断电重启即可

### 5. 刷完开机"没反应"

- **现象**：上电后 ping 不通、面板不亮或停在 logo
- **原因**：首次启动要初始化 flash（2~5 分钟）；或根本没断电重启过
- **解决**：等 5 分钟再 ping；确认执行过手动断电重启。仍不通 → 重进 CFE 重刷（CFE 独立于固件，通常不会真砖）

### 6. 直连光猫时 `192.168.1.1` 打开是"路由器"管理页

- **现象**：准备刷完进 OpenWrt 初始化，浏览器打开 192.168.1.1 却是个陌生的 LuCI 风格页面，怎么改都不是 K3
- **原因**：中国电信智能网关（光猫）默认也是 192.168.1.1，且管理界面同样是 LuCI 风格，**极易混淆**
- **解决**：刷机和初始化阶段，K3 与光猫之间**不要连线**，电脑直连 K3 LAN 口操作；两者都连时注意看页面上的设备型号

## 刷后配置阶段（OpenWrt 实测）

### 7. Windows SSH 连不上新刷的 OpenWrt

- **现象**：`ssh root@192.168.1.1` 报 "no matching host key type" 或被拒绝
- **原因**：OpenWrt 19.07 的 dropbear 只支持 ssh-rsa，新版 Windows OpenSSH 默认禁用 ssh-rsa；root 默认空密码
- **解决**：加参数：`ssh -o HostKeyAlgorithms=+ssh-rsa -o PubkeyAcceptedKeyTypes=+ssh-rsa -o PreferredAuthentications=password -o PubkeyAuthentication=no root@<ip>`（可直接用 [tools/k3ssh.sh](../tools/k3ssh.sh)）；**登录后第一件事改密码**

### 8. WiFi `channel=auto` 起不来（ACS 失败）

- **现象**：hostapd 日志 "ACS: All study options have failed"，WiFi 无法上线
- **原因**：固件缺 `clm_blob`（Country Locale Matrix，Broadcom 不允许自由分发），信道自动选择功能不可用
- **解决**：**固定信道**。先用 `iwinfo wlan0 scan` / `iwinfo wlan1 scan` 挑干扰最少的信道，再 `uci set wireless.radioN.channel=X` 固定（参考 [post-flash.md](post-flash.md#wifi-信道与频宽)）

### 9. 5G 换 ch149 / ch52 等信道后 AP 起不来

- **现象**：`uci set wireless.radio1.channel=149` 后 hostapd 报 `scan error (-52)` / `Unable to setup interface`，5G 掉线；`iw phy phy1 channels` 却显示该信道"可用"
- **原因**：缺 `clm_blob` 时 BCM4366 固件实际**只支持 ch36–48**，内核的信道表与固件能力不一致
- **解决**：5G 老老实实用 ch36–48；想解锁高频段需找到板级 `brcmfmac4366c-pcie.clm_blob` 放入 `/lib/firmware/brcm/`（来源：同芯片设备的厂商固件），风险自担

### 10. 反复 `wifi reload` 后 WiFi 起不来

- **现象**：连续改了几次信道/SSID 后，连原本正常的信道都报 `scan error (-52)`、mac80211 报 "Too many open files"，AP 起不来
- **原因**：brcmfmac 的扫描状态机被反复重载搞楔死了（这个驱动就这脾气）
- **解决**：**重启路由器**（最可靠）；平时改无线配置尽量一步到位，别来回 reload

### 11. 双频合一 + 拥挤信道 = 手机反复断连

- **现象**：手机 WiFi 频繁"连上→几秒后断→重连"，刷视频卡顿；日志里同一台设备在 2.4G/5G 间反复关联/断开
- **原因**：2.4G 和 5G 同名同密码时，手机自动在两个频段间挑信号；拥挤信道上 5G 上行链路质量差（实测案例：隔墙 -68 dBm 时手机上行速率掉到 MCS0/6.5 Mbit/s，路由器固件收不到 ACK 后主动踢人）
- **解决**：① 拆分 SSID（如 `Home` / `Home_5G`），手机不再自动横跳；② 挑干净信道（见第 8 条）；③ 若 5G 频段整体拥挤且缺 clm_blob 无法换高频段，把 5G 频宽缩到 20/40MHz 占一个干扰最少的信道，优先保证稳定

## 网络拓扑阶段

### 12. 光猫 → K3 WAN 口后没有外网

- **现象**：WAN 口 DHCP 拿不到地址
- **原因**：光猫是路由模式时 WAN 用 DHCP 即可；光猫是桥接模式时 WAN 要配 PPPoE。另外 K3 交换芯片是 bcm53011，VLAN 划分错了也会不通
- **解决**：默认 VLAN 已验证可用：VLAN1 = `0 1 2 5t`（LAN），VLAN2 = `3 5t`（WAN），端口 3 是 WAN 口。光猫模式查光猫管理页
