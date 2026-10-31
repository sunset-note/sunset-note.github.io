# 38커뮤니케이션에서 공모주 청약일정·신규상장 수집 -> ipo.json
import os, re, sys, json, math, time, html, urllib.request, datetime as dt

BASE = "https://www.38.co.kr/html/fund/"
OUT = sys.argv[1] if len(sys.argv) > 1 else "ipo.json"
KST = dt.timezone(dt.timedelta(hours=9))
TODAY = dt.datetime.now(KST).date()  # GitHub 서버(UTC)에서도 한국 날짜로
CUT = TODAY - dt.timedelta(days=380)  # 최근 1년 통계용
HCUT = dt.date(2021, 1, 1)  # 상장 결과 통계: 균등배정 도입(2021) 이후

BROKERS = [("한국투자", "한투"), ("미래에셋", "미래"), ("NH", "NH"), ("대신", "대신"), ("KB", "KB"),
           ("삼성", "삼성"), ("신한", "신한"), ("키움", "키움"), ("하나", "하나"), ("유안타", "유안타"),
           ("DB", "DB"), ("교보", "교보"), ("IBK", "IBK"), ("신영", "신영"), ("SK", "SK"),
           ("한화", "한화"), ("유진", "유진"), ("아이엠", "iM"), ("iM", "iM"), ("하이투자", "iM"),
           ("LS", "LS"), ("이베스트", "LS"), ("현대차", "현대차"), ("BNK", "BNK"), ("상상인", "상상인"),
           ("케이프", "케이프"), ("부국", "부국"), ("다올", "다올"), ("메리츠", "메리츠"), ("우리투자", "우리"),
           ("토스", "토스"), ("카카오", "카카오"), ("한양", "한양"), ("코리아에셋", "코리아에셋"), ("흥국", "흥국")]


def short(name):
    for k, v in BROKERS:
        if k in name:
            return v
    return name.replace("증권", "").replace("투자", "").strip()


def get(url):
    for i in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            b = urllib.request.urlopen(req, timeout=20).read()
            time.sleep(0.4)
            return b.decode("euc-kr", "ignore")
        except Exception:
            time.sleep(2)
    raise RuntimeError("fetch fail " + url)


def text(s):
    return html.unescape(re.sub(r"<[^>]+>", " ", s)).replace("\xa0", " ").strip()


def num(s):
    s = re.sub(r"[^\d.\-]", "", s or "")
    try:
        return float(s) if s not in ("", "-", ".") else None
    except ValueError:
        return None


def d(s):
    return dt.date(*map(int, re.split(r"[./]", s)))


