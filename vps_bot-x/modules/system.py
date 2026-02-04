# -*- coding: utf-8 -*-
# modules/system.py (V5.9.5 最终优化版)
import psutil, subprocess, json, re, shutil, os
from datetime import datetime, timedelta
from config import load_config, save_config
import modules.docker_mgr as dk_mgr
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# --- 1. 核心数据采集 ---

def get_public_ip():
    """获取公网IP (多重降级方案)"""
    sources = [
        "curl -s --max-time 2 ifconfig.me",
        "curl -s --max-time 2 http://checkip.amazonaws.com",
        "curl -s --max-time 2 icanhazip.com",
        "curl -s --max-time 2 ipinfo.io/ip"
    ]
    
    for cmd in sources:
        try:
            ip = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL).decode().strip()
            # 验证IP格式
            if ip and len(ip) < 50 and ip.count('.') == 3:
                return ip
        except:
            continue
    
    return "未知IP"

def get_traffic_stats(period='day'):
    """
    获取流量数值(GB)
    兼容 vnstat --json 格式及流量校准偏差值
    """
    conf = load_config()
    import shutil
    vnstat_path = shutil.which("vnstat") or "vnstat"
    
    try:
        # 尝试读取 vnstat JSON 数据
        raw = subprocess.check_output([vnstat_path, "-d", "--json"], stderr=subprocess.DEVNULL).decode('utf-8')
        data = json.loads(raw)['interfaces']
        
        # ✅ 优化: 找到总流量最大的网卡 (排除 lo)
        target_interface = None
        max_total = -1
        for iface in data:
            if iface['name'] == 'lo': continue
            current_total = iface['traffic']['total']['rx'] + iface['traffic']['total']['tx']
            if current_total > max_total:
                max_total = current_total
                target_interface = iface
        
        if not target_interface:
            target_interface = data[0]
            
        traffic_data = target_interface['traffic']['day']
        today = datetime.now()
        
        if period == 'day':
            # 查找今天的流量记录
            for i in traffic_data:
                if i['date']['day'] == today.day and i['date']['month'] == today.month:
                    return (i['rx'] + i['tx']) / 1024**3  # 转换为 GB
            return 0.0
        
        # 月流量计算
        b_day = conf.get('billing_day', 1)
        if today.day >= b_day:
            start_date = today.replace(day=b_day, hour=0, minute=0, second=0)
        else:
            last_month_end = today.replace(day=1) - timedelta(days=1)
            try: start_date = last_month_end.replace(day=b_day)
            except: start_date = last_month_end.replace(day=28)
            
        total_bytes = 0
        for i in traffic_data:
            entry_dt = datetime(i['date']['year'], i['date']['month'], i['date']['day'])
            if entry_dt >= start_date:
                total_bytes += (i['rx'] + i['tx'])
        
        val = total_bytes / 1024**3 + conf.get('traffic_offset_gb', 0.0)
        return max(0.0, val)
        
    except Exception as e:
        return 0.0

def check_traffic_alert():
    """检测日流量是否超过预警阈值"""
    conf = load_config()
    limit = conf.get('daily_warn_gb', 50)
    today_str = datetime.now().strftime("%Y-%m-%d")
    
    # 幂等性检查：今日已报警则跳过
    if conf.get('last_daily_warn_date') == today_str:
        return None 

    used = get_traffic_stats('day')
    if used > limit:
        conf['last_daily_warn_date'] = today_str
        save_config(conf)
        return used
    return None

# --- 1.5 🔧 一键故障诊断 ---

