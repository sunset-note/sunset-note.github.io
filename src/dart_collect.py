# 수집용: 2021년 이후 공모주(균등배정 있는 것)의 증권발행실적보고서와 발행조건확정 증권신고서 본문을 받아 out/에 저장
# (키는 환경변수 DART_KEY, 출력하지 않음). 파싱·모델링은 받은 본문으로 따로 한다.
import gzip, io, json, os, re, sys, time, zipfile, urllib.request, urllib.parse, datetime as dt
K = os.environ["DART_KEY"]
def get(path, **q):
    q["crtfc_key"] = K
    for i in range(4):
        try:
            return urllib.request.urlopen("https://opendart.fss.or.kr/api/%s?%s" % (path, urllib.parse.urlencode(q)), timeout=90).read()
        except Exception as e:
            print("retry", path, type(e).__name__); time.sleep(5 * (i + 1))
    raise SystemExit("fail " + path)
def text(rcept):
    b = get("document.xml", rcept_no=rcept)
    try: d = zipfile.ZipFile(io.BytesIO(b))
    except zipfile.BadZipFile: return ""
    t = " ".join(re.sub(r"<[^>]+>", " ", d.read(n).decode("utf-8", "ignore")) for n in d.namelist())
    return re.sub(r"\s+", " ", t)
def listing(bgn, end, **kw):
    out, p = [], 1
    while True:
        L = json.loads(get("list.json", bgn_de=bgn, end_de=end, page_no=p, page_count=100, **kw))
        if L.get("status") != "000": break
        out += L["list"]
        if p >= L.get("total_page", 1): break
        p += 1
    return out
start = dt.date.fromisoformat(sys.argv[1] if len(sys.argv) > 1 else "2021-01-01")
today = dt.date.today()
os.makedirs("out", exist_ok=True)
rep, eq = {}, set()
d = start
while d < today:
    e = min(d + dt.timedelta(days=89), today)
    for r in listing(d.strftime("%Y%m%d"), e.strftime("%Y%m%d"), pblntf_ty="C"):
        if "발행조건확정" in r["report_nm"] and "지분증권" in r["report_nm"]: eq.add(r["corp_code"])
        if "증권발행실적보고서" in r["report_nm"]:
            rep.setdefault(r["corp_code"], []).append(r)
    d = e + dt.timedelta(days=1)
# 채권 발행실적이 수천 건이라, 지분증권 발행조건확정 신고서를 낸 회사(공모주·일반공모 증자)만 본다
rep = {c: r for c, r in rep.items() if c in eq}
print("발행실적보고서 회사 수(지분증권)", len(rep), flush=True)
meta, n = [], 0
for c, rs in sorted(rep.items(), key=lambda x: min(r["rcept_no"] for r in x[1])):
    # 한 회사에 채권·증자 실적보고서가 섞여 있으니 최신(정정본)부터 보며 균등배정 있는 것을 고른다
    for r in sorted(rs, key=lambda r: r["rcept_no"], reverse=True):
        t = text(r["rcept_no"])
        if "균등방식" in t and "청약건수" in t: break
    else: continue
    # 같은 회사의 발행조건확정 증권신고서(수요예측 결과·확약) — 실적보고서 접수일 기준 1년 안
    rd = dt.datetime.strptime(r["rcept_no"][:8], "%Y%m%d").date()
    L = json.loads(get("list.json", corp_code=c, bgn_de=(rd - dt.timedelta(days=360)).strftime("%Y%m%d"), end_de=r["rcept_no"][:8], pblntf_ty="C", page_count=100)).get("list", [])
    f = [x for x in L if "발행조건확정" in x["report_nm"] and "지분증권" in x["report_nm"]]
    f2 = text(max(f, key=lambda x: x["rcept_no"])["rcept_no"]) if f else ""
    with gzip.open("out/%s.json.gz" % c, "wt", encoding="utf-8") as g:
        json.dump({"corp": c, "name": r["corp_name"], "rcept": r["rcept_no"], "cls": r.get("corp_cls"), "rep": t, "fix": f2}, g, ensure_ascii=False)
    meta.append([c, r["corp_name"], r["rcept_no"], bool(f2)]); n += 1
    if n % 25 == 0: print(n, r["corp_name"], r["rcept_no"][:8], flush=True)
json.dump(meta, open("out/meta.json", "w"), ensure_ascii=False)
print("공모주 수", n)
