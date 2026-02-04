# -*- coding: utf-8 -*-
# modules/health_check.py (V5.9.4 优化版 - 增强诊断能力)
import subprocess, json, time, requests
from datetime import datetime, timedelta
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# 全局缓存：记录容器重启历史
RESTART_HISTORY = {}

def get_container_health_data():
    """
    采集所有容器的健康数据
    返回格式: [{'id', 'name', 'state', 'restarts', 'cpu', 'mem', 'uptime', 'health_score'}]
    """
    try:
        # 获取容器基础信息
        cmd = "docker ps -a --format '{{.ID}}|{{.Names}}|{{.State}}|{{.Status}}'"
        raw = subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode('utf-8').strip()
        
        containers = []
        for line in raw.split('\n'):
            if not line or '|' not in line:
                continue
            
            parts = line.split('|')
            if len(parts) < 4:
                continue
            
            cid, name, state, status = parts[0], parts[1], parts[2], parts[3]
            
            # 提取重启次数
            restarts = 0
            if 'Restarting' in status:
                try:
                    restarts = int(status.split('(')[1].split(')')[0])
                except:
                    pass
            
            # 获取运行时长
            uptime = "未知"
            if state == "running":
                if "Up" in status:
                    uptime = status.split("Up ")[-1].split("(")[0].strip()
            
            # 获取资源占用
            cpu, mem = "0%", "0%"
            if state == "running":
                try:
                    stats_cmd = f"docker stats {cid} --no-stream --format '{{{{.CPUPerc}}}}|{{{{.MemPerc}}}}'"
                    stats = subprocess.check_output(stats_cmd, shell=True, timeout=3).decode().strip()
                    if '|' in stats:
                        cpu, mem = stats.split('|')
                except:
                    pass
            
            # 计算健康评分 (0-100)
            score = calculate_health_score(state, restarts, cpu, mem, uptime)
            
            containers.append({
                'id': cid,
                'name': name,
                'state': state,
                'restarts': restarts,
                'cpu': cpu,
                'mem': mem,
                'uptime': uptime,
                'health_score': score
            })
        
        return containers
    except Exception as e:
        print(f"⚠️ 健康检查异常: {e}")
        return []

def calculate_health_score(state, restarts, cpu, mem, uptime):
    """
    计算健康评分 (0-100)
    规则：
    - 停止状态: 0分
    - 运行中基础分: 60分
    - 重启次数: 每次重启 -10分
    - CPU/内存异常: -10分
    - 运行时长加分
    """
    if state != "running":
        return 0
    
    score = 60
    
    # 重启惩罚 (最多扣30分)
    score -= min(restarts * 10, 30)
    
    # CPU 占用检查
    try:
        cpu_val = float(cpu.replace('%', ''))
        if cpu_val > 90:
            score -= 10
        elif cpu_val > 70:
            score -= 5
    except:
        pass
    
    # 内存占用检查
    try:
        mem_val = float(mem.replace('%', ''))
        if mem_val > 90:
            score -= 10
        elif mem_val > 70:
            score -= 5
    except:
        pass
    
    # 运行时长加分
    if "day" in uptime or "week" in uptime or "month" in uptime:
        score += 20
    elif "hour" in uptime:
        score += 10
    
    return max(0, min(100, score))

def get_health_report_view(page=0):
    """生成健康报告界面 (带分页)"""
    containers = get_container_health_data()
    
    if not containers:
        txt = "🏥 <b>容器健康检查</b>\n━━━━━━━━━━━━━━━\n⚠️ 未检测到任何容器"
        kb = [[InlineKeyboardButton("🔙 返回系统体检", callback_data="sys_report")]]
        return txt, InlineKeyboardMarkup(kb)
    
    # 按健康评分排序（问题容器排前面）
    containers.sort(key=lambda x: x['health_score'])
    
    # 统计
    total = len(containers)
    running = len([c for c in containers if c['state'] == 'running'])
    critical = len([c for c in containers if c['health_score'] < 40])
    warning = len([c for c in containers if 40 <= c['health_score'] < 70])
    healthy = len([c for c in containers if c['health_score'] >= 70])
    
    # 分页
    PER_PAGE = 5
    total_pages = (total + PER_PAGE - 1) // PER_PAGE
    page = min(page, total_pages - 1)
    start = page * PER_PAGE
    current_containers = containers[start:start + PER_PAGE]
    
    txt = (f"🏥 <b>容器健康检查报告</b>\n"
           f"━━━━━━━━━━━━━━━\n"
           f"📊 概览: {running}/{total} 运行中\n"
           f"❌ 危险: {critical} | ⚠️ 警告: {warning} | ✅ 健康: {healthy}\n\n")
    
    kb = []
    for c in current_containers:
        # 健康状态图标
        if c['health_score'] >= 70:
            icon = "✅"
        elif c['health_score'] >= 40:
            icon = "⚠️"
        else:
            icon = "❌"
        
        # 状态显示
        if c['state'] != 'running':
            status_icon = "🔴"
        else:
            status_icon = "🟢"
        
        # 容器详情文本
        txt += (f"{icon} <b>{c['name']}</b> {status_icon}\n"
                f"   评分: <code>{c['health_score']}/100</code> | "
                f"CPU: <code>{c['cpu']}</code> | MEM: <code>{c['mem']}</code>\n")
        
        if c['restarts'] > 0:
            txt += f"   ⚠️ 重启次数: <code>{c['restarts']}</code> 次\n"
        if c['state'] == 'running':
            txt += f"   ⏱️ 运行: {c['uptime']}\n"
        txt += "\n"
        
        # 添加操作按钮
        kb.append([InlineKeyboardButton(
            f"{icon} {c['name'][:20]}", 
            callback_data=f"health_detail_{c['id']}"
        )])
    
    # 分页按钮
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton("⬅️ 上页", callback_data=f"health_page_{page-1}"))
    if page < total_pages - 1:
        nav.append(InlineKeyboardButton("下页 ➡️", callback_data=f"health_page_{page+1}"))
    if nav:
        kb.append(nav)
    
    kb.append([InlineKeyboardButton("🔄 刷新检查", callback_data="health_check")])
    kb.append([InlineKeyboardButton("🔙 返回系统体检", callback_data="sys_report")])
    
    return txt, InlineKeyboardMarkup(kb)

