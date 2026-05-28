from flask import Flask, jsonify, request, send_from_directory
from pynput.keyboard import Key, Controller, KeyCode
import argparse
import socket
import os
# import qrcode
import time
import json
import xml.etree.ElementTree as ET
import re
import html
import copy

keyboard = Controller()


class SoundpadPipe:
    """通过 Windows 命名管道与 Soundpad Remote Control API 通信"""

    PIPE_NAME = r"\\.\pipe\sp_remote_control"

    def __init__(self):
        self.pipe = None
        self._connected = False

    def connect(self):
        """连接到 Soundpad 的命名管道"""
        try:
            self.pipe = open(self.PIPE_NAME, "r+b", buffering=0)
            self._connected = True
            return True
        except FileNotFoundError:
            print("[SoundpadPipe] Soundpad 未运行（管道不存在）")
            self._connected = False
            return False
        except Exception as e:
            print(f"[SoundpadPipe] 连接失败: {e}")
            self._connected = False
            return False

    def disconnect(self):
        """断开管道连接"""
        if self.pipe:
            try:
                self.pipe.close()
            except Exception:
                pass
            finally:
                self.pipe = None
        self._connected = False

    def is_connected(self):
        return self._connected and self.pipe is not None

    def send_command(self, command):
        """发送命令并读取响应"""
        try:
            self.pipe.write(command.encode("utf-8"))
            # 循环读取直到收完完整响应
            chunks = []
            while True:
                chunk = self.pipe.read(65536)
                if not chunk:
                    break
                chunks.append(chunk)
                # 如果收到闭合标签，说明响应完整了
                if b"</SoundList>" in chunk or b"/> " in chunk or len(chunk) < 65536:
                    break
            return b"".join(chunks) if chunks else None
        except Exception as e:
            print(f"[SoundpadPipe] 命令 '{command}' 执行失败: {e}")
            self.disconnect()
            return None

    def _fix_xml(self, xml_str):
        """修复 XML 中常见的格式问题（未转义的特殊字符）"""
        # 去掉 BOM 和尾部 null 字符
        xml_str = xml_str.lstrip("\ufeff").rstrip("\x00")
        # 修复属性值中的未转义 & 符号（& 后面不跟 amp;/lt;/gt;/quot;/apos;/# 的）
        xml_str = re.sub(r'&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9a-fA-F]+;)', '&amp;', xml_str)
        return xml_str

    def get_all_sounds(self):
        """获取 Soundpad 中所有音频列表，返回 [{index, title, duration}, ...]"""
        data = self.send_command("GetSoundlist()")
        if not data:
            return []
        try:
            xml_str = data.decode("utf-8", errors="replace")
            xml_str = self._fix_xml(xml_str)

            # 方案 A：标准 XML 解析
            try:
                root = ET.fromstring(xml_str)
                sounds = []
                for sound in root.findall("Sound"):
                    idx = sound.attrib.get("index", "")
                    title = html.unescape(sound.attrib.get("title", ""))
                    duration = sound.attrib.get("duration", "")
                    sounds.append({
                        "index": idx,
                        "title": title,
                        "duration": duration
                    })
                if sounds:
                    return sounds
            except ET.ParseError as pe:
                print(f"[SoundpadPipe] 标准XML解析失败({pe}), 尝试正则解析...")

            # 方案 B：正则表达式从 XML 中提取
            sounds = []
            pattern = re.compile(
                r'<Sound\s+[^>]*?index="([^"]*)"[^>]*?title="([^"]*)"[^>]*?(?:duration="([^"]*)")?[^>]*?/?>',
                re.DOTALL
            )
            for match in pattern.finditer(xml_str):
                idx = match.group(1)
                title = html.unescape(match.group(2))
                duration = match.group(3) or ""
                sounds.append({
                    "index": idx,
                    "title": title,
                    "duration": duration
                })
            if sounds:
                print(f"[SoundpadPipe] 正则解析成功，获取 {len(sounds)} 个音频")
                return sounds

            print("[SoundpadPipe] 所有解析方式均失败")
            return []
        except Exception as e:
            print(f"[SoundpadPipe] 解析音频列表失败: {e}")
            return []

    def play_sound(self, sound_id):
        """播放指定 index 的音频"""
        result = self.send_command(f"DoPlaySound({sound_id})")
        return result is not None

    def stop_sound(self):
        """停止当前播放"""
        result = self.send_command("DoStopSound()")
        return result is not None


