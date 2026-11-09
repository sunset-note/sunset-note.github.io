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

# 후보 모델: 매 실행마다 최근 100종목을 "그 종목 청약 시작 전에 공시된 자료만으로" 다시 맞혀 보고 평균 오차가 가장 작은 것을 쓴다
CANDS = {"전체": {}, "증권사 제외": {"nobk": 1}, "최근 2년만 학습": {"years": 2}, "기관경쟁률 곡선": {"curve": 1}}
def shape(f, c):
    f = list(f)
    if c.get("curve"): f.append(f[1] ** 2 / 10)
    return f[:8] if c.get("nobk") else f
LOG = os.path.join(SRC, "eq_log.json")

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
        return ols([shape(F[i], c) for i in R], [math.log(J[i]["n"]) for i in R]), len(R)
    idx = [i for i in range(len(J)) if F[i]][-100:]
    score = {}
    for name, c in CANDS.items():
        E = []
        for i in idx:
            b, _ = train(c, J[i]["sub"][0]); E.append(math.log(J[i]["n"]) - sum(p * q for p, q in zip(shape(F[i], c), b)))
        A = sorted(abs(x) for x in E)
        score[name] = {"mae": sum(A) / len(A), "med": round((math.exp(A[len(A) // 2]) - 1) * 100), "in50": round(sum(a < math.log(1.5) for a in A) / len(A) * 100), "E": sorted(E)}
    # 후보끼리 오차 차이가 작으면 바꾸지 않는다(실행마다 모델이 오락가락하지 않게): 현재 모델보다 평균 오차가 5% 이상 작을 때만 교체
    try: cur = json.load(open(os.path.join(ROOT, "eq.json"), encoding="utf-8")).get("model") or "전체"
    except Exception: cur = "전체"
    if cur not in score: cur = "전체"
    best = min(score, key=lambda k: score[k]["mae"]); best = best if score[best]["mae"] < score[cur]["mae"] * 0.95 else cur
    c = CANDS[best]; E = score[best]["E"]
    lo, hi = E[int(len(E) * 0.2)], E[int(len(E) * 0.8)]   # 범위도 학습 오차가 아니라 실제로 맞혀 본 오차의 가운데 60%
    today = dt.date.today().isoformat(); tomorrow = (dt.date.today() + dt.timedelta(days=1)).isoformat()
    b, fit = train(c, tomorrow); pred = {}
    log = json.load(open(LOG, encoding="utf-8")) if os.path.exists(LOG) else {}
    for u in D["upcoming"] + D["listed"]:
        if not u.get("sub") or u["sub"][1] < today or re.search("스팩|기업인수목적", u["name"]): continue
        f = feats(u, J)
        if not f: continue
        n = math.exp(sum(p * q for p, q in zip(shape(f, c), b))); q = sum(a.get("shares") or 0 for a in u.get("alloc") or [])
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
    json.dump(out, open(os.path.join(ROOT, "eq.json"), "w", encoding="utf-8"), ensure_ascii=False, separators=(",", ":"))
    print("모델", best, "학습", fit, "후보", rank, "실전", live, "예측", pred)

if __name__ == "__main__": main()
