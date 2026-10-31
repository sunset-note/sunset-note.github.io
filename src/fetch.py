import json, time, urllib.request, sys, os
OUT=sys.argv[1]
def get(url):
    for i in range(5):
        try:
            r=urllib.request.Request(url,headers={"User-Agent":"Mozilla/5.0"})
            return json.load(urllib.request.urlopen(r,timeout=30))
        except Exception as e:
            print("retry",url,e); time.sleep(2)
    raise SystemExit("fail "+url)
def upbitlike(base, market, key="candle_date_time_utc", z="Z"):
    res={}; to=""
    while True:
        d=get(f"{base}/v1/candles/days?market={market}&count=200"+(f"&to={to}" if to else ""))
        if not isinstance(d,list) or not d: break
        for c in d:
            res[c[key][:10]]=[c["high_price"],c["low_price"],c["trade_price"]]
        last=d[-1]["candle_date_time_utc"]
        if len(d)<200: break
        to=last+z
        time.sleep(0.15)
    return res
def binance(tz="0"):
    res={}; start=1500000000000
    while True:
        d=get(f"https://data-api.binance.vision/api/v3/klines?symbol=BTCUSDT&interval=1d&limit=1000&startTime={start}&timeZone={tz}")
        if not d: break
        for k in d: res[time.strftime("%Y-%m-%d",time.gmtime(k[0]/1000+int(tz)*3600))]=float(k[4])
        if len(d)<1000: break
        start=d[-1][0]+86400000
    return res
def fx():
    d=get("https://query1.finance.yahoo.com/v8/finance/chart/KRW=X?period1=1483228800&period2=%d&interval=1d"%int(time.time()))
    r=d["chart"]["result"][0]; res={}
    for t,c in zip(r["timestamp"],r["indicators"]["quote"][0]["close"]):
        if c: res[time.strftime("%Y-%m-%d",time.gmtime(t))]=c
    return res
data={"upbit_usdt":upbitlike("https://api.upbit.com","KRW-USDT"),
      "upbit_btc":upbitlike("https://api.upbit.com","KRW-BTC"),
      "bithumb_usdt":upbitlike("https://api.bithumb.com","KRW-USDT","candle_date_time_kst",""),
      "bithumb_btc":upbitlike("https://api.bithumb.com","KRW-BTC","candle_date_time_kst",""),
      "binance_btc":binance(),"binance_btc_kst":binance("9"),"fx":fx()}
for k,v in data.items(): print(k,len(v),min(v),max(v))
json.dump(data,open(OUT,"w"))