def get_container_detail_health(cid):
    """获取单个容器的详细健康信息"""
    try:
        # 获取容器详细信息
        inspect_cmd = f"docker inspect {cid}"
        raw = subprocess.check_output(inspect_cmd, shell=True).decode('utf-8')
        data = json.loads(raw)[0]
        
        name = data['Name'].strip('/')
        state = data['State']
        config = data['Config']
        
        # 构建详情文本
        txt = f"🏥 <b>容器健康详情</b>\n━━━━━━━━━━━━━━━\n"
        txt += f"📦 名称: <code>{name}</code>\n"
        txt += f"🆔 ID: <code>{cid[:12]}</code>\n\n"
        
        # 运行状态
        if state['Running']:
            txt += f"✅ <b>运行中</b>\n"
            started_at = state['StartedAt'][:19].replace('T', ' ')
            txt += f"⏱️ 启动时间: <code>{started_at}</code>\n"
            txt += f"🔄 重启次数: <code>{state.get('RestartCount', 0)}</code> 次\n"
        else:
            txt += f"🔴 <b>已停止</b>\n"
            finished_at = state['FinishedAt'][:19].replace('T', ' ')
            txt += f"⏱️ 停止时间: <code>{finished_at}</code>\n"
            exit_code = state.get('ExitCode', 0)
            txt += f"📉 退出码: <code>{exit_code}</code>\n"
            if exit_code != 0:
                txt += f"⚠️ <b>异常退出！</b>\n"
        
        # OOM 检查
        if state.get('OOMKilled'):
            txt += f"💥 <b>检测到内存溢出 (OOM)！</b>\n"
        
        # 重启策略
        restart_policy = data['HostConfig']['RestartPolicy']['Name']
        txt += f"\n🔁 重启策略: <code>{restart_policy}</code>\n"
        
        # 资源限制
        mem_limit = data['HostConfig'].get('Memory', 0)
        if mem_limit > 0:
            txt += f"💾 内存限制: <code>{mem_limit / 1024**3:.2f} GB</code>\n"
        else:
            txt += f"💾 内存限制: <code>无限制</code>\n"
        
        # 端口映射
        ports = data['NetworkSettings'].get('Ports', {})
        if ports:
            txt += f"\n🔌 <b>端口映射</b>:\n"
            for container_port, host_bindings in ports.items():
                if host_bindings:
                    for binding in host_bindings:
                        txt += f"   • {binding['HostPort']} → {container_port}\n"
        
        # 健康检查建议
        txt += f"\n💡 <b>健康建议</b>:\n"
        suggestions = []
        
        if state.get('RestartCount', 0) > 3:
            suggestions.append("⚠️ 容器频繁重启，建议检查日志")
        
        if not state['Running'] and state.get('ExitCode', 0) != 0:
            suggestions.append("⚠️ 容器异常退出，建议查看错误日志")
        
        if state.get('OOMKilled'):
            suggestions.append("⚠️ 内存溢出，建议增加内存限制")
        
        if mem_limit == 0:
            suggestions.append("💡 建议设置内存限制，防止占满系统内存")
        
        if restart_policy == "no":
            suggestions.append("💡 建议设置重启策略为 'always' 或 'unless-stopped'")
        
        if not suggestions:
            suggestions.append("✅ 容器配置良好，未发现明显问题")
        
        txt += "\n".join(suggestions)
        
        kb = [
            [InlineKeyboardButton("📄 查看日志", callback_data=f"dk_log_dl_{cid}")],
            [InlineKeyboardButton("🔄 重启容器", callback_data=f"dk_op_restart_{cid}")],
            [InlineKeyboardButton("🔙 返回列表", callback_data="health_check")]
        ]
        
        return txt, InlineKeyboardMarkup(kb)
        
    except Exception as e:
        return f"❌ 获取详情失败: {str(e)}", InlineKeyboardMarkup([[
            InlineKeyboardButton("🔙 返回", callback_data="health_check")
        ]])

# ✅ 新增: 批量健康检查快速诊断
def get_quick_diagnosis():
    """
    快速诊断: 一句话总结系统健康状况
    """
    containers = get_container_health_data()
    
    if not containers:
        return "📋 无容器运行"
    
    critical = len([c for c in containers if c['health_score'] < 40])
    warning = len([c for c in containers if 40 <= c['health_score'] < 70])
    
    if critical > 0:
        return f"🚨 发现 {critical} 个严重问题容器"
    elif warning > 0:
        return f"⚠️ 发现 {warning} 个需要关注的容器"
    else:
        return "✅ 所有容器运行正常"

# ✅ 新增: 获取最近异常容器
def get_recent_problematic_containers(limit=3):
    """
    获取最近出现问题的容器列表
    """
    containers = get_container_health_data()
    
    # 筛选有问题的容器 (评分<70 或 已停止)
    problematic = [
        c for c in containers 
        if c['health_score'] < 70 or c['state'] != 'running'
    ]
    
    # 按评分排序
    problematic.sort(key=lambda x: x['health_score'])
    
    return problematic[:limit]