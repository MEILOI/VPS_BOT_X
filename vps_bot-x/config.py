# -*- coding: utf-8 -*-
import json
import os

# 配置文件路径
CONFIG_FILE = "/root/sentinel_config.json"  # 使用主配置文件
SSH_FILE = "/root/.ssh/authorized_keys"
AUDIT_FILE = "/home/vboxuser/公共/vps_bot-x/bot.log"  # 审计日志文件路径

# 默认配置模板
DEFAULT_CONFIG = {
    "bot_token": "",
    "admin_id": 0,
    "server_remark": "VPS_bot-X",
    "traffic_limit_gb": 1024,
    "backup_paths": [],
    "daily_report_times": ["08:00", "20:00"]
}

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return DEFAULT_CONFIG
    try:
        with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    except:
        return DEFAULT_CONFIG

def save_config(config):
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error saving config: {e}")

# 加载配置供 main.py 使用
_conf = load_config()

# 映射 main.py 需要的变量名
TOKEN = _conf.get("bot_token", "")
ALLOWED_USER_ID = _conf.get("admin_id", 0)
ALLOWED_USER_IDS = [ALLOWED_USER_ID] if ALLOWED_USER_ID else []

# 配置加载函数
def load_ports():
    # 从配置中加载端口信息
    config = load_config()
    return config.get('ports', {})

def save_ports(data):
    # 保存端口信息到配置
    config = load_config()
    config['ports'] = data
    save_config(config)