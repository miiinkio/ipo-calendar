"""과거 상장 종목 찾기 (확약 해제 캘린더용). GitHub Actions에서 미리보기로 실행.

이미 상장한 회사(corp_cls Y/K)의 지분증권 신고서 중 '신규 상장 공모'를 골라
청약일·환불일·확정 공모가·주관사·공모주식수와, 거래소 공시에서 상장일 후보를 뽑아 출력합니다.
결과는 data/backfill_candidates.json (BACKFILL_WRITE=true일 때만 저장).
"""
from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import dart_sync as d  # noqa: E402

OUT = d.ROOT / "data" / "backfill_candidates.json"
WINDOWS = [("20260301", "20260528"), ("20260529", "20260825"), ("20260826", "20261031")]


def main() -> int:
    filings: dict[str, list[dict]] = {}
    for bgn, end in WINDOWS:
        for page in range(1, 30):
            r = d.call_json("list.json", bgn_de=bgn, end_de=end, pblntf_ty="C", pblntf_detail_ty="C001", page_no=page, page_count=100)
            for it in r.get("list") or []:
                if "지분증권" in it.get("report_nm", ""):
                    filings.setdefault(it["corp_code"], []).append(it)
            if page >= int(r.get("total_page") or 1):
                break
    d.log(f"지분증권 신고 회사 {len(filings)}곳")
    out = []
    for corp, fs in filings.items():
        fs.sort(key=lambda x: x["rcept_no"])
        cls = fs[-1].get("corp_cls")
        if cls not in ("Y", "K"):
            continue
        # 실적보고서는 C001이 아닐 수 있어 회사별로 다시 조회
        allf = d.call_json("list.json", corp_code=corp, bgn_de=fs[0]["rcept_dt"], end_de="20261103", pblntf_ty="C", page_count=100).get("list") or []
        rep = [f for f in allf if "실적보고서" in f.get("report_nm", "")]
        conf = [f for f in fs if "발행조건확정" in f.get("report_nm", "")]
        if not rep:
            continue
        t = d.document_text(rep[-1]["rcept_no"])
        ipo = ("공모 후" in t or "공모후" in t) and "최대주주" in t
        def snip(kw, n=110):
            m = re.search(kw, t)
            return t[m.start(): m.start() + n] if m else ""
        item = {
            "corp": fs[-1]["corp_name"], "corp_code": corp, "cls": cls, "ipo_like": ipo,
            "report": rep[-1]["rcept_no"], "conf": conf[-1]["rcept_no"] if conf else None,
            "s_listing": snip(r"상장\s*(예정)?\s*일"), "s_sub": snip(r"청약\s*기일|청약\s*일"),
            "s_pay": snip(r"납입\s*기일|납입\s*일"), "s_price": snip(r"(발행|모집|공모)\s*가액"),
            "s_uw": snip(r"(대표)?\s*주관회사|인수인"), "s_shares": snip(r"(발행|모집)\s*(주식)?\s*수"),
        }
        out.append(item)
        d.log(f"* {item['corp']} {cls} IPO형={ipo} 상장:[{item['s_listing'][:60]}] 청약:[{item['s_sub'][:60]}]")
    d.log(f"\n후보 {len(out)}곳")
    if os.environ.get("BACKFILL_WRITE") == "true":
        OUT.write_text(json.dumps(out, ensure_ascii=False, indent=0), encoding="utf-8")
    return 0


if __name__ == "__main__":
    try:
        code = main()
    except Exception as e:  # noqa: BLE001
        d.log(f"오류: {type(e).__name__}: {e}")
        code = 1
    d.annotate("error" if code else "notice")
    sys.exit(code)