def rows(h, summary):
    i = h.find(summary)
    j = h.find("</table>", h.find("<tbody", i))
    for r in re.findall(r"<tr[^>]*>(.*?)</tr>", h[i:j], re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", r, re.S)
        m = re.search(r"no=(\d+)", r)
        if m and len(tds) >= 6:
            yield int(m.group(1)), [text(t) for t in tds]


# 1) 청약일정 (o=k)
sched = {}
for p in range(1, 60):
    h = get(BASE + "index.htm?o=k&page=%d" % p)
    old = False
    for no, t in rows(h, 'summary="공모주 청약일정"'):
        m = re.match(r"(\d{4})\.(\d\d)\.(\d\d)~(\d\d)\.(\d\d)", t[1].replace(" ", ""))
        if not m:
            continue
        y, a, b, c, e = map(int, m.groups())
        s = dt.date(y, a, b)
        en = dt.date(y + (1 if c < a else 0), c, e)
        sched[no] = dict(no=no, name=re.sub(r"\s+", " ", t[0]), sub=[s.isoformat(), en.isoformat()], price=num(t[2]),
                         band=t[3], comp=t[4] or None,
                         brokers=[short(x) for x in re.split(r"[,/]", t[5]) if x.strip()])
        if en < HCUT:
            old = True
    if old:
        break

# 2) 신규상장 (o=nw): 상장일·공모가·시초가·첫날종가
listed = {}
for p in range(1, 60):
    h = get(BASE + "index.htm?o=nw&page=%d" % p)
    old = False
    for no, t in rows(h, "신규상장일"):
        try:
            ld = d(t[1])
        except Exception:
            continue
        listed[no] = dict(no=no, name=re.sub(r"\s+", " ", t[0]), list=ld.isoformat(), price=num(t[4]),
                          open=num(t[6]), close=num(t[8]))
        if ld < HCUT:
            old = True
    if old:
        break

# 2b) 수요예측 결과 (o=r1): 기관경쟁률·의무보유확약·주간사
demand = {}
for p in range(1, 60):
    h = get(BASE + "index.htm?o=r1&page=%d" % p)
    old = False
    for no, t in rows(h, "의무보유"):
        if len(t) < 8:
            continue
        # 기관경쟁률은 "714.52:1" 또는 ":1" 없이 "714.52"로 나온다
        demand[no] = dict(inst=num(t[5].split(":")[0]) if re.search(r"\d", t[5]) else None, lock=num(t[6]),
                          brokers=[short(x) for x in re.split(r"[,/]", t[7]) if x.strip()])
        try:
            if d(t[1]) < HCUT - dt.timedelta(days=40):
                old = True
        except Exception:
            pass
    if old:
        break

def parse_float(t):
    """38 상세 텍스트에서 '공모후 유통가능 물량' 표 합계 행 → {total, shares, pct} (주식 수: 공모전, 공모후, 매각제한, 유통가능 순)"""
    i = t.find("공모후 유통가능")
    if i < 0: return None
    j = t.find("5.요약재무제표", i); sec = t[i:j if j > 0 else i + 30000]
    m = None
    for m in re.finditer(r"(합\s*계|총\s*계)", sec): pass
    if not m: return None
    nums = [int(x.replace(",", "")) for x in re.findall(r"(?<![\d.])(\d{1,3}(?:,\d{3})+|\d{4,})(?![\d.%])", sec[m.end():m.end() + 300])]
    if len(nums) < 4: return None
    pre, post, lock, fl = nums[:4]
    if post < pre or abs(lock + fl - post) > post * 0.02: return None
    return dict(total=post, shares=fl, pct=round(fl / post * 100, 2))


# 3) 다가오는 종목 상세: 상장일, 주간사별 배정, 기관경쟁률, 확약
def detail(no):
    t = text(get(BASE + "?o=v&no=%d&l=&page=1" % no))
    t = re.sub(r"\s+", " ", t)
    o = {}
    m = re.search(r"수요예측일 (\d{4}\.\d\d\.\d\d) ~ (\d{4}\.\d\d\.\d\d)", t)
    o["fc"] = [d(m.group(1)).isoformat(), d(m.group(2)).isoformat()] if m else None
    m = re.search(r"환불일 (\d{4}\.\d\d\.\d\d)", t)
    o["refund"] = d(m.group(1)).isoformat() if m else None
    m = re.search(r"상장일 (\d{4}\.\d\d\.\d\d)", t)
    o["list"] = d(m.group(1)).isoformat() if m else None
    m = re.search(r"시장구분 (\S+)", t)
    o["market"] = m.group(1) if m else None
    m = re.search(r"기관경쟁률 ([\d,.]+)(?::1)?", t)
    o["inst"] = num(m.group(1)) if m else None
    m = re.search(r"의무보유확약 ([\d.]+)%", t)
    o["lock"] = num(m.group(1)) if m else None
    m = re.search(r"청약증거금율 : (\d+)% 청약 최고한도", t)
    o["margin"] = num(m.group(1)) if m else 50
    m = re.search(r"주간사 (.*?) 주요일정", t)
    bk = []
    if m:
        g = m.group(1)
        if "인수회사" in g:  # 공동주관: 인수회사별 표
            g = g.split("기타", 1)[1]
            pat = r"(\S+?(?:증권|금융투자))\s+([\d,]+)(?:\s*~\s*[\d,]+)?\s*주\s+([\d,]+\s*~\s*[\d,]+|[\d,]+|-)\s*주"
            for name, sh, lim in re.findall(pat, g):
                bk.append(dict(name=short(name), shares=int(num(sh) or 0), limit=lim.replace(" ", "")))
        else:
            for name, sh, lim in re.findall(r"(\S+?(?:증권|금융투자))\s*주식수:\s*([\d,]+)[^/]*/\s*청약한도:\s*([\d,~\- ]+?)\s*주", g):
                bk.append(dict(name=short(name), shares=int(num(sh) or 0), limit=lim.replace(" ", "")))
    o["alloc"] = bk
    # 공모후 유통가능 물량(증권신고서 표의 합계 행): 상장주식수, 유통가능 주식수·비율
    o["float"] = parse_float(t)
    m = re.search(r"기관투자자등\s+([\d,]+)\s*주", t)
    o["instAlloc"] = int(num(m.group(1))) if m else None
    return o


up = []
for no, s in sched.items():
    en = dt.date.fromisoformat(s["sub"][1])
    li = listed.get(no)
    if en >= TODAY - dt.timedelta(days=21) or (li and dt.date.fromisoformat(li["list"]) >= TODAY):
        s.update(detail(no))
        if li:
            s["list"] = s.get("list") or li["list"]
        up.append(s)
up.sort(key=lambda x: x["sub"][0])

# 확약·유통가능물량 변화 기록: 매일 값을 저장해 두고 처음 값과 비교한다
TRACK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ipo_track.json")
try:
    track = json.load(open(TRACK))
except Exception:
    track = {}
for s in up:
    if s.get("inst") is None:
        continue
    h = track.setdefault(str(s["no"]), [])
    cur = [TODAY.isoformat(), s.get("lock"), (s.get("float") or {}).get("shares")]
    if not h or h[-1][1:] != cur[1:]:
        h.append(cur)
    s["hist"] = h
json.dump(track, open(TRACK, "w"), ensure_ascii=False)

hist = []
for no, l in listed.items():
    s = sched.get(no, {})
    dm = demand.get(no, {})
    l["brokers"] = s.get("brokers") or dm.get("brokers", [])
    l["sub"] = s.get("sub")
    l["inst"], l["lock"] = dm.get("inst"), dm.get("lock")
    l["comp"] = num((s.get("comp") or "").split(":")[0]) if re.search(r"\d", s.get("comp") or "") else None
    if l["list"] >= HCUT.isoformat():
        hist.append(l)
hist.sort(key=lambda x: x["list"], reverse=True)

# 점수(0~100): 기관경쟁률·확약·상장일 유통금액(확약분 제외)이 비슷한 과거 종목의 시초가 성적으로 매긴다.
# 2023.6.26 이후 상장(스팩 제외)을 비교 대상으로, 개편(2025-07-15) 이후 종목은 2배 가중.
# 상장 결과의 점수는 그 종목 상장 전에 나온 결과만으로 계산해 실제로 맞았는지 확인할 수 있게 한다.
FC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "float_cache.json")
try:
    fcache = json.load(open(FC_PATH))
