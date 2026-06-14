"""
B站视频音频下载器 - 直接调用 Bilibili API
无需 yt-dlp 即可下载 B站视频的音频流
"""

import hashlib
import json
import os
import re
import subprocess
import time
import urllib.request
import urllib.parse
from functools import reduce


# ---- WBI 签名 ----
# B站前端 MixinKey 混淆表（固定值，来自 B站 JS 源码）
MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 52, 44, 34,
]

# 固定 User-Agent
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

# WBI 密钥缓存
_wbi_keys_cache = {"img_key": "", "sub_key": "", "ts": 0}


def get_mixin_key(orig: str) -> str:
    """用 B站混淆表生成 mixin key"""
    return reduce(lambda s, i: s + orig[i], MIXIN_KEY_ENC_TAB, '')[:32]


def fetch_wbi_keys():
    """从 B站 nav 接口获取 WBI 签名密钥（缓存 1 小时）"""
    global _wbi_keys_cache
    now = time.time()
    if _wbi_keys_cache["img_key"] and (now - _wbi_keys_cache["ts"]) < 3600:
        return _wbi_keys_cache["img_key"], _wbi_keys_cache["sub_key"]

    url = "https://api.bilibili.com/x/web-interface/nav"
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Referer": "https://www.bilibili.com",
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        raise RuntimeError(f"获取 WBI 密钥失败（网络问题或 B站 API 不可用）: {e}")

    wbi_img = data.get("data", {}).get("wbi_img", {})
    # B站 nav 接口返回 img_url / sub_url（也可能是 img_key / sub_key）
    img_key = wbi_img.get("img_key", "") or wbi_img.get("img_url", "")
    sub_key = wbi_img.get("sub_key", "") or wbi_img.get("sub_url", "")
    # 提取文件名中的 hash 部分
    img_key = img_key.split("/")[-1].split(".")[0] if img_key else ""
    sub_key = sub_key.split("/")[-1].split(".")[0] if sub_key else ""

    if not img_key or not sub_key:
        raise RuntimeError("WBI 密钥获取失败，B站 API 可能已更新")

    _wbi_keys_cache = {"img_key": img_key, "sub_key": sub_key, "ts": now}
    return img_key, sub_key


def sign_params(params: dict) -> dict:
    """对请求参数进行 WBI 签名"""
    img_key, sub_key = fetch_wbi_keys()
    mixin_key = get_mixin_key(img_key + sub_key)

    params["wts"] = int(time.time())
    # 按 key 排序
    sorted_params = sorted(params.items(), key=lambda x: x[0])
    # 拼接参数字符串（只包含值，不包含 key）
    query_string = "&".join(f"{k}={v}" for k, v in sorted_params)
    # 计算 w_rid
    w_rid = hashlib.md5((query_string + mixin_key).encode()).hexdigest()
    params["w_rid"] = w_rid

    return params


def api_request(url, params=None, cookies=None):
    """发起带签名的 B站 API 请求"""
    if params is None:
        params = {}
    params = sign_params(params)
    query_string = urllib.parse.urlencode(params)
    full_url = f"{url}?{query_string}"

    headers = {
        "User-Agent": UA,
        "Referer": "https://www.bilibili.com",
    }
    if cookies:
        headers["Cookie"] = cookies

    req = urllib.request.Request(full_url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"API 请求失败 HTTP {e.code}: {url}")
    except Exception as e:
        raise RuntimeError(f"API 请求异常: {e}")


