# RWA 주식토큰 LP 관찰(돈 안 넣는 모의 운용). 매일 아침 GitHub에서 돌아 rwa.json에 날짜별 결과를 쌓는다.
# 대상: Base의 Aerodrome Slipstream 주식토큰/USDC 풀(게이지 스테이킹, 보상 AERO).
# 가격: 풀 Swap 이벤트의 tick(체인 원본). 보상: 풀의 rewardGrowthGlobalX128(유동성 1단위당 누적 AERO)을 시간마다 읽어 계산.
# 규칙(텔레그램 글 명세 단순화): 원금 $3,000, 현재가 중심 B칸(1칸=tickSpacing 10=0.1%), 범위 밖 W분 연속이면 리밸,
#   평일 미국장(뉴욕 07:55~16:30) 전부 회수 후 USDC 보관, 주말은 계속. 비용 = 스왑 수수료(그때 풀 수수료) + 가스 $0.02.
# 빠진 것: 체결 지연·MEV, 하방 확장, AERO 보유 손익(시간 가격으로 바로 판다고 봄). 좁은 구간일수록 실제보다 좋게 나온다.
import json, math, os, sys, time, bisect, urllib.request
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, 'rwa.json')
POOLS = {'GOOGL': '0x16c70f04c3080a127486cdf5a4c33c066bbf47c3', 'AMZN': '0x532e0f46d1e528507fc9454d5847c231f23bddf6',
         'META': '0xd072410fa13d242e1d53721bcf7af02e3455dc96', 'AAPL': '0xf5fcb9cdafce67d50afef298f88e709d2b946ba6',
         'TSLA': '0x7a33000372f3f028f074182ccb9d16cbeefbf920', 'NVDA': '0xf668e21993f0acd7ab00bb1cfbaed0df28a3c8ec'}
AERO = '0x940181a94a35a4569e4529a3cdfb74e38fd98631'
CFG = [(b, w) for b in (1, 2, 4, 6, 10, 20) for w in (1, 5, 10)]
RPCS = ['https://base-rpc.publicnode.com', 'https://mainnet.base.org', 'https://base.drpc.org']
LOGRPC = 'https://base-rpc.publicnode.com'          # 50,000블록 getLogs 허용(약 11일 과거까지)
SEL = {'G': '0x57806ada', 'SL': '0x3ab04b20', 'S0': '0x3850c7bd', 'FEE': '0xddca3f43'}   # rewardGrowthGlobalX128, stakedLiquidity, slot0, fee
TOPIC = '0xc42079f94a6350d7e6235f29174924f928cc2ac818eb64fed8004e115fbcca67'          # Swap(address,address,int256,int256,uint160,uint128,int24)
UA = {'user-agent': 'Mozilla/5.0', 'accept': 'application/json'}
ET, KST = ZoneInfo('America/New_York'), timezone(timedelta(hours=9))
Q128, TS, GAS, CAP = 2 ** 128, 10, 0.02, 3000.0

# ---------- 수집 ----------
def post(url, body, timeout=60):
    return json.load(urllib.request.urlopen(urllib.request.Request(url, json.dumps(body).encode(), {'content-type': 'application/json', **UA}), timeout=timeout))

def rpc_batch(batch):
    for i in range(9):
        try:
            r = post(RPCS[i % len(RPCS)], batch)
            if isinstance(r, list) and all('result' in x for x in r): return {x['id']: x['result'] for x in r}
        except Exception: pass
        time.sleep(2 + i)
    raise RuntimeError('rpc batch')

def rpc1(url, m, params):
    for i in range(7):
        try:
            r = post(url, {'jsonrpc': '2.0', 'id': 1, 'method': m, 'params': params})
            if 'result' in r: return r['result']
        except Exception: pass
        time.sleep(2 + 2 * i)
    raise RuntimeError(m)

def head():
    h = rpc1(LOGRPC, 'eth_getBlockByNumber', ['latest', False]); return int(h['number'], 16), int(h['timestamp'], 16)

def blk_time(bn, bt):
    """블록 간격 실측(0.2초 근처)으로 시간<->블록 변환. 하루 전 블록 타임스탬프로 맞춘다."""
    b = bn - 432000; t = int(rpc1(LOGRPC, 'eth_getBlockByNumber', [hex(b), False])['timestamp'], 16)
    return (bt - t) / (bn - b)

