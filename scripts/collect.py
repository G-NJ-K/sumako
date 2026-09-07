#!/usr/bin/env python3
"""
スマ庫 動画自動収集スクリプト

収集元:
  1) config.json の youtube_channels … RSSで新着取得（filter_keywords一致のみ）
  2) config.json の players          … プレイヤー名でYouTube検索して収集
        - dr_mario_only=true  … 「名前 ドクターマリオ」で検索し、ドクマリ動画だけ
        - dr_mario_only=false … 「名前 スマブラ」で幅広く（ドクマリ使いの選手向け）
        - aliases（表記ズレ）も全部検索・タグ付けの対象
        - 環境変数 YOUTUBE_API_KEY があれば公式API、無ければキーなし解析
  3) config.json の twitch_channels  … TwitchのVOD（要 TWITCH_CLIENT_ID/SECRET）

各動画に players（登場プレイヤー名）タグを付与し、サイトのタブ分けに使う。
結果は videos.json に保存。GitHub Actions から定期実行される想定。
"""
import json
import os
import re
import sys
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(ROOT, "config.json")
VIDEOS_PATH = os.path.join(ROOT, "videos.json")

NS = {
    "atom": "http://www.w3.org/2005/Atom",
    "yt": "http://www.youtube.com/xml/schemas/2015",
    "media": "http://search.yahoo.com/mrss/",
}
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36"


def fetch(url, headers=None, data=None, method=None):
    h = {"User-Agent": UA, "Accept-Language": "ja,en;q=0.8"}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h, data=data, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


def matches_keywords(text, keywords):
    if not keywords:
        return True
    low = (text or "").lower()
    return any(k.lower() in low for k in keywords)


# ---------------- プレイヤー名マッチャ ----------------
def build_matchers(players):
    """[(canonical_name, [('sub', text) | ('word', regex), ...]), ...]"""
    matchers = []
    for p in players:
        name = p.get("name")
        if not name:
            continue
        aliases = p.get("aliases") or [name]
        pats = []
        for a in aliases:
            if not a:
                continue
            if re.search(r"[^\x00-\x7f]", a):        # 日本語などを含む → 部分一致
                pats.append(("sub", a.lower()))
            else:                                     # 英数字のみ → 単語境界で一致（誤検出を減らす）
                pats.append(("word", re.compile(r"(?<![A-Za-z0-9])" + re.escape(a) + r"(?![A-Za-z0-9])", re.I)))
        matchers.append((name, pats))
    return matchers


def tag_players(text, matchers):
    low = (text or "").lower()
    found = []
    for name, pats in matchers:
        for kind, pat in pats:
            if (kind == "sub" and pat in low) or (kind == "word" and pat.search(text or "")):
                found.append(name)
                break
    return found


def make_video(vid, title, author, published, players):
    return {
        "source": "youtube",
        "id": vid,
        "title": title,
        "author": author,
        "published": published,
        "url": f"https://www.youtube.com/watch?v={vid}",
        "thumb": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
        "players": players,
    }


# ---------------- YouTube: チャンネルRSS ----------------
def resolve_channel_id(channel):
    channel = channel.strip()
    if re.fullmatch(r"UC[0-9A-Za-z_-]{22}", channel):
        return channel
    url = channel if channel.startswith("http") else "https://www.youtube.com/" + (channel if channel.startswith("@") else "@" + channel)
    try:
        html = fetch(url).decode("utf-8", "ignore")
        m = re.search(r'"(?:channelId|externalId)":"(UC[0-9A-Za-z_-]{22})"', html)
        if m:
            return m.group(1)
    except Exception as e:
        print(f"  ! チャンネルID解決に失敗: {channel} ({e})", file=sys.stderr)
    return None