except Exception:
    fcache = {}
for s in up:
    f = s.get("float")
    if f and f.get("shares"):
        fcache[str(s["no"])] = dict(f, instAlloc=s.get("instAlloc"))
json.dump(fcache, open(FC_PATH, "w"), ensure_ascii=False)


def flt(x):
    f = fcache.get(str(x["no"])) or {}
    if not f.get("shares") or not x.get("price"):
        return None
    return (f["shares"] - round((f.get("instAlloc") or 0) * (x.get("lock") or 0) / 100)) * x["price"] / 1e8


def feat(x):
    fl = flt(x)
    return (math.log10(max(x["inst"], 1)), math.log10(1 + (x.get("lock") or 0)), None if fl is None else math.log10(max(fl, 10)))


SC_BASE = [x for x in hist if x["list"] >= "2023-06-26" and "스팩" not in x["name"] and x.get("inst") is not None and x.get("price") and x.get("open")]
for x in SC_BASE:
    x["_f"] = feat(x)


def score(u, pool):
    if u.get("inst") is None or len(pool) < 30:
        return None
    fu, ds = feat(u), []
    for x in pool:
        fx = x["_f"]
        d = ((fu[0] - fx[0]) / 0.35) ** 2 + ((fu[1] - fx[1]) / 0.25) ** 2
        d += ((fu[2] - fx[2]) / 0.3) ** 2 if fu[2] is not None and fx[2] is not None else 0.5
        ds.append((math.exp(-d / 2) * (2 if x["list"] >= "2025-07-15" else 1), x["open"] / x["price"] - 1))
    sw = sum(w for w, _ in ds)
    win = sum(w for w, r in ds if r > 0) / sw
    acc = 0
    for w, r in sorted(ds, key=lambda t: t[1]):
        acc += w
        if acc >= sw / 2:
            med = r
            break
    raw = 0.4 * win * 100 + 0.6 * max(0, min(100, 50 + 25 * math.log2(max(1 + med, 0.05))))
    return max(0, min(100, round((raw - 40) / 55 * 100)))


for s in up:
    s["score"] = None if "스팩" in s["name"] else score(s, SC_BASE)
for x in hist:
    if x.get("inst") is not None and x["list"] >= "2023-06-26" and "스팩" not in x["name"]:
        x["score"] = score(x, [y for y in SC_BASE if y["list"] < x["list"]])
for x in SC_BASE:
    del x["_f"]
    fl = flt(x)
    if fl is not None:
        x["fl"] = round(fl, 1)

json.dump(dict(asof=dt.datetime.now(KST).strftime("%Y-%m-%d %H:%M"), upcoming=up, listed=hist),
          open(OUT, "w"), ensure_ascii=False, separators=(",", ":"))
print("ipo: upcoming %d, listed %d (inst %d)" % (len(up), len(hist), sum(1 for x in hist if x["inst"])))
