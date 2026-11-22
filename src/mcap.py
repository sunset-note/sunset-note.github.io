# 미국·한국 시가총액 상위 10개와 1년 주가 흐름을 모아 mcap.json을 만든다.
# 미국 순위: companiesmarketcap.com CSV(미국 기업만), 한국 순위: 네이버 증권 코스피 시총 순위(우선주 제외).
# p는 순위 출처가 시총을 잴 때 쓴 가격(페이지가 오늘 가격으로 시총을 다시 맞출 때 기준).
# 주가 흐름: 야후 차트 일봉 1년. 페이지는 이 파일로 순위·크기를 그리고, 오늘 시세는 워커로 따로 받아 덮어쓴다.
# 실패하면 기존 파일을 그대로 둔다(빈 값으로 덮지 않음).
import csv, io, json, sys, time, urllib.request

UA = {"User-Agent": "Mozilla/5.0"}   # 전체 브라우저 문자열을 쓰면 야후가 429로 막는다
def get(u, t=30):
    for i in range(3):
        try:
            with urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=t) as r:
                return r.read()
        except Exception as e:
            err = e; time.sleep(3)
    raise err

KO = {"AAPL": "애플", "MSFT": "마이크로소프트", "GOOG": "알파벳(구글)", "GOOGL": "알파벳(구글)", "NVDA": "엔비디아", "AMZN": "아마존",
      "META": "메타", "TSLA": "테슬라", "AVGO": "브로드컴", "BRK-B": "버크셔 해서웨이", "LLY": "일라이 릴리", "JPM": "JP모건",
      "WMT": "월마트", "V": "비자", "ORCL": "오라클", "MA": "마스터카드", "XOM": "엑슨모빌", "NFLX": "넷플릭스", "COST": "코스트코",
      "SPCX": "스페이스X", "PLTR": "팔란티어", "JNJ": "존슨앤드존슨", "HD": "홈디포", "PG": "P&G", "UNH": "유나이티드헬스",
      "ABBV": "애브비", "AMD": "AMD", "BAC": "뱅크오브아메리카", "KO": "코카콜라", "CRM": "세일즈포스"}

def us_top():
    rows = list(csv.DictReader(io.StringIO(get("https://companiesmarketcap.com/?download=csv").decode("utf-8"))))
    out = []
    for r in rows:
        if r["country"] != "United States": continue
        s = r["Symbol"].replace(".", "-")
        out.append({"s": s, "n": KO.get(s, r["Name"]), "cap": float(r["marketcap"]), "p": float(r["price (USD)"])})
        if len(out) == 10: break
    return out

def kr_top():
    d = json.loads(get("https://m.stock.naver.com/api/stocks/marketValue/KOSPI?page=1&pageSize=20"))
    out = []
    for x in d["stocks"]:
        if x["stockEndType"] != "stock" or not x["itemCode"].endswith("0"): continue   # 우선주(끝자리 5·7·9·K) 제외
        out.append({"s": x["itemCode"] + ".KS", "n": x["stockName"], "cap": float(x["marketValue"].replace(",", "")) * 1e8, "p": float(x["closePrice"].replace(",", ""))})
        if len(out) == 10: break
    return out

def hist(s):
    r = json.loads(get(f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?range=1y&interval=1d"))["chart"]["result"][0]
    ts, cl = r["timestamp"], r["indicators"]["quote"][0]["close"]
    h = [[t, round(c, 4)] for t, c in zip(ts, cl) if c is not None]
    m = r["meta"]
    return h, m["regularMarketPrice"], m.get("chartPreviousClose")

def main(path):
    try: old = json.load(open(path))
    except Exception: old = {}
    res = {"t": int(time.time())}
    for k, f in (("us", us_top), ("kr", kr_top)):
        try:
            L = f()
            for x in L:
                h, p, _ = hist(x["s"])
                x["h"] = [c for _, c in h]; x["d0"] = h[0][0]      # 1년 일봉 종가
                time.sleep(0.3)
            if len(L) < 10: raise ValueError(f"{k} {len(L)}개뿐")
            res[k] = L
        except Exception as e:
            print(f"{k} 시총 수집 실패: {e}", file=sys.stderr)
            if k in old: res[k] = old[k]
    if "us" not in res and "kr" not in res: sys.exit(1)
    json.dump(res, open(path, "w"), ensure_ascii=False, separators=(",", ":"))
    print("시총 Top10:", {k: [x["n"] for x in res.get(k, [])] for k in ("us", "kr")})

main(sys.argv[1])
