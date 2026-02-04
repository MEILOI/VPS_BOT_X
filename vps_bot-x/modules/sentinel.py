# -*- coding: utf-8 -*-
# modules/sentinel.py (V5.9.5 完整版 - 增强监控能力)
import asyncio, subprocess, re, time, os
from datetime import datetime, timedelta
from config import load_config, save_config, ALLOWED_USER_ID, AUDIT_FILE
from utils import log_audit
from telegram.ext import ContextTypes
import modules.backup as bk_mgr

# 全局状态追踪
FAILED_LOGINS = {}  # SSH 失败登录追踪
LAST_BACKUP_CHECK = None  # 上次备份检查时间

async def sentinel_loop(context: ContextTypes.DEFAULT_TYPE):
    """
    哨兵主监控循环
    每30秒执行一次全面检查
    """
    global LAST_BACKUP_CHECK
    
    while True:
        try:
            await asyncio.sleep(30)  # 30秒检查一次
            
            # 1. SSH 爆破检测
            await check_ssh_attacks(context)
            
            # 2. 流量预警 (已在 main.py 的 traffic_monitor 中实现,这里跳过)
            # await check_traffic_alerts(context)
            
            # 3. 定时备份检查
            await check_scheduled_backup(context)
            
            # 4. 系统资源预警
            await check_system_resources(context)
            
        except Exception as e:
            print(f"⚠️ 哨兵监控异常: {e}")
            await asyncio.sleep(60)

async def check_ssh_attacks(context: ContextTypes.DEFAULT_TYPE):
    """
    SSH 爆破检测
    监控 /var/log/auth.log 中的失败登录
    """
    global FAILED_LOGINS
    
    conf = load_config()
    threshold = conf.get('ban_threshold', 5)
    
    try:
        # 读取最近的失败登录记录
        log_cmd = "grep 'Failed password' /var/log/auth.log 2>/dev/null | tail -100"
        log_output = subprocess.getoutput(log_cmd)
        
        if not log_output:
            return
        
        # 正则提取 IP 地址
        pattern = r'from\s+([\d\.]+)\s+port'
        
        # 统计每个 IP 的失败次数
        ip_counts = {}
        for line in log_output.split('\n'):
            match = re.search(pattern, line)
            if match:
                ip = match.group(1)
                ip_counts[ip] = ip_counts.get(ip, 0) + 1
        
        # 检查是否有 IP 超过阈值
        for ip, count in ip_counts.items():
            # 检查是否已经处理过
            if ip in FAILED_LOGINS:
                continue
            
            if count >= threshold:
                # 自动封禁
                ban_cmd = f"iptables -I INPUT 1 -s {ip} -j DROP"
                subprocess.run(ban_cmd, shell=True)
                
                # 记录到全局追踪
                FAILED_LOGINS[ip] = {
                    'count': count,
                    'banned_at': datetime.now().isoformat()
                }
                
                # 记录审计日志
                log_audit("SENTINEL", "自动封禁", f"IP: {ip}, 失败次数: {count}")
                
                # 发送告警消息
                msg = (f"🚨 <b>SSH 爆破检测</b>\n\n"
                       f"🎯 IP: <code>{ip}</code>\n"
                       f"📊 失败尝试: <code>{count}</code> 次\n"
                       f"🛡️ 状态: 已自动封禁\n"
                       f"⏰ 时间: <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>")
                
                await context.bot.send_message(
                    chat_id=ALLOWED_USER_ID,
                    text=msg,
                    parse_mode="HTML"
                )
        
        # 清理超过24小时的追踪记录
        now = datetime.now()
        expired_ips = [
            ip for ip, data in FAILED_LOGINS.items()
            if (now - datetime.fromisoformat(data['banned_at'])).total_seconds() > 86400
        ]
        for ip in expired_ips:
            del FAILED_LOGINS[ip]
    
    except Exception as e:
        print(f"⚠️ SSH 检测异常: {e}")

async def check_scheduled_backup(context: ContextTypes.DEFAULT_TYPE):
    """
    检查是否需要执行定时备份
    """
    global LAST_BACKUP_CHECK
    
    conf = load_config()
    auto = conf.get('auto_backup', {})
    mode = auto.get('mode', 'off')
    
    if mode == 'off':
        return
    
    now = datetime.now()
    
    # 避免频繁检查 (至少间隔5分钟)
    if LAST_BACKUP_CHECK:
        if (now - LAST_BACKUP_CHECK).total_seconds() < 300:
            return
    
    LAST_BACKUP_CHECK = now
    
    try:
        # 获取上次执行时间
        last_run_str = auto.get('last_run', '')
        if last_run_str:
            last_run = datetime.fromisoformat(last_run_str)
        else:
            last_run = None
        
        should_run = False
        
        if mode == 'daily':
            # 每日备份
            target_time = auto.get('time', '03:00')
            target_hour, target_minute = map(int, target_time.split(':'))
            
            # 检查是否到达备份时间
            if now.hour == target_hour and now.minute == target_minute:
                if last_run is None or last_run.date() < now.date():
                    should_run = True
        
        elif mode == 'weekly':
            # 每周备份
            target_weekday = auto.get('weekday', 0)  # 0=周一
            target_time = auto.get('time', '03:00')
            target_hour, target_minute = map(int, target_time.split(':'))
            
            if now.weekday() == target_weekday:
                if now.hour == target_hour and now.minute == target_minute:
                    if last_run is None or (now - last_run).days >= 7:
                        should_run = True
        
        if should_run:
            # 执行备份
            file_path, msg = bk_mgr.run_backup_task(is_auto=True)
            
            # 更新最后执行时间
            auto['last_run'] = now.isoformat()
            conf['auto_backup'] = auto
            save_config(conf)
            
            if file_path:
                # 发送备份文件
                try:
                    with open(file_path, 'rb') as f:
                        await context.bot.send_document(
                            chat_id=ALLOWED_USER_ID,
                            document=f,
                            caption=f"⏰ <b>定时备份完成</b>\n\n{msg}",
                            parse_mode="HTML"
                        )
                    
                    # 删除临时文件
                    os.remove(file_path)
                    
                except Exception as e:
                    await context.bot.send_message(
                        chat_id=ALLOWED_USER_ID,
                        text=f"⚠️ 定时备份完成,但发送失败: {str(e)}",
                        parse_mode="HTML"
                    )
            else:
                # 备份失败,发送告警
                await context.bot.send_message(
                    chat_id=ALLOWED_USER_ID,
                    text=f"❌ <b>定时备份失败</b>\n\n{msg}",
                    parse_mode="HTML"
                )
    
    except Exception as e:
        print(f"⚠️ 定时备份检查异常: {e}")

