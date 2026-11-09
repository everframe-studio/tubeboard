"""유튜브 Data API v3 (공개 데이터, API 키). 표준 라이브러리만 쓴다."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from . import cache, logic

API = "https://www.googleapis.com/youtube/v3"
COSTS = {"search": 100, "videos": 1, "channels": 1}


class ApiError(RuntimeError):
    pass


class QuotaExceeded(ApiError):
    pass


def load_env():
    """trend/.env 의 KEY=값 줄을 환경변수로 (이미 있는 환경변수가 우선)."""
    path = Path(__file__).resolve().parent.parent / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        k, v = raw.split("=", 1)
        os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def api_key():
    load_env()
    key = os.environ.get("YOUTUBE_API_KEY", "").strip()
    if not key:
        raise ApiError("YOUTUBE_API_KEY 가 없습니다. .env 파일에 키를 넣어 주세요 (README 참고).")
    return key


def request(path, params):
    """한 번의 API 호출. 시험할 때 이 함수를 바꿔 끼운다."""
    q = urllib.parse.urlencode({**params, "key": api_key()})
    try:
        with urllib.request.urlopen(f"{API}/{path}?{q}", timeout=30) as r:
            data = json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            err = json.loads(body)["error"]
            reason = (err.get("errors") or [{}])[0].get("reason", "")
            msg = err.get("message", body)
        except (ValueError, KeyError):
            reason, msg = "", body
        if reason in ("quotaExceeded", "rateLimitExceeded", "dailyLimitExceeded"):
            raise QuotaExceeded("유튜브 하루 한도가 찼습니다. 태평양시 자정(한국 오후 4~5시)에 초기화됩니다.")
        raise ApiError(f"유튜브 API 오류 {e.code}: {msg}")
    except urllib.error.URLError as e:
        raise ApiError(f"네트워크 오류: {e.reason}")
    cache.add_quota(COSTS.get(path, 1))
    return data


def channel_subs(ids):
    out = {}
    ids = list(dict.fromkeys(i for i in ids if i))
    for i in range(0, len(ids), 50):
        data = request("channels", {"part": "statistics", "id": ",".join(ids[i:i + 50])})
        for c in data.get("items", []):
            st = c["statistics"]
            out[c["id"]] = None if st.get("hiddenSubscriberCount") else int(st.get("subscriberCount", 0))
    return out


def popular(region):
    """지역 인기 급상승 50개 (1유닛 + 구독자 조회 1유닛)."""
    data = request("videos", {"part": "snippet,statistics,contentDetails", "chart": "mostPopular",
                              "regionCode": region, "maxResults": 50})
    videos = [logic.normalize_video(v) for v in data.get("items", [])]
    logic.attach_subs(videos, channel_subs([v["channelId"] for v in videos]))
    return {
        "videos": videos,
        "categories": logic.category_counts(videos),
        "shorts": sum(1 for v in videos if v["seconds"] <= logic.SHORT_SECONDS),
    }


def topic_shorts(topic, region, days):
    """주제의 최근 days 일 쇼츠, 조회순 (검색 100유닛 + 조회 1 + 구독자 1)."""
    _, lang = logic.REGIONS[region]
    found = request("search", {"part": "snippet", "q": topic, "type": "video", "videoDuration": "short",
                               "order": "viewCount", "regionCode": region, "relevanceLanguage": lang,
                               "publishedAfter": logic.published_after(days), "maxResults": 25}).get("items", [])
    ids = [i["id"]["videoId"] for i in found]
    if not ids:
        return {"videos": [], "summary": logic.summarize([]), "breakouts": []}
    items = request("videos", {"part": "snippet,statistics,contentDetails", "id": ",".join(ids)}).get("items", [])
    videos = [logic.normalize_video(v) for v in items]
    videos = [v for v in videos if v["seconds"] <= logic.SHORT_SECONDS]
    logic.attach_subs(videos, channel_subs([v["channelId"] for v in videos]))
    videos.sort(key=lambda v: -v["views"])
    return {"videos": videos, "summary": logic.summarize(videos), "breakouts": logic.small_breakouts(videos)}


def google_trends(region):
    """구글 급상승 검색어 RSS (키 필요 없음, 한도 무관)."""
    url = f"https://trends.google.com/trending/rss?geo={region}"
    req = urllib.request.Request(url, headers={"User-Agent": "tubeboard"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return logic.parse_trends_rss(r.read())
    except (urllib.error.URLError, TimeoutError, ValueError):
        raise ApiError("구글 트렌드를 읽지 못했습니다. 잠시 뒤 다시 시도해 주세요.")


def categories(region):
    """카테고리별 인기 급상승 (카테고리마다 20개를 읽고 그 카테고리 영상만 남김) (카테고리마다 1유닛, 구독자 조회 몇 유닛)."""
    per = {}
    for cid, name in logic.CATEGORIES.items():
        try:
            data = request("videos", {"part": "snippet,statistics,contentDetails", "chart": "mostPopular",
                                      "regionCode": region, "videoCategoryId": cid, "maxResults": 20})
        except QuotaExceeded:
            raise
        except ApiError:
            continue  # 그 지역에서 인기 차트를 지원하지 않는 카테고리는 건너뛴다
        # videoCategoryId 를 줘도 유튜브가 다른 카테고리 영상으로 채워 돌려주는 일이 많아, 영상 자신의 카테고리로 다시 거른다
        vids = [v for v in (logic.normalize_video(i) for i in data.get("items", [])) if v["categoryId"] == cid]
        if vids:
            per[name] = vids
    subs = channel_subs([v["channelId"] for vs in per.values() for v in vs])
    rows = [logic.category_stats(name, logic.attach_subs(vs, subs)) for name, vs in per.items()]
    rows.sort(key=lambda r: -r["median"])
    return {"rows": rows}
