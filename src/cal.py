# 공모주 캘린더 후보 목록(events)과 알림용 종목 요약(up) -> cal.json (GitHub 자동 실행에서 ipo.json으로 만든다)
# 구글 Apps Script가 이 목록을 읽어, graded(비례·대출)이거나 사이트에서 ★로 고른 종목만 구글 캘린더에 등록한다.
# 사용: python3 cal.py <ipo.json> > cal.json
# 등급 기준은 template.html의 recKind()와 같게 유지한다.
# cal.json은 공개 파일이라 가족 이름은 넣지 않고 '가족'으로만 쓴다(누구 핸드폰이 필요한지는 텔레그램 알림이 연동 저장소에서 읽어 알려 준다).
import sys, json, datetime as dt

D = json.load(open(sys.argv[1]))
st = {"done": {}}
today = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date().isoformat()


def kind(i, l):
    l = l or 0
    if i < 100 or (l < 1 and (i < 500 or i >= 1000)) or (i < 500 and l < 5): return "x"
    if i >= 500 and l >= 15: return "l"
    if (i >= 500 and l >= 2) or (i >= 1000 and l >= 1) or (i < 500 and l >= 25): return "p"   # 예전 균등은 2026-11-01부터 비례로 합침
    return "c"


FAMILY = {"한투", "미래", "NH", "대신"}   # 가족 계좌가 있는 증권사
NAME = {"l": "대출", "p": "비례", "e": "균등"}
COLOR = "2"  # 공모주 일정은 전부 연두(Sage)
ACT = {"l": "여유자금+마통으로 비례", "p": "여유자금으로 비례", "e": "균등 최소 수량"}
INST_B, LOCK_B = [0, 100, 500, 1000, 1e12], [0, 1, 5, 15, 1e12]
bk = lambda B, v: next(j for j in range(4) if B[j] <= v < B[j + 1])
H = [x for x in D["listed"] if x["list"] >= "2023-06-26" and "스팩" not in x["name"] and x.get("inst") is not None and x.get("price") and x.get("open")]
ro = lambda x: x["open"] / x["price"] - 1

