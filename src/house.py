# 마이홈포털에서 인천·경기 임대주택 공고를 모은다 -> house.json. 실패하면 직전 페이지에 들어 있던 자료를 그대로 쓴다.
# 공개 공고만 담는다. 동네·소득 같은 내 조건은 여기 넣지 않고 주인 기기의 연동 기록에만 둔다.
import sys, re, json, time, html, urllib.request, urllib.parse, http.cookiejar, datetime as dt

OUT, PREV = sys.argv[1], sys.argv[2]
VIEW = "https://www.myhome.go.kr/hws/portal/sch/selectRsdtRcritNtcView.do"
LIST = "https://www.myhome.go.kr/hws/portal/sch/selectRsdtRcritNtcList.do"
APPLY = "https://www.applyhome.co.kr/ai/aia/selectOtherLttotPblancListView.do"
UA = "Mozilla/5.0 (Macintosh) AppleWebKit/537.36 Chrome/130 Safari/537.36"
KST = dt.timezone(dt.timedelta(hours=9))


def fetch():
    o = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    o.open(urllib.request.Request(VIEW, headers={"User-Agent": UA}), timeout=25).read()
    head = {"User-Agent": UA, "X-Requested-With": "XMLHttpRequest", "Referer": VIEW}

    def q(page, brtc, ty="", st=""):
        body = urllib.parse.urlencode(dict(pageIndex=page, srchbrtcCode=brtc, srchSuplyTy=ty, srchPrgrStts=st)).encode()
        time.sleep(1.5)
        return json.load(o.open(urllib.request.Request(LIST, body, head), timeout=25))["resultList"]

    raw = []
    for b in ("28", "41"):   # 인천, 경기
        for p in range(1, 5):   # 최근 공고(한 쪽 5건)
            L = q(p, b); raw += L
            if len(L) < 5: break
        for p in range(1, 3):   # 공공지원 민간임대는 뜸해서 따로 모은다
            L = q(p, b, ty="11"); raw += L
            if len(L) < 5: break
    seen, items = {}, []
    for x in sorted(raw, key=lambda v: v.get("rcritPblancDe") or "", reverse=True):
        name = re.sub(r"\s+", " ", html.unescape(x.get("pblancNm") or "")).strip()
        url = x.get("url") or ""
        if not name or name in seen: continue   # 정정공고는 같은 이름으로 또 올라온다. 최신 하나만
        seen[name] = 1
        items.append(dict(n=name, s=x.get("prgrStts") or "", d=x.get("rcritPblancDe") or "", t=x.get("suplyTyNm") or "",
                          i=x.get("prvateInsttNm") or x.get("suplyInsttNm") or "", r=x.get("brtcCodeNm") or "",
                          u=url if url.startswith(("https://", "http://")) else VIEW))
    if not items: raise ValueError("공고 없음")
    return dict(asof=dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M"), items=items)


def rental():   # 청약홈 민간임대(공공지원 포함): 마이홈에는 최근 민간임대 공고가 거의 없어 따로 받는다. 제목에 시·동이 없어 권역 공고로 다룬다(w)
    out, today = [], dt.datetime.now(KST).strftime("%Y-%m-%d")
    for p in range(1, 5):
        q = urllib.parse.urlencode(dict(searchHouseSecd="0203", pageIndex=p))
        b = urllib.request.urlopen(urllib.request.Request(APPLY + "?" + q, headers={"User-Agent": UA}), timeout=25).read().decode("utf-8", "replace")
        rows = re.findall(r"<tr[^>]*>\s*<td.*?</tr>", b, re.S)
        for r in rows:
            c = [html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", t))).strip() for t in re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)]
            if len(c) < 7 or c[0] not in ("인천", "경기") or "임대" not in c[1]: continue
            end = c[6].split("~")[-1].strip()
            out.append(dict(n=c[2], s="모집중" if end >= today else "모집완료", d=c[5].replace("-", ""), t=c[1], i=c[3], r=c[0], u=APPLY, w=1))
        if len(rows) < 10: break
        time.sleep(1.5)
    return out


try:
    d = fetch()
    try:
        names = {x["n"] for x in d["items"]}
        d["items"] = [x for x in rental() if x["n"] not in names] + d["items"]
        d["items"].sort(key=lambda x: x["d"], reverse=True)
    except Exception as e:
        print("청약홈 민간임대를 받지 못했습니다:", e, file=sys.stderr)
except Exception as e:
    print("임대주택 공고를 받지 못했습니다:", e, file=sys.stderr)
    try:
        m = re.search(r'<script id="housedata" type="application/json">(.*?)</script>', open(PREV, encoding="utf-8").read(), re.S)
        d = json.loads(m.group(1).replace("<\\/", "</"))
    except Exception:
        d = dict(asof="", items=[])
json.dump(d, open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))
