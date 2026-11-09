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
            t = min(C, key=lambda t: t["rcept"]); out.append({**l, "n": t["n"], "q0": t["q0"], "eq": t["eq"], "rd": "%s-%s-%s" % (t["rcept"][:4], t["rcept"][4:6], t["rcept"][6:8])})
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

# 후보 모델: 매 실행마다 과거 종목을 "그 종목 청약 시작 전에 공시된 자료만으로" 다시 맞혀 보고 비교한다
BASE = "증권사 반영"   # 미래·KB 같은 대형사와 신영·하나 같은 곳의 청약건수 차이는 사실이라 기본으로 쓴다(단독 주관 같은 조건 대비 +25%~−49%)
CANDS = {BASE: {"nobk": 1, "shrink": 10}, "전체": {}, "증권사 제외": {"nobk": 1}, "최근 2년만 학습": {"years": 2}, "기관경쟁률 곡선": {"curve": 1}}
def shape(f, c):
    f = list(f)
    if c.get("curve"): f.append(f[1] ** 2 / 10)
    return f[:8] if c.get("nobk") else f
LOG = os.path.join(SRC, "eq_log.json")

# ---- 시초가 예측 ----
# 근거(2023-06-26 가격제한 60~400% 이후 공모주 239건, 앞 60건 뒤 매번 과거만으로 맞혀 본 179건):
#   평균만 쓰면 오차 중앙 58%p. 청약 전(기관경쟁률·확약·일반 공모금액·시장) 36%p, 순위상관 0.70. 청약 후(+청약 경쟁률) 30%p, 순위상관 0.80.
OLOG = os.path.join(SRC, "open_log.json")
def compn(c):
    if isinstance(c, (int, float)): return float(c)
    m = re.match(r"\s*([\d,.]+)", str(c or "")); return float(m.group(1).replace(",", "")) if m else None
