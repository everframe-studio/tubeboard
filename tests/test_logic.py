import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tubeboard import cache, logic


def test_seconds():
    assert logic.seconds("PT58S") == 58
    assert logic.seconds("PT1M") == 60
    assert logic.seconds("PT1H2M3S") == 3723
    assert logic.seconds("P1DT1S") == 86401
    assert logic.seconds("") == 0 and logic.seconds(None) == 0


def test_clean():
    assert logic.clean_region("us") == "US"
    assert logic.clean_region("zz") == "KR"
    assert logic.clean_days("abc") == 7
    assert logic.clean_days("500") == 90 and logic.clean_days("0") == 1


def video(i, views, ch, dur="PT30S"):
    return logic.normalize_video({"id": i, "snippet": {"title": i, "channelId": ch, "channelTitle": ch, "categoryId": "22"},
                                  "statistics": {"viewCount": str(views)}, "contentDetails": {"duration": dur}})


def test_ratio_and_breakouts():
    vs = [video("a", 1500, "small"), video("b", 900000, "big"), video("c", 400, "hidden"), video("d", 50000, "tiny")]
    logic.attach_subs(vs, {"small": 1000, "big": 2_000_000, "hidden": None, "tiny": 100})
    assert vs[0]["ratio"] == 1.5
    assert vs[2]["ratio"] is None
    vs.append(video("e", 900, "Artist - Topic"))
    logic.attach_subs(vs, {"small": 1000, "big": 2_000_000, "hidden": None, "tiny": 100, "Artist - Topic": 5})
    top = logic.small_breakouts(vs)
    assert [v["id"] for v in top] == ["d", "a"]  # 배수 큰 순, 큰 채널 · 숨긴 채널 제외


def test_summarize_and_categories():
    assert logic.summarize([]) == {"count": 0, "median": 0, "max": 0}
    vs = [video("a", 10, "x"), video("b", 30, "x"), video("c", 20, "x")]
    assert logic.summarize(vs) == {"count": 3, "median": 20, "max": 30}
    assert logic.category_counts(vs) == [("인물·블로그", 3)]


def test_parse_trends_rss():
    raw = ('<rss xmlns:ht="https://trends.google.com/trending/rss"><channel>'
           '<item><title>검색어</title><ht:approx_traffic>200+</ht:approx_traffic></item>'
           '<item><title>둘째</title></item></channel></rss>').encode()
    assert logic.parse_trends_rss(raw) == [{"title": "검색어", "traffic": "200+"}, {"title": "둘째", "traffic": ""}]


def test_cache_ttl_and_force():
    with tempfile.TemporaryDirectory() as d:
        cache.CACHE_DIR = Path(d)
        calls = []
        def prod():
            calls.append(1)
            return {"n": len(calls)}
        assert cache.cached("k", 60, prod)[:2] == ({"n": 1}, False)
        assert cache.cached("k", 60, prod)[:2] == ({"n": 1}, True)      # 캐시 적중, 호출 안 늘어남
        assert cache.cached("k", 60, prod, force=True)[:2] == ({"n": 2}, False)
        assert cache.cached("k", 0, prod)[1] is False                    # 만료
        cache.add_quota(100); cache.add_quota(1)
        assert cache.quota_used() == 101
        assert json.loads((Path(d) / "quota.json").read_text())["used"] == 101


def test_category_stats():
    vs = [video("a", 100, "s"), video("b", 300, "s"), video("c", 200, "big")]
    logic.attach_subs(vs, {"s": 50, "big": 10**6})
    r = logic.category_stats("게임", vs)
    assert (r["count"], r["median"], r["total"], r["small"]) == (3, 200, 600, 2)
    assert logic.category_stats("x", [])["median"] == 0


if __name__ == "__main__":  # pytest 없이도: python3 tests/test_logic.py
    for name, fn in sorted(globals().items()):
        if name.startswith("test_"):
            fn()
            print("통과", name)