def hourly(since, bn, bt, bs):
    hrs = list(range(since - since % 3600, bt, 3600)); calls = []
    for t in hrs:
        b = hex(bn - int((bt - t) / bs))
        for k, p in POOLS.items():
            for f in SEL: calls.append((t, k, f, {'to': p, 'data': SEL[f]}, b))
    vals = {}
    for i in range(0, len(calls), 100):
        ch = calls[i:i + 100]
        r = rpc_batch([{'jsonrpc': '2.0', 'id': j, 'method': 'eth_call', 'params': [c[3], c[4]]} for j, c in enumerate(ch)])
        for j, c in enumerate(ch): vals[(c[0], c[1], c[2])] = r[j]
        time.sleep(0.3)
    res = {k: [] for k in POOLS}
    for t in hrs:
        for k in POOLS:
            g, sl, s0, fe = (vals[(t, k, f)] for f in SEL)
            if not g or g == '0x': continue
            tk = int(s0[66:130], 16); tk -= (1 << 256) if tk >= 1 << 255 else 0
            res[k].append([t, int(g[:66], 16), int(sl[:66], 16), tk, int(fe[:66], 16)])
    return res

def swaps(pool, since, bn, bt, bs):
    out = []
    for a in range(bn - int((bt - since) / bs), bn + 1, 50000):
        for lg in rpc1(LOGRPC, 'eth_getLogs', [{'address': pool, 'topics': [TOPIC], 'fromBlock': hex(a), 'toBlock': hex(min(a + 49999, bn))}]):
            d = lg['data'][2:]; tk = int(d[256:320], 16); tk -= (1 << 256) if tk >= 1 << 255 else 0
            out.append([bt - (bn - int(lg['blockNumber'], 16)) * bs, tk])
        time.sleep(0.2)
    return out

def aero_px(since):
    def get(u):
        for i in range(6):
            try: return json.load(urllib.request.urlopen(urllib.request.Request(u, headers=UA), timeout=30))
            except Exception: time.sleep(8 * (i + 1))
        raise RuntimeError(u)
    d = get(f'https://api.geckoterminal.com/api/v2/networks/base/tokens/{AERO}/pools?page=1')['data'][0]
    tok = 'base' if d['relationships']['base_token']['data']['id'].split('_')[1].lower() == AERO else 'quote'
    L = get(f"https://api.geckoterminal.com/api/v2/networks/base/pools/{d['attributes']['address']}/ohlcv/hour?aggregate=1&limit=1000&token={tok}")['data']['attributes']['ohlcv_list']
    return {x[0] - x[0] % 3600: x[4] for x in L if x[0] >= since - 3600}

# ---------- 모의 운용 ----------
def off_hours(t):
    d = datetime.fromtimestamp(t, ET)
    if d.weekday() >= 5: return False
    m = d.hour * 60 + d.minute
    return 475 <= m < 990            # 07:55 ~ 16:30 (뉴욕)

def amounts(L, sp, sa, sb):
    if sp <= sa: return L * (sb - sa) / (sa * sb), 0.0
    if sp >= sb: return 0.0, L * (sb - sa)
    return L * (sb - sp) / (sp * sb), L * (sp - sa)

def series(T, t0, t1, step=10):
    out, i, last = [], 0, T[0][1]
    for g in range(t0 - t0 % step + step, t1, step):
        while i < len(T) and T[i][0] < g:
            if T[i][0] >= t0: out.append((T[i][0], T[i][1]))
            last = T[i][1]; i += 1
        out.append((g, last))
    return out