def open_part(D, J, today):
    q = {r["no"]: r["q0"] for r in J}
    def size(u):
        n = sum(a.get("shares") or 0 for a in u.get("alloc") or []) or q.get(u["no"]); return n * u["price"] / 1e8 if n and u.get("price") else None
    def f(u, post):
        sz = size(u); c = compn(u.get("comp"))
        if not sz or not u.get("inst") or (post and not c): return None
        return [1, math.log(u["inst"] + 1), (u.get("lock") or 0) / 10, math.log(sz), 1 if "유가" in (u.get("market") or "") + u["name"] else 0] + ([math.log(c + 1)] if post else [])
    bad = "스팩|기업인수목적|리츠|인프라|부동산투자"
    H = sorted([l for l in D["listed"] if l.get("open") and l.get("price") and l.get("sub") and l.get("list") and l["list"] >= "2023-06-26" and not re.search(bad, l["name"])], key=lambda r: r["list"])
    y = lambda r: math.log(r["open"] / r["price"]); M = {}
    for post in (False, True):
        idx = [i for i in range(len(H)) if f(H[i], post)]; E = []
        for i in idx[-100:]:
            date = H[i]["sub"][1] if post else H[i]["sub"][0]; tr = [j for j in idx if H[j]["list"] < date]
            b = ols([f(H[j], post) for j in tr], [y(H[j]) for j in tr]); E.append(y(H[i]) - sum(a * c for a, c in zip(f(H[i], post), b)))
        E.sort(); M[post] = (ols([f(H[j], post) for j in idx], [y(H[j]) for j in idx]), E[int(len(E) * 0.2)], E[int(len(E) * 0.8)], len(idx))
    pc = lambda v: round((min(max(math.exp(v), 0.6), 4.0) - 1) * 100)   # 상장일 시초 범위: 공모가의 60~400%
    seen, out = set(), {}; log = json.load(open(OLOG, encoding="utf-8")) if os.path.exists(OLOG) else {}
    for u in D["upcoming"] + D["listed"]:
        if u["no"] in seen or u.get("open") or not u.get("sub") or re.search(bad, u["name"]) or (u.get("list") and u["list"] < today): continue
        seen.add(u["no"]); post = u["sub"][1] < today and compn(u.get("comp")) is not None; x = f(u, post) or (None if not post else f(u, False)); post = post and bool(f(u, True))
        if not x: continue
        b, lo, hi, _ = M[post]; v = sum(a * c for a, c in zip(x, b)); k = str(u["no"])
        out[k] = {"p": pc(v), "lo": pc(v + lo), "hi": pc(v + hi), "st": "post" if post else "pre"}
        g = log.setdefault(k, {"name": u["name"], "list": u.get("list")}); g["list"] = u.get("list") or g.get("list")
        if post: g["post"] = {**out[k], "made": today}
        elif "pre" not in g or today <= u["sub"][0]: g["pre"] = {**out[k], "made": today}
    act = {}
    for r in H:
        k = str(r["no"]); a = round((r["open"] / r["price"] - 1) * 100)
        if k in log: log[k]["act"] = a
        if days(today, r["list"]) <= 30: act[k] = a
    json.dump(log, open(OLOG, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    return out, act, {"pre": M[False][3], "post": M[True][3]}

def main():
    tot = json.load(open(TOT, encoding="utf-8"))
    if K: collect(tot)
    json.dump(tot, open(TOT, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    html = open(os.path.join(ROOT, "index.html"), encoding="utf-8").read()
    D = json.loads(re.search(r'<script[^>]*id="ipodata"[^>]*>(.*?)</script>', html, re.S).group(1))
    J = [r for r in join(D["listed"], tot) if r.get("inst") and r.get("price") and r["n"] > 100]
    F = [feats(r, [p for p in J if p["rd"] < r["sub"][0]]) for r in J]   # 학습 자료도 실제 예측 때와 똑같이, 당시 공시된 실적만으로 분위기를 계산
    def train(c, date):
        R = [i for i, r in enumerate(J) if F[i] and r["rd"] < date and (not c.get("years") or days(date, r["sub"][1]) <= 365 * c["years"])]
        b = ols([shape(F[i], c) for i in R], [math.log(J[i]["n"]) for i in R]); eff = {}
        if c.get("shrink"):   # 증권사 효과: 같은 조건 대비 그 증권사 종목들의 평균 차이, 표본이 적으면 0 쪽으로 줄인다
            S = {}
            for i in R:
                for x in J[i]["brokers"]: S.setdefault(x, []).append(math.log(J[i]["n"]) - sum(p * q for p, q in zip(shape(F[i], c), b)))
            eff = {x: sum(v) / (len(v) + c["shrink"]) for x, v in S.items()}
        return b, eff, len(R)
    def value(f, u, c, b, eff):   # 증권사가 여럿이면 효과가 가장 큰 곳 기준
        return sum(p * q for p, q in zip(shape(f, c), b)) + (max(eff.get(x, 0) for x in u["brokers"]) if eff else 0)
    idx = [i for i in range(len(J)) if F[i]][80:]
    score = {}
    for name, c in CANDS.items():
        E = []
        for i in idx:
            b, eff, _ = train(c, J[i]["sub"][0]); E.append(math.log(J[i]["n"]) - value(F[i], J[i], c, b, eff))
        A = sorted(abs(x) for x in E[-100:])
        score[name] = {"mae": sum(abs(x) for x in E) / len(E), "med": round((math.exp(A[len(A) // 2]) - 1) * 100), "in50": round(sum(a < math.log(1.5) for a in A) / len(A) * 100), "E": E}
    # 모델 교체: 전 구간 짝지은 오차 차이가 통계적으로 뚜렷할 때(t≥2)만. 비슷하면 현재 모델 유지(최근 100종목 5% 차이는 t=1 수준의 우연이었다)
    try: cur = json.load(open(os.path.join(ROOT, "eq.json"), encoding="utf-8")).get("model") or BASE
    except Exception: cur = BASE
    if cur not in score: cur = BASE
    best = min(score, key=lambda k: score[k]["mae"]); d = [abs(x) - abs(y) for x, y in zip(score[cur]["E"], score[best]["E"])]
    m = sum(d) / len(d); sd = (sum((x - m) ** 2 for x in d) / max(len(d) - 1, 1)) ** 0.5; t = m / (sd / len(d) ** 0.5) if sd else 0
    best = best if t >= 2 else cur
    c = CANDS[best]; E = sorted(score[best]["E"][-100:])
    lo, hi = E[int(len(E) * 0.2)], E[int(len(E) * 0.8)]   # 범위도 학습 오차가 아니라 실제로 맞혀 본 최근 100종목 오차의 가운데 60%
    today = dt.date.today().isoformat(); tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    b, eff, fit = train(c, tomorrow); pred = {}
    log = json.load(open(LOG, encoding="utf-8")) if os.path.exists(LOG) else {}
    for u in D["upcoming"] + D["listed"]:
        if not u.get("sub") or u["sub"][1] < today or re.search("스팩|기업인수목적", u["name"]): continue
        f = feats(u, J)
        if not f: continue
        n = math.exp(value(f, u, c, b, eff)); q = sum(a.get("shares") or 0 for a in u.get("alloc") or [])
        k = str(u["no"]); pred[k] = {"n": round(n), "e": round(q / 2 / n, 2), "lo": round(q / 2 / (n * math.exp(hi)), 2), "hi": round(q / 2 / (n * math.exp(lo)), 2), "q": q // 2}
        if k not in log or today <= u["sub"][0]: log[k] = {"name": u["name"], "made": today, "sub": u["sub"][0], "model": best, **pred[k]}   # 청약 첫날까지의 예측을 기록으로 고정
    act = {str(r["no"]): {"n": r["n"], "e": round(r["eq"] / r["n"], 2)} for r in J if days(today, r["sub"][1]) <= 60}
    for r in J:
        k = str(r["no"])
        if k in log: log[k]["act"] = round(r["eq"] / r["n"], 2); log[k]["actn"] = r["n"]
    json.dump(log, open(LOG, "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    done = [v for v in log.values() if "actn" in v]; AE = sorted(abs(math.log(v["n"] / v["actn"])) for v in done)
    live = {"n": len(done), "med": round((math.exp(AE[len(AE) // 2]) - 1) * 100) if AE else None, "inrange": round(sum(v["lo"] <= v["act"] <= v["hi"] for v in done) / len(done) * 100) if done else None}
    rank = {k: {"med": v["med"], "in50": v["in50"]} for k, v in sorted(score.items(), key=lambda x: x[1]["mae"])}
    out = {"asof": dt.datetime.utcnow().strftime("%Y-%m-%dT%H:%MZ"), "fit": fit, "model": best, "test": rank, "live": live, "pred": pred, "act": act}
    out["open"], out["oa"], out["ofit"] = open_part(D, join(D["listed"], tot), today)
    print("시초", out["open"], out["ofit"])
    json.dump(out, open(os.path.join(ROOT, "eq.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("모델", best, "학습", fit, "후보", rank, "실전", live, "예측", pred)

if __name__ == "__main__": main()
