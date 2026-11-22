---
name: phicomm-k3-flash
description: 斐讯 K3 路由器刷机技能 —— CFE + TFTP 刷机全流程、坑清单、刷后配置与固件兼容矩阵。当用户要刷机、救砖、进 CFE、或配置已刷 OpenWrt 的斐讯 K3 时使用。Phoenix K3 router flashing (CFE+TFTP), pitfalls, post-flash setup, firmware compatibility.
---

# 斐讯 K3 刷机技能

本技能提供经过实测验证的 K3（BCM4709C + 双 BCM4366）刷机与配置流程。

## 使用原则

1. **动手前先读两个文件**：
   - `docs/flashing-guide.md` —— 完整刷机流程（进 CFE、TFTP、do.htm、重启、初始化）
   - `docs/pitfalls.md` —— 坑清单，每条按"现象 → 原因 → 解决"组织
2. **刷之前核对三件事**（做不到就停下来问用户）：
   - 目标固件 sha256 与官方发布一致
   - 目标固件在 `docs/compatibility/` 有实测记录（没有 = 提醒用户这是首刷）
   - 电脑直连的是 **K3 的 LAN 口**，不是光猫（电信智能网关也是 LuCI 风格页面，极易混淆）
3. **工具**：
   - TFTP 服务器用 `tools/tftpd.py`（Python 3），监听 UDP 69，固件放同目录改短名
   - SSH 用 `tools/k3ssh.sh <ip> <命令>`（适配 Windows OpenSSH 禁 ssh-rsa、root 空密码的场景）
4. **刷完必做**（`docs/post-flash.md`）：立即让用户改 root 密码；配置按需进行
5. **安全红线**：任何文档、issue、PR 都不得出现密码/PPPoE 账号等敏感信息；固件二进制不入库，只放官方链接 + sha256

## 关键事实速查

- CFE 固定 IP `192.168.2.1`；电脑需手动设 `192.168.2.22/24`；`ping` 出 `TTL=100` 即 CFE 就绪
- CFE 网页上传框不可用（必跳 `f2.htm`）→ 必须用 `do.htm` + TFTP：
  `http://192.168.2.1/do.htm?cmd=flash+-noheader+192.168.2.22:k3.trx+nflash0.trx`
- 刷完 **CFE 不会自动重启**（TTL=100 挂着是正常），需手动断电重启；首次启动 2~5 分钟
- OpenWrt 19.07.10 实测要点：缺 clm_blob → WiFi 必须固定信道（`channel=auto` 会 ACS 失败）；5G 只支持 ch36–48；反复 `wifi reload` 会让 brcmfmac 扫描状态机楔死，需重启路由器恢复
- 新固件版本实测后，按 `docs/compatibility/README.md` 的模板新增条目并更新矩阵表格

## 流程概览

1. 读指南与坑清单 → 2. 核对固件 → 3. 直连 K3 LAN → 4. 进 CFE → 5. TFTP + do.htm 刷写 → 6. 断电重启 → 7. 初始化 + 改密码 → 8. 记录兼容性与新坑
