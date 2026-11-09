# 매일: ① OpenDART에서 새 공모주 증권발행실적보고서(일반 청약건수·균등 물량)를 받아 src/dart_tot.json에 쌓고
# ② 과거 실적으로 "일반 청약건수"를 예측하는 회귀식을 다시 맞춰 ③ 청약 전 종목의 예상 균등(주)과 최근 종목의 실제 균등을 eq.json에 쓴다.
# Worker가 eq.json을 읽어 청약 첫날 알림에 공모주린이 예상과 나란히 넣고, 실제가 나오면 비교 알림을 보낸다.
# 근거(2022-08~2026-11 공모주 274건, 앞 80건으로 시작해 매번 과거만으로 맞추고 다음 종목을 맞히는 방식):
#   청약건수 중앙 오차 ±36%, ±50% 안에 63% (각 종목 청약 시작 전에 공시된 실적만 쓴 206건 검증).
import io, json, math, os, re, sys, time, zipfile, urllib.request, urllib.parse, datetime as dt
K = os.environ.get("DART_KEY")
SRC = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(SRC)
TOT = os.path.join(SRC, "dart_tot.json")
num = lambda x: int(x.replace(",", ""))

def get(path, **q):
    q["crtfc_key"] = K
    for i in range(4):
        try:
            return urllib.request.urlopen("https://opendart.fss.or.kr/api/%s?%s" % (path, urllib.parse.urlencode(q)), timeout=90).read()
        except Exception as e:
            print("retry", path, type(e).__name__); time.sleep(5 * (i + 1))
    raise SystemExit("fail " + path)

def text(rcept):
    try: d = zipfile.ZipFile(io.BytesIO(get("document.xml", rcept_no=rcept)))
    except zipfile.BadZipFile: return ""
    return re.sub(r"\s+", " ", " ".join(re.sub(r"<[^>]+>", " ", d.read(n).decode("utf-8", "ignore")) for n in d.namelist()))

def parse(t):
    m = re.search(r"일반(?:투자자|청약자)\s+([\d,]+)\s+([\d.]+)\s+([\d,]+)\s+([\d,]+)", t)
    g = re.search(r"균등방식\s*유형\s*균등방식\s*([\d,]+)", t) or re.search(r"균등방식\s+([\d,]+)\s+[\d.]+", t)
    return {"q0": num(m.group(1)), "n": num(m.group(3)), "eq": num(g.group(1))} if m and g and "청약건수" in t else None

def listing(bgn, end, **kw):
    out, p = [], 1
    while True:
        L = json.loads(get("list.json", bgn_de=bgn.strftime("%Y%m%d"), end_de=end.strftime("%Y%m%d"), page_no=p, page_count=100, **kw))
        if L.get("status") != "000": break
        out += L["list"]
        if p >= L.get("total_page", 1): break
        p += 1
    return out

def collect(tot):
    today = dt.date.today(); seen = {r["rcept"] for r in tot}; eq = set(); rep = []
    for k in range(2):   # 최근 180일: 지분증권 발행조건확정 신고서를 낸 회사 / 최근 30일 발행실적보고서
        e = today - dt.timedelta(days=90 * k); b = e - dt.timedelta(days=89)
        for r in listing(b, e, pblntf_ty="C"):
            if "발행조건확정" in r["report_nm"] and "지분증권" in r["report_nm"]: eq.add(r["corp_code"])
            if "증권발행실적보고서" in r["report_nm"] and r["rcept_dt"] >= (today - dt.timedelta(days=30)).strftime("%Y%m%d"): rep.append(r)
    have = {r["corp"] for r in tot}
    for r in sorted(rep, key=lambda r: r["rcept_no"], reverse=True):   # 정정본이 최신
        if r["corp_code"] not in eq or r["rcept_no"] in seen: continue
        p = parse(text(r["rcept_no"]))
        if not p: continue
        tot[:] = [x for x in tot if x["corp"] != r["corp_code"]]   # 같은 회사 이전(정정 전) 기록은 교체
        tot.append({"corp": r["corp_code"], "name": r["corp_name"], "rcept": r["rcept_no"], **p}); seen.add(r["rcept_no"])
        print("새 실적", r["corp_name"], p, flush=True)
    tot.sort(key=lambda r: r["rcept"])

