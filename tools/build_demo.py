"""데모 페이지(docs/index.html)를 만든다. 서버 없이 열리는 정적 페이지이며, 로컬 캐시의 한국 스냅샷을 그대로 보여 준다.
사용: 먼저 프로그램에서 한국 지역의 '지금 뜨는 영상'·'카테고리 대결'·'검색어 급상승'을 한 번씩 열어 캐시를 만든 뒤 python3 tools/build_demo.py"""
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache"
OUT = ROOT / "docs"


def load(key):
    f = CACHE / (hashlib.sha1(key.encode("utf-8")).hexdigest() + ".json")
    if not f.exists():
        sys.exit(f"캐시가 없습니다: {key} (프로그램에서 해당 탭을 먼저 열어 주세요)")
    return json.loads(f.read_text(encoding="utf-8"))


def main():
    keys = {"popular": "popular:KR", "categories": "categories2:KR", "trends": "trends:KR"}
    got = {k: load(v) for k, v in keys.items()}
    at = min(v["at"] for v in got.values())
    data = {"at": at, **{k: v["value"] for k, v in got.items()}}
    OUT.mkdir(exist_ok=True)
    (OUT / "data.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    (OUT / "fonts").mkdir(exist_ok=True)
    shutil.copy(ROOT / "tubeboard/static/fonts/PretendardVariable.woff2", OUT / "fonts/PretendardVariable.woff2")
    html = (ROOT / "tubeboard/static/index.html").read_text(encoding="utf-8")
    html = html.replace("url(/fonts/", "url(fonts/")
    day = datetime.fromtimestamp(at).strftime("%Y-%m-%d")
    shim = SHIM.replace("__DAY__", day)
    html = html.replace("<script>", shim + "\n<script>", 1)
    (OUT / "index.html").write_text(html, encoding="utf-8")
    print("만들었습니다:", OUT / "index.html", "스냅샷", day)


SHIM = """<script>
/* 데모: 서버 대신 docs/data.json(한국 스냅샷 __DAY__)을 돌려 준다 */
(function(){
  const KOL=(new URLSearchParams(location.search).get("lang")||localStorage.getItem("lang")||navigator.language||"ko").toLowerCase().startsWith("ko");
  const realFetch=window.fetch.bind(window);
  let snap=null; const load=()=>snap||(snap=realFetch("data.json").then(r=>r.json()));
  const json=(o,code)=>new Response(JSON.stringify(o),{status:code||200,headers:{"Content-Type":"application/json"}});
  window.fetch=async function(u,o){
    const url=new URL(typeof u==="string"?u:u.url,location.href);
    if(!url.pathname.startsWith("/api/")) return realFetch(u,o);
    const d=await load(), p=url.pathname;
    if(p==="/api/status") return json({hasKey:true,quotaUsed:0,quotaLimit:10000,regions:{KR:"한국"}});
    const map={"/api/popular":"popular","/api/categories":"categories","/api/trends":"trends"};
    if(map[p]) return json({data:d[map[p]],cached:true,at:d.at,quotaUsed:0,quotaLimit:10000});
    return json({error:KOL?"데모에서는 쓸 수 없습니다. 내려받아 본인 키로 실행하면 됩니다.":"Not available in the demo. Download it and run with your own key."},400);
  };
  document.addEventListener("DOMContentLoaded",()=>{
    const b=document.createElement("div");
    b.style.cssText="padding:12px 16px;margin:0;background:#16142c;color:#fff;font:15px/1.5 system-ui,sans-serif;text-align:center";
    const a=(h,t)=>'<a style="color:#ffd9ec;font-weight:600" href="'+h+'">'+t+'</a>';
    b.innerHTML=KOL
      ? "데모 화면입니다. 한국 지역의 __DAY__ 스냅샷이고 실시간이 아닙니다. 지금 데이터를 보려면 "+a("https://github.com/everframe-studio/tubeboard/releases","내려받아")+" 본인 키로 실행하세요."
      : "Demo: a snapshot of Korea taken on __DAY__, not live. To see current data, "+a("https://github.com/everframe-studio/tubeboard/releases","download it")+" and run it with your own key.";
    document.body.prepend(b);
  });
})();
</script>"""

main()
