# -*- coding: utf-8 -*-
# modules/backup.py (V5.9.4 优化版 - 增强错误处理)
import os, subprocess, glob, shutil
from datetime import datetime
from config import load_config, save_config
from utils import log_audit, get_path_id
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

def run_backup_task(is_auto=False):
    """
    执行备份任务
    返回: (文件路径, 消息) 或 (None, 错误消息)
    """
    conf = load_config()
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    tar_path = f"/tmp/backup_{conf['server_remark']}_{ts}.tar.gz"
    
    # 构建排除规则
    cmd = ["tar", "-czf", tar_path]
    for exc in conf['backup_exclude']:
        cmd.append(f"--exclude={exc}")
    
    # 验证备份路径
    valid = [p for p in conf['backup_paths'] if os.path.exists(p)]
    if not valid:
        return None, "⚠️ 无有效备份路径\n\n💡 请先在备份菜单中添加要备份的目录"
    
    cmd.extend(valid)
    
    try:
        # 执行备份 (5分钟超时)
        result = subprocess.run(
            cmd,
            check=True,
            timeout=300,
            capture_output=True,
            text=True
        )
        
        # 验证文件是否生成
        if not os.path.exists(tar_path):
            return None, "❌ 备份文件未生成"
        
        file_size = os.path.getsize(tar_path)
        
        # 检查文件大小
        if file_size == 0:
            os.remove(tar_path)
            return None, "❌ 备份文件为空，可能没有权限访问某些目录"
        
        # 记录日志
        prefix = "⏰ 定时备份" if is_auto else "📦 手动备份"
        log_audit("SYS" if is_auto else "USER", "备份成功", f"文件: {tar_path}")
        
        # 构建成功消息
        msg = (f"✅ <b>备份完成</b>\n\n"
               f"📦 文件: <code>{os.path.basename(tar_path)}</code>\n"
               f"📊 大小: <code>{file_size / 1024**2:.2f} MB</code>\n"
               f"📂 包含: {len(valid)} 个目录\n"
               f"⏰ 时间: <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>")
        
        return tar_path, msg
        
    except subprocess.TimeoutExpired:
        return None, "❌ 备份超时 (超过5分钟)\n\n💡 文件可能过大，建议减少备份内容"
    
    except subprocess.CalledProcessError as e:
        error_msg = e.stderr if e.stderr else str(e)
        return None, f"❌ 备份失败\n\n<pre>\n{error_msg[:200]}\n</pre>"
    
    except Exception as e:
        return None, f"❌ 备份异常: {str(e)}"

def get_backup_menu():
    """构建备份菜单 (交互升级版)"""
    conf = load_config()
    
    paths = conf.get('backup_paths', [])
    path_list_text = []
    kb = []
    
    # 顶部操作
    kb.append([InlineKeyboardButton("▶️ 立即执行备份", callback_data="bk_do")])
    
    if paths:
        for i, p in enumerate(paths):
            exists = os.path.exists(p)
            status_icon = "✅" if exists else "❌"
            # 缩短路径显示
            short_p = p if len(p) < 30 else "..." + p[-27:]
            path_list_text.append(f"{i+1}. {status_icon} <code>{p}</code>")
            # 为每个路径增加 [❌ 删除] 按钮
            kb.append([InlineKeyboardButton(f"{status_icon} {short_p}", callback_data="none"),
                       InlineKeyboardButton("🗑️ 移除", callback_data=f"bk_del_path_{i}")])
    else:
        path_list_text.append("⚠️ (暂无备份路径)")

    paths_display = "\n".join(path_list_text)
    auto = conf.get("auto_backup", {})
    mode = auto.get("mode", "off")
    sch = f"📅 每日 {auto.get('time', '03:00')}" if mode == "daily" else "🚫 已禁用"

    txt = (f"☁️ <b>备份资产管理</b>\n"
           f"━━━━━━━━━━━━━━━\n"
           f"📂 <b>备份清单</b> (✅=正常 ❌=失效):\n{paths_display}\n\n"
           f"⏰ <b>自动计划</b>: {sch}\n"
           f"📦 <b>预计体积</b>: <code>{get_backup_size_estimate()}</code>")
    
    kb.append([InlineKeyboardButton("📤 立即上传文件", callback_data="tool_upload_start"),
               InlineKeyboardButton("📥 设定上传目录", callback_data="tool_set_upload")])
    kb.append([InlineKeyboardButton("➕ 新增备份路径", callback_data="bk_add"),
               InlineKeyboardButton("📜 历史文件", callback_data="bk_history")])
    kb.append([InlineKeyboardButton("⏰ 自动备份设置", callback_data="bk_auto_set")])
    kb.append([InlineKeyboardButton("🔙 返回主菜单", callback_data="back")])
    
    return txt, InlineKeyboardMarkup(kb)

def build_history_menu():
    """构建历史备份记录菜单"""
    files = glob.glob("/tmp/backup_*.tar.gz")
    files.sort(key=os.path.getmtime, reverse=True)
    
    txt = "📜 <b>历史备份文件 (临时存放)</b>\n━━━━━━━━━━━━━━━\n"
    kb = []
    
    if not files:
        txt += "📭 暂无备份文件。"
    else:
        for f in files[:8]:
            name = os.path.basename(f)
            size = os.path.getsize(f) / 1024**2
            txt += f"▫️ <code>{name}</code> ({size:.1f}MB)\n"
            kb.append([InlineKeyboardButton(f"📤 发送 {name[:20]}", callback_data=f"bk_send_{name}")])
    
    kb.append([InlineKeyboardButton("🔙 返回", callback_data="bk_menu")])
    return txt, InlineKeyboardMarkup(kb)

