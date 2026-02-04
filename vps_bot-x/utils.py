# -*- coding: utf-8 -*-
# utils.py - 工具函数模块 (V5.9.3 完整版)
import subprocess, requests, os, glob, zlib
from datetime import datetime
from config import AUDIT_FILE, TOKEN, ALLOWED_USER_ID

def get_public_ip():
    """获取公网IP地址"""
    try:
        ip = subprocess.getoutput("curl -s --max-time 2 http://checkip.amazonaws.com").strip()
        if ip and "curl" not in ip.lower() and len(ip) < 50:
            return ip
    except:
        pass
    
    # 降级方案
    try:
        ip = subprocess.getoutput("curl -s --max-time 2 ifconfig.me").strip()
        if ip and len(ip) < 50:
            return ip
    except:
        pass
    
    return "未知IP"

def get_ip_info(ip):
    """获取IP地理信息"""
    # 过滤内网IP
    if ip.startswith("127.") or ip.startswith("10.") or ip.startswith("192.168."):
        return "🏠 内网"
    
    try:
        r = requests.get(
            f"http://ip-api.com/json/{ip}?lang=zh-CN&fields=status,country,city", 
            timeout=2
        ).json()
        
        if r.get('status') == 'success':
            country = r.get('country', '')
            city = r.get('city', '')
            return f"📍 {country} {city}"
        else:
            return "📍 未知"
    except:
        return "📍 查询失败"

def get_audit_tail(n=10):
    """
    读取审计日志的最后 N 行
    这是之前遗漏的关键函数!
    """
    if not os.path.exists(AUDIT_FILE):
        return "📭 暂无日志记录"
    
    try:
        # 使用 tail 命令读取最后 n 行
        result = subprocess.getoutput(f"tail -n {n} {AUDIT_FILE}")
        if result.strip():
            return result
        else:
            return "📭 日志文件为空"
    except Exception as e:
        return f"❌ 读取失败: {str(e)}"

def log_audit(actor, action, target):
    """
    记录操作审计日志
    格式: [时间] [操作者] 动作: 目标
    """
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        with open(AUDIT_FILE, 'a', encoding='utf-8') as f:
            f.write(f"[{timestamp}] [{actor}] {action}: {target}\n")
    except Exception as e:
        print(f"⚠️ 日志记录失败: {e}")

def get_path_id(path):
    """为路径生成唯一ID (用于备份标识)"""
    return str(zlib.crc32(path.encode('utf-8')))

async def split_and_send(file_path, caption):
    """
    发送文件到 Telegram
    简化版实现,处理大文件分片
    """
    url = f"https://api.telegram.org/bot{TOKEN}/sendDocument"
    
    if not os.path.exists(file_path):
        return "❌ 文件不存在"
    
    file_size = os.path.getsize(file_path)
    
    # Telegram 文件大小限制: 50MB
    if file_size > 49 * 1024 * 1024:
        return f"❌ 文件过大 ({file_size / 1024**2:.1f} MB),请手动处理"
    
    try:
        with open(file_path, 'rb') as f:
            response = requests.post(
                url, 
                data={'chat_id': ALLOWED_USER_ID, 'caption': caption}, 
                files={'document': f}, 
                timeout=120
            )
            
            if response.status_code == 200:
                return "✅ 发送成功"
            else:
                return f"❌ 发送失败: {response.text[:100]}"
    except Exception as e:
        return f"❌ 发送失败: {str(e)}"

def format_bytes(bytes_value):
    """格式化字节数为人类可读格式"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_value < 1024.0:
            return f"{bytes_value:.2f} {unit}"
        bytes_value /= 1024.0
    return f"{bytes_value:.2f} PB"

def safe_run_command(cmd, timeout=30):
    """
    安全执行系统命令
    带超时保护和异常捕获
    """
    try:
        result = subprocess.run(
            cmd,
            shell=True,
            capture_output=True,
            timeout=timeout,
            text=True
        )
        return result.stdout.strip() if result.returncode == 0 else result.stderr.strip()
    except subprocess.TimeoutExpired:
        return f"❌ 命令超时 (>{timeout}秒)"
    except Exception as e:
        return f"❌ 执行失败: {str(e)}"