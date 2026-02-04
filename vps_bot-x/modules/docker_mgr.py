# -*- coding: utf-8 -*-
# modules/docker_mgr.py (V6.0.3 稳定修正版)
import subprocess, json, datetime, os, random, string, time
from telegram import InlineKeyboardButton, InlineKeyboardMarkup

# --- 🛠️ 基础工具 ---
def run_cmd(cmd):
    """执行命令并返回输出"""
    try:
        return subprocess.check_output(cmd, shell=True, stderr=subprocess.STDOUT).decode('utf-8')
    except subprocess.CalledProcessError as e:
        return f"Error: {e.output.decode('utf-8')}"
    except Exception as e:
        return f"Error: {str(e)}"

def safe_md(text):
    """转义 Markdown 特殊字符"""
    if not text: return "N/A"
    return text.replace("_", "\\_").replace("*", "\\*").replace("<code>", "\\</code>").replace("[", "\\[")

# --- 1. 数据采集 ---
def get_containers():
    cmd = "docker ps -a --format '{{.ID}}|{{.Names}}|{{.State}}|{{.Status}}|{{.Image}}'"
    out = run_cmd(cmd)
    cons = []
    if "Error" in out or not out.strip(): return []
    for line in out.strip().split('\n'):
        if "|" not in line: continue
        p = line.split('|')
        cons.append({"id": p[0], "name": p[1], "state": p[2], "status": p[3], "image": p[4]})
    return cons

def get_images():
    cmd = "docker images --format '{{.ID}}|{{.Repository}}|{{.Tag}}|{{.Size}}'"
    out = run_cmd(cmd)
    imgs = []
    if "Error" in out or not out.strip(): return []
    for line in out.strip().split('\n'):
        if "|" not in line: continue
        p = line.split('|')
        imgs.append({"id": p[0], "repo": p[1], "tag": p[2], "size": p[3]})
    return imgs

def get_in_use_image_ids():
    cmd = "docker ps -a --format '{{.Image}}'"
    out = run_cmd(cmd).strip().split('\n')
    in_use = set()
    for item in out:
        if not item: continue
        iid = run_cmd(f"docker inspect --format '{{{{.Id}}}}' {item}").strip()
        if iid: in_use.add(iid.replace("sha256:", "")[:12])
    return in_use

def get_networks():
    cmd = "docker network ls --format '{{.Name}}|{{.Driver}}'"
    out = run_cmd(cmd)
    nets = []
    if "Error" in out: return []
    for line in out.strip().split('\n'):
        if "|" in line:
            p = line.split('|')
            nets.append({'name': p[0], 'driver': p[1]})
    return nets

def get_stacks():
    try:
        cmd = "docker compose ls --format json"
        out = run_cmd(cmd)
        if "Error" in out or not out.strip(): return []
        return json.loads(out)
    except: return []

# --- 2. 向导逻辑 (Wizard) ---
WIZARD_CACHE = {}
WIZARD_EXPIRE = {}
CACHE_TIMEOUT = 3600

def clean_expired_wizards():
    now = time.time()
    expired = [u for u, t in WIZARD_EXPIRE.items() if now - t > CACHE_TIMEOUT]
    for u in expired:
        WIZARD_CACHE.pop(u, None)
        WIZARD_EXPIRE.pop(u, None)

def init_wizard(uid, iid):
    clean_expired_wizards()
    img = next((i for i in get_images() if i['id'] == iid), None)
    if not img: return False
    repo_name = img['repo'].split('/')[-1]
    rnd = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    WIZARD_CACHE[uid] = {
        'image': f"{img['repo']}:{img['tag']}",
        'name': f"{repo_name}-{rnd}",
        'net': 'bridge',
        'ports': [],
        'vols': [],
        'envs': [],
        'privileged': False
    }
    WIZARD_EXPIRE[uid] = time.time()
    return True

