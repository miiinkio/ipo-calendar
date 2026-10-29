"""OpenDART로 공모주 데이터 보강 (GitHub Actions에서 실행).

무엇을 하나
- 최근 증권신고서(지분증권) 목록에서 종목별 최신 접수번호(dart_rcp)를 찾고
- 증권신고서 주요정보(estkRs)로 청약기일·납입기일(=환불일)·확정 공모가를 확인하고
- 증권신고서 원문(document.xml)에서 상장예정주식수, 기관 청약수수료, 수요예측 기간을 읽어
- data/ipo.json의 빈칸을 채우고, DART와 다른 청약·환불 일정은 DART 기준으로 고칩니다.

환경변수
- DART_API_KEY (필수): OpenDART 인증키. GitHub 저장소 Secret으로 넣습니다.
- DRY_RUN=true 이면 파일을 쓰지 않고 바뀔 내용만 출력합니다.
"""
from __future__ import annotations

import datetime as dt
import io
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data" / "ipo.json"
META = ROOT / "data" / "meta.json"
ALIASES = ROOT / "data" / "dart_aliases.json"  # {"우리 이름": "DART 회사명"} 수동 보정용(선택)
API = "https://opendart.fss.or.kr/api/"
KEY = os.environ.get("DART_API_KEY", "").strip()
DRY = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
KST = dt.timezone(dt.timedelta(hours=9))
ORDER = ["name", "market", "type", "demand_start", "demand_end", "sub_start", "sub_end", "refund", "listing",
         "band_low", "band_high", "price_final", "underwriter", "inst_fee", "dart_rcp", "listed_shares", "note"]
log_lines: list[str] = []


def log(s: str) -> None:
    print(s)
    log_lines.append(s)


def call(path: str, **params) -> bytes:
    params["crtfc_key"] = KEY
    url = API + path + "?" + urllib.parse.urlencode(params)
    for attempt in range(3):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                body = r.read()
            time.sleep(0.3)  # 천천히
            return body
        except Exception as e:  # noqa: BLE001
            log(f"  ! {path} 재시도 {attempt + 1}: {e}")
            time.sleep(2 + attempt * 2)
    raise RuntimeError(f"OpenDART 호출 실패: {path}")


def call_json(path: str, **params) -> dict:
    d = json.loads(call(path, **params).decode("utf-8"))
    st = d.get("status")
    if st not in ("000", "013"):  # 013 = 데이터 없음
        raise RuntimeError(f"OpenDART {path} 오류 {st}: {d.get('message')}")
    return d


# ---------- 이름 맞추기 ----------
def norm(s: str) -> str:
    s = re.sub(r"\(주\)|㈜|주식회사|\s|·", "", s or "")
    s = s.replace("기업인수목적", "스팩")
    for a, b in (("에스케이", "SK"), ("엔에이치", "NH"), ("케이비", "KB"), ("아이비케이", "IBK"), ("비엔케이", "BNK")):
        s = s.replace(a, b)
    s = re.sub(r"제(\d+)호", r"\1호", s)
    s = s.replace("증권", "").replace("투자증권", "투자").upper()
    if "스팩" in s:  # 스팩은 '스폰서+스팩+N호' 형태로 통일
        m = re.search(r"(\d+)호", s)
        if m:
            sponsor = s.replace("스팩", "").replace(m.group(0), "")
            s = f"{sponsor}스팩{m.group(1)}호"
    return s


# ---------- 날짜/숫자 파싱 ----------
DATE_RE = re.compile(r"(\d{4})\s*[년.\-/]\s*(\d{1,2})\s*[월.\-/]\s*(\d{1,2})")


def dates_in(s: str) -> list[str]:
    out = []
    for y, m, d in DATE_RE.findall(s or ""):
        try:
            out.append(dt.date(int(y), int(m), int(d)).isoformat())
        except ValueError:
            pass
    return out


def to_int(s) -> int | None:
    if s is None:
        return None
    t = re.sub(r"[^\d]", "", str(s))
    return int(t) if t else None


