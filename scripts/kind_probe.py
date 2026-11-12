"""한국거래소 KIND의 공모기업 현황에서 상장예정일을 읽을 수 있는지 시험 (데이터는 안 바꿈)."""
import re
import sys
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import dart_sync as d  # noqa: E402

URLS = [
    ("공모기업현황", "https://kind.krx.co.kr/listinvstg/pubofrprogcom.do",
     {"method": "searchPubofrProgComSub", "currentPageSize": "100", "pageIndex": "1", "orderMode": "1", "orderStat": "D"}),
    ("신규상장", "https://kind.krx.co.kr/listinvstg/listingcompany.do",
     {"method": "searchListingTypeSub", "currentPageSize": "100", "pageIndex": "1", "orderMode": "1", "orderStat": "D"}),
]
for name, url, params in URLS:
    try:
        req = urllib.request.Request(url, data=urllib.parse.urlencode(params).encode(),
                                     headers={"User-Agent": "Mozilla/5.0 (ipo-calendar)", "Referer": "https://kind.krx.co.kr/"})
        body = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
        txt = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))
        d.log(f"[{name}] {len(body)}바이트")
        for kw in ("엠비디", "에이엘로봇", "하나에어로", "유캐스트", "아델", "상장예정일", "상장일"):
            i = txt.find(kw)
            if i >= 0:
                d.log(f"  {kw}: …{txt[max(0, i - 40): i + 160]}…")
    except Exception as e:  # noqa: BLE001
        d.log(f"[{name}] 실패 {type(e).__name__}: {e}")
d.annotate("notice")
