# 공모주린이(공모주투자의법칙) 유튜브 '분석과 종합점수' 영상 끝에서 말하는 등급(A+~D)을 자막에서 뽑아 ipo.json 종목에 붙인다.
# 새 영상은 채널 동영상 페이지에서 찾고, 한 번 뽑은 등급은 ipo_track.json의 "_yt"에 저장해 다시 받지 않는다(실패는 3번까지 재시도).
import json, os, re, sys, datetime as dt, urllib.request

sys.path.insert(0, os.environ.get("YT_LIB", ""))
CH = "UCstq1xNCuEIR43dM3CMop3g"
TRACK = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ipo_track.json")
LET = {"A": "A", "에이": "A", "B": "B", "비": "B", "C": "C", "씨": "C", "시": "C", "D": "D", "디": "D"}


def grade(text):
    g = None
    for m in re.finditer(r"종합\s*점수는?\s*([A-Da-d]|에이|비|씨|시|디)\s*(플러스|마이너스|\+|-)?\s*(?:입니다|이에요|예요|로|으로|라고|를|점)", text):
        g = LET[m.group(1).upper() if len(m.group(1)) == 1 else m.group(1)] + {"플러스": "+", "+": "+", "마이너스": "-", "-": "-"}.get(m.group(2) or "", "")
    return g


def norm(s):
    return re.sub(r"\(.*?\)|\s|주식회사|㈜", "", s or "")


def main(path):
    d = json.load(open(path))
    track = json.load(open(TRACK)) if os.path.exists(TRACK) else {}
    yt = track.setdefault("_yt", {})
    # 유튜브 RSS가 자주 404/500을 내서 채널 '동영상' 페이지에서 제목과 영상 ID를 읽는다(제목 바로 앞의 videoId가 그 영상)
    feed, today = [], dt.date.today().isoformat()
    try:
        h = urllib.request.urlopen(urllib.request.Request("https://www.youtube.com/channel/%s/videos" % CH, headers={"User-Agent": "Mozilla/5.0", "Accept-Language": "ko"}), timeout=30).read().decode()
        for m in re.finditer(r'"title":\{"content":"([^"]+)"', h):
            v = re.findall(r'"videoId":"([\w-]{11})"', h[max(0, m.start() - 8000):m.start()])
            if v and v[-1] not in [f[0] for f in feed]:
                feed.append((v[-1], json.loads('"%s"' % m.group(1)), today))
    except Exception as e:
        print("yt: 채널 페이지 실패", e)
    api = None
    for vid, title, day in feed:
        m = re.match(r"\[공모주\]\s*(.+?)\s*분석과\s*종합점수", title)
        if not m:
            continue
        r = yt.setdefault(vid, {"n": m.group(1), "d": day, "try": 0})
        if r.get("g") or r["try"] >= 3:
            continue
        r["try"] += 1
        try:
            if api is None:
                from youtube_transcript_api import YouTubeTranscriptApi
                api = YouTubeTranscriptApi()
            r["g"] = grade(" ".join(s.text for s in api.fetch(vid, languages=["ko"])))
            print("yt:", r["n"], r["g"])
        except Exception as e:
            print("yt: 자막 실패", r["n"], type(e).__name__, str(e)[:200])
    old = (dt.date.today() - dt.timedelta(120)).isoformat()
    for k in [k for k, r in yt.items() if r["d"] < old]:
        del yt[k]
    json.dump(track, open(TRACK, "w"), ensure_ascii=False)
    by = {norm(r["n"]): (r["g"], k) for k, r in sorted(yt.items(), key=lambda t: t[1]["d"]) if r.get("g")}
    for u in d["upcoming"] + d["listed"]:
        n = norm(u["name"])
        hit = by.get(n)   # 이름이 정확히 같을 때만: '영광'과 '영광와이케이엠씨'는 다른 종목
        if hit:
            u["yt"] = {"g": hit[0], "v": hit[1]}
    json.dump(d, open(path, "w"), ensure_ascii=False, separators=(",", ":"))


if __name__ == "__main__":
    main(sys.argv[1])
