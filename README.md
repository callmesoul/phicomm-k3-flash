# phicomm-k3-flash

斐讯 K3 路由器刷机指南与工具集 —— 基于真实刷机过程整理，方法、流程、坑全记录。

K3 是一台 2017 年的旗舰路由（BCM4709C + 双 BCM4366），原厂固件已停更。本项目整理了一条**经过实测验证**的刷机路线（CFE + TFTP），并持续收集不同固件版本的兼容性记录，供社区参考与贡献。

> ⚠️ **免责声明**：刷机有变砖风险，请确认理解了每一步再操作。本项目内容按"现状"提供，不提供任何担保。刷机前请先阅读 [docs/pitfalls.md](docs/pitfalls.md)。

## 目录结构

```
phicomm-k3-flash/
├── README.md                 本文件
├── SKILL.md                  Claude Code Skill 入口（可选安装）
├── CONTRIBUTING.md           贡献指南（如何添加新固件版本/新坑）
├── docs/
│   ├── flashing-guide.md     完整刷机流程（进 CFE → TFTP → do.htm → 重启）
│   ├── pitfalls.md           坑清单（现象 → 原因 → 解决）
│   ├── post-flash.md         刷后必做配置与常用诊断
│   └── compatibility/        固件版本兼容矩阵（欢迎贡献）
│       ├── README.md         矩阵总览与条目模板
│       └── openwrt-19.07.10.md
└── tools/
    ├── tftpd.py              极简 TFTP 服务器（RFC 1350，专为 K3 CFE 定制）
    ├── k3ssh.sh              SSH 助手（适配 Windows OpenSSH + 老版 dropbear）
    └── README.md             工具说明
```

## 快速开始

1. 阅读 [docs/flashing-guide.md](docs/flashing-guide.md)，核对 [docs/compatibility/README.md](docs/compatibility/README.md) 中目标固件的兼容记录
2. 下载目标固件并**核对 sha256**（不比对就刷 = 赌命）
3. 电脑直连 K3 LAN 口 → 进 CFE → 启动 `tools/tftpd.py` → `do.htm` 刷写
4. 断电重启 → 初始化新系统 → 按 [docs/post-flash.md](docs/post-flash.md) 完成必做配置
5. 把你遇到的新坑/新固件的实测结果贡献回来（见 [CONTRIBUTING.md](CONTRIBUTING.md)）

## 作为 Claude Code Skill 使用

把本仓库克隆后，在仓库内工作时 `SKILL.md` 会自动被 Claude Code 识别；
也可以复制到用户级 skills 目录：

```
mkdir -p ~/.claude/skills/phicomm-k3-flash
cp SKILL.md docs tools -r ~/.claude/skills/phicomm-k3-flash/
```

之后对 Claude 说"帮我把 K3 刷成 OpenWrt"即可由它按本仓库流程引导。

## 兼容矩阵

| 固件 | 版本 | CFE 刷入 | 状态 | 记录 |
|---|---|---|---|---|
| OpenWrt | 19.07.10 | ✅ 实测 | ✅ 稳定（含已知坑） | [详情](docs/compatibility/openwrt-19.07.10.md) |

其他固件版本（OpenWrt 21.02+、官改、梅林等）欢迎按 [模板](docs/compatibility/README.md#条目模板) 贡献。

## 许可证

[MIT](LICENSE) © 2026 phicomm-k3-flash contributors