def parse_spl_file(filepath):
    """解析 SPL XML 获取音频列表(1-based 位置索引)和 Categories 分组"""
    try:
        tree = ET.parse(filepath)
        root = tree.getroot()

        # 解析所有顶层 <Sound> 元素（按文档顺序 1-based 索引）
        top_sounds = list(root.findall("Sound"))
        sounds = []
        for i, sound in enumerate(top_sounds):
            sounds.append({
                "index": str(i + 1),
                "hash": sound.attrib.get("hash", ""),
                "title": sound.attrib.get("title", ""),
                "duration": sound.attrib.get("duration", ""),
                "artist": sound.attrib.get("artist", ""),
            })

        # 解析 <Categories> 分组树
        categories_node = root.find("Categories")
        categories = []
        if categories_node is not None:
            categories = _parse_category_children(categories_node, sounds)

        return sounds, categories
    except Exception as e:
        print(f"[SPL] 解析失败: {e}")
        return [], []


def _parse_category_children(node, all_sounds):
    """递归解析 Category 子节点，将 Sound 引用 id 解析为实际音频信息"""
    categories = []
    for cat in node.findall("Category"):
        name = cat.attrib.get("name", "")
        if not name:
            continue

        # 收集该分类下直接引用的音频
        cat_sounds = []
        for snd_ref in cat.findall("Sound"):
            sid_str = snd_ref.attrib.get("id", "")
            if sid_str:
                try:
                    sid = int(sid_str)
                    if 1 <= sid <= len(all_sounds):
                        s = all_sounds[sid - 1]
                        cat_sounds.append({
                            "index": s["index"],
                            "title": s["title"],
                            "duration": s["duration"],
                        })
                except ValueError:
                    pass

        # 递归处理子分类
        children = _parse_category_children(cat, all_sounds)

        categories.append({
            "name": name,
            "sounds": cat_sounds,
            "children": children,
        })

    return categories

app = Flask(__name__)


@app.route("/heartbeat", methods=["GET"])
def heartbeat():
    return jsonify(status="alive")


@app.route("/keyboard", methods=["POST"])
def keyboard_event():
    try:
        data = request.get_json()
        print(data)
        # time.sleep(1)
        keyboard.press(Key.alt_l)
        time.sleep(0.02)
        for key in data["key"]:
            t = int(key) + 96
            keyboard.press(KeyCode.from_vk(t))
            time.sleep(0.02)
        for key in data["key"]:
            t = int(key) + 96
            time.sleep(0.02)
            keyboard.release(KeyCode.from_vk(t))
        keyboard.release(Key.alt_l)
        return jsonify(status="ok")
    except Exception as e:
        return jsonify(status="error", message=str(e))


@app.route("/stop", methods=["POST"])
def stop():
    try:
        keyboard.press(Key.alt_l)
        keyboard.press("0")
        time.sleep(0.05)
        keyboard.release("0")
        keyboard.release(Key.alt_l)
        return jsonify(status="ok")
    except Exception as e:
        return jsonify(status="error", message=str(e))


@app.route("/", methods=["GET"])
def index():
    print("index")
    return send_from_directory("web", "index.html")


@app.route("/<path:filename>", methods=["GET"])
def serve_file(filename):
    return send_from_directory("web", filename)