def collect_youtube_channels(channels, keywords, require_kw, matchers):
    out = []
    for ch in channels:
        if not ch or "XXXX" in ch:
            continue
        cid = resolve_channel_id(ch)
        if not cid:
            print(f"  - チャンネルIDが分かりませんでした: {ch}")
            continue
        print(f"  - YouTubeチャンネル取得中: {cid}")
        try:
            root = ET.fromstring(fetch(f"https://www.youtube.com/feeds/videos.xml?channel_id={cid}"))
        except Exception as e:
            print(f"    ! 取得失敗: {e}", file=sys.stderr)
            continue
        author = root.findtext("atom:author/atom:name", default="", namespaces=NS)
        for entry in root.findall("atom:entry", NS):
            vid = entry.findtext("yt:videoId", default="", namespaces=NS)
            title = entry.findtext("atom:title", default="", namespaces=NS)
            published = entry.findtext("atom:published", default="", namespaces=NS)
            desc = entry.findtext("media:group/media:description", default="", namespaces=NS)
            if not vid:
                continue
            if require_kw and not matches_keywords(title + " " + desc, keywords):
                continue
            out.append(make_video(vid, title, author, published, tag_players(title + " " + desc, matchers)))
    return out


# ---------------- YouTube: プレイヤー名で検索 ----------------
def yt_search_api(query, limit, key):
    url = ("https://www.googleapis.com/youtube/v3/search?part=snippet&type=video"
           f"&maxResults={min(limit, 50)}&q={urllib.parse.quote(query)}&key={key}")
    data = json.loads(fetch(url))
    hits = []
    for it in data.get("items", []):
        vid = it.get("id", {}).get("videoId")
        sn = it.get("snippet", {})
        if vid:
            hits.append((vid, sn.get("title", ""), sn.get("channelTitle", ""), sn.get("publishedAt", "")))
    return hits


def yt_search_keyless(query, limit):
    url = "https://www.youtube.com/results?search_query=" + urllib.parse.quote(query) + "&hl=ja&gl=JP"
    html = fetch(url, headers={"Cookie": "CONSENT=YES+cb.20210328-17-p0.en+FX+000"}).decode("utf-8", "ignore")
    m = re.search(r"ytInitialData\s*=\s*(\{.*?\})\s*;\s*</script>", html, re.S)
    if not m:
        m = re.search(r'ytInitialData"\]\s*=\s*(\{.*?\})\s*;', html, re.S)
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except Exception:
        return []
    hits = []

    def walk(o):
        if isinstance(o, dict):
            vr = o.get("videoRenderer")
            if isinstance(vr, dict) and vr.get("videoId"):
                title = "".join(r.get("text", "") for r in vr.get("title", {}).get("runs", []))
                owner = "".join(r.get("text", "") for r in vr.get("ownerText", {}).get("runs", []))
                hits.append((vr["videoId"], title, owner, ""))
            for v in o.values():
                walk(v)
        elif isinstance(o, list):
            for v in o:
                walk(v)

    walk(data)
    return hits[:limit]


def collect_youtube_search(players, suffix_broad, suffix_dr, per, keywords):
    if not players:
        return []
    key = os.environ.get("YOUTUBE_API_KEY")
    print(f"  - プレイヤー検索方式: {'公式API' if key else 'キーなし'}")
    out = []
    seen = set()
    for p in players:
        name = p.get("name")
        if not name:
            continue
        strict = bool(p.get("dr_mario_only"))
        aliases = p.get("aliases") or [name]
        got = 0
        for alias in aliases:
            alias = (alias or "").strip()
            if not alias:
                continue
            suffix = suffix_dr if strict else suffix_broad
            query = (alias + " " + suffix).strip()
            try:
                hits = yt_search_api(query, per, key) if key else yt_search_keyless(query, per)
            except Exception as e:
                print(f"    ! 検索失敗({query}): {e}", file=sys.stderr)
                continue
            for vid, title, owner, published in hits:
                k = "youtube:" + vid
                if k in seen:
                    continue
                # ドクマリ限定の選手は、タイトルにドクマリ語が無ければ除外
                # （クエリには常に含まれるため、判定はタイトルのみで行う）
                if strict and keywords and not matches_keywords(title, keywords):
                    continue
                seen.add(k)
                out.append(make_video(vid, title, owner, published, [name]))
                got += 1
        print(f"    ・{name}{'(ドクマリ限定)' if strict else ''}: {got}本")
    return out


