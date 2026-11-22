# OpenWrt 19.07.10

## 基本信息
- **固件文件**：`openwrt-19.07.10-bcm53xx-phicomm-k3-squashfs.trx`
- **下载链接**：<https://downloads.openwrt.org/releases/19.07.10/targets/bcm53xx/generic/>
- **sha256**：`683912d3e3c47050f232091ca5fb6493c68da8f59050b4280232f1d58510af25`
- **刷入方式**：CFE + TFTP do.htm（见 [flashing-guide.md](../flashing-guide.md)）
- **测试日期**：2026-10-23 ~ 2026-10-24
- **记录人**：社区实测

## 实测结果
- **CFE 刷入**：✅（do.htm + tftpd.py，固件 7,995,392 字节，注意 0 字节结束块，见 pitfalls#2）
- **启动**：✅（首次 2~5 分钟；CFE 刷完不自动重启，需手动断电，见 pitfalls#3）
- **LAN**：✅（默认 192.168.1.1；bcm53011 默认 VLAN：LAN=`0 1 2 5t` / WAN=`3 5t` 实测可用）
- **WAN（DHCP）**：✅（电信光猫路由模式下正常拿地址）
- **WAN（PPPoE）**：✅（ITV 独立 PPPoE 拨号实测可用，默认路由关掉即可）
- **2.4G WiFi**：✅（`channel=auto` 会 ACS 失败，必须固定信道；见 pitfalls#8）
- **5G WiFi**：✅ 但受限（缺 clm_blob：只支持 **ch36–48**，ch149/ch52 被固件拒绝；拥挤环境弱信号下上行易瘫，见 pitfalls#9/#11）
- **稳定性**：⚠️（家庭环境 8~10 客户端可长期运行；brcmfmac 有"反复 wifi reload 楔死扫描状态机"问题，重启即恢复，见 pitfalls#10）

## 坑
- 全量见 [pitfalls.md](../pitfalls.md)：CFE f2.htm、TFTP 结束块、TTL=100 不重启、光猫混淆、ssh-rsa、ACS 失败、ch149/52 被拒、reload 楔死、双频合一横跳、WAN 拓扑

## 备注
- 软件源与安全更新已停止（19.07 EOL），**刷完第一时间改 root 密码**（默认空密码）
- 缺板级参数文件（`brcmfmac4366c-pcie.phicomm,k3.txt`）与 `clm_blob`，射频表现非最优；解锁高频段需自行找同芯片设备的 clm_blob（见 post-flash.md），有实测结论欢迎回填本条目
- 内核 4.14 / hostapd 老版本，性能上限约：有线满速，2.4G HT20 ~70Mbps 实测，5G 视频宽与干扰
