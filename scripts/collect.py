#!/usr/bin/env python3
"""
スマ庫 動画自動収集スクリプト
- config.json の youtube_channels / twitch_channels から新着動画を取得
- filter_keywords（例: ドクターマリオ）にタイトル/説明が一致するものだけ保存
- 結果を videos.json に追記（YouTubeはAPIキー不要。Twitchは要APIキー）
- GitHub Actions から定期実行される想定。

Twitch を使う場合は、GitHub の Secrets に以下を登録してください:
  TWITCH_CLIENT_ID / TWITCH_CLIENT_SECRET
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
UA = "Mozilla/5.0 (compatible; SumakoArchiver/1.0)"


def fetch(url, headers=None, data=None, method=None):
    h = {"User-Agent": UA}
    if headers:
        h.update(headers)
    req = urllib.request.Request(url, headers=h, data=data, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read()


# ---------------- キーワード絞り込み ----------------
def matches_keywords(text, keywords):
    if not keywords:
        return True
    low = (text or "").lower()
    return any(k.lower() in low for k in keywords)


# ---------------- YouTube ----------------
def resolve_channel_id(channel):
    channel = channel.strip()
    if re.fullmatch(r"UC[0-9A-Za-z_-]{22}", channel):
        return channel
    if channel.startswith("http"):
        url = channel
    elif channel.startswith("@"):
        url = "https://www.youtube.com/" + channel
    else:
        url = "https://www.youtube.com/@" + channel
    try:
        html = fetch(url).decode("utf-8", "ignore")
        m = re.search(r'"(?:channelId|externalId)":"(UC[0-9A-Za-z_-]{22})"', html)
        if m:
            return m.group(1)
        m = re.search(r'channel_id=(UC[0-9A-Za-z_-]{22})', html)
        if m:
            return m.group(1)
    except Exception as e:
        print(f"  ! チャンネルID解決に失敗: {channel} ({e})", file=sys.stderr)
    return None


def collect_youtube(channels, keywords, require_kw):
    out = []
    for ch in channels:
        if not ch or "XXXX" in ch:
            print(f"  - スキップ(未設定): {ch}")
            continue
        cid = resolve_channel_id(ch)
        if not cid:
            print(f"  - チャンネルIDが分かりませんでした: {ch}")
            continue
        print(f"  - YouTube取得中: {ch} -> {cid}")
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
            out.append({
                "source": "youtube",
                "id": vid,
                "title": title,
                "author": author,
                "published": published,
                "url": f"https://www.youtube.com/watch?v={vid}",
                "thumb": f"https://i.ytimg.com/vi/{vid}/hqdefault.jpg",
            })
    return out


# ---------------- Twitch ----------------
def twitch_token(cid, secret):
    body = urllib.parse.urlencode({
        "client_id": cid, "client_secret": secret, "grant_type": "client_credentials",
    }).encode()
    data = json.loads(fetch("https://id.twitch.tv/oauth2/token", data=body, method="POST"))
    return data["access_token"]


def twitch_get(url, cid, token):
    return json.loads(fetch(url, headers={"Client-Id": cid, "Authorization": f"Bearer {token}"}))


def collect_twitch(channels, keywords, require_kw):
    if not channels:
        return []
    cid = os.environ.get("TWITCH_CLIENT_ID")
    secret = os.environ.get("TWITCH_CLIENT_SECRET")
    if not cid or not secret:
        print("  - Twitch: APIキー(Secrets)が未設定のためスキップ")
        return []
    try:
        token = twitch_token(cid, secret)
    except Exception as e:
        print(f"    ! Twitch認証に失敗: {e}", file=sys.stderr)
        return []
    out = []
    for login in channels:
        login = login.strip().lstrip("@")
        if not login:
            continue
        print(f"  - Twitch取得中: {login}")
        try:
            users = twitch_get(f"https://api.twitch.tv/helix/users?login={urllib.parse.quote(login)}", cid, token)
            if not users.get("data"):
                print(f"    ! ユーザーが見つかりません: {login}")
                continue
            uid = users["data"][0]["id"]
            disp = users["data"][0].get("display_name", login)
            vids = twitch_get(f"https://api.twitch.tv/helix/videos?user_id={uid}&type=archive&first=100", cid, token)
        except Exception as e:
            print(f"    ! Twitch取得失敗: {e}", file=sys.stderr)
            continue
        for v in vids.get("data", []):
            title = v.get("title", "")
            if require_kw and not matches_keywords(title, keywords):
                continue
            thumb = (v.get("thumbnail_url") or "").replace("%{width}", "640").replace("%{height}", "360")
            out.append({
                "source": "twitch",
                "id": v.get("id"),
                "title": title,
                "author": disp,
                "published": v.get("published_at", ""),
                "url": v.get("url"),
                "thumb": thumb,
            })
    return out


# ---------------- main ----------------
def main():
    with open(CONFIG_PATH, encoding="utf-8") as f:
        config = json.load(f)

    keywords = config.get("filter_keywords", [])
    require_kw = bool(config.get("require_keyword", True))
    max_keep = int(config.get("max_keep", 500))

    if os.path.exists(VIDEOS_PATH):
        with open(VIDEOS_PATH, encoding="utf-8") as f:
            existing = json.load(f)
    else:
        existing = []
    by_key = {f"{v.get('source','youtube')}:{v['id']}": v for v in existing}
    before = len(by_key)

    found = []
    found += collect_youtube(config.get("youtube_channels", []), keywords, require_kw)
    found += collect_twitch(config.get("twitch_channels", []), keywords, require_kw)

    for it in found:
        key = f"{it['source']}:{it['id']}"
        if key not in by_key:
            by_key[key] = it

    merged = list(by_key.values())
    merged.sort(key=lambda v: v.get("published", ""), reverse=True)
    merged = merged[:max_keep]

    with open(VIDEOS_PATH, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(f"完了: 新規 {len(by_key) - before} 本 / 合計 {len(merged)} 本")


if __name__ == "__main__":
    main()