# ---------- 원문 ----------
def document_text(rcept_no: str) -> str:
    raw = call("document.xml", rcept_no=rcept_no)
    try:
        z = zipfile.ZipFile(io.BytesIO(raw))
    except zipfile.BadZipFile:
        log(f"  ! 원문 zip 아님 ({rcept_no}): {raw[:120]!r}")
        return ""
    names = sorted(z.namelist(), key=lambda n: (not n.startswith(rcept_no), -z.getinfo(n).file_size))
    texts = []
    for n in names[:3]:
        b = z.read(n)
        for enc in ("utf-8", "cp949", "euc-kr"):
            try:
                t = b.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            t = b.decode("utf-8", "ignore")
        t = re.sub(r"<[^>]+>", " ", t)
        t = t.replace("&nbsp;", " ").replace("&amp;", "&")
        texts.append(re.sub(r"\s+", " ", t))
    return " ".join(texts)


def parse_doc(t: str) -> dict:
    out = {}
    m = re.search(r"상장\s*예정\s*주식\s*수[^0-9]{0,40}([\d,]{6,})\s*주", t)
    if m:
        out["listed_shares"] = int(m.group(1).replace(",", ""))
    if re.search(r"기관투자자[^.]{0,30}(대상으로 한|에 대한)?\s*청약\s*수수료[는은]?\s*(없|부과하지)", t):
        out["inst_fee"] = "없음"
    else:
        for m2 in re.finditer(r"청약\s*수수료", t):
            ctx = t[max(0, m2.start() - 120): m2.end() + 20]
            if "기관" in ctx and re.search(r"배정\s*된?\s*금액의\s*[\d.]+\s*%", ctx):
                out["inst_fee"] = "있음"
                break
    m = re.search(r"수요예측[^.]{0,300}?접수\s*기간[^0-9]{0,15}(\d{4}\s*년\s*\d{1,2}\s*월\s*\d{1,2}\s*일)[^~]{0,30}~\s*((?:\d{4}\s*년\s*)?\d{1,2}\s*월\s*\d{1,2}\s*일)", t)
    if m:
        a = dates_in(m.group(1))
        y = a[0][:4] if a else None
        b_txt = m.group(2) if re.match(r"\d{4}", m.group(2)) else f"{y}년 {m.group(2)}"
        b = dates_in(b_txt)
        if a and b and a[0] <= b[0]:
            out["demand_start"], out["demand_end"] = a[0], b[0]
    return out


