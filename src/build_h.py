import json,sys
R=json.load(open(sys.argv[1])); H=3600; out={}
fx={int(k):v for k,v in R["fx"].items()}
for ex in ["upbit","bithumb"]:
    u={int(k):v for k,v in R[ex].items()}
    t0=max(min(u),min(fx)); t1=max(u); k=[];f=[]; lf=lu=None; t=t0
    while t<=t1:
        if t in fx: lf=fx[t]
        if t in u: lu=u[t]
        k.append(round((lu/lf-1)*100,3)); f.append(round(lf,2)); t+=H
    out[ex]={"t0":t0,"k":k,"fx":f}
    print(ex,len(k),"non-int prices:",sum(1 for v in u.values() if v!=int(v)))
d=json.load(open(sys.argv[2])); d["h"]=out
# 1시간봉 환율이 있는 날은 일봉 환율도 그날 마감 시각(업비트 00시 UTC, 빗썸 00시 KST)의 시간별 환율로 바꿈
import datetime as dt
for ex,off in [("upbit",0),("bithumb",-9)]:
    E=d["ex"][ex]; d0=dt.date.fromisoformat(E["d0"]); n=0
    for i in range(len(E["fx"])):
        e=d0+dt.timedelta(i+1); c=int(dt.datetime(e.year,e.month,e.day,tzinfo=dt.timezone.utc).timestamp())+off*H
        j=(c-H-out[ex]["t0"])//H   # 마감 직전 1시간봉의 종가 = 마감 시각 환율 (주말 등 빈 시간은 직전 값)
        if 0<=j<len(out[ex]["fx"]):
            nf=out[ex]["fx"][j]
            if E["bk"][i] is not None: E["bk"][i]=round(((1+E["bk"][i]/100)*E["fx"][i]/nf-1)*100,3)   # 비트김프도 같은 환율로
            E["fx"][i]=nf; n+=1
    print(ex,"daily fx from hourly:",n)
json.dump(d,open(sys.argv[3],"w"),separators=(",",":"))