def get_wizard_menu(uid):
    if uid not in WIZARD_CACHE: return "⚠️ 已过期", None
    d = WIZARD_CACHE[uid]
    txt = (f"🧙 <b>安装向导 (草稿)</b>\n━━━━━━━━━━━━━━━\n"
           f"🖼️ 镜像: <code>{d['image']}</code>\n"
           f"🏷️ 名称: <code>{d['name']}</code>\n"
           f"🌐 网络: <code>{d['net']}</code>\n"
           f"🔌 端口: <code>{d['ports'] or '无'}</code>\n"
           f"📂 挂载: <code>{d['vols'] or '无'}</code>\n"
           f"⚡ 特权: <code>{'开启' if d['privileged'] else '关闭'}</code>")
    kb = [[InlineKeyboardButton("🏷️ 改名", callback_data="dk_wiz_set_name"), InlineKeyboardButton("🌐 网络", callback_data="dk_wiz_net")],
          [InlineKeyboardButton("🔌 端口", callback_data="dk_wiz_set_port"), InlineKeyboardButton("📂 挂载", callback_data="dk_wiz_set_vol")],
          [InlineKeyboardButton("🚀 立即启动", callback_data="dk_wiz_commit"), InlineKeyboardButton("❌ 取消", callback_data="dk_m")]]
    return txt, InlineKeyboardMarkup(kb)

def update_wizard_val(uid, key, val):
    if uid in WIZARD_CACHE:
        if key in ['net', 'name']: WIZARD_CACHE[uid][key] = val
        elif key == 'privileged': WIZARD_CACHE[uid]['privileged'] = not WIZARD_CACHE[uid].get('privileged', False)
        else: WIZARD_CACHE[uid][key+'s'].append(val)
    return get_wizard_menu(uid)

def commit_wizard(uid):
    d = WIZARD_CACHE.get(uid)
    if not d: return "❌ 丢失"
    cmd = f"docker run -d --name {d['name']} --net {d['net']} --restart always "
    if d.get('privileged'): cmd += "--privileged "
    for p in d['ports']: cmd += f"-p {p} "
    for v in d['vols']: 
        if ':' not in v: continue
        cmd += f"-v {v} "
    cmd += d['image']
    
    try:
        out = run_cmd(cmd)
        if "Error" not in out and len(out.strip()) >= 12:
            WIZARD_CACHE.pop(uid, None)
            WIZARD_EXPIRE.pop(uid, None)
            return f"✅ <b>部署成功!</b>\nID: <code>{out[:12]}</code>"
        return f"❌ <b>部署失败:</b>\n<pre>\n{out[:500]}\n</pre>"
    except Exception as e: return f"❌ 异常: {e}"

# --- 3. 核心菜单构建 ---
def build_main_menu():
    cons = get_containers()
    stacks = get_stacks()
    run = len([c for c in cons if c['state'] == 'running'])
    txt = (f"🐳 <b>容器指挥官 V6.0</b>\n━━━━━━━━━━━━━━━\n"
           f"📦 容器: <code>{run}</code> 运行中 / <code>{len(cons)}</code> 总计\n"
           f"📚 堆栈: <code>{len(stacks)}</code> 个 Compose 项目")
    kb = [
        [InlineKeyboardButton(f"📦 容器列表 ({len(cons)})", callback_data="dk_list_cons"),
         InlineKeyboardButton("🚀 应用商店", callback_data="dk_store")],
        [InlineKeyboardButton(f"📚 堆栈管理 ({len(stacks)})", callback_data="dk_list_stacks")],
        [InlineKeyboardButton("🖼️ 镜像管理 (安装/更新)", callback_data="dk_res_imgs")],
        [InlineKeyboardButton("🧹 深度清理", callback_data="dk_op_prune"), 
         InlineKeyboardButton("📝 实时事件", callback_data="dk_events")],
        [InlineKeyboardButton("🔙 返回主菜单", callback_data="back")]
    ]
    return txt, InlineKeyboardMarkup(kb)

def build_container_list():
    cons = get_containers()
    txt = "📦 <b>容器列表</b> (点击管理):\n━━━━━━━━━━━━━━━\n"
    kb = []
    row = []
    for c in cons:
        icon = "🟢" if c['state'] == 'running' else "🔴"
        if c['state'] == 'paused': icon = "🟡"
        
        p_raw = run_cmd(f"docker inspect {c['id']} --format '{{{{range $p, $conf := .NetworkSettings.Ports}}}}{{{{$p}}}}->{{{{(index $conf 0).HostPort}}}} {{{{end}}}}'").strip()
        p_info = f" | <code>{p_raw}</code>" if p_raw else ""
        txt += f"{icon} <code>{c['name'][:15]}</code>{p_info}\n"
        
        btn_name = c['name'][:15] + ".." if len(c['name']) > 15 else c['name']
        row.append(InlineKeyboardButton(f"{icon} {btn_name}", callback_data=f"dk_view_{c['id']}"))
        if len(row) == 2:
            kb.append(row); row = []
    if row: kb.append(row)
    kb.append([InlineKeyboardButton("🔙 返回指挥官", callback_data="dk_m")])
    return txt, InlineKeyboardMarkup(kb)