def get_auto_diagnosis():
    """
    一键诊断系统问题
    检查项目：磁盘、内存、僵尸进程、网络、Docker
    """
    issues = []
    warnings = []
    goods = []
    
    # 1. 磁盘检查
    disk = shutil.disk_usage("/")
    disk_percent = disk.used / disk.total * 100
    disk_free_gb = (disk.total - disk.used) / 1024**3
    
    if disk_percent > 90:
        issues.append(f"❌ <b>磁盘严重不足</b> ({disk_percent:.1f}% 已用)")
        issues.append(f"   建议: 清理日志或删除无用文件")
    elif disk_percent > 80:
        warnings.append(f"⚠️ 磁盘空间紧张 ({disk_percent:.1f}% 已用)")
    else:
        goods.append(f"✅ 磁盘空间充足 (剩余 {disk_free_gb:.1f} GB)")
    
    # 2. 内存检查
    mem = psutil.virtual_memory()
    swap = psutil.swap_memory()
    
    if mem.percent > 90:
        issues.append(f"❌ <b>内存严重不足</b> ({mem.percent:.1f}% 已用)")
        # 找出内存占用最高的进程
        try:
            procs = sorted(
                psutil.process_iter(['name', 'memory_percent']), 
                key=lambda p: p.info['memory_percent'] or 0,
                reverse=True
            )[:3]
            issues.append(f"   占用最高:")
            for p in procs:
                issues.append(f"     • {p.info['name']}: {p.info['memory_percent']:.1f}%")
        except:
            pass
    elif mem.percent > 75:
        warnings.append(f"⚠️ 内存使用偏高 ({mem.percent:.1f}%)")
    else:
        goods.append(f"✅ 内存充足 ({mem.available / 1024**3:.1f} GB 可用)")
    
    if swap.percent > 50:
        warnings.append(f"⚠️ 交换区使用 {swap.percent:.1f}% (性能可能下降)")
    
    # 3. CPU 检查
    cpu_percent = psutil.cpu_percent(interval=1)
    if cpu_percent > 90:
        issues.append(f"❌ <b>CPU 负载过高</b> ({cpu_percent:.1f}%)")
    elif cpu_percent > 70:
        warnings.append(f"⚠️ CPU 使用偏高 ({cpu_percent:.1f}%)")
    else:
        goods.append(f"✅ CPU 正常 ({cpu_percent:.1f}%)")
    
    # 4. 僵尸进程检查
    try:
        zombies = [p for p in psutil.process_iter(['status']) if p.info['status'] == 'zombie']
        if len(zombies) > 0:
            warnings.append(f"⚠️ 检测到 {len(zombies)} 个僵尸进程")
    except:
        pass
    
    # 5. Docker 检查
    try:
        docker_ps = subprocess.getoutput("docker ps 2>&1")
        if "Cannot connect" in docker_ps or "permission denied" in docker_ps:
            issues.append(f"❌ <b>Docker 服务异常</b>")
            issues.append(f"   建议: 执行 <code>systemctl restart docker</code>")
        else:
            goods.append(f"✅ Docker 服务正常")
    except:
        warnings.append(f"⚠️ 无法检测 Docker 状态")
    
    # 6. 网络检查
    try:
        resp = subprocess.run(
            ["ping", "-c", "1", "-W", "2", "8.8.8.8"], 
            capture_output=True, 
            timeout=3
        )
        if resp.returncode == 0:
            goods.append(f"✅ 网络连接正常")
        else:
            warnings.append(f"⚠️ 外网连接异常")
    except:
        warnings.append(f"⚠️ 网络检测超时")
    
    # 7. SSH 安全检查
    try:
        ssh_log = subprocess.getoutput("grep 'Failed password' /var/log/auth.log 2>/dev/null | tail -5")
        if ssh_log:
            failed_count = len(ssh_log.split('\n'))
            if failed_count >= 5:
                warnings.append(f"⚠️ 检测到 SSH 爆破尝试 (近期 {failed_count} 次)")
    except:
        pass
    
    # 8. ✅ 新增: 系统运行时间检查
    try:
        uptime_info = subprocess.getoutput("uptime -p")
        if uptime_info:
            goods.append(f"⏱️ 系统运行时间: {uptime_info.replace('up ', '')}")
    except:
        pass
    
    # 生成报告
    txt = "🔧 <b>一键故障诊断报告</b>\n━━━━━━━━━━━━━━━\n\n"
    
    if issues:
        txt += "❌ <b>严重问题</b> (需立即处理):\n"
        txt += "\n".join(issues) + "\n\n"
    
    if warnings:
        txt += "⚠️ <b>警告信息</b> (建议关注):\n"
        txt += "\n".join(warnings) + "\n\n"
    
    if goods:
        txt += "✅ <b>正常项目</b>:\n"
        txt += "\n".join(goods) + "\n\n"
    
    if not issues and not warnings:
        txt += "🎉 <b>系统运行完美！未发现任何问题。</b>\n"
    
    # 智能建议
    txt += "━━━━━━━━━━━━━━━\n💡 <b>智能建议</b>:\n"
    if disk_percent > 80:
        txt += "• 执行系统清理可释放空间\n"
    if mem.percent > 80:
        txt += "• 考虑重启高占用容器\n"
    if issues or warnings:
        txt += "• 建议定期运行诊断工具\n"
    else:
        txt += "• 系统健康，保持现状即可\n"
    
    kb = [
        [InlineKeyboardButton("🧹 执行清理", callback_data="tool_clean")],
        [InlineKeyboardButton("🏥 容器体检", callback_data="health_check")],
        [InlineKeyboardButton("🔄 重新诊断", callback_data="sys_diagnose")],
        [InlineKeyboardButton("🔙 返回", callback_data="sys_report")]
    ]
    
    return txt, InlineKeyboardMarkup(kb)

