"""
歌词搜索 & 嵌入模块
- 从网易云音乐搜索歌词
- 支持中英文双语歌词（原文 + 中文翻译）
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

# 相似度最低阈值，低于此值视为不匹配
MIN_SIMILARITY_THRESHOLD = 0.25


def clean_title(title: str) -> str:
    """去掉标题中常见的噪音后缀/前缀，提取纯净的歌名+歌手信息"""
    # 去掉括号内的版本信息
    title = re.sub(r'[\(（[\[【][^)）\]】]*?(?:Official|官方|MV|Music Video|Live|现场|Cover|翻唱|Remix|Ver\.|Version|Explicit|Hi-Res|Hi-res|HIRES|无损|高清|纯享|动态歌词|Lyrics|Audio|Official|Instrumental|伴奏|KTV|Karaoke|Performance|feat\.|ft\.)[^)）\]】]*?[\)）\]】]',
                   '', title, flags=re.IGNORECASE)
    # 去掉方括号/全角括号内的标签
    title = re.sub(r'[\[【][^\]】]*?(?:MV|HD|4K|1080p|60fps|Hi-res|Hi-Res|无损|高清|纯享|动态歌词|Lyrics|Audio|Official|HIRES|HQ|SQ|HDR)[^\]】]*?[\]】]',
                   '', title, flags=re.IGNORECASE)
    # 去掉单独的标签前缀
    title = re.sub(r'^[\[【].+?[\]】]\s*', '', title)
    # 去掉常见的噪音前缀（如"在百万录音棚听"）
    title = re.sub(r'^.{0,20}?(?:在.{1,15}?(?:录音棚|音响|耳机|音箱|扬声器).{0,10}?[听试])\s*', '', title)
    title = re.sub(r'^(?:戴上耳机|[试尝]听|来听听|听听看)\s*', '', title)
    # 去掉末尾的 -Topic / -VEVO 等频道名
    title = re.sub(r'\s*[-–—]\s*Topic\s*$', '', title)
    title = re.sub(r'\s*VEVO\s*$', '', title)
    # 去掉末尾的分隔符 + 空白
    title = re.sub(r'\s*[-–—·|/~:]\s*$', '', title)
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

    # ---- 模式1: 《歌曲名》或【歌曲名】或「歌曲名」（全角书名号/方括号/日文引号）----
    m = re.search(r'[《【「](.+?)[》】」]', title)
    if m:
        raw_song = m.group(1).strip()
        # 排除纯标签（如【Hi-Res】）
        if re.match(r'^(?:Hi[-\s]?Res|HIRES|无损|高清|HQ|SQ|MV|Official|Live|现场|纯享|4K|1080p|60fps|HDR)$', raw_song, re.IGNORECASE):
            song = ""  # 重置，走后续匹配
        else:
            song = raw_song
            # 提取引号之前的部分作为歌手
            prefix = title.split(m.group(0))[0].strip()
            prefix = re.sub(r'\s*[-–—·|/~:]\s*$', '', prefix)
            # 尝试从长前缀中提取歌手名（取最后一个看起来像歌手名的片段）
            if prefix:
                # 如果前缀太长（>15字），尝试取最后一部分
                if len(prefix) > 15:
                    # 取最后一个分隔符之后的部分
                    parts = re.split(r'\s+', prefix)
                    if len(parts) > 1:
                        # 取末尾较短的几段作为歌手
                        short_prefix = ''
                        for part in reversed(parts):
                            candidate = (part + ' ' + short_prefix).strip()
                            if len(candidate) <= 15:
                                short_prefix = candidate
                            else:
                                break
                        if short_prefix:
                            prefix = short_prefix
                artist = prefix if len(prefix) <= 15 else ''

    # ---- 模式2: 歌手 - 歌名 或 歌手 – 歌名（各种分隔符）----
    if not artist or not song:
        m = re.search(
            r'^(.+?)\s*[-–—·|/~:]\s*(.+?)$',
            title
        )
        if m and not re.search(r'[《》【】]', title):
            left = m.group(1).strip()
            right = m.group(2).strip()
            # 左边不能太长（超过30字不像歌手名）
            if len(left) <= 30 and left and right:
                # 右边去掉可能的噪音后缀
                right_clean = re.sub(r'\s*[\(（[\[【].*?(?:Official|MV|Live|现场|Cover|翻唱|Remix|Hi-Res).*?[\)）\]】]?\s*$', '', right, flags=re.IGNORECASE)
                artist = left
                song = right_clean.strip() or right.strip()

    # ---- 模式3: "歌名" by 歌手 ----
    if not artist or not song:
        m = re.search(r'^[""“”](.+?)[""“”]\s*by\s+(.+?)$', title, re.IGNORECASE)
        if m:
            song = m.group(1).strip()
            artist = m.group(2).strip()

    # ---- 模式4: 歌手 "歌名" ----
    if not artist or not song:
        m = re.search(r'^(.+?)\s+[""“”](.+?)[""“”]', title)
        if m and len(m.group(1)) <= 30:
            artist = m.group(1).strip()
            song = m.group(2).strip()

    # ---- 模式5: 只有《》/【】找到了歌名，没有歌手 ----
    if song and not artist:
        before = title
        for delim in ['《', '【']:
            end = '》' if delim == '《' else '】'
            if f'{delim}{song}{end}' in before:
                before = before.split(f'{delim}{song}{end}')[0]
                break
        before = re.sub(r'\s*[-–—·|/~:]\s*$', '', before.strip())
        if before and len(before) <= 30:
            artist = before

    # ---- 兜底: 都没匹配到，整个标题当歌名搜 ----
    if not song:
        song = title
        artist = ""

    # 清理可能残留的噪音
    artist = re.sub(r'\s+', ' ', artist).strip()
    song = re.sub(r'\s+', ' ', song).strip()

    # 去掉歌名末尾的分隔符 + 空白
    song = re.sub(r'\s*[-–—·|/~:]\s*$', '', song)

    return artist, song


def _tokenize(text: str) -> set:
    """将文本拆分为 token 集合（用于相似度计算）"""
    if not text:
        return set()
    text = text.lower().strip()
    # 按空格和常见分隔符拆分
    tokens = set(re.split(r'[\s,，、·/\-–—|&]+', text))
    # 也加入单字（对中文友好）
    tokens.update(re.findall(r'[一-鿿]', text))
    # 加入原始关键词
    tokens.add(text)
    # 去掉空 token
    tokens.discard('')
    return tokens


def _similarity(query: str, candidate_name: str, candidate_artist: str) -> float:
    """计算搜索词与候选结果的相似度分数 (0~1)"""
    if not query or not candidate_name:
        return 0.0

    query_tokens = _tokenize(query)
    name_tokens = _tokenize(candidate_name)
    artist_tokens = _tokenize(candidate_artist)

    # 计算歌名匹配度
    if query_tokens and name_tokens:
        name_overlap = len(query_tokens & name_tokens)
        name_score = name_overlap / max(len(query_tokens), 1)
    else:
        name_score = 0.0

    # 计算歌手匹配度
    if query_tokens and artist_tokens:
        artist_overlap = len(query_tokens & artist_tokens)
        artist_score = artist_overlap / max(len(query_tokens), 1)
    else:
        artist_score = 0.0

    # 综合分数（歌名权重更高）
    score = name_score * 0.7 + artist_score * 0.3

    # 精确子串匹配加成
    query_lower = query.lower()
    if query_lower in candidate_name.lower():
        score = max(score, 0.6)
    if candidate_artist and query_lower in candidate_artist.lower():
        score = max(score, 0.5)

    return min(score, 1.0)


def _merge_lrc_with_translation(lrc: str, tlyric: str) -> str:
    """
    将原文 LRC 和翻译 LRC 合并为双语歌词。
    同时间戳的行会相邻排列（播放器会交替显示原文和译文）。
    """
    if not tlyric or not tlyric.strip():
        return lrc

    # 解析翻译歌词的时间戳和文本
    tl_lines = {}
    for line in tlyric.strip().split('\n'):
        m = re.match(r'\[(\d+:\d+[\.:]\d+)\](.*)', line.strip())
        if m:
            ts = m.group(1)
            text = m.group(2).strip()
            if text:
                tl_lines[ts] = text

    if not tl_lines:
        return lrc

    # 合并：对每个原文行，如果有对应翻译则追加
    merged = []
    for line in lrc.strip().split('\n'):
        line = line.strip()
        if not line:
            merged.append('')
            continue

        m = re.match(r'\[(\d+:\d+[\.:]\d+)\](.*)', line)
        if m:
            ts = m.group(1)
            orig_text = m.group(2).strip()
            merged.append(line)

            # 如果存在对应时间戳的翻译，追加一行
            if ts in tl_lines and tl_lines[ts] != orig_text:
                merged.append(f"[{ts}]{tl_lines[ts]}")
        else:
            # 元数据行（如 [ti:...] [ar:...]）保留
            merged.append(line)

    return '\n'.join(merged)


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
        keyword_sets.append((artist, song, f"{artist} {song}"))
        # 只用歌名搜索
        keyword_sets.append(("", song, song))
    else:
        keyword_sets.append(("", song, song))

    # 尝试去掉括号内容再搜
    clean_song = re.sub(r'[\(（\[【].*?[\)）\]】]', '', song).strip()
    if clean_song and clean_song != song:
        if artist:
            keyword_sets.append((artist, clean_song, f"{artist} {clean_song}"))
        keyword_sets.append(("", clean_song, clean_song))

    for search_artist, search_song, query in keyword_sets:
        result = _search_netease(query, artist=search_artist, song=search_song)
        if result:
            return result

    return None


def _search_netease(query: str, artist="", song=""):
    """
    在网易云音乐搜索歌词，使用相似度匹配选择最佳结果。
    同时获取翻译歌词 (tlyric) 并合并为双语输出。
    """
    try:
        # 搜索歌曲
        params = urllib.parse.urlencode({"s": query, "type": 1, "limit": 10})
        req = urllib.request.Request(
            f"https://music.163.com/api/search/get?{params}",
            headers={"User-Agent": UA, "Referer": "https://music.163.com"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))

        songs = data.get("result", {}).get("songs", [])
        if not songs:
            return None

        # 计算所有候选歌曲的相似度分数
        scored_candidates = []
        for song_info in songs:
            song_name = song_info.get("name", "")
            song_artists = ", ".join(
                a["name"] for a in song_info.get("artists", [])
            )

            # 计算匹配度
            score = _similarity(query, song_name, song_artists)

            # 如果提供了原始 artist/song，做额外校验
            if artist and song_artists:
                artist_tokens = _tokenize(artist)
                result_artist_tokens = _tokenize(song_artists)
                if artist_tokens and result_artist_tokens:
                    artist_overlap = len(artist_tokens & result_artist_tokens)
                    if artist_overlap > 0:
                        score += 0.15  # 歌手匹配加成

            if song and song_name:
                song_tokens = _tokenize(song)
                result_song_tokens = _tokenize(song_name)
                if song_tokens and result_song_tokens:
                    song_overlap = len(song_tokens & result_song_tokens)
                    if song_overlap > 0:
                        score += 0.15  # 歌名匹配加成

            scored_candidates.append({
                "id": song_info["id"],
                "name": song_name,
                "artists": song_artists,
                "score": min(score, 1.0),
            })

        # 按分数从高到低排序
        scored_candidates.sort(key=lambda x: x["score"], reverse=True)
        best_score = scored_candidates[0]["score"]

        # 低于阈值则放弃
        if best_score < MIN_SIMILARITY_THRESHOLD:
            return None

        # 逐个尝试获取歌词（按分数排序）
        for candidate in scored_candidates[:5]:
            song_id = candidate["id"]
            song_name = candidate["name"]
            song_artists = candidate["artists"]

            # 获取歌词（同时获取 lrc 和 tlyric）
            lyric_url = f"https://music.163.com/api/song/lyric?id={song_id}&lv=1"
            req2 = urllib.request.Request(
                lyric_url,
                headers={"User-Agent": UA, "Referer": "https://music.163.com"},
            )
            try:
                with urllib.request.urlopen(req2, timeout=10) as resp2:
                    lyric_data = json.loads(resp2.read().decode("utf-8"))
            except Exception:
                continue

            lrc = lyric_data.get("lrc", {}).get("lyric", "")
            tlyric = lyric_data.get("tlyric", {}).get("lyric", "")

            if lrc and lrc.strip():
                # 合并双语歌词
                if tlyric and tlyric.strip():
                    merged_lrc = _merge_lrc_with_translation(lrc, tlyric)
                else:
                    merged_lrc = lrc.strip()

                # 去掉 LRC 时间戳，生成纯文本
                plain = re.sub(r"\[\d+:\d+[\.:]\d+\]", "", merged_lrc).strip()
                plain = re.sub(r"\n\s*\n", "\n", plain)

                source_info = f"网易云音乐 - {song_name} / {song_artists}"
                if tlyric and tlyric.strip():
                    source_info += " [双语]"

                return {
                    "lyrics_lrc": merged_lrc.strip(),
                    "lyrics_plain": plain,
                    "source": source_info,
                    "song_name": song_name,
                    "artist": song_artists,
                    "score": candidate["score"],
                }

            # 如果这首没歌词，继续下一个候选
            continue

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
