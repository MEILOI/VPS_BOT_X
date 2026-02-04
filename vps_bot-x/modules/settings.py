# -*- coding: utf-8 -*-
# modules/settings.py (V5.9.3 优化版 - 增强流量校准逻辑)
import json
import os
import subprocess
import re
import math
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from config import load_config, save_config
import modules.system as sys_mod

def get_ssh_security_menu():
    """构建 SSH 安全设置菜单"""
    conf = load_config()
    threshold = conf.get('ban_threshold', 5)
    duration = conf.get('ban_duration', 'permanent')
    import modules.network as net_mod
    ssh_port = net_mod.get_ssh_port()
    
    # 获取当前连接
    raw_ss = subprocess.getoutput("ss -tnp | grep ':22' || ss -tnp | grep ':" + ssh_port + "'")
    active_ips = []
    for line in raw_ss.split('\n'):
        if 'ESTAB' in line:
            parts = line.split()
            if len(parts) >= 5:
                remote = parts[4].rsplit(':', 1)[0].replace('[', '').replace(']', '')
                if remote not in ["127.0.0.1", "::1"]:
                    active_ips.append(remote)
    
    # 获取登录失败的 IP (从 journalctl)
    raw_journal = subprocess.getoutput("journalctl -u ssh -n 500 --no-pager")
    failed_attempts = {}
    pattern = r"Failed password for (.*) from ([\d\.]+) port"
    for line in raw_journal.split('\n'):
        match = re.search(pattern, line)
        if match:
            user, ip = match.group(1), match.group(2)
            if ip not in failed_attempts:
                failed_attempts[ip] = []
            failed_attempts[ip].append({'time': line[:15], 'user': user})
            
    txt = (f"🛡️ <b>SSH 安全设置中心</b>\n"
           f"━━━━━━━━━━━━━━━\n"
           f"📟 <b>当前端口</b>: <code>{ssh_port}</code>\n"
           f"🚨 <b>当前策略</b>: 失败 <code>{threshold}</code> 次封禁\n"
           f"⏳ <b>封禁时长</b>: <code>{duration}</code>\n\n"
           f"🟢 <b>当前活跃连接</b>: {len(active_ips)} 个\n")
    
    for ip in list(set(active_ips))[:3]:
        txt += f" ├ <code>{ip}</code>\n"
        
    txt += f"\n🔴 <b>近登录失败 IP</b>: {len(failed_attempts)} 个\n"
    
    kb = []
    # 策略设置按钮
    kb.append([InlineKeyboardButton(f"⚙️ 阈值: {threshold}次", callback_data="set_ban"),
               InlineKeyboardButton(f"⏳ 时长设置", callback_data="set_ssh_dur_list")])
    
    # 端口修改按钮
    kb.append([InlineKeyboardButton("🚪 修改 SSH 端口", callback_data="set_ssh_port_warn")])
    
    # 失败 IP 列表按钮 (洋葱菜单)
    if failed_attempts:
        for ip in list(failed_attempts.keys())[:5]:
            count = len(failed_attempts[ip])
            kb.append([InlineKeyboardButton(f"🔍 {ip} ({count}次)", callback_data=f"ssh_fail_ip_{ip}")])
            
    kb.append([InlineKeyboardButton("🔙 返回设置", callback_data="sent_lab")])
    return txt, InlineKeyboardMarkup(kb)

def get_ssh_fail_detail(ip):
    """查看特定 IP 的登录失败详情"""
    raw_journal = subprocess.getoutput(f"journalctl -u ssh -n 1000 --no-pager | grep '{ip}'")
    attempts = []
    pattern = r"Failed password for (.*) from .* port"
    
    for line in raw_journal.split('\n'):
        match = re.search(pattern, line)
        if match:
            attempts.append(f"⏰ <code>{line[:15]}</code>\n👤 用户: <code>{match.group(1)}</code>")
            
    txt = (f"🔍 <b>攻击溯源:</b> <code>{ip}</code>\n"
           f"━━━━━━━━━━━━━━━\n"
           f"{chr(10).join(attempts[-5:]) if attempts else '查无详细记录'}")
           
    kb = [
        [InlineKeyboardButton(f"🚫 立即封禁 {ip}", callback_data=f"ghost_quick_ban_{ip}")],
        [InlineKeyboardButton("🔙 返回", callback_data="set_ssh_security")]
    ]
    return txt, InlineKeyboardMarkup(kb)

def get_ssh_duration_menu():
    """封禁时长选择菜单"""
    kb = [
        [InlineKeyboardButton("5 分钟", callback_data="set_ssh_dur_5m"),
         InlineKeyboardButton("1 小时", callback_data="set_ssh_dur_1h")],
        [InlineKeyboardButton("24 小时", callback_data="set_ssh_dur_24h"),
         InlineKeyboardButton("永久封禁", callback_data="set_ssh_dur_permanent")],
        [InlineKeyboardButton("🔙 返回", callback_data="set_ssh_security")]
    ]
    return "⏳ <b>请选择封禁时长策略:</b>\n自动封禁将按此时间执行。", InlineKeyboardMarkup(kb)