# --- 2. 🌡️ 系统体检报告 ---

def get_system_report():
    """生成详尽的体检报告文本"""
    conf = load_config()
    ip = get_public_ip()
    cpu = psutil.cpu_percent(interval=0.5)
    ram = psutil.virtual_memory()
    disk = shutil.disk_usage("/")
    
    used_m = get_traffic_stats('month')
    used_d = get_traffic_stats('day')
    limit = conf.get('traffic_limit_gb', 1000)
    
    # 进度条逻辑
    perc = (used_m / limit * 100) if limit > 0 else 0
    bar_len = 10
    filled = int(perc / (100 / bar_len))
    bar = f"{'▓' * filled}{'░' * (bar_len - filled)} {perc:.1f}%"
    
    # Docker 状态
    try:
        docks = dk_mgr.get_containers()
        d_run = len([d for d in docks if d['state'] == 'running'])
        d_total = len(docks)
    except:
        d_run, d_total = 0, 0
    
    # 统计防火墙封禁数 (只统计DROP规则)
    try:
        fw_out = subprocess.getoutput("iptables -S INPUT 2>/dev/null | grep 'DROP'")
        # 只匹配 -j DROP 的规则,排除 0.0.0.0/0 这种全局规则
        ban_ips = re.findall(r'-A INPUT -s ([\d\./]+).*?-j DROP', fw_out)
        ban_ips = [ip for ip in ban_ips if ip != "0.0.0.0/0"]
        ban_count = len(ban_ips)
    except:
        ban_count = 0

    txt = (f"🏥 <b>VPS 系统体检报告</b>\n"
           f"━━━━━━━━━━━━━━━\n"
           f"📛 <b>备注</b>: <code>{conf.get('server_remark', 'MyVPS')}</code>\n"
           f"🌐 <b>IP</b>: <code>{ip}</code>\n"
           f"🌡️ <b>负载</b>: <code>{cpu}%</code> CPU | <code>{ram.percent}%</code> RAM\n"
           f"💾 <b>硬盘</b>: <code>{int(disk.used/1024**3)}G</code> / <code>{int(disk.total/1024**3)}G</code>\n"
           f"🐳 <b>Docker</b>: <code>{d_run}</code> 运行中 / <code>{d_total}</code> 总计\n"
           f"💰 <b>月流量</b>: <code>{used_m:.2f} G</code> / <code>{limit} G</code>\n"
           f"🚨 <b>今日流量</b>: <code>{used_d:.2f} G</code>\n"
           f"📈 <b>使用率</b>: <code>{bar}</code>\n"
           f"🛡️ <b>防火墙</b>: 已封禁 <code>{ban_count}</code> 个恶意 IP\n")
            
    # 构建按钮(添加黑名单快速入口)
    kb_rows = [
        [InlineKeyboardButton("🏥 容器体检", callback_data="health_check"), 
         InlineKeyboardButton("🔧 故障诊断", callback_data="sys_diagnose")],
    ]
    
    # 如果有封禁IP,添加快速查看按钮
    if ban_count > 0:
        kb_rows.append([InlineKeyboardButton(f"🚫 查看黑名单 ({ban_count}个)", callback_data="ban_list")])
    
    kb_rows.extend([
        [InlineKeyboardButton("🔄 重新体检", callback_data="sys_report")],
        [InlineKeyboardButton("🔙 返回主菜单", callback_data="back")]
    ])
    
    kb = InlineKeyboardMarkup(kb_rows)
    return txt, kb

# --- 3. 🧹 智能扫地僧 ---

CLEAN_STATES = {}

