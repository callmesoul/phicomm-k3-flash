# K3 刷机完整流程（CFE + TFTP）

适用范围：斐讯 K3（BCM4709C + 双 BCM4366）。原厂固件、第三方固件互刷、任何变砖状态（CFE 独立于固件，只要 CFE 在就能救）均适用。

## 0. 准备

- 电脑 × 1（下文以 Windows 为例），带网口（USB 网卡也行）
- 网线 × 1，**电脑直连 K3 的 LAN 口**（注意：不是光猫！直连光猫时 192.168.1.1 打开的是光猫管理页，见 [pitfalls.md](pitfalls.md#6)）
- 目标固件 trx，先与官方 `sha256sums` 核对
- [tools/tftpd.py](../tools/tftpd.py)（TFTP 服务器，仅需 Python 3）

## 1. 进入 CFE

1. 电脑手动设 IP：`192.168.2.22`，掩码 `255.255.255.0`
2. K3 **断电** → 按住 **RESET** 不放 → **上电** → 继续按住约 10~20 秒后松开
3. `ping 192.168.2.1`，出现 `TTL=100` 即 CFE 就绪
4. 浏览器打开 `http://192.168.2.1` 可看到 CFE 管理页

> CFE 的 IP 固定为 `192.168.2.1`，与已刷系统的 IP 无关。

## 2. 启动 TFTP 服务器

把固件 trx 复制到 `tftpd.py` 同目录，**改短名**（如 `k3.trx`）：

```bat
python tftpd.py
```

Windows 需放行 UDP 69（管理员命令行）：

```bat
netsh advfirewall firewall add rule name="TFTP-69" dir=in action=allow protocol=UDP localport=69
```

## 3. 执行刷写

在浏览器地址栏执行（**不要**用 CFE 页面的上传框，那个必跳 `f2.htm`）：

```
http://192.168.2.1/do.htm?cmd=flash+-noheader+192.168.2.22:k3.trx+nflash0.trx
```

参数说明：

| 部分 | 含义 |
|---|---|
| `192.168.2.22` | TFTP 服务器（你的电脑）IP，按实际修改 |
| `k3.trx` | 固件文件名 |
| `nflash0.trx` | 目标分区 |

观察 `tftpd.py` 输出：出现 `RRQ 'k3.trx' ...` 和 `完成！` 即传输成功。CFE 页面显示 `Command completed. Continue.` 是**正常回应**，不是失败。

## 4. 重启

**CFE 刷完不会自动重启**，`TTL=100` 一直挂着是正常的 —— 手动断电，等几秒后重新上电。

首次启动需 **2~5 分钟**（初始化 flash），期间不要断电。

## 5. 初始化新系统

1. 电脑改回自动获取 IP（`ipconfig /renew`）
2. 浏览器打开 `http://192.168.1.1`（OpenWrt 默认 LAN）
3. `root` / 空密码登录，**立即改密码**（见 [post-flash.md](post-flash.md)）

## 回滚 / 救砖

任何时候重复第 1 步进 CFE 重刷即可。原厂固件同样可以用这个方法刷回。

## 刷完后

把你实测的固件版本记录到 [compatibility](../compatibility/README.md)，遇到新坑补充到 [pitfalls.md](pitfalls.md)。
