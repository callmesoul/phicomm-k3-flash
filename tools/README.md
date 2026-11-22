# 工具说明

## tftpd.py

极简 TFTP 服务器（RFC 1350，仅 RRQ/octet），专为 K3 CFE 刷机定制。只用 Python 3 标准库，无依赖。

**特性**：
- 监听 UDP 69，服务脚本所在目录下的文件
- 正确处理 K3 固件的"整块"问题：文件大小恰为 512 的整数倍时补发 0 字节结束块（K3 CFE 会干等，见 docs/pitfalls.md#2）
- 支持 blksize 选项协商（客户端带选项时回 OACK）

**用法**：

```bat
:: 1. 把固件 trx 放到本脚本同目录，改短名（如 k3.trx）
:: 2. 放行防火墙（管理员）：
netsh advfirewall firewall add rule name="TFTP-69" dir=in action=allow protocol=UDP localport=69
:: 3. 启动：
python tftpd.py
:: 4. 浏览器执行 do.htm（IP 改成本机实际 IP）：
:: http://192.168.2.1/do.htm?cmd=flash+-noheader+192.168.2.22:k3.trx+nflash0.trx
```

看到 `RRQ 'k3.trx' ...` 和 `完成！` 即传输成功。

## k3ssh.sh

SSH 助手，适配两个兼容性问题（见 docs/pitfalls.md#7）：

- OpenWrt 19.07 的 dropbear 只支持 ssh-rsa，而新版 Windows OpenSSH 默认禁用 → 自动加 `HostKeyAlgorithms=+ssh-rsa`
- root 默认空密码 → 自动管道送空密码，避免卡在密码提示

**用法**（Git Bash / WSL / MSYS2）：

```bash
./k3ssh.sh 192.168.2.1 'uci show wireless'
./k3ssh.sh 192.168.2.1 'iwinfo wlan0 assoclist'
```

> ⚠️ 依赖 root **空密码**。改完密码后本脚本不再适用，请用标准 `ssh` 登录；也正因如此，改密码是刷机后第一件事（docs/post-flash.md）。