res = []
for u in D["upcoming"]:
    k = kind(u["inst"], u.get("lock")) if u.get("inst") is not None else None
    if "스팩" in u["name"] and k not in NAME:
        k = None
    mine = k not in NAME   # 등급 밖 종목은 ★로 골랐을 때만 등록되므로 그 경우의 문구로 만든다
    tag = NAME.get(k, "내 청약")
    grade = NAME.get(k) or {"x": "패스", "c": "패스 권장", None: "수요예측 전"}[k]
    lkey = "L%d" % u["no"]
    if u.get("list") and u["list"] >= today and lkey not in st["done"]:
        res.append(dict(no=lkey, summary="[상장] %s 시초가 매도 (%s)" % (u["name"] + (" ★" if mine else ""), "/".join(u["brokers"])),
                        startTime=u["list"] + "T08:30:00", endTime=u["list"] + "T09:00:00", colorId=COLOR, reminders=[0], graded=k in NAME, ipo=u["no"],
                        description="상장일: 9시 시초가에 매도 (%s 등급%s)\n공모가 %s · 기관경쟁률 %s:1 · 확약 %.2f%%\n동시호가(08:30~09:00)에 시장가 매도 주문을 걸어 두면 시초가로 팔립니다.\n\nhttps://sunset-note.github.io/#ipo" % (
                            grade, ", 내 청약" if mine else "", "{:,}원".format(int(u["price"])) if u.get("price") else "?", "{:,.0f}".format(u["inst"] or 0), u.get("lock") or 0)))
    if u["sub"][1] < today or str(u["no"]) in st["done"]:
        continue
    lk = u.get("lock") or 0
    G = sorted(ro(x) for x in H if kind(x["inst"], x.get("lock")) == k) if k else []
    B = sorted(ro(x) for x in H if bk(INST_B, x["inst"]) == bk(INST_B, u["inst"]) and bk(LOCK_B, x.get("lock") or 0) == bk(LOCK_B, lk)) if k else []
    med = B[len(B) // 2] if B else None
    who = "나 + 가족" if FAMILY & set(u["brokers"]) else "나만"
    px = "{:,}원".format(int(u["price"])) if u.get("price") else "희망 " + (u.get("band") or "?")
    rf = u.get("refund")
    lines = [("추천: %s (%s)" % (NAME[k], ACT[k]) if k in NAME else "등급: %s · 내 청약(★)으로 고른 종목이라 등록" % grade) + (" · 점수 %d/100" % u["score"] + (" (확약 %.2f%%→%.2f%%로 늘기 전 %d점)" % (u["lock0"], u.get("lock") or 0, u["score0"]) if u.get("score0") is not None and u["score0"] != u["score"] else "") if u.get("score") is not None else ""),
             "청약 %s~%s 16:00 · %s · 청약 가능: %s · 공모가 %s · 증거금 %d%%" % (u["sub"][0][5:].replace("-", "/"), u["sub"][1][5:].replace("-", "/"), "/".join(u["brokers"]), who, px, u.get("margin") or 50),
             "기관경쟁률 %s:1 · 의무보유확약 %.2f%% · 상장 %s%s" % ("{:,.0f}".format(u["inst"]) if u.get("inst") is not None else "–", lk, (u.get("list") or "미정")[5:].replace("-", "/"), " · 환불 " + rf[5:].replace("-", "/") if rf else ""),
             ""]
    if G:
        lines.append("같은 등급 과거 %d건: 시초 중앙값 %+.0f%%, 공모가 밑 %d건" % (len(G), 100 * G[len(G) // 2], sum(v < 0 for v in G)))
    if med is not None:
        lines.append("같은 구간(기관·확약) 과거 %d건: 시초 중앙값 %+.0f%%" % (len(B), 100 * med))
    if k in ("p", "l") and med and rf:
        days = (dt.date.fromisoformat(rf) - dt.date.fromisoformat(u["sub"][1])).days
        lc, ic = 0.05 * days / 365, 0.025 * days / 365
        lines.append("마통 5%% 이자: 1억당 약 %s원 (%d일)" % ("{:,.0f}".format(1e8 * lc), days))
        lines.append("마감일 오후 경쟁률이 약 %s:1 아래면 마통 비례까지 이득, 약 %s:1 아래면 여유자금 비례 이득" % ("{:,.0f}".format(med / lc), "{:,.0f}".format(med / ic)))
    if k in ("p", "l"):   # 근거: 빗썸 2023-12~2026-10 일봉에서 김프가 매수선보다 1%p 이상 높으면 2일 안에 매수선에 닿은 날이 10% 안팎 이하
        lines.append("돈 쓰는 기준(마감일 김프, 횡보장 기준): 마통은 +0.5% 이상, 여유자금은 +1.5% 이상일 때만 · 아니면 김프 매수용으로 남겨 둠 (텔레그램 마감일 알림에 실시간 판단)")
    lines += ["", "https://sunset-note.github.io/#ipo"]
    start = dt.date.fromisoformat(u["sub"][0]); end = dt.date.fromisoformat(u["sub"][1])
    # 대출 등급은 마통 이자를 하루 아끼려고 마감일 14~15시에 청약한다: 15~16시 일정에 14시·15시 알림
    loan = k == "l"
    res.append(dict(no=str(u["no"]), ipo=u["no"], graded=k in NAME,
                    summary="[%s] %s %s (%s)" % (tag, u["name"] + (" ★" if mine and k in NAME else ""), "마통 청약 14~15시" if loan else "청약 마감", "/".join(u["brokers"])),
                    startTime=u["sub"][1] + ("T15:00:00" if loan else "T14:30:00"), endTime=u["sub"][1] + "T16:00:00", colorId=COLOR,
                    reminders=[60, 0] if loan else [(end - start).days * 1440 + 380, 0], description="\n".join(lines)))
# 텔레그램 공모주 알림(Cloudflare 중계 서버)용 요약: 청약·상장이 남은 종목
KEEP = ("no", "name", "sub", "list", "price", "band", "inst", "lock", "lock0", "score", "score0", "brokers", "refund", "margin", "market")
up = [dict({k: u.get(k) for k in KEEP}, kind=kind(u["inst"], u.get("lock")) if u.get("inst") is not None else None, spac="스팩" in u["name"])
      for u in D["upcoming"] if u["sub"][1] >= today or (u.get("list") or "") >= today]
print(json.dumps({"events": res, "up": up}, ensure_ascii=False))