def build_container_dashboard(cid):
    c = next((i for i in get_containers() if i['id'].startswith(cid)), None)
    if not c: return "⚠️ 容器不存在", InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="dk_list_cons")]])
    
    stats_raw = run_cmd(f"docker stats {c['id']} --no-stream --format '{{{{.CPUPerc}}}}|{{{{.MemUsage}}}}|{{{{.MemPerc}}}}'").strip()
    cpu, mem_usage, mem_perc = stats_raw.split('|') if "|" in stats_raw else ("0%", "0B / 0B", "0%")
    
    inspect_raw_json = run_cmd(f"docker inspect {c['id']}")
    try:
        inspect_data = json.loads(inspect_raw_json)[0]
        ports = inspect_data.get('NetworkSettings', {}).get('Ports', {})
        port_list = [f"{v[0]['HostPort']}->{k}" for k, v in ports.items() if v]
        port_str = ", ".join(port_list) if port_list else "无"
        mount_count = len(inspect_data.get('Mounts', []))
        limit_bytes = inspect_data.get('HostConfig', {}).get('Memory', 0)
        limit_str = f"{limit_bytes/1024**2:.0f}M" if limit_bytes > 0 else "无限制"
        ip_addr = "N/A"
        for net_val in inspect_data.get('NetworkSettings', {}).get('Networks', {}).values():
            if net_val.get('IPAddress'): ip_addr = net_val['IPAddress']; break
    except: port_str, mount_count, limit_str, ip_addr = "未知", 0, "未知", "N/A"

    def get_bar(s):
        try: p = float(s.replace('%', ''))
        except: p = 0
        f = int(p/10); return f"{'▓'*f}{'░'*(10-f)} {p:.1f}%"

    txt = (f"📦 <b>容器: {safe_md(c['name'])}</b>\n"
           f"━━━━━━━━━━━━━━━\n"
           f"🆔 <code>ID</code>: <code>{c['id'][:12]}</code>\n"
           f"📡 <code>状态</code>: <code>{c['state']}</code> ({c['status']})\n"
           f"🌐 <code>IP</code>: <code>{ip_addr}</code>\n"
           f"🔌 <code>端口</code>: <code>{port_str}</code>\n"
           f"💾 <code>挂载</code>: <code>{mount_count} 个目录</code> | 🛡️ <code>限制</code>: <code>{limit_str}</code>\n\n"
           f"🌡️ <b>资源占用</b>:\n"
           f"⚡ <code>CPU</code>: <code>{get_bar(cpu)}</code>\n"
           f"🧠 <code>MEM</code>: <code>{get_bar(mem_perc)}</code> (<code>{mem_usage.split(' / ')[0]}</code>)\n"
           f"━━━━━━━━━━━━━━━\n"
           f"🚀 1Panel 式快捷操作:")
    
    kb = []
    if c['state'] == 'running':
        kb.append([InlineKeyboardButton("⏹️ 停止", callback_data=f"dk_op_stop_{cid}"), InlineKeyboardButton("🔄 重启", callback_data=f"dk_op_restart_{cid}")])
        kb.append([InlineKeyboardButton("⏸️ 暂停", callback_data=f"dk_op_pause_{cid}"), InlineKeyboardButton("💻 命令", callback_data=f"dk_op_exec_ask_{cid}")])
    elif c['state'] == 'paused':
        kb.append([InlineKeyboardButton("▶️ 恢复", callback_data=f"dk_op_unpause_{cid}"), InlineKeyboardButton("⏹️ 停止", callback_data=f"dk_op_stop_{cid}")])
    else:
        kb.append([InlineKeyboardButton("▶️ 启动", callback_data=f"dk_op_start_{cid}")])
    
    kb.append([InlineKeyboardButton("📄 日志预览", callback_data=f"dk_log_v_{cid}"), InlineKeyboardButton("⚡ 资源限制", callback_data=f"dk_lim_menu_{cid}")])
    kb.append([InlineKeyboardButton("🗑️ 删除容器", callback_data=f"dk_op_rm_{cid}"), InlineKeyboardButton("🔙 返回列表", callback_data="dk_list_cons")])
    return txt, InlineKeyboardMarkup(kb)

