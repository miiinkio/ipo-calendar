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
        names = {f["corp_name"] for f in fs}
        cls = fs[-1].get("corp_cls")
        if cls not in ("Y", "K"):
            continue  # 아직 비상장(공모 중) — 기존 동기화가 처리
        e = d.call_json("estkRs.json", corp_code=corp, bgn_de=fs[0]["rcept_dt"], end_de=fs[-1]["rcept_dt"])
        groups = {g.get("title", ""): g.get("list") or [] for g in (e.get("group") or [])}
        kinds = sorted(groups.get("증권의종류", []), key=lambda x: x.get("rcept_no", ""))
        gen = sorted(groups.get("일반사항", []), key=lambda x: x.get("rcept_no", ""))
        meth = " ".join({k.get("slmthn", "") for k in kinds})
        spac = any("기업인수목적" in n for n in names)
        if not spac and "주주배정" in meth:
            continue  # 상장사 유상증자
        if not spac and not any("발행조건확정" in f["report_nm"] for f in fs):
            continue  # 수요예측 거친 IPO가 아님
        # 거래소 공시(상장 관련) — 상장일 후보
        ex = d.call_json("list.json", corp_code=corp, bgn_de=fs[0]["rcept_dt"], end_de="20261103", pblntf_ty="I", page_count=100)
        exl = [(x["rcept_dt"], x["report_nm"], x.get("flr_nm")) for x in (ex.get("list") or [])]
        ex_listing = [x for x in exl if "신규상장" in x[1] or "상장승인" in x[1] or "매매개시" in x[1]]
        conf = next((f for f in reversed(fs) if "발행조건확정" in f["report_nm"]), None)
        kconf = next((k for k in kinds if conf and k.get("rcept_no") == conf["rcept_no"]), kinds[-1] if kinds else {})
        g = gen[-1] if gen else {}
        uw = []
        for u in groups.get("인수인정보", []):
            nm = (u.get("actnmn") or "").strip()
            if nm and nm not in uw and "대표" in (u.get("actsen") or ""):
                uw.append(nm)
        item = {
            "corp": fs[-1]["corp_name"], "corp_code": corp, "cls": cls, "spac": spac,
            "sbd": d.dates_in(g.get("sbd", "")), "pymd": d.dates_in(g.get("pymd", "")),
            "price": d.to_int(kconf.get("slprc")), "offer_shares": d.to_int(kconf.get("stkcnt")),
            "method": meth, "underwriter": uw, "dart_rcp": fs[-1]["rcept_no"],
            "reports": [f"{f['rcept_dt']} {f['report_nm']}" for f in fs][-4:],
            "ex_listing": ex_listing[:4], "ex_sample": sorted({x[1] for x in exl})[:12],
        }
        out.append(item)
        d.log(f"* {item['corp']} {cls} 청약{item['sbd']} 납입{item['pymd']} 가격{item['price']} 공모{item['offer_shares']} 주관{uw} 방식[{meth}] 상장공시{ex_listing[:2]}")
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