CLEAN_TASKS = {
    'apt': {
        'name': '系统缓存', 
        'cmd': 'apt-get autoremove -y && apt-get clean', 
        'default': True
    },
    'log': {
        'name': '日志瘦身', 
        'cmd': 'journalctl --vacuum-size=50M', 
        'default': True
    },
    'tmp': {
        'name': '临时文件', 
        'cmd': 'find /tmp -type f -atime +7 -delete 2>/dev/null || true',  # ✅ 优化: 只删除7天前的临时文件
        'default': False
    }
}

def get_clean_menu(uid):
    """构建清理菜单"""
    if uid not in CLEAN_STATES:
        CLEAN_STATES[uid] = {k: v['default'] for k, v in CLEAN_TASKS.items()}
    st = CLEAN_STATES[uid]
    
    txt = (f"🧹 <b>智能扫地僧</b>\n"
           f"━━━━━━━━━━━━━━━\n"
           f"请配置清理策略 (🟢开启 / 🔴关闭)：\n\n"
           f"💡 <b>提示</b>: Docker 镜像和容器请到 <code>容器指挥官</code> 中管理\n")
    
    kb = []
    row = []
    for k, v in CLEAN_TASKS.items():
        icon = "🟢" if st[k] else "🔴"
        row.append(InlineKeyboardButton(f"{icon} {v['name']}", callback_data=f"clean_sw_{k}"))
        if len(row) == 2:
            kb.append(row)
            row = []
    if row:
        kb.append(row)
    
    kb.append([InlineKeyboardButton("▶️ 立即执行清理", callback_data="clean_run")])
    kb.append([InlineKeyboardButton("🔙 返回工具箱", callback_data="tool_box")])
    
    return txt, InlineKeyboardMarkup(kb)

def toggle_clean_option(uid, key):
    """切换清理项开关"""
    if uid in CLEAN_STATES and key in CLEAN_STATES[uid]:
        CLEAN_STATES[uid][key] = not CLEAN_STATES[uid][key]
    return get_clean_menu(uid)

def run_smart_clean(uid):
    """执行清理任务"""
    if uid not in CLEAN_STATES:
        return "⚠️ 请重新打开菜单", None
    
    st = CLEAN_STATES[uid]
    res = []
    
    for k, v in CLEAN_TASKS.items():
        if st[k]:
            try:
                # 获取清理前的磁盘使用
                disk_before = shutil.disk_usage("/").used
                
                # 执行清理命令
                subprocess.run(v['cmd'], shell=True, check=True, timeout=60, 
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                
                # 计算释放空间
                disk_after = shutil.disk_usage("/").used
                freed = (disk_before - disk_after) / 1024**2  # MB
                
                if freed > 0:
                    res.append(f"✅ {v['name']}: 释放 {freed:.1f} MB")
                else:
                    res.append(f"✅ {v['name']}: 完成")
                    
            except subprocess.TimeoutExpired:
                res.append(f"⏱️ {v['name']}: 超时")
            except Exception as e:
                res.append(f"❌ {v['name']}: 失败")
    
    if not res:
        res.append("⚠️ 未选择任何清理项")
    
    report = "🧹 <b>清理报告</b>\n━━━━━━━━━━━━━━━\n" + "\n".join(res)
    report += "\n\n💡 Docker 相关清理请前往 <code>容器指挥官 > 镜像管理</code>"
    
    kb = InlineKeyboardMarkup([
        [InlineKeyboardButton("🔄 再次清理", callback_data="tool_clean")],
        [InlineKeyboardButton("🔙 返回工具箱", callback_data="tool_box")]
    ])
    
    return report, kb

def check_system_limits():
    """检查系统资源是否超过极限 (90%)"""
    alerts = []
    
    # 1. CPU
    cpu = psutil.cpu_percent(interval=0.5)
    if cpu > 90:
        alerts.append(f"🔥 <b>CPU 负载过高</b>: <code>{cpu}%</code>")
        
    # 2. RAM
    ram = psutil.virtual_memory()
    if ram.percent > 90:
        alerts.append(f"🧠 <b>內存即將耗盡</b>: <code>{ram.percent}%</code> (剩餘 {ram.available/1024**2:.1f}MB)")
        
    # 3. Disk
    disk = shutil.disk_usage("/")
    disk_p = (disk.used / disk.total) * 100
    if disk_p > 90:
        alerts.append(f"💾 <b>磁盤空間不足</b>: <code>{disk_p:.1f}%</code> (剩餘 {disk.free/1024**3:.2f}GB)")
        
    return alerts