# --- 🚀 1Panel 式应用商店 ---
APP_TEMPLATES = {
    'nginx': {
        'name': 'Nginx Web 服务器',
        'image': 'nginx:latest',
        'ports': ['80:80'],
        'vols': ['/opt/vps_bot/data/nginx/html:/usr/share/nginx/html'],
        'desc': '最流行的 Web 服务器/反向代理'
    },
    'redis': {
        'name': 'Redis 缓存',
        'image': 'redis:alpine',
        'ports': ['6379:6379'],
        'desc': '高性能 Key-Value 数据库'
    },
    'tailscale': {
        'name': 'Tailscale (TAI)',
        'image': 'tailscale/tailscale:latest',
        'privileged': True,
        'vols': ['/dev/net/tun:/dev/net/tun', '/var/lib/tailscale:/var/lib/tailscale'],
        'desc': '零配置内网穿透与虚拟组网'
    },
    'zerotier': {
        'name': 'ZeroTier (ZT)',
        'image': 'zerotier/zerotier:latest',
        'privileged': True,
        'vols': ['/var/lib/zerotier-one:/var/lib/zerotier-one'],
        'desc': '强大的 P2P 内网穿透工具'
    }
}

def build_app_store_menu():
    txt = "🚀 <b>X-Lab 应用商店</b>\n━━━━━━━━━━━━━━━\n请选择要安装的模板:\n"
    kb = []
    for key, app in APP_TEMPLATES.items():
        txt += f"• <b>{app['name']}</b>\n  _{app['desc']}_\n"
        kb.append([InlineKeyboardButton(f"📥 安装 {app['name']}", callback_data=f"dk_store_ask_{key}")])
    kb.append([InlineKeyboardButton("🔙 返回", callback_data="dk_m")])
    return txt, InlineKeyboardMarkup(kb)

def build_app_install_confirm(app_key):
    app = APP_TEMPLATES.get(app_key)
    if not app: return "⚠️ 模板不存在", None
    txt = (f"❓ <b>确认安装此应用吗？</b>\n━━━━━━━━━━━━━━━\n"
           f"📦 应用: <b>{app['name']}</b>\n"
           f"🖼️ 镜像: <code>{app['image']}</code>\n"
           f"🔌 端口: <code>{', '.join(app.get('ports', ['无']))}</code>\n\n"
           f"⚠️ 点击确认后将立即部署。")
    kb = [[InlineKeyboardButton("✅ 确认安装", callback_data=f"dk_store_do_{app_key}"), InlineKeyboardButton("❌ 取消", callback_data="dk_store")]]
    return txt, InlineKeyboardMarkup(kb)

def install_app_template(uid, app_key):
    app = APP_TEMPLATES.get(app_key)
    if not app: return False
    clean_expired_wizards()
    rnd = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    WIZARD_CACHE[uid] = {
        'image': app['image'], 'name': f"{app_key}-{rnd}", 'net': 'bridge',
        'ports': app.get('ports', []), 'vols': app.get('vols', []),
        'envs': app.get('envs', []), 'privileged': app.get('privileged', False)
    }
    WIZARD_EXPIRE[uid] = time.time()
    return True

# --- 其他辅助功能 (限制、日志、清理、Stack、Events) ---
def build_limit_menu(cid):
    inspect_raw = run_cmd(f"docker inspect {cid} --format '{{{{.HostConfig.Memory}}}}'").strip()
    try: cur = int(inspect_raw)
    except: cur = 0
    opts = {'512m': 512*1024*1024, '1g': 1024*1024*1024, '2g': 2048*1024*1024, '0': 0}
    def get_btn(l, k): return f"✅ {l}" if cur == opts[k] else l
    txt = f"⚡ <b>资源限制</b>: <code>{cid[:12]}</code>"
    kb = [[InlineKeyboardButton(get_btn("512M", '512m'), callback_data=f"dk_set_lim_{cid}_512m"), InlineKeyboardButton(get_btn("1G", '1g'), callback_data=f"dk_set_lim_{cid}_1g")],
          [InlineKeyboardButton(get_btn("2G", '2g'), callback_data=f"dk_set_lim_{cid}_2g"), InlineKeyboardButton(get_btn("🔓 不限制", '0'), callback_data=f"dk_set_lim_{cid}_0")],
          [InlineKeyboardButton("🔙 返回", callback_data=f"dk_view_{cid}")]]
    return txt, InlineKeyboardMarkup(kb)