def run(P, H, A, B, W):
    Ht = [h[0] for h in H]; day = {}
    pos = None; out_since = None; prev_v = None
    for j in range(len(P) - 1):
        t, tick = P[j]; dt = P[j + 1][0] - t
        if dt <= 0: continue
        S = 100.0 / 1.0001 ** tick; sp = 1.0001 ** (tick / 2)          # USDC(6) / 주식토큰(8)
        hi = max(0, min(bisect.bisect_right(Ht, t) - 1, len(H) - 2)); h0, h1 = H[hi], H[hi + 1]
        fee = h0[4] / 1e6
        k = datetime.fromtimestamp(t, KST).strftime('%Y-%m-%d')
        d = day.setdefault(k, [0.0, 0.0, 0.0, 0, 0.0, 0.0])   # 보상, LP손익, 비용, 리밸, 범위안(분), 운용(분)
        if off_hours(t):
            if pos:
                a0, a1 = amounts(pos[0], sp, pos[1], pos[2]); v = a0 / 1e6 + a1 / 1e8 * S
                d[1] += v - prev_v; d[2] += a1 / 1e8 * S * fee + GAS; pos = None
            continue
        inr = pos is not None and pos[3] <= tick < pos[4]
        out_since = (out_since or t) if (pos is not None and not inr) else None
        if pos is None or (out_since is not None and t - out_since >= W * 60):
            if pos:
                a0, a1 = amounts(pos[0], sp, pos[1], pos[2]); v = a0 / 1e6 + a1 / 1e8 * S
                d[1] += v - prev_v; held = a0 / 1e6; d[3] += 1
            else: v = held = CAP
            lo = math.floor(tick / TS) * TS - (B // 2) * TS; up = lo + B * TS
            sa, sb = 1.0001 ** (lo / 2), 1.0001 ** (up / 2)
            u0, u1 = amounts(1.0, sp, sa, sb); L = v / (u0 / 1e6 + u1 / 1e8 * S)
            d[2] += abs(L * u0 / 1e6 - held) * fee + GAS
            pos = (L, sa, sb, lo, up); prev_v = v; out_since = None; inr = True
        a0, a1 = amounts(pos[0], sp, pos[1], pos[2]); v = a0 / 1e6 + a1 / 1e8 * S
        d[1] += v - prev_v; prev_v = v; d[5] += dt / 60
        if inr:
            d[4] += dt / 60
            rate = (h1[1] - h0[1]) / Q128 / max(1, h1[0] - h0[0]); sl = h0[2]
            d[0] += pos[0] * rate * dt * (sl / (sl + pos[0]) if sl > 0 else 0) / 1e18 * (A.get(h0[0]) or 0)
    return day

def main(days):
    bn, bt = head(); bs = blk_time(bn, bt)
    since = int(bt - days * 86400)
    print(f'블록 간격 {bs:.3f}초, {days}일', file=sys.stderr)
    A = aero_px(since); H = hourly(since, bn, bt, bs)
    first = datetime.fromtimestamp(since, KST).strftime('%Y-%m-%d'); today = datetime.fromtimestamp(bt, KST).strftime('%Y-%m-%d')
    try: J = json.load(open(OUT))
    except Exception: J = {}
    if J.get('cfg') != [list(c) for c in CFG]: J = {'cfg': [list(c) for c in CFG], 'pools': list(POOLS), 'days': {}}
    for k, p in POOLS.items():
        T = swaps(p, since, bn, bt, bs)
        print(k, len(T), len(H[k]), file=sys.stderr)
        if len(T) < 10 or len(H[k]) < 3: continue
        P = series(T, int(since), int(bt))
        res = [run(P, H[k], A, b, w) for b, w in CFG]
        for dk in res[0]:
            if dk <= first or dk >= today: continue      # 창의 첫날(시작 상태 미정)과 오늘(진행 중)은 버린다
            D = J['days'].setdefault(dk, {'r': {}, 'px': {}})
            D['r'][k] = [[round(x, 2) if isinstance(x, float) else x for x in r[dk]] if dk in r else None for r in res]
            day_t = [x for x in T if datetime.fromtimestamp(x[0], KST).strftime('%Y-%m-%d') == dk]
            if day_t: D['px'][k] = [round(100 / 1.0001 ** day_t[0][1], 2), round(100 / 1.0001 ** day_t[-1][1], 2)]
    for dk, D in J['days'].items():
        ps = [c for t, c in A.items() if datetime.fromtimestamp(t, KST).strftime('%Y-%m-%d') == dk]
        if ps: D['aero'] = [round(ps[0], 4), round(ps[-1], 4)]
    J['days'] = dict(sorted(J['days'].items())[-400:])
    J['at'] = bt
    json.dump(J, open(OUT, 'w'), ensure_ascii=False, separators=(',', ':'))
    print('저장', len(J['days']), '일', file=sys.stderr)

if __name__ == '__main__':
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 3.5)