# ---------------- Twitch ----------------
def collect_twitch(channels, keywords, require_kw, matchers):
    if not channels:
        return []
    cid = os.environ.get("TWITCH_CLIENT_ID")
    secret = os.environ.get("TWITCH_CLIENT_SECRET")
    if not cid or not secret:
        print("  - Twitch: APIキー未設定のためスキップ")
        return []
    try:
        body = urllib.parse.urlencode({
            "client_id": cid, "client_secret": secret, "grant_type": "client_credentials"}).encode()
        token = json.loads(fetch("https://id.twitch.tv/oauth2/token", data=body, method="POST"))["access_token"]
    except Exception as e:
        print(f"    ! Twitch認証失敗: {e}", file=sys.stderr)
        return []
    hdr = {"Client-Id": cid, "Authorization": f"Bearer {token}"}
    out = []
    for login in channels:
        login = login.strip().lstrip("@")
        if not login:
            continue
        try:
            users = json.loads(fetch(f"https://api.twitch.tv/helix/users?login={urllib.parse.quote(login)}", headers=hdr))
            if not users.get("data"):
                continue
            uid = users["data"][0]["id"]
            disp = users["data"][0].get("display_name", login)
            vids = json.loads(fetch(f"https://api.twitch.tv/helix/videos?user_id={uid}&type=archive&first=100", headers=hdr))
        except Exception as e:
            print(f"    ! Twitch取得失敗({login}): {e}", file=sys.stderr)
            continue
        for v in vids.get("data", []):
            title = v.get("title", "")
            if require_kw and not matches_keywords(title, keywords):
                continue
            thumb = (v.get("thumbnail_url") or "").replace("%{width}", "640").replace("%{height}", "360")
            out.append({
                "source": "twitch", "id": v.get("id"), "title": title, "author": disp,
                "published": v.get("published_at", ""), "url": v.get("url"), "thumb": thumb,
                "players": tag_players(title, matchers),
            })
    return out


# ---------------- main ----------------
def main():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)

    keywords = config.get("filter_keywords", [])
    require_kw = bool(config.get("require_keyword", True))
    players = config.get("players", [])
    matchers = build_matchers(players)
    suffix_broad = config.get("search_suffix_broad", "スマブラ")
    suffix_dr = config.get("search_suffix_drmario", "ドクターマリオ")
    per = int(config.get("search_per_player", 15))
    max_keep = int(config.get("max_keep", 2000))

    if os.path.exists(VIDEOS_PATH):
        with open(VIDEOS_PATH, encoding="utf-8") as f:
            existing = json.load(f)
    else:
        existing = []
    by_key = {f"{v.get('source', 'youtube')}:{v['id']}": v for v in existing}
    before = len(by_key)

    found = []
    found += collect_youtube_channels(config.get("youtube_channels", []), keywords, require_kw, matchers)
    found += collect_youtube_search(players, suffix_broad, suffix_dr, per, keywords)
    found += collect_twitch(config.get("twitch_channels", []), keywords, require_kw, matchers)

    for it in found:
        k = f"{it['source']}:{it['id']}"
        if k in by_key:
            by_key[k]["players"] = sorted(set(by_key[k].get("players", [])) | set(it.get("players", [])))
        else:
            by_key[k] = it

    merged = list(by_key.values())
    merged.sort(key=lambda v: v.get("published", ""), reverse=True)
    merged = merged[:max_keep]

    with open(VIDEOS_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"完了: 新規 {len(by_key) - before} 本 / 合計 {len(merged)} 本")


if __name__ == "__main__":
    main()
