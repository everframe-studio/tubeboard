"""순수 함수 모음 (네트워크 없음). 시험은 tests/test_logic.py."""
import re
import statistics
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

SHORT_SECONDS = 60
SMALL_CHANNEL = 10_000

# 지역 코드 -> (이름, 검색 언어)
REGIONS = {
    "KR": ("한국", "ko"), "US": ("미국", "en"), "JP": ("일본", "ja"), "GB": ("영국", "en"),
    "DE": ("독일", "de"), "FR": ("프랑스", "fr"), "BR": ("브라질", "pt"), "IN": ("인도", "en"),
    "ID": ("인도네시아", "id"), "TW": ("대만", "zh-Hant"), "VN": ("베트남", "vi"), "TH": ("태국", "th"),
}

CATEGORIES = {"1": "영화·애니", "2": "자동차", "10": "음악", "15": "동물", "17": "스포츠", "19": "여행", "20": "게임",
              "22": "인물·블로그", "23": "코미디", "24": "엔터", "25": "뉴스", "26": "노하우·스타일", "27": "교육",
              "28": "과학·기술"}


def seconds(iso):
    """ISO 8601 길이(PT1M2S)를 초로."""
    m = re.fullmatch(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", iso or "")
    if not m:
        return 0
    d, h, mi, s = (int(x or 0) for x in m.groups())
    return d * 86400 + h * 3600 + mi * 60 + s


def clean_region(code):
    code = (code or "KR").upper()
    return code if code in REGIONS else "KR"


def clean_days(value, default=7):
    try:
        n = int(value)
    except (TypeError, ValueError):
        return default
    return max(1, min(n, 90))


def published_after(days, now=None):
    now = now or datetime.now(timezone.utc)
    return (now - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_video(v):
    """videos.list 항목을 화면용 평평한 dict 로."""
    sn, st = v.get("snippet", {}), v.get("statistics", {})
    thumbs = sn.get("thumbnails", {})
    thumb = (thumbs.get("medium") or thumbs.get("default") or {}).get("url", "")
    return {
        "id": v["id"], "title": sn.get("title", ""), "channel": sn.get("channelTitle", ""),
        "channelId": sn.get("channelId", ""), "views": int(st.get("viewCount", 0)),
        "likes": int(st.get("likeCount", 0)), "seconds": seconds(v.get("contentDetails", {}).get("duration")),
        "published": sn.get("publishedAt", ""), "categoryId": sn.get("categoryId", ""), "category": CATEGORIES.get(sn.get("categoryId", ""), ""),
        "thumb": thumb, "url": f"https://www.youtube.com/watch?v={v['id']}",
    }


def attach_subs(videos, subs):
    """구독자 수와 조회/구독자 배수를 붙인다. 구독자를 숨긴 채널은 None."""
    for v in videos:
        s = subs.get(v["channelId"])
        v["subs"] = s
        v["ratio"] = round(v["views"] / s, 1) if s else None
    return videos


def is_small(v, limit=SMALL_CHANNEL):
    """작은 채널인가. 유튜브가 음원 유통으로 자동 만든 「- Topic」 채널은 구독자가 없어도 작은 채널이 아니라 뺀다."""
    s = v.get("subs")
    return s is not None and s < limit and not v.get("channel", "").endswith(" - Topic")


def summarize(videos):
    views = [v["views"] for v in videos]
    if not views:
        return {"count": 0, "median": 0, "max": 0}
    return {"count": len(views), "median": int(statistics.median(views)), "max": max(views)}


def category_counts(videos):
    out = {}
    for v in videos:
        name = v["category"] or "기타"
        out[name] = out.get(name, 0) + 1
    return sorted(out.items(), key=lambda x: -x[1])


def small_breakouts(videos, limit=SMALL_CHANNEL, top=10):
    """구독자 limit 미만 채널의 영상을 조회/구독자 배수 큰 순으로."""
    small = [v for v in videos if is_small(v, limit) and v["ratio"] is not None]
    small.sort(key=lambda v: -v["ratio"])
    return small[:top]


def parse_trends_rss(raw):
    """구글 트렌드 RSS(bytes)에서 (검색어, 대략 검색량) 목록."""
    root = ET.fromstring(raw)
    out = []
    for item in root.iter("item"):
        traffic = ""
        for child in item:
            if child.tag.endswith("approx_traffic"):
                traffic = (child.text or "").strip()
        out.append({"title": item.findtext("title") or "", "traffic": traffic})
    return out


def category_stats(name, videos):
    """한 카테고리의 인기 급상승 영상들을 비교용 수치 한 줄로."""
    views = sorted(v["views"] for v in videos)
    return {
        "name": name, "count": len(videos),
        "median": int(statistics.median(views)) if views else 0,
        "total": sum(views),
        "small": sum(1 for v in videos if is_small(v) and v["ratio"] is not None),
        "videos": videos,
    }