async def check_system_resources(context: ContextTypes.DEFAULT_TYPE):
    """
    系统资源预警
    检查 CPU/内存/磁盘 是否超过阈值
    """
    try:
        import psutil
        import shutil
        
        conf = load_config()
        cpu_limit = conf.get('cpu_limit', 90)
        ram_limit = conf.get('ram_limit', 90)
        
        # CPU 检查
        cpu = psutil.cpu_percent(interval=1)
        if cpu > cpu_limit:
            msg = f"⚠️ <b>CPU 负载预警</b>\n\n🌡️ 当前: <code>{cpu:.1f}%</code>\n🛑 阈值: <code>{cpu_limit}%</code>"
            await context.bot.send_message(
                chat_id=ALLOWED_USER_ID,
                text=msg,
                parse_mode="HTML"
            )
            log_audit("SENTINEL", "CPU预警", f"{cpu:.1f}%")
        
        # 内存检查
        ram = psutil.virtual_memory()
        if ram.percent > ram_limit:
            msg = (f"⚠️ <b>内存使用预警</b>\n\n"
                   f"💾 当前: <code>{ram.percent:.1f}%</code>\n"
                   f"🛑 阈值: <code>{ram_limit}%</code>\n"
                   f"📊 可用: <code>{ram.available / 1024**3:.2f} GB</code>")
            await context.bot.send_message(
                chat_id=ALLOWED_USER_ID,
                text=msg,
                parse_mode="HTML"
            )
            log_audit("SENTINEL", "内存预警", f"{ram.percent:.1f}%")
        
        # 磁盘检查 (超过95%告警)
        disk = shutil.disk_usage("/")
        disk_percent = disk.used / disk.total * 100
        if disk_percent > 95:
            msg = (f"🚨 <b>磁盘空间严重不足</b>\n\n"
                   f"💾 已用: <code>{disk_percent:.1f}%</code>\n"
                   f"📊 剩余: <code>{(disk.total - disk.used) / 1024**3:.2f} GB</code>\n"
                   f"💡 建议立即清理")
            await context.bot.send_message(
                chat_id=ALLOWED_USER_ID,
                text=msg,
                parse_mode="HTML"
            )
            log_audit("SENTINEL", "磁盘预警", f"{disk_percent:.1f}%")
    
    except Exception as e:
        print(f"⚠️ 资源检查异常: {e}")

async def check_docker_health(context: ContextTypes.DEFAULT_TYPE):
    """
    Docker 容器健康检查
    检测容器是否异常退出
    """
    try:
        # 获取最近退出的容器
        cmd = "docker ps -a --filter 'status=exited' --format '{{.ID}}|{{.Names}}|{{.Status}}' --no-trunc"
        output = subprocess.getoutput(cmd)
        
        if not output.strip():
            return
        
        for line in output.split('\n'):
            if '|' not in line:
                continue
            
            parts = line.split('|')
            cid, name, status = parts[0][:12], parts[1], parts[2]
            
            # 检查退出码
            if 'Exited (0)' not in status:
                # 非正常退出
                msg = (f"⚠️ <b>容器异常退出</b>\n\n"
                       f"📦 名称: <code>{name}</code>\n"
                       f"🆔 ID: <code>{cid}</code>\n"
                       f"📉 状态: <code>{status}</code>")
                
                await context.bot.send_message(
                    chat_id=ALLOWED_USER_ID,
                    text=msg,
                    parse_mode="HTML"
                )
                
                log_audit("SENTINEL", "容器异常", f"{name} - {status}")
    
    except Exception as e:
        print(f"⚠️ Docker 健康检查异常: {e}")

# ✅ 新增: 网络异常检测
async def check_network_health(context: ContextTypes.DEFAULT_TYPE):
    """
    网络健康检查
    检测网络连接是否正常
    """
    try:
        # Ping 测试
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "2", "8.8.8.8"],
            capture_output=True,
            timeout=3
        )
        
        if result.returncode != 0:
            msg = "⚠️ <b>网络连接异常</b>\n\n无法连接到外网,请检查网络设置"
            await context.bot.send_message(
                chat_id=ALLOWED_USER_ID,
                text=msg,
                parse_mode="HTML"
            )
            log_audit("SENTINEL", "网络异常", "外网不可达")
    
    except Exception as e:
        print(f"⚠️ 网络检查异常: {e}")

# ✅ 新增: 获取哨兵状态摘要
def get_sentinel_status():
    """
    获取哨兵监控状态摘要
    用于显示在系统报告中
    """
    status = {
        'ssh_bans': len(FAILED_LOGINS),
        'last_backup': LAST_BACKUP_CHECK.isoformat() if LAST_BACKUP_CHECK else "从未执行",
        'monitoring': True
    }
    return status