"""디스크 캐시와 하루 사용량 추정. 같은 조회를 반복해 API 한도를 태우지 않으려는 용도."""
import hashlib
import json
import time
from datetime import datetime
from pathlib import Path

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None

CACHE_DIR = Path(__file__).resolve().parent.parent / ".cache"


def _read(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _write(path, data):
    CACHE_DIR.mkdir(exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def _safe(key):
    return hashlib.sha1(key.encode("utf-8")).hexdigest()


def cached(key, ttl, producer, force=False):
    """key 의 결과를 ttl 초 동안 재사용. (값, 캐시에서 왔는지, 만든 시각) 을 돌려준다."""
    path = CACHE_DIR / f"{_safe(key)}.json"
    hit = _read(path)
    if hit and not force and time.time() - hit["at"] < ttl:
        return hit["value"], True, hit["at"]
    value = producer()
    now = time.time()
    _write(path, {"at": now, "value": value})
    return value, False, now


def quota_day():
    """유튜브 한도는 태평양시 자정에 초기화된다."""
    if ZoneInfo:
        return datetime.now(ZoneInfo("America/Los_Angeles")).strftime("%Y-%m-%d")
    return datetime.utcnow().strftime("%Y-%m-%d")


def quota_used():
    data = _read(CACHE_DIR / "quota.json") or {}
    return data.get("used", 0) if data.get("day") == quota_day() else 0


def add_quota(units):
    path = CACHE_DIR / "quota.json"
    _write(path, {"day": quota_day(), "used": quota_used() + units})