@app.route("/sync_sounds", methods=["GET"])
def sync_sounds():
    """同步 Soundpad 音频列表：优先使用命名管道，失败则回退到 SPL 文件"""
    sounds = []
    categories = []
    method = "spl"

    # 查找 SPL 文件路径（用于解析分组）
    spl_paths = [
        os.path.join(os.path.dirname(os.path.dirname(rootdir)), "音频路径.spl"),
        os.path.join(rootdir, "音频路径.spl"),
        os.path.join(os.path.dirname(rootdir), "音频路径.spl"),
        r"D:\音频路径.spl",
    ]

    # 先解析 SPL（获取分组信息和回退音频列表）
    spl_sounds = []
    for spl_path in spl_paths:
        if os.path.exists(spl_path):
            print(f"[sync_sounds] 找到 SPL 文件: {spl_path}")
            spl_sounds, categories = parse_spl_file(spl_path)
            print(f"[sync_sounds] 解析结果: {len(spl_sounds)} 个音频, {len(categories)} 个主分类")
            break

    # 方案一：通过命名管道 API 获取实时音频列表
    pipe = SoundpadPipe()
    if pipe.connect():
        try:
            pipe_sounds = pipe.get_all_sounds()
            if pipe_sounds:
                sounds = pipe_sounds
                method = "pipe"
                # 将分类中的 SPL 索引按标题映射为管道 API 返回的索引
                if categories and spl_sounds:
                    categories = _map_categories_to_pipe(categories, spl_sounds, pipe_sounds)
        except Exception as e:
            print(f"[sync_sounds] 管道方式失败: {e}")
        finally:
            pipe.disconnect()

    # 方案二：回退到 SPL 音频列表
    if not sounds and spl_sounds:
        sounds = spl_sounds
        method = "spl"

    if not sounds:
        return jsonify(status="error", message="无法获取音频列表：Soundpad 未运行且未找到 SPL 文件")

    # 收集所有出现在分类中的音效索引（用于前端过滤"自定义控件"中的重复项）
    category_sound_indices = []
    if categories:
        def _collect_indices(cat_list):
            for cat in cat_list:
                for s in cat.get("sounds", []):
                    category_sound_indices.append(s.get("index", ""))
                if cat.get("children"):
                    _collect_indices(cat["children"])
        _collect_indices(categories)

    return jsonify(
        status="ok", method=method, sounds=sounds,
        categories=categories,
        category_sound_indices=category_sound_indices
    )


def _map_categories_to_pipe(categories, spl_sounds, pipe_sounds):
    """将分类中的 SPL 1-based 索引替换为管道 API 返回的 Soundpad 索引

    匹配策略（按优先级）：
    1. 标题精确匹配（忽略大小写和首尾空格）
    2. 标题标准化匹配（去掉特殊字符后比较）
    3. 回退：保留 SPL 原始索引（管道 API 可能兼容同一编号体系）
    """
    # 建立 SPL 索引 -> 完整信息 的映射
    spl_idx_to_info = {}
    for s in spl_sounds:
        idx = s.get("index", "")
        if idx:
            spl_idx_to_info[idx] = {
                "title": s.get("title", ""),
                "hash": s.get("hash", ""),
            }

    # 建立 标准化标题 -> 管道索引 的映射
    def normalize_title(t):
        """去除特殊字符用于模糊匹配"""
        import re
        t = t.strip().lower()
        t = re.sub(r'[^\w\u4e00-\u9fff]+', '', t)  # 只保留字母数字中文
        return t

    title_to_pipe_idx = {}
    title_norm_to_pipe_idx = {}
    for ps in pipe_sounds:
        t = ps.get("title", "").strip()
        if t:
            title_to_pipe_idx[t.lower()] = ps.get("index", "")
            nt = normalize_title(t)
            if nt:
                title_norm_to_pipe_idx[nt] = ps.get("index", "")

    unmapped_count = 0

    def walk(node_list):
        nonlocal unmapped_count
        for cat in node_list:
            new_sounds = []
            for s in cat.get("sounds", []):
                spl_idx = s.get("index", "")
                info = spl_idx_to_info.get(spl_idx, {})
                title = info.get("title", s.get("title", ""))
                matched = True  # 标记是否通过标题匹配到管道索引

                # 策略1: 原始标题精确匹配
                pipe_idx = title_to_pipe_idx.get(title.strip().lower(), "")

                # 策略2: 标准化标题模糊匹配
                if not pipe_idx:
                    nt = normalize_title(title)
                    if nt:
                        pipe_idx = title_norm_to_pipe_idx.get(nt, "")

                # 策略3: 回退到 SPL 索引——标记为需要键盘模拟播放
                if not pipe_idx:
                    pipe_idx = spl_idx
                    matched = False
                    unmapped_count += 1
                    if unmapped_count <= 5:
                        print(f"[_map] 标题未匹配，回退用 SPL 索引 {spl_idx}: \"{title[:40]}\"")

                entry = {
                    "index": pipe_idx,
                    "title": s["title"],
                    "duration": s.get("duration", ""),
                }
                if not matched:
                    entry["use_keyboard"] = True  # 前端读此标记走键盘模拟
                new_sounds.append(entry)
            cat["sounds"] = new_sounds
            if cat.get("children"):
                walk(cat["children"])

    result = copy.deepcopy(categories)
    walk(result)

    if unmapped_count > 0:
        print(f"[_map] 共 {unmapped_count} 个音频标题匹配失败，已回退使用 SPL 索引")

    return result


