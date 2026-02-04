bash
git clone https://github.com/MEILOI/VPS_BOT_X.git
cd VPS_BOT_X/vps_bot-x
bash install.sh

# 定义颜色
GREEN='\033[0;32m'
SKY='\033[0;36m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m'

clear
echo -e "${SKY}==============================================${NC}"
echo -e "    VPS 遥控器 (Sentinel-X) 安装向导 V6.5    "
echo -e "${SKY}==============================================${NC}"
echo ""

# ✅ Root 权限检查
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}错误: 请使用 root 用户运行此脚本!${NC}"
   exit 1
fi

# ✅ 路径定义 (明确指向 /root/vps_bot-x)
SOURCE_DIR=$(cd $(dirname $0); pwd)
TARGET_DIR="/root/vps_bot-x"

echo -e "${GREEN}>>> [1/6] 检查系统环境...${NC}"

# Python 版本检查
PYTHON_VERSION=$(python3 --version 2>&1 | awk '{print $2}')
echo -e "${SKY}    系统版本: $(cat /etc/os-release | grep PRETTY_NAME | cut -d'"' -f2)${NC}"
echo -e "${SKY}    Python 版本: $PYTHON_VERSION${NC}"

echo -e "${GREEN}>>> [2/6] 正在安装系统依赖...${NC}"
apt update -y > /dev/null 2>&1
apt install -y python3 python3-pip curl nano git vnstat nethogs iptables net-tools > /dev/null 2>&1

# 配置 vnstat
systemctl enable vnstat > /dev/null 2>&1
systemctl restart vnstat > /dev/null 2>&1

# Docker 检查
if ! command -v docker &> /dev/null; then
    echo -e "${YELLOW}警告: 未检测到 Docker，正在自动尝试安装...${NC}"
    curl -fsSL https://get.docker.com | sh > /dev/null 2>&1
    systemctl enable docker > /dev/null 2>&1
    systemctl start docker > /dev/null 2>&1
fi

echo -e "${GREEN}>>> [3/6] 同步代码并安装 Python 库...${NC}"

# ✅ 代码同步逻辑：如果是从仓库安装，则复制到 /root/vps_bot-x
if [ "$SOURCE_DIR" != "$TARGET_DIR" ]; then
    echo -e "${SKY}    正在同步代码到 $TARGET_DIR...${NC}"
    mkdir -p "$TARGET_DIR"
    cp -r "$SOURCE_DIR"/* "$TARGET_DIR/"
fi

# 安装依赖
pip3 install python-telegram-bot psutil requests netifaces --break-system-packages > /dev/null 2>&1

echo -e "${GREEN}>>> [4/6] 配置初始化...${NC}"
CONFIG_FILE="/root/sentinel_config.json"

if [ ! -f "$CONFIG_FILE" ]; then
    echo -e "${YELLOW}未检测到配置文件，开始引导...${NC}"
    read -p "请输入 Bot Token: " INPUT_TOKEN
    read -p "请输入管理员 User ID: " INPUT_ID
    read -p "服务器备注 (如: 搬瓦工): " INPUT_NAME
    INPUT_NAME=${INPUT_NAME:-MyVPS}

    cat > "$CONFIG_FILE" <<EOF
{
  "bot_token": "${INPUT_TOKEN}",
  "admin_id": ${INPUT_ID},
  "server_remark": "${INPUT_NAME}",
  "ban_threshold": 5,
  "ban_duration": "permanent",
  "daily_report_times": ["08:00", "20:00"],
  "traffic_limit_gb": 1024,
  "billing_day": 1,
  "daily_warn_gb": 50,
  "traffic_daily_report": true,
  "backup_paths": ["${TARGET_DIR}"],
  "backup_exclude": ["*.log", "*.tmp", "__pycache__", "cache"],
  "auto_backup": {"mode": "off", "time": "03:00"}
}
EOF
else
    echo -e "${GREEN}    ✓ 检测到现有配置，已跳过初始化${NC}"
fi

echo -e "${GREEN}>>> [5/6] 注册系统服务...${NC}"

# 生成服务文件 (指向 vps_bot-x)
cat > /etc/systemd/system/vpsbot.service <<EOF
[Unit]
Description=VPS Remote Controller Bot X
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=${TARGET_DIR}
ExecStart=/usr/bin/python3 ${TARGET_DIR}/main.py
Restart=always
RestartSec=10
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable vpsbot > /dev/null 2>&1
systemctl restart vpsbot

echo -e "${GREEN}>>> [6/6] 安装快捷指令 'kk'...${NC}"

cat > /usr/bin/kk <<EOFKK
#!/bin/bash
# 控制台快捷脚本
while true; do
    clear
    echo -e "\033[0;36m==============================\033[0m"
    echo -e "    VPS 遥控器-X 控制台       "
    echo -e "\033[0;36m==============================\033[0m"
    echo -e "  [1] 启动  [2] 重启  [3] 停止"
    echo -e "  [4] 日志  [5] 配置  [0] 退出"
    read -p "请选择: " choice
    case \$choice in
        1) systemctl start vpsbot ;;
        2) systemctl restart vpsbot ;;
        3) systemctl stop vpsbot ;;
        4) journalctl -u vpsbot -f -n 50 ;;
        5) nano /root/sentinel_config.json ;;
        0) exit 0 ;;
    esac
    read -p "按回车继续..."
done
EOFKK

chmod +x /usr/bin/kk

echo -e "${GREEN}🎉 安装完成！请在 TG 发送 /start 开始使用。${NC}"
echo -e "${SKY}代码目录: ${TARGET_DIR}${NC}"
echo -e "${SKY}配置文件: ${CONFIG_FILE}${NC}"