def main() -> int:
    if not KEY:
        log("DART_API_KEY 가 없습니다. 저장소 Settings → Secrets 에 등록하세요.")
        return 1
    rows = json.loads(DATA.read_text(encoding="utf-8"))
    aliases = json.loads(ALIASES.read_text(encoding="utf-8")) if ALIASES.exists() else {}
    today = dt.datetime.now(KST).date()
    bgn = (today - dt.timedelta(days=120)).strftime("%Y%m%d")
    end = today.strftime("%Y%m%d")

    # 1) 증권신고서(지분증권) 목록
    filings: dict[str, list[dict]] = {}
    for page in range(1, 20):
        d = call_json("list.json", bgn_de=bgn, end_de=end, pblntf_ty="C", pblntf_detail_ty="C001", page_no=page, page_count=100)
        items = d.get("list") or []
        for it in items:
            filings.setdefault(norm(it["corp_name"]), []).append(it)
        if page >= int(d.get("total_page") or 1):
            break
    log(f"증권신고서(지분증권) {sum(map(len, filings.values()))}건, 회사 {len(filings)}곳")

    changes: list[str] = []
    for r in rows:
        name = r["name"]
        key = norm(aliases.get(name, name))
        fs = sorted(filings.get(key, []), key=lambda x: x["rcept_no"], reverse=True)
        if not fs:
            log(f"- {name}: DART 목록에서 못 찾음 (norm={key})")
            continue
        latest = fs[0]
        corp = latest["corp_code"]
        upd: dict = {}
        if "철회" in latest.get("report_nm", "") and "공모 철회" not in (r.get("note") or ""):
            upd["note"] = ((r.get("note") or "") + "; " if r.get("note") else "") + "공모 철회(DART)"
        if r.get("dart_rcp") != latest["rcept_no"]:
            upd["dart_rcp"] = latest["rcept_no"]

        # 2) 증권신고서 주요정보: 청약기일, 납입기일, 모집가액
        try:
            e = call_json("estkRs.json", corp_code=corp, bgn_de=bgn, end_de=end)
        except Exception as ex:  # noqa: BLE001
            log(f"- {name}: estkRs 실패 {ex}")
            e = {}
        groups = {g.get("title", ""): g.get("list") or [] for g in (e.get("group") or [])}
        gen = sorted(groups.get("일반사항", []), key=lambda x: x.get("rcept_no", ""), reverse=True)
        if gen:
            g0 = gen[0]
            sbd = dates_in(g0.get("sbd", ""))
            pym = dates_in(g0.get("pymd", ""))
            if len(sbd) >= 2 and (sbd[0], sbd[-1]) != (r.get("sub_start"), r.get("sub_end")):
                upd["sub_start"], upd["sub_end"] = sbd[0], sbd[-1]
                upd["note"] = ((upd.get("note") or r.get("note") or "") + "; " if (upd.get("note") or r.get("note")) else "") + \
                    f"일정 정정({r.get('sub_start')}~{r.get('sub_end')}→{sbd[0]}~{sbd[-1]}, DART)"
            if pym and pym[0] != r.get("refund"):
                upd["refund"] = pym[0]
        if "발행조건확정" in latest.get("report_nm", "") and r.get("price_final") is None:
            kinds = sorted(groups.get("증권의종류", []), key=lambda x: x.get("rcept_no", ""), reverse=True)
            if kinds and kinds[0].get("rcept_no") == latest["rcept_no"]:
                p = to_int(kinds[0].get("slprc"))
                if p and (r.get("band_low") is None or 0.5 * r["band_low"] <= p <= 1.5 * (r.get("band_high") or p)):
                    upd["price_final"] = p

        # 3) 원문: 상장예정주식수, 기관 청약수수료, 수요예측 기간 (발행조건확정 제외한 최신 신고서)
        need_doc = r.get("listed_shares") is None or r.get("inst_fee") is None or r.get("demand_start") is None
        if need_doc:
            body = next((f for f in fs if "발행조건확정" not in f.get("report_nm", "")), latest)
            info = parse_doc(document_text(body["rcept_no"]))
            for k in ("listed_shares", "inst_fee"):
                if r.get(k) is None and info.get(k) is not None:
                    upd[k] = info[k]
            if r.get("demand_start") is None and info.get("demand_start"):
                upd["demand_start"], upd["demand_end"] = info["demand_start"], info["demand_end"]

        if upd:
            r.update(upd)
            changes.append(f"- {name}: " + ", ".join(f"{k}={v}" for k, v in upd.items()))
            log(changes[-1])
        else:
            log(f"- {name}: 변경 없음")

    log(f"\n변경 {len(changes)}종목")
    if changes and not DRY:
        rows = [{k: r.get(k) for k in ORDER} | {k: v for k, v in r.items() if k not in ORDER} for r in rows]
        rows.sort(key=lambda x: x.get("sub_start") or "")
        DATA.write_text("[\n" + ",\n".join(json.dumps(x, ensure_ascii=False) for x in rows) + "\n]\n", encoding="utf-8")
        now = dt.datetime.now(KST).replace(microsecond=0).isoformat()
        meta = json.loads(META.read_text(encoding="utf-8")) if META.exists() else {}
        meta.update({"updated_at": now, "checked_at": now})
        META.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        log("data/ipo.json 저장함")
    elif DRY:
        log("미리보기 모드라 파일은 바꾸지 않았습니다.")

    summ = os.environ.get("GITHUB_STEP_SUMMARY")
    if summ:
        with open(summ, "a", encoding="utf-8") as f:
            f.write("## DART 동기화" + (" (미리보기)" if DRY else "") + "\n\n```\n" + "\n".join(log_lines) + "\n```\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
