import json,sys,bisect,datetime as dt,statistics as st
def corr(a,b):
    ma,mb=st.mean(a),st.mean(b); c=sum((x-ma)*(y-mb) for x,y in zip(a,b))
    return c/(sum((x-ma)**2 for x in a)*sum((y-mb)**2 for y in b))**.5
raw=json.load(open(sys.argv[1]))
fx=raw["fx"]; END=sys.argv[3] if len(sys.argv)>3 else "2026-10-25"  # 마지막으로 다 끝난 날
FXD=sorted(fx)
def fxclose(d):  # d일 또는 그 전 마지막 야후 일봉 환율 (2024년 이후는 build_h.py가 마감 시각의 1시간봉 환율로 덮어씀)
    i=bisect.bisect_right(FXD,d)-1
    return fx[FXD[max(i,0)]]
def days(a,b):
    d=dt.date.fromisoformat(a); e=dt.date.fromisoformat(b)
    while d<=e: yield d.isoformat(); d+=dt.timedelta(1)
out={"end":END,"ex":{}}
for ex,bk,bn in [("upbit","upbit_btc","binance_btc"),("bithumb","bithumb_btc","binance_btc_kst")]:
    btc=raw[bk]; bin_=raw[bn]; us=raw[ex+"_usdt"]
    start=max(min(btc),min(bin_),"2017-09-25" if ex=="upbit" else "2017-08-17")
    last=None; rows={"d0":start,"fx":[],"bk":[],"uc":[],"uh":[],"ul":[]}
    for d in days(min(fx),END):
        if d<start: continue
        f=fxclose(d); b=btc.get(d); n=bin_.get(d)
        bk_=round((b[2]/(n*f)-1)*100,3) if b and n else None
        u=us.get(d)
        rows["fx"].append(round(f,2)); rows["bk"].append(bk_)
        for i,k in enumerate(["uh","ul","uc"]): rows[k].append(u[i] if u else None)
    out["ex"][ex]=rows
    # overlap stats
    pairs=[(rows["bk"][i],(rows["uc"][i]/rows["fx"][i]-1)*100) for i in range(len(rows["fx"])) if rows["uc"][i] and rows["bk"][i] is not None]
    a=[p[0] for p in pairs]; b=[p[1] for p in pairs]
    print(ex,len(rows["fx"]),"overlap",len(pairs),"corr",round(corr(a,b),3),"meandiff",round(st.mean(x-y for x,y in pairs),3))
    bks=[x for x in rows["bk"] if x is not None]; print(" btc kimp min/max",min(bks),max(bks), "missing",rows["bk"].count(None))
json.dump(out,open(sys.argv[2],"w"),separators=(",",":"))
