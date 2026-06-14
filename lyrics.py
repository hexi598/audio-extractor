"""
歌词搜索 & 嵌入模块
- 从网易云音乐搜索歌词
- 将歌词嵌入 MP3 文件的 ID3 标签
"""

import json
import re
import urllib.request
import urllib.parse


UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)


def clean_title(title: str) -> str:
    """去掉标题中常见的噪音后缀，提取纯净的歌名+歌手信息"""
    # 去掉括号内的版本信息
    title = re.sub(r'[\(（][^)）]*?(?:Official|官方|MV|Music Video|Live|现场|Cover|翻唱|Remix|Ver\.|Version|Explicit)[^)）]*?[\)）]',
                   '', title, flags=re.IGNORECASE)
    # 去掉方括号内的标签
    title = re.sub(r'[\[【][^\]】]*?(?:MV|HD|4K|1080p|Hi-res|Hi-Res|无损|高清|纯享|动态歌词|Lyrics|Audio|Official)[^\]】]*?[\]】]',
                   '', title, flags=re.IGNORECASE)
    # 去掉单独的标签前缀
    title = re.sub(r'^[\[【].+?[\]】]\s*', '', title)
    # 去掉末尾的 -Topic / -VEVO 等频道名
    title = re.sub(r'\s*[-–—]\s*Topic\s*$', '', title)
    title = re.sub(r'\s*VEVO\s*$', '', title)
    # 合并多余空格
    title = re.sub(r'\s+', ' ', title).strip()
    return title


def extract_artist_song(title: str) -> tuple:
    """
    从视频标题中提取歌手和歌名。
    覆盖绝大多数 B站 / YouTube / 音乐平台 的标题格式。

    返回 (artist, song) 元组，缺省部分为空字符串。
    """
    if not title:
        return "", ""

    # 先清理噪音
    title = clean_title(title)

    artist, song = "", ""

    # ---- 模式1: 《歌曲名》----
    m = re.search(r'《(.+?)》', title)
    if m:
        song = m.group(1).strip()
        # 提取《》之前的部分作为歌手
        before = title.split(f'《{song}》')[0].strip()
        # 去掉分隔符
        before = re.sub(r'\s*[-–—·|/~]\s*$', '', before)
        if before:
            artist = before

    # ---- 模式2: 歌手 - 歌名 或 歌手 – 歌名（各种分隔符）----
    if not artist or not song:
        # 支持的分隔符: - – — · : |
        m = re.search(
            r'^(.+?)\s*[-–—·|/~:]\s*(.+?)$',
            title
        )
        if m and not re.search(r'[《》]', title):
            left = m.group(1).strip()
            right = m.group(2).strip()
            # 左边不能太长（超过30字不像歌手名）
            if len(left) <= 30 and left and right:
                artist = left
                song = right

    # ---- 模式3: "歌名" by 歌手 ----
    if not artist or not song:
        m = re.search(r'^["“](.+?)["”]\s*by\s+(.+?)$', title, re.IGNORECASE)
        if m:
            song = m.group(1).strip()
            artist = m.group(2).strip()

    # ---- 模式4: 歌手 "歌名" ----
    if not artist or not song:
        m = re.search(r'^(.+?)\s+["“](.+?)["”]', title)
        if m and len(m.group(1)) <= 30:
            artist = m.group(1).strip()
            song = m.group(2).strip()

    # ---- 模式5: 只有《》找到了歌名，没有歌手 ----
    if song and not artist:
        # 尝试从歌名前提取歌手名
        before = title.split(f'《{song}》')[0] if f'《{song}》' in title else title
        before = re.sub(r'\s*[-–—·|/~]\s*$', '', before.strip())
        if before and len(before) <= 30:
            artist = before

    # ---- 兜底: 都没匹配到，整个标题当歌名搜 ----
    if not song:
        song = title
        artist = ""

    # 清理可能残留的噪音
    artist = re.sub(r'\s+', ' ', artist).strip()
    song = re.sub(r'\s+', ' ', song).strip()

    return artist, song


def search_lyrics(artist="", song="", title=""):
    """
    搜索歌词，返回 {"lyrics_lrc": "...", "lyrics_plain": "...", "source": "..."} 或 None。
    采用多轮尝试策略，提高命中率。
    """
    # 如果只传了 title，先尝试提取
    if title and not song:
        artist, song = extract_artist_song(title)

    if not song:
        return None

    # 构建多组搜索关键词，按优先级尝试
    keyword_sets = []

    if artist and song:
        # 精确搜索
        keyword_sets.append(f"{artist} {song}")
        # 只用歌名搜索
        keyword_sets.append(song)
    else:
        keyword_sets.append(song)
        # 尝试去掉括号内容再搜
        clean = re.sub(r'[\(（\[【].*?[\)）\]】]', '', song).strip()
        if clean and clean != song:
            keyword_sets.append(clean)

    for query in keyword_sets:
        result = _search_netease(query)
        if result:
            return result

    return None


def _search_netease(query: str):
    """在网易云音乐搜索歌词"""
    try:
        # 搜索歌曲
        params = urllib.parse.urlencode({"s": query, "type": 1, "limit": 5})
        req = urllib.request.Request(
            f"https://music.163.com/api/search/get?{params}",
            headers={"User-Agent": UA, "Referer": "https://music.163.com"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        songs = data.get("result", {}).get("songs", [])
        if not songs:
            return None

        # 逐个尝试获取歌词（有时第一个结果没歌词）
        for song_info in songs[:3]:
            song_id = song_info["id"]
            song_name = song_info["name"]
            song_artists = ", ".join(
                a["name"] for a in song_info.get("artists", [])
            )

            # 获取歌词
            lyric_url = f"https://music.163.com/api/song/lyric?id={song_id}&lv=1"
            req2 = urllib.request.Request(
                lyric_url,
                headers={"User-Agent": UA, "Referer": "https://music.163.com"},
            )
            with urllib.request.urlopen(req2, timeout=10) as resp2:
                lyric_data = json.loads(resp2.read().decode("utf-8"))

            lrc = lyric_data.get("lrc", {}).get("lyric", "")

            if lrc and lrc.strip():
                # 去掉 LRC 时间戳，生成纯文本
                plain = re.sub(r"\[\d+:\d+[\.:]\d+\]", "", lrc).strip()
                plain = re.sub(r"\n\s*\n", "\n", plain)

                return {
                    "lyrics_lrc": lrc.strip(),
                    "lyrics_plain": plain,
                    "source": f"网易云音乐 - {song_name} / {song_artists}",
                    "song_name": song_name,
                    "artist": song_artists,
                }

    except Exception:
        pass

    return None


def embed_lyrics(mp3_path: str, lyrics_lrc: str) -> bool:
    """
    将歌词嵌入 MP3 文件的 ID3 USLT 标签。
    大多数音乐播放器（Apple Music、酷狗、千千静听等）都能识别。
    """
    try:
        from mutagen.id3 import ID3, USLT, Encoding

        try:
            tags = ID3(mp3_path)
        except Exception:
            tags = ID3()

        uslt = USLT(
            encoding=Encoding.UTF8,
            lang="chi",
            desc="",
            text=lyrics_lrc,
        )
        tags.delall("USLT")
        tags.add(uslt)
        tags.save(mp3_path)
        return True

    except Exception:
        return False
