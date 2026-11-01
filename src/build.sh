#!/bin/bash
# GitHub 자동 실행용 페이지 빌드: 시세·공모주 데이터를 새로 받아 index.html과 cal.json(캘린더 후보)을 만든다.
# 상태 파일(src/ipo_track.json, src/float_cache.json)도 갱신되므로 함께 커밋한다.
set -e
S="$(cd "$(dirname "$0")" && pwd)"; R="$(dirname "$S")"; T=$(mktemp -d); trap 'rm -rf "$T"' EXIT
cd "$T"
# 38커뮤니케이션은 해외 서버(GitHub)를 막아서 Cloudflare 중계로 받는다
[ -n "$GITHUB_ACTIONS" ] && export FUND_BASE="https://sunset-fx.ghlckd01.workers.dev/f38/"
END=$(TZ=Asia/Seoul python3 -c "import datetime;print(datetime.date.today()-datetime.timedelta(1))")
python3 -I "$S/fetch.py" raw.json
python3 -I "$S/build.py" raw.json kimp.json "$END"
python3 -I "$S/fetch_h.py" rawh.json
python3 -I "$S/build_h.py" rawh.json kimp.json all.json
python3 -I "$S/ipo.py" ipo.json
# 공모주린이 유튜브 종합점수(A+~D): 자막 라이브러리를 임시 폴더에 받아 쓴다. 실패해도 빌드는 계속
python3 -m pip install -q --target "$T/py" youtube-transcript-api >/dev/null 2>&1 || true
YT_LIB="$T/py" python3 -I "$S/yt.py" ipo.json || echo "yt: 건너뜀"
# 미국 ETF 백테스터용 2004년 이전 원/달러(FRED DEXKOUS). 실패하면 빈 배열
curl -s -m 60 "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DEXKOUS" > fred.csv || true
python3 -I -c "
import json
try: r=[[d,round(float(v),2)] for d,v in (l.split(',') for l in open('fred.csv').read().splitlines()[1:]) if d<'2004-01-01' and v not in ('','.')]
except Exception: r=[]
open('fxold.json','w').write(json.dumps(r,separators=(',',':')))"
python3 -I -c "import sys;t=open(sys.argv[1]).read();d=open(sys.argv[2]).read();i=open(sys.argv[3]).read().replace('</','<\\/');f=open(sys.argv[5]).read();open(sys.argv[4],'w').write(t.replace('__DATA__',d).replace('__IPO__',i).replace('__FXOLD__',f))" "$S/template.html" all.json ipo.json page.html fxold.json
{ printf '<!doctype html>\n<html lang="ko">\n<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover"><link rel="icon" href="favicon.svg" type="image/svg+xml"><link rel="icon" href="favicon-32.png" sizes="32x32" type="image/png"><link rel="apple-touch-icon" href="apple-touch-icon.png"><meta name="theme-color" content="#7f6bb8"></head>\n<body style="margin:0">\n'; cat page.html; printf '\n</body>\n</html>\n'; } > "$R/index.html"
python3 -I "$S/cal.py" ipo.json > "$R/cal.json"
echo "빌드 완료: $END까지"
