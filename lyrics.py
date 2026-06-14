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


def extract_artist_song(title: str) -> tuple:
    """
    从视频标题中提取歌手和歌名。
    支持多种常见中文标题格式：
      - "陈奕迅《最佳损友》"
      - "【Hi-res】陈奕迅 - 最佳损友"
      - "在百万豪装录音棚大声听 陈奕迅《最佳损友》【Hi-res】"
    """
    artist, song = "", ""

    # 格式: XXX《歌曲名》
    m = re.search(r"《(.+?)》", title)
    if m:
        song = m.group(1)

    # 格式: 歌手 - 歌名 或 歌手·歌名
    m = re.search(r"([一-鿿\w]+)\s*[-·]\s*([一-鿿\w「」『』【】《》\s]+)", title)
    if m:
        artist = m.group(1).strip()
        if not song:
            song = m.group(2).strip()

    # 如果只找到歌名但没有歌手，尝试从歌名前的部分提取
    if song and not artist:
        before_song = title.split(f"《{song}》")[0].strip()
        # 去掉常见前缀
        before_song = re.sub(
            r"^(在|【.*?】|\[.*?\]|\[|】|\s|Hi-res|Hi-Res|无损|高清|纯享|MV|Official|官方|Live)+",
            "", before_song
        ).strip()
        if before_song:
            artist = before_song

    # 如果都没匹配到，用整个标题搜索
    if not song:
        song = title
        artist = ""

    return artist.strip(), song.strip()


def search_lyrics(artist="", song="", title=""):
    """
    搜索歌词。
    返回 {"lyrics_lrc": "...", "lyrics_plain": "...", "source": "..."} 或 None
    """
    # 构建搜索关键词
    if artist and song:
        keywords = [artist, song]
    elif song:
        keywords = [song]
    elif title:
        # 从标题提取
        artist, song = extract_artist_song(title)
        keywords = [artist, song] if artist else [song]
    else:
        return None

    query = " ".join(keywords)

    try:
        # 网易云音乐搜索 API
        url = "https://music.163.com/api/search/get"
        params = urllib.parse.urlencode({"s": query, "type": 1, "limit": 3})
        req = urllib.request.Request(
            f"{url}?{params}",
            headers={"User-Agent": UA, "Referer": "https://music.163.com"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        songs = data.get("result", {}).get("songs", [])
        if not songs:
            return None

        # 取第一个结果
        best = songs[0]
        song_id = best["id"]
        song_name = best["name"]
        song_artists = ", ".join(a["name"] for a in best.get("artists", []))

        # 获取歌词
        lyric_url = f"https://music.163.com/api/song/lyric?id={song_id}&lv=1"
        req2 = urllib.request.Request(
            lyric_url,
            headers={"User-Agent": UA, "Referer": "https://music.163.com"},
        )
        with urllib.request.urlopen(req2, timeout=10) as resp2:
            lyric_data = json.loads(resp2.read().decode("utf-8"))

        lrc = lyric_data.get("lrc", {}).get("lyric", "")
        tlyric = lyric_data.get("tlyric", {}).get("lyric", "")  # 翻译歌词

        if not lrc.strip():
            return None

        # 去掉 LRC 时间戳，生成纯文本版本
        plain = re.sub(r"\[\d+:\d+[\.\:]\d+\]", "", lrc).strip()
        plain = re.sub(r"\n\s*\n", "\n", plain)  # 去除空行

        return {
            "lyrics_lrc": lrc.strip(),
            "lyrics_plain": plain,
            "source": f"网易云音乐 - {song_name} / {song_artists}",
            "song_name": song_name,
            "artist": song_artists,
        }

    except Exception:
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

        # 添加歌词标签
        uslt = USLT(
            encoding=Encoding.UTF8,
            lang="chi",
            desc="",
            text=lyrics_lrc,
        )
        tags.delall("USLT")  # 先删除旧的
        tags.add(uslt)
        tags.save(mp3_path)
        return True

    except Exception:
        return False