# ---- 모델 ----
BK = ["미래", "한투", "NH", "삼성", "KB", "대신", "신한", "하나", "키움"]
nz = lambda x: re.sub(r"\(.*?\)|㈜|주식회사|\s", "", x).upper()
ALIAS = {"LGCNS": "LG씨엔에스", "디에스단석": "DS단석", "GC지놈": "지씨지놈"}
def days(a, b): return (dt.date.fromisoformat(a) - dt.date.fromisoformat(b)).days

def join(listed, tot):
    out = []
    for l in listed:
        if re.search("스팩|기업인수목적", l["name"]) or not l.get("sub"): continue
        a = nz(l["name"]); a = ALIAS.get(a, a); e = l["sub"][1].replace("-", "")
        C = [t for t in tot if e <= t["rcept"][:8] <= str(int(e) + 300) and (nz(t["name"]) in a or a in nz(t["name"]) or nz(t["name"])[:3] == a[:3])]
        if C:
            t = min(C, key=lambda t: t["rcept"]); out.append({**l, "n": t["n"], "q0": t["q0"], "eq": t["eq"]})
    return sorted(out, key=lambda r: r["sub"][1])

def mood(u, hist):   # 최근 분위기: 이 종목 청약 시작 전 45일 안에 청약이 끝난 종목들의 청약건수 중앙값(없으면 90일)
    for w in (45, 90):
        P = sorted(r["n"] for r in hist if 0 < days(u["sub"][0], r["sub"][1]) <= w)
        if len(P) >= 3: return math.log(P[len(P) // 2])
    return None

def feats(u, hist):
    m = mood(u, hist); q0 = sum(a.get("shares") or 0 for a in u.get("alloc") or []) or u.get("q0")
    if m is None or not u.get("inst") or not u.get("price") or not q0: return None
    return [1, math.log(u["inst"] + 1), (u.get("lock") or 0) / 10, math.log(q0 * u["price"]), math.log(u["price"]), len(u["brokers"]),
            1 if "유가" in (u.get("market") or u["name"]) else 0, m] + [1 if b in u["brokers"] else 0 for b in BK]

def ols(X, Y, lam=1e-3):   # 정규방정식 + 아주 작은 릿지(증권사 더미 공선성 대비)
    k = len(X[0]); A = [[sum(x[i] * x[j] for x in X) + (lam if i == j and i else 0) for j in range(k)] + [sum(x[i] * y for x, y in zip(X, Y))] for i in range(k)]
    for c in range(k):
        p = max(range(c, k), key=lambda r: abs(A[r][c])); A[c], A[p] = A[p], A[c]
        for r in range(k):
            if r != c and A[c][c]:
                f = A[r][c] / A[c][c]; A[r] = [a - f * b for a, b in zip(A[r], A[c])]
    return [A[i][k] / A[i][i] for i in range(k)]

def main():
    tot = json.load(open(TOT, encoding="utf-8"))
    if K: collect(tot)
    json.dump(tot, open(TOT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    D = json.loads(re.search(r'<script[^>]*id="ipodata"[^>]*>(.*?)</script>', html, re.S).group(1))
    J = join(D["listed"], tot)
    X, Y = [], []
    for i, r in enumerate(J):
        f = feats(r, J[:i])
        if f: X.append(f); Y.append(math.log(r["n"]))
    b = ols(X, Y)
    res = sorted(y - sum(p * q for p, q in zip(f, b)) for f, y in zip(X, Y))
    lo, hi = res[int(len(res) * 0.2)], res[int(len(res) * 0.8)]   # 80% 구간이 아니라 가운데 60%: 알림엔 "보통 이 범위"로
    today = dt.date.today().isoformat()
    pred = {}
    for u in D["upcoming"] + D["listed"]:
        if not u.get("sub") or u["sub"][1] < today or re.search("스팩|기업인수목적", u["name"]): continue
        f = feats(u, J)
        if not f: continue
        n = math.exp(sum(p * q for p, q in zip(f, b))); q = sum(a.get("shares") or 0 for a in u.get("alloc") or [])
        pred[str(u["no"])] = {"n": round(n), "e": round(q / 2 / n, 2), "lo": round(q / 2 / (n * math.exp(hi)), 2), "hi": round(q / 2 / (n * math.exp(lo)), 2), "q": q // 2}
    act = {str(r["no"]): {"n": r["n"], "e": round(r["eq"] / r["n"], 2)} for r in J if days(today, r["sub"][1]) <= 60}
    out = {"asof": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ"), "fit": len(Y), "pred": pred, "act": act}
    json.dump(out, open(os.path.join(ROOT, "eq.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("학습", len(Y), "예측", pred, "실제", len(act))

if __name__ == "__main__": main()
