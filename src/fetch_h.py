import json, time, urllib.request, sys, calendar
OUT=sys.argv[1]
def get(url):
    for i in range(6):
        try:
            r=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
            return json.load(urllib.request.urlopen(r,timeout=30))
        except Exception as e:
            print("retry",url,e); time.sleep(2+i)
    raise SystemExit("fail "+url)
def ts(s): return calendar.timegm(time.strptime(s,"%Y-%m-%dT%H:%M:%S"))
def hourly(base, market, stop, z):
    res={}; to=""
    while True:
        d=get(f"{base}/v1/candles/minutes/60?market={market}&count=200"+(f"&to={to}" if to else ""))
        if not isinstance(d,list) or not d: break
        for c in d: res[ts(c["candle_date_time_utc"])]=c["trade_price"]   # 키 = 봉 시작 UTC epoch
        last=d[-1]["candle_date_time_utc"]
        if len(d)<200 or last<stop: break
        to=last+z if z else d[-1]["candle_date_time_kst"]
        time.sleep(0.12)
    return res
def fx():
    d=get("https://query1.finance.yahoo.com/v8/finance/chart/KRW=X?range=730d&interval=60m")
    r=d["chart"]["result"][0]; res={}
    for t,c in zip(r["timestamp"],r["indicators"]["quote"][0]["close"]):
        if c: res[t - t%3600]=c
    return res
data={"upbit":hourly("https://api.upbit.com","KRW-USDT","2024-01-01","Z"),
      "bithumb":hourly("https://api.bithumb.com","KRW-USDT","2024-01-01",""),
      "fx":fx()}
for k,v in data.items(): print(k,len(v),time.strftime("%Y-%m-%d %H",time.gmtime(min(v))),time.strftime("%Y-%m-%d %H",time.gmtime(max(v))))
json.dump({k:{str(a):b for a,b in v.items()} for k,v in data.items()},open(OUT,"w"))