def extract_bvid(url: str) -> str:
    """从各种B站链接中提取 BV 号"""
    patterns = [
        r"BV([a-zA-Z0-9]{10})",
        r"b23\.tv/([a-zA-Z0-9]+)",  # 短链接（需解析）
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            bv = match.group(1)
            # 处理短链接 - 直接解析
            if "b23.tv" in url[:20]:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                try:
                    with urllib.request.urlopen(req, timeout=10) as resp:
                        final_url = resp.geturl()
                    return extract_bvid(final_url)
                except Exception:
                    pass
            return f"BV{bv}" if not bv.startswith("BV") else bv
    raise ValueError(f"无法从链接中解析 BV 号: {url}")


def get_video_info(bvid: str, cookies=None):
    """获取视频基本信息（标题、cid 等）"""
    data = api_request(
        "https://api.bilibili.com/x/web-interface/view",
        {"bvid": bvid},
        cookies=cookies,
    )
    if data.get("code") != 0:
        raise RuntimeError(f"获取视频信息失败: {data.get('message', '未知错误')}")

    video_data = data["data"]
    title = video_data.get("title", "unknown")
    cid = video_data.get("cid", 0)
    if not cid and video_data.get("pages"):
        cid = video_data["pages"][0].get("cid", 0)

    return {
        "title": title,
        "bvid": bvid,
        "cid": cid,
        "duration": video_data.get("duration", 0),
    }


def get_audio_url(bvid: str, cid: int, cookies=None):
    """获取音频流的直接 URL"""
    data = api_request(
        "https://api.bilibili.com/x/player/wbi/playurl",
        {
            "bvid": bvid,
            "cid": str(cid),
            "fnval": "4048",   # DASH + Dolby + 8K + Hi-Res
            "fnver": "0",
            "fourk": "1",
        },
        cookies=cookies,
    )
    if data.get("code") != 0:
        raise RuntimeError(f"获取播放地址失败: {data.get('message', '未知错误')}")

    dash = data.get("data", {}).get("dash", {})
    if not dash:
        raise RuntimeError("该视频不支持 DASH 格式（可能是老视频）")

    # 优先选最高音质的音频流
    audio_streams = dash.get("audio", [])
    if not audio_streams:
        raise RuntimeError("未找到音频流")

    # 按码率/质量排序，选最高音质
    best_audio = max(audio_streams, key=lambda x: x.get("bandwidth", 0))
    # 同时返回备用 URL
    return (
        best_audio.get("baseUrl") or best_audio.get("base_url", ""),
        best_audio.get("backupUrl") or best_audio.get("backup_url", []),
        best_audio.get("bandwidth", 0),
        best_audio.get("codecs", "mp4a"),
    )


def _download_raw_audio(url: str, output_path: str, backup_urls=None):
    """下载原始音频流到临时文件"""
    import ssl

    if backup_urls is None:
        backup_urls = []

    # 全部候选 URL
    all_urls = [url] + (backup_urls if isinstance(backup_urls, list) else [backup_urls])

    # 创建 SSL 上下文（绕过 PyInstaller 打包后证书丢失问题）
    ssl_ctx = ssl.create_default_context()
    try:
        ssl_ctx = ssl._create_unverified_context()
    except Exception:
        pass

    last_error = None
    for idx, try_url in enumerate(all_urls):
        if not try_url:
            continue
        try:
            headers = {
                "User-Agent": UA,
                "Referer": "https://www.bilibili.com",
                "Origin": "https://www.bilibili.com",
            }
            req = urllib.request.Request(try_url, headers=headers)

            with urllib.request.urlopen(req, timeout=60, context=ssl_ctx) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                with open(output_path, "wb") as f:
                    while True:
                        chunk = resp.read(65536)
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                return total or downloaded
        except Exception as e:
            last_error = e
            continue  # 试下一个 URL

    raise RuntimeError(f"下载失败 (已尝试 {len(all_urls)} 个地址): {last_error}")


def download_audio(url: str, output_path: str, ffmpeg_path="ffmpeg"):
    """下载音频流并转为目标格式（保留用于命令行调用）"""
    raw_file = output_path + ".temp_audio"
    try:
        _download_raw_audio(url, raw_file)
    except Exception:
        raise

    print(f"    转码...")
    cmd = [
        ffmpeg_path, "-y",
        "-i", raw_file,
        "-acodec", "libmp3lame",
        "-b:a", "320k",
        "-vn",
        output_path,
    ]
    try:
        subprocess.run(cmd, check=True, capture_output=True, timeout=120)
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"音频转码失败: {e.stderr.decode() if e.stderr else e}")
    finally:
        if os.path.exists(raw_file):
            os.remove(raw_file)

    return output_path