def docker_action(action, target, extra=None):
    if action == "start": cmd = f"docker start {target}"
    elif action == "stop": cmd = f"docker stop {target}"
    elif action == "restart": cmd = f"docker restart {target}"
    elif action == "pause": cmd = f"docker pause {target}"
    elif action == "unpause": cmd = f"docker unpause {target}"
    elif action == "rm": cmd = f"docker rm -f {target}"
    elif action == "rmi": cmd = f"docker rmi {target}"
    elif action == "update_mem":
        if extra == "0": cmd = f"docker update --memory 0 --memory-swap 0 {target}"
        else:
            val = int(extra.lower().replace('g', '').replace('m', ''))
            unit = 'g' if 'g' in extra.lower() else 'm'
            cmd = f"docker update --memory {extra} --memory-swap {val*2}{unit} {target}"
    else: return False, "未知"
    try:
        subprocess.check_call(cmd, shell=True); return True, "成功"
    except Exception as e: return False, str(e)

def build_logs_preview(cid):
    try: logs = subprocess.check_output(f"docker logs --tail 30 {cid}", shell=True, stderr=subprocess.STDOUT).decode('utf-8')
    except: logs = "无法读取"
    c = next((i for i in get_containers() if i['id'].startswith(cid)), None)
    txt = f"📄 <b>日志预览: {safe_md(c['name'] if c else cid)}</b>\n<pre>\n{logs[-3500:]}\n</pre>"
    kb = [[InlineKeyboardButton("🔄 刷新", callback_data=f"dk_log_v_{cid}"), InlineKeyboardButton("🔙 返回", callback_data=f"dk_view_{cid}")]]
    return txt, InlineKeyboardMarkup(kb)

def prune_docker_resources():
    out = run_cmd("docker system prune -f")
    return f"✅ <b>清理成功</b>\n\n<pre>\n{out}\n</pre>"

def build_image_menu():
    imgs = get_images(); in_use = get_in_use_image_ids()
    txt = f"🖼️ <b>镜像管理</b>"
    kb = [[InlineKeyboardButton(f"{'🔒' if i['id'] in in_use else '🟡'} {i['repo'].split('/')[-1]}:{i['tag']}", callback_data=f"dk_img_v_{i['id']}")] for i in imgs[:15]]
    kb.append([InlineKeyboardButton("🔙 返回", callback_data="dk_m")])
    return txt, InlineKeyboardMarkup(kb)

def build_image_dashboard(iid):
    img = next((i for i in get_images() if i['id'] == iid), None)
    if not img: return "⚠️ 丢失", None
    txt = f"🖼️ <b>镜像: {img['repo']}</b>\nTag: <code>{img['tag']}</code>"
    kb = [[InlineKeyboardButton("🔄 更新", callback_data=f"dk_img_upd_{img['repo']}:{img['tag']}")],[InlineKeyboardButton("🗑️ 删除", callback_data=f"dk_op_rmi_{iid}")],[InlineKeyboardButton("🔙 返回", callback_data="dk_res_imgs")]]
    return txt, InlineKeyboardMarkup(kb)

def get_docker_events(): return run_cmd("docker events --since 30m --until 0s --format '{{.Time}} {{.Action}} {{.Actor.Attributes.name}}' | tail -10")
def build_stack_menu():
    stacks = get_stacks()
    if not stacks: return "📚 无项目", InlineKeyboardMarkup([[InlineKeyboardButton("🔙", callback_data="dk_m")]])
    kb = [[InlineKeyboardButton(f"{s.get('Name')} | {s.get('Status')}", callback_data=f"dk_stack_opt_{s.get('Name')}")] for s in stacks]
    kb.append([InlineKeyboardButton("🔙 返回", callback_data="dk_m")])
    return "📚 <b>堆栈管理</b>", InlineKeyboardMarkup(kb)
def build_stack_dashboard(name):
    txt = f"📚 <b>堆栈: {name}</b>"
    kb = [[InlineKeyboardButton("▶️ 启动", callback_data=f"dk_sop_up_{name}"), InlineKeyboardButton("⏹️ 停止", callback_data=f"dk_sop_down_{name}")],
          [InlineKeyboardButton("🔄 重启", callback_data=f"dk_sop_restart_{name}"), InlineKeyboardButton("🔙 返回", callback_data="dk_list_stacks")]]
    return txt, InlineKeyboardMarkup(kb)