@app.route("/play_sound", methods=["POST"])
def play_sound():
    """通过 Soundpad API 直接播放指定音频"""
    try:
        data = request.get_json()
        sound_id = data.get("index", "")
        if not sound_id:
            return jsonify(status="error", message="缺少 index 参数")

        pipe = SoundpadPipe()
        if not pipe.connect():
            # 回退到键盘模拟方式
            keyboard_event_internal(sound_id)
            return jsonify(status="ok", method="keyboard")

        try:
            ok = pipe.play_sound(sound_id)
            pipe.disconnect()
            if ok:
                return jsonify(status="ok", method="pipe")
            else:
                return jsonify(status="error", message="播放命令发送失败")
        except Exception as e:
            pipe.disconnect()
            return jsonify(status="error", message=str(e))
    except Exception as e:
        return jsonify(status="error", message=str(e))


@app.route("/stop_sound", methods=["POST"])
def stop_sound_api():
    """通过 Soundpad API 停止播放"""
    try:
        pipe = SoundpadPipe()
        if pipe.connect():
            try:
                ok = pipe.stop_sound()
                pipe.disconnect()
                if ok:
                    return jsonify(status="ok", method="pipe")
            except Exception:
                pipe.disconnect()

        # 回退到键盘模拟 Alt+0
        keyboard.press(Key.alt_l)
        keyboard.press("0")
        time.sleep(0.05)
        keyboard.release("0")
        keyboard.release(Key.alt_l)
        return jsonify(status="ok", method="keyboard")
    except Exception as e:
        return jsonify(status="error", message=str(e))


def keyboard_event_internal(key_str):
    """内部键盘模拟，供 play_sound 回退使用"""
    keyboard.press(Key.alt_l)
    time.sleep(0.02)
    for key in key_str:
        t = int(key) + 96
        keyboard.press(KeyCode.from_vk(t))
        time.sleep(0.02)
    for key in key_str:
        t = int(key) + 96
        time.sleep(0.02)
        keyboard.release(KeyCode.from_vk(t))
    keyboard.release(Key.alt_l)


def get_all_ip_addresses():
    hostname = socket.gethostname()
    ip_addresses = socket.gethostbyname_ex(hostname)[2]
    return ip_addresses

@app.route("/save_config", methods=["POST"])
def save_config():
    try:
        data = request.get_data().decode("utf-8")
        with open(os.path.join(rootdir, "config.json"), "w", encoding="utf-8") as f:
            f.write(data)
        return jsonify(status="ok")
    except Exception as e:
        return jsonify(status="error", message=str(e))

@app.route("/load_config", methods=["GET"])
def load_config():
    try:
        with open(os.path.join(rootdir, "config.json"), "r", encoding="utf-8") as f:
            data = f.read()
        return jsonify(status="ok", data=data)
    except Exception as e:
        return jsonify(status="error", message=str(e))
        
                       

rootdir = os.path.abspath(os.path.dirname(__file__))
    
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="将收到的post请求转发到本地键盘")
    parser.add_argument(
        "-p",
        "--port",
        type=int,
        default=11451,
        help="服务器端口, 默认11451，例:-p 14514",
    )
    args = parser.parse_args()
    ips = get_all_ip_addresses()
    print("请尝试以下地址")
    for ip in ips:
        print(ip + ":" + str(args.port))
    # generate_qr_code(ip_str)
    app.run(host="0.0.0.0", port=args.port, debug=True)
