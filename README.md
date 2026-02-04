# 🚀 VPS 遥控器 (VPS Remote Controller)

[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.7+-blue.svg)](https://www.python.org/downloads/)
[![Telegram](https://img.shields.io/badge/telegram-bot-blue.svg)](https://telegram.org/)

通过 Telegram Bot 轻松管理你的 VPS 服务器 - 系统监控、Docker 管理、安全防护一应俱全!

## ✨ 核心功能

- 📊 **系统监控**: CPU/内存/磁盘/流量实时监控
- 🐳 **Docker 管理**: 容器启停、日志查看、健康检查
- 🛡️ **安全防护**: SSH 爆破防御、IP 黑名单、审计日志
- 📈 **流量管理**: 月流量统计、预警、排行榜
- 🌐 **网络工具**: 端口扫描、内网控制、连接监控
- ☁️ **备份管理**: 定时备份、一键恢复

## 🚀 一键安装

### 方法1: 一键脚本 (推荐)

```bash
curl -fsSL https://raw.githubusercontent.com/MEILOI/VPS_BOT_X/main/vps_bot-x/install.sh -o install.sh && chmod +x install.sh && bash install.sh
```


## 📋 系统要求

- **操作系统**: Ubuntu 18.04+ / Debian 10+
- **Python**: 3.7 或更高版本
- **权限**: Root 用户
- **可选**: Docker (用于容器管理功能)

## 🔧 配置

### 获取 Bot Token

1. 在 Telegram 中找到 [@BotFather](https://t.me/BotFather)
2. 发送 `/newbot` 创建新 Bot
3. 复制获得的 Token

### 获取 User ID

1. 在 Telegram 中找到 [@userinfobot](https://t.me/userinfobot)
2. 发送任意消息
3. 复制返回的 ID 数字

### 配置文件

安装时会提示输入以上信息,或手动编辑配置文件:

```bash
nano /root/sentinel_config.json
```

配置示例:

```json
{
  "bot_token": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
  "admin_id": 123456789,
  "server_remark": "我的VPS",
  "ban_threshold": 5,
  "cpu_limit": 90,
  "ram_limit": 90,
  "traffic_limit_gb": 1024,
  "billing_day": 1,
  "daily_warn_gb": 50
}
```

## 📱 使用

### 启动 Bot

安装完成后,在 Telegram 中:
1. 搜索你的 Bot 名称
2. 发送 `/start` 或 `/kk`

### 管理服务

```bash
# 进入控制台
kk

# 查看服务状态
systemctl status vpsbot

# 查看日志
journalctl -u vpsbot -f

# 重启服务
systemctl restart vpsbot
```

## 🎯 主要命令

| 命令 | 说明 |
|------|------|
| `/start` 或 `/kk` | 打开主菜单 |
| `kk` (终端) | 进入管理控制台 |
| `systemctl status vpsbot` | 查看服务状态 |
| `journalctl -u vpsbot -f` | 查看实时日志 |

## 📂 目录结构

```
/root/vps_bot/              # 安装目录
├── main.py                 # 主程序
├── config.py               # 配置管理
├── modules/                # 功能模块
│   ├── system.py          # 系统监控
│   ├── docker_mgr.py      # Docker 管理
│   ├── network.py         # 网络工具
│   ├── backup.py          # 备份管理
│   ├── sentinel.py        # 安全哨兵
│   └── settings.py        # 设置管理
└── utils.py               # 工具函数

/root/sentinel_config.json  # 配置文件
/root/sentinel_audit.log    # 审计日志
```

## 🔍 故障排查

### Bot 无响应

```bash
# 查看服务状态
systemctl status vpsbot

# 查看错误日志
journalctl -u vpsbot -n 50

# 重启服务
systemctl restart vpsbot
```

### 流量统计不准确

```bash
# 检查 vnstat
systemctl status vnstat

# 重启 vnstat
systemctl restart vnstat
```

### 更多问题

查看 [故障排查指南](TROUBLESHOOTING.md)

## 🔐 安全建议

1. ✅ 保护好 Bot Token,不要泄露
2. ✅ 只添加信任的用户到管理员列表
3. ✅ 定期检查审计日志
4. ✅ 启用自动备份功能
5. ✅ 配合防火墙使用

## 🆕 更新日志

### V6.0 (2025-02-05)
- ✨ 支持从 GitHub 一键安装
- 🎨 优化安装脚本和界面
- 🔧 修复黑名单显示问题
- 📊 增强 IP 地理信息展示
- 🛡️ 优化防火墙统计逻辑

### V5.9
- 首个公开版本

## 🤝 贡献

欢迎提交 Issue 和 Pull Request!

## 📝 许可证

[MIT License](LICENSE)

## 📧 联系

- GitHub Issues: [提交问题](https://github.com/MEILOI/VPS_BOT_X/issues)
- Telegram: 待添加

---

**⭐ 如果这个项目对你有帮助,请给个 Star!**

## 📸 截图预览

_待添加截图_

## ❓ 常见问题

**Q: 支持哪些系统?**  
A: Ubuntu 18.04+, Debian 10+, 理论上支持所有 systemd 的 Linux 系统

**Q: 必须要 Docker 吗?**  
A: 不是,Docker 是可选的。不安装 Docker 也能使用 90% 的功能

**Q: 流量统计准确吗?**  
A: 基于 vnstat,准确度很高。首次安装需要等待 5-10 分钟收集数据

**Q: 可以管理多台服务器吗?**  
A: 可以,每台服务器安装一个 Bot,用不同的 Token

**Q: 支持多管理员吗?**  
A: 支持,在配置文件中将 `admin_id` 改为数组格式

**Q: 数据会丢失吗?**  
A: 配置文件和审计日志都保存在 `/root/`,重装系统前记得备份

---

**🌟 Star History**

[![Star History Chart](https://api.star-history.com/svg?repos=MEILOI/VPS_BOT_X&type=Date)](https://star-history.com/#MEILOI/VPS_BOT_X&Date)
