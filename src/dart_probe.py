# 시험용: OpenDART 증권발행실적보고서에 증권사별 청약 건수가 어떻게 적혀 있는지 본다(키는 환경변수 DART_KEY, 출력하지 않음)
import io, json, os, re, sys, zipfile, urllib.request, urllib.parse
K = os.environ["DART_KEY"]
def get(path, **q):
    q["crtfc_key"] = K
    return urllib.request.urlopen("https://opendart.fss.or.kr/api/%s?%s" % (path, urllib.parse.urlencode(q)), timeout=60).read()
z = zipfile.ZipFile(io.BytesIO(get("corpCode.xml")))
x = z.read(z.namelist()[0]).decode("utf-8")
codes = {}
for m in re.finditer(r"<corp_code>(\d+)</corp_code>\s*<corp_name>([^<]+)</corp_name>", x):
    codes.setdefault(m.group(2).strip(), m.group(1))
print("회사 수", len(codes))
for name in sys.argv[1:]:
    c = codes.get(name)
    print("==", name, c)
    if not c: continue
    L = json.loads(get("list.json", corp_code=c, bgn_de="20240101", pblntf_ty="C", page_count=100))
    rs = [r for r in L.get("list", []) if "발행실적" in r["report_nm"]]
    print(L.get("status"), L.get("message"), [r["report_nm"] for r in L.get("list", [])][:8])
    if not rs: continue
    d = zipfile.ZipFile(io.BytesIO(get("document.xml", rcept_no=rs[0]["rcept_no"])))
    t = " ".join(re.sub(r"<[^>]+>", " ", d.read(n).decode("utf-8", "ignore")) for n in d.namelist())
    t = re.sub(r"\s+", " ", t)
    for kw in ["청약건수", "청약 건수", "건수"]:
        i = t.find(kw)
        if i >= 0:
            print("[", kw, "]", t[max(0, i - 300):i + 2500]); break
    else:
        print(t[:3000])