def get_menu():
    """
    构建设置菜单
    包含 7 项核心配置功能
    """
    conf = load_config()
    
    # 获取当前流量用于显示
    curr_tf = sys_mod.get_traffic_stats('month')
    
    kb = [
        [InlineKeyboardButton(f"🖊️ 备注: {conf.get('server_remark', 'MyVPS')}", callback_data="set_remark")],
        [InlineKeyboardButton("🛡️ SSH 安全设置", callback_data="set_ssh_security")],
        [InlineKeyboardButton(f"💰 月限额: {conf.get('traffic_limit_gb', 1000)}GB", callback_data="set_tf")],
        [InlineKeyboardButton(f"🔧 流量校准 (当前:{curr_tf:.1f}G)", callback_data="set_calib")],
        [InlineKeyboardButton(f"🚨 日预警: {conf.get('daily_warn_gb', 50)}GB", callback_data="set_dw")],
        [InlineKeyboardButton(f"📅 结算日: {conf.get('billing_day', 1)}号", callback_data="set_day")],
        [InlineKeyboardButton("🔙 返回主菜单", callback_data="back")]
    ]
    
    txt = "⚙️ <b>哨兵卫士系统设置</b>\n请选择要修改的项目:"
    return txt, InlineKeyboardMarkup(kb)

def get_prompt_text(action):
    """
    根据操作类型返回提示文本
    """
    prompts = {
        "set_remark": "🖊️ <b>修改机器备注</b>\n\n请输入新的备注名称 (如: 搬瓦工-01):",
        
        "set_ban": "🛡️ <b>修改封禁阈值</b>\n\n请输入触发封禁的尝试次数 (建议 5-10):",
        
        "set_tf": "💰 <b>修改月流量限额</b>\n\n请输入每月允许的最大流量 (GB):",
        
        "set_calib": (
            "🔧 <b>流量校准向导</b>\n\n"
            "请输入运营商后台显示的<b>已用流量</b> (GB):\n\n"
            "💡 <b>原理</b>: 系统将自动计算偏差值\n"
            "📊 <b>公式</b>: 偏差 = 真实值 - vnstat值\n\n"
            "⚠️ <b>注意</b>: 请确保输入的是本计费周期的累计流量"
        ),
        
        "set_dw": "🚨 <b>修改日流量预警</b>\n\n请输入单日触发警报的流量值 (GB):",
        
        "set_day": "📅 <b>修改结算日</b>\n\n请输入每月流量清零的日期 (1-31):"
    }
    return prompts.get(action, "⚠️ 未知操作项")

def update_setting(action, value):
    """
    更新配置项
    包含完整的验证和错误处理
    """
    conf = load_config()
    
    try:
        if action == "set_remark":
            # 备注修改
            conf['server_remark'] = str(value).strip()
            
        elif action == "set_ban":
            # 封禁阈值修改
            ban_val = int(value)
            if ban_val < 1 or ban_val > 100:
                return "❌ 错误: 阈值必须在 1-100 之间", get_menu()
            conf['ban_threshold'] = ban_val
            
        elif action == "set_tf":
            # 月流量限额修改
            tf_val = float(value)
            if tf_val <= 0:
                return "❌ 错误: 流量限额必须大于 0", get_menu()
            conf['traffic_limit_gb'] = tf_val
            
        elif action == "set_dw":
            # 日预警修改
            dw_val = float(value)
            if dw_val <= 0:
                return "❌ 错误: 预警值必须大于 0", get_menu()
            conf['daily_warn_gb'] = dw_val
            
        elif action == "set_day":
            # 结算日修改
            day = int(value)
            if day < 1 or day > 31:
                return "❌ 错误: 日期必须在 1-31 之间", get_menu()
            conf['billing_day'] = day
            
        elif action == "set_calib":
            # ✅ 流量校准深度逻辑
            try:
                target_val = float(value)
                
                if target_val < 0:
                    return "❌ 错误: 流量不能为负数", get_menu()
                
                # 获取当前显示值 (已包含旧偏差)
                current_display = sys_mod.get_traffic_stats('month')
                
                # 获取旧偏差值
                old_offset = conf.get('traffic_offset_gb', 0.0)
                
                # 计算 vnstat 原始值 = 当前显示值 - 旧偏差值
                pure_vnstat_val = current_display - old_offset
                
                # 计算新偏差 = 目标值 - vnstat原始值
                new_offset = target_val - pure_vnstat_val
                
                # 保存新偏差
                conf['traffic_offset_gb'] = round(new_offset, 3)
                
                # 验证结果
                verification = pure_vnstat_val + new_offset
                
                save_config(conf)
                
                msg = (
                    f"✅ <b>流量校准成功</b>\n\n"
                    f"📊 vnstat原始值: <code>{pure_vnstat_val:.2f} GB</code>\n"
                    f"🎯 目标值: <code>{target_val:.2f} GB</code>\n"
                    f"🔧 新偏差值: <code>{new_offset:+.3f} GB</code>\n"
                    f"✔️ 验证结果: <code>{verification:.2f} GB</code>\n\n"
                    f"💡 下次刷新流量将显示校准后的数值"
                )
                return msg, get_menu()
                
            except ValueError:
                return "❌ 错误: 请输入有效的数字", get_menu()
        
        # 执行保存
        save_config(conf)
        
        return f"✅ <b>修改成功</b>\n\n已更新为: <code>{value}</code>", get_menu()
        
    except ValueError:
        return "❌ 格式错误: 请输入正确的数字格式", get_menu()
    except Exception as e:
        return f"❌ 系统错误: {str(e)}", get_menu()