def add_backup_path(path):
    """
    添加备份路径
    带路径验证
    """
    conf = load_config()
    
    # 去除首尾空格
    path = path.strip()
    
    # 验证路径格式
    if not path.startswith('/'):
        return "❌ 路径必须以 / 开头 (绝对路径)"
    
    # 检查路径是否存在
    if not os.path.exists(path):
        return f"⚠️ 警告: 路径 <code>{path}</code> 不存在\n\n是否仍要添加? (已添加,但备份时会跳过)"
    
    # 检查是否已存在
    if path in conf['backup_paths']:
        return f"⚠️ 路径 <code>{path}</code> 已在备份列表中"
    
    # 添加到列表
    conf['backup_paths'].append(path)
    save_config(conf)
    
    return f"✅ <b>路径已添加</b>\n\n📂 <code>{path}</code>"

def remove_backup_path(index_or_path):
    """
    删除备份路径
    支持按序号或路径删除
    """
    conf = load_config()
    paths = conf.get('backup_paths', [])
    
    if not paths:
        return "⚠️ 备份列表为空"
    
    # 尝试按序号删除
    try:
        index = int(index_or_path) - 1
        if 0 <= index < len(paths):
            removed = paths.pop(index)
            save_config(conf)
            return f"✅ <b>已删除路径</b>\n\n📂 <code>{removed}</code>"
        else:
            return f"❌ 序号超出范围 (1-{len(paths)})"
    except ValueError:
        pass
    
    # 尝试按路径删除
    if index_or_path in paths:
        paths.remove(index_or_path)
        save_config(conf)
        return f"✅ <b>已删除路径</b>\n\n📂 <code>{index_or_path}</code>"
    else:
        return f"❌ 未找到路径: <code>{index_or_path}</code>"

def get_backup_size_estimate():
    """
    估算备份大小 (用于显示)
    """
    conf = load_config()
    total_size = 0
    
    for path in conf.get('backup_paths', []):
        if not os.path.exists(path):
            continue
        
        try:
            # 使用 du 命令估算大小
            result = subprocess.run(
                ['du', '-sb', path],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                size = int(result.stdout.split()[0])
                total_size += size
        except:
            continue
    
    # 转换为人类可读格式
    if total_size == 0:
        return "未知"
    elif total_size < 1024**2:
        return f"{total_size / 1024:.1f} KB"
    elif total_size < 1024**3:
        return f"{total_size / 1024**2:.1f} MB"
    else:
        return f"{total_size / 1024**3:.2f} GB"

def clean_old_backups(keep_count=5):
    """
    清理旧备份文件
    保留最新的 N 个
    """
    try:
        backup_files = glob.glob("/tmp/backup_*.tar.gz")
        
        if len(backup_files) <= keep_count:
            return f"✅ 当前有 {len(backup_files)} 个备份文件，无需清理"
        
        # 按修改时间排序
        backup_files.sort(key=os.path.getmtime, reverse=True)
        
        # 删除多余的
        deleted = 0
        for old_file in backup_files[keep_count:]:
            try:
                os.remove(old_file)
                deleted += 1
            except:
                pass
        
        return f"✅ 清理完成，删除了 {deleted} 个旧备份"
    
    except Exception as e:
        return f"❌ 清理失败: {str(e)}"

def validate_backup_paths():
    """
    验证所有备份路径的有效性
    返回: (有效路径列表, 无效路径列表)
    """
    conf = load_config()
    paths = conf.get('backup_paths', [])
    
    valid = []
    invalid = []
    
    for path in paths:
        if os.path.exists(path):
            valid.append(path)
        else:
            invalid.append(path)
    
    return valid, invalid

def get_backup_history():
    """
    获取备份历史记录
    读取临时目录中的备份文件
    """
    try:
        backup_files = glob.glob("/tmp/backup_*.tar.gz")
        
        if not backup_files:
            return "📭 暂无备份历史"
        
        # 按修改时间排序
        backup_files.sort(key=os.path.getmtime, reverse=True)
        
        history = []
        for i, file_path in enumerate(backup_files[:10], 1):
            file_name = os.path.basename(file_path)
            file_size = os.path.getsize(file_path) / 1024**2  # MB
            mod_time = datetime.fromtimestamp(os.path.getmtime(file_path))
            
            history.append(
                f"<code>{i}.</code> {file_name}\n"
                f"    📊 {file_size:.2f} MB | "
                f"⏰ {mod_time.strftime('%m-%d %H:%M')}"
            )
        
        return "📜 <b>备份历史</b> (最近10次):\n\n" + "\n\n".join(history)
    
    except Exception as e:
        return f"❌ 读取历史失败: {str(e)}"

# ✅ 新增: 获取备份状态摘要
def get_backup_status_summary():
    """
    获取备份状态一句话摘要
    用于在主菜单或系统报告中显示
    """
    conf = load_config()
    paths = conf.get('backup_paths', [])
    auto = conf.get("auto_backup", {})
    
    if not paths:
        return "❌ 未配置备份"
    
    valid, invalid = validate_backup_paths()
    
    if invalid:
        return f"⚠️ {len(invalid)} 个路径失效"
    
    if auto.get('mode') == 'off':
        return f"⏸️ 手动备份模式 ({len(valid)}个路径)"
    else:
        return f"✅ 自动备份已启用"