# 매시간: 38커뮤니케이션에 수요예측 결과가 아직 없는 청약 예정 종목을 OpenDART [발행조건확정] 증권신고서에서 찾아 src/dart_fc.json에 쌓는다.
# ipo.py가 38에 값이 없을 때만 이 값을 쓰고, 38에 올라오면 38 값을 쓴다.
# 파서 검증(2022-08 이후 공모주 대조, 38 값과 비교): 확정공모가 287/287, 기관경쟁률 259/264(±2%), 확약 186/192(±0.5%p)
import json, os, re, sys, datetime as dt
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import dart_eq as E
FC = os.path.join(E.SRC, "dart_fc.json")
num = lambda x: float(x.replace(",", ""))

def parse(t):
    out = {}
    m = re.search(r"수량\s+[\d,\s\-]+?경쟁률\s+((?:[\d,.\-]+\s+)+)", t)
    if m:
        v = [x for x in m.group(1).split() if x != "-"]
        if v and num(v[-1]) > 0: out["inst"] = num(v[-1])
    i = next((t.find(k) for k in ("확약기간별", "확약 기간별") if t.find(k) >= 0), -1)
    if i >= 0:
        e = t.find("확정공모가액의 결정", i); sec = t[i:e if e > 0 else i + 9000]; T = None
        for g in re.finditer(r"합\s*계\s+[\d,]+\s+100(?:\.0+)?\s*%\s+([\d,]+)\s+100", t[max(0, i - 3000):i]): T = num(g.group(1))
        un = list(re.finditer(r"미\s*확\s*약\s+((?:[\d,]+\s+|-\s+)+)", sec)); tt = list(re.finditer(r"(?:합\s*계|(?<=\s)계)\s+((?:[\d,]+\s+|-\s+)+)", sec))
        if un and tt:
            a = un[-1].group(1).split(); b = [g for g in tt if g.start() > un[-1].start()]; b = (b or tt)[-1].group(1).split()
            v = [num(x) if x != "-" else 0 for x in b]; T = T if T in v else max(v)
            if len(a) == len(b) and T > 0:
                x = a[v.index(T)]; out["lock"] = round((1 - (num(x) if x != "-" else 0) / T) * 100, 2)
    p = re.search(r"확정\s*공모가(?:액)?(?:인|은|:)?\s*(?:금\s*)?([\d,]{3,})\s*원", t)
    if p: out["price"] = num(p.group(1))
    return out

def main():
    if not E.K: return print("DART_KEY 없음")
    html = open(os.path.join(E.ROOT, "index.html"), encoding="utf-8").read()
    D = json.loads(re.search(r'<script[^>]*id="ipodata"[^>]*>(.*?)</script>', html, re.S).group(1))
    today = dt.date.today(); iso = today.isoformat()
    T = [u for u in D["upcoming"] if u.get("inst") is None and u.get("sub") and u["sub"][1] >= iso and not re.search("스팩|기업인수목적", u["name"])]
    fc = json.load(open(FC, encoding="utf-8")) if os.path.exists(FC) else {}
    T = [u for u in T if str(u["no"]) not in fc]
    print("확인 대상", [u["name"] for u in T], flush=True)
    if not T: return
    L = [r for r in E.listing(today - dt.timedelta(days=21), today, pblntf_ty="C", pblntf_detail_ty="C001") if "발행조건확정" in r["report_nm"]]
    for u in T:
        a = E.nz(u["name"]); C = [r for r in L if E.nz(r["corp_name"]) == a or E.nz(r["corp_name"]) in a or a in E.nz(r["corp_name"])]
        if not C: continue
        r = max(C, key=lambda r: r["rcept_no"]); p = parse(E.text(r["rcept_no"]))
        print(u["name"], r["report_nm"], r["rcept_no"], p, flush=True)
        if p.get("inst"): fc[str(u["no"])] = {"name": u["name"], "rcept": r["rcept_no"], **p}
    json.dump(fc, open(FC, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))

if __name__ == "__main__": main()
