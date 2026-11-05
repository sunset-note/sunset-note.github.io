# 거래소 예치 상품 수집: 바이낸스·OKX·바이비트·비트겟·게이트의 스테이블코인 상품을 키 없이 받아 earn.json으로 합친다.
# 거래소 하나가 실패하면 그 거래소만 지난번 값을 유지한다(at에 마지막 성공 시각).
import calendar, html, json, re, sys, time, urllib.request

COINS = ['USDT', 'USDC', 'USD1', 'RLUSD', 'FDUSD', 'USDE', 'USDG', 'USDGO', 'USDD', 'PYUSD', 'DAI', 'U', 'BFUSD', 'RWUSD']
UA = {'User-Agent': 'Mozilla/5.0', 'Accept': 'application/json'}

def get(url, body=None):
    h = dict(UA)
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        h['Content-Type'] = 'application/json'
    with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h), timeout=25) as r:
        return json.load(r)

def pct(v):
    return round(float(v), 2)

def binance():
    out = []
    for c in COINS:
        d = get(f'https://www.binance.com/bapi/earn/v1/friendly/finance-earn/simple-earn/homepage/details?asset={c}&pageSize=20&current=1')
        for x in d['data']['list']:
            if x['asset'] != c:
                continue
            for p in x['productDetailList']:
                if p.get('status') != 'ENABLE':
                    continue
                days = int(p.get('duration') or 0)
                if p['productType'] == 'LENDING_FLEXIBLE':
                    base = float(p.get('marketApr') or 0)
                    t = [[float(o['endAmount']), pct((float(o['ratio']) + base) * 100)] for o in (p.get('apyTierOption') or [])]
                    t.append([None, pct(base * 100)])
                    out.append(dict(c=c, n='심플 언 자유', a=pct(float(p['apy']) * 100), t=t, l=0, v=bool(p.get('vip')), s=bool(p.get('sellOut'))))
                elif days:
                    out.append(dict(c=c, n=f'심플 언 {days}일', a=pct(float(p['apy']) * 100), t=[[None, pct(float(p['apy']) * 100)]], l=days, v=bool(p.get('vip')), s=bool(p.get('sellOut'))))
        time.sleep(.2)
    return out

def okx():
    out = []
    for c in COINS:
        try:
            r = get(f'https://www.okx.com/api/v5/finance/savings/lending-rate-history?ccy={c}&limit=100')['data']
        except Exception:      # OKX에 없는 코인은 400을 준다
            continue
        rows = list(r)
        if c in ('USDT', 'USDC'):           # 변동 금리라 30일 평균을 함께 낸다
            while len(rows) < 720 and r:
                r = get(f'https://www.okx.com/api/v5/finance/savings/lending-rate-history?ccy={c}&limit=100&after={r[-1]["ts"]}')['data']
                rows += r
                time.sleep(.2)
        if rows:
            v = [float(x['lendingRate']) * 100 for x in rows[:720]]
            avg = lambda n: pct(sum(v[:n]) / len(v[:n]))
            now_r = pct(v[0])
            # 매시간 바뀌는 금리: 지금 금리와 지난 1·7·30일 평균
            out.append(dict(c=c, n='심플 언 자유', a=now_r, t=[[None, now_r]], l=0, o=f'매시간 변동 · 1일 {avg(24)}%, 7일 {avg(168)}%, 30일 {avg(720)}%', p=[now_r, avg(168), avg(720)]))
        time.sleep(.2)
    for cur in get('https://www.okx.com/priapi/v1/earn/simple-earn/all-products?limit=200&offset=0&type=all')['data']['allProducts']['currencies']:
        c = cur['investCurrency']['currencyName']
        if c not in COINS:
            continue
        for p in cur['products']:
            rate = p['rate'].get('rateNum', {}).get('value') or []
            if not rate or p.get('purchaseStatus') != 1:
                continue
            a = pct(max(float(x) for x in rate))
            days = int(p['term']['value']) if p['term'].get('type') == 'DAY' and p['term'].get('value', 0) > 1 else 0
            b = p.get('bonusDescription') or ''
            new = 'new user' in b.lower()
            out.append(dict(c=c, n=f'고정 {days}일' if days else ('신규 보너스' if new else '심플 언'), a=a, t=[[None, a]], l=days, w=new, o=('신규 가입자만, 180일' if new else b)))
    return out

def bybit():
    out = []
    for cat, label in (('FlexibleSaving', '이지 언 자유'), ('OnChain', '온체인 언')):
        for x in get(f'https://api.bybit.com/v5/earn/product?category={cat}')['result']['list']:
            if x['coin'] not in COINS or x.get('status') != 'Available':
                continue
            a = pct(x['estimateApr'].rstrip('%'))
            t = []
            for o in x.get('tierAprDetails') or []:
                t.append([None if o['max'] == '-1' else float(o['max']), pct(o['estimateApr'].rstrip('%'))])
            if not t:
                t = [[None, a]]
            head = max(r for _, r in t)
            days = int(x.get('term') or 0)
            sw = x.get('swapCoin') or ''
            out.append(dict(c=x['coin'], n=label + (f' {days}일' if days else ''), a=head, t=t, l=days, e=cat == 'OnChain', o=(f'{sw}로 바꿔 운용' if sw else '')))
    return out

def bitget():
    out = []
    for cur in get('https://www.bitget.com/v1/finance/savings/product/list', {'pageNo': 1, 'pageSize': 500})['data']:
        c = cur['coinName']
        if c not in COINS:
            continue
        for bl in cur['bizLineProductList']:
            for p in bl['productList']:
                if not p.get('visibleApy', True):
                    continue
                t = [[float(o['maxStepValue']), pct(o['apy'])] for o in p['apyList']]
                if not t:
                    continue
                days = int(p.get('period') or 0) if p.get('periodType') == 2 else 0
                vip = p.get('productLevel') == 2                 # 화면의 VIP 줄
                new = not vip and p.get('annualizedRateType') == 1   # 바커가 신규로 표시하는 12% 상품과 같은 값
                kind = f'고정 {days}일' if days else '자유'
                out.append(dict(c=c, n=('VIP ' if vip else '신규 ' if new else '') + kind, a=max(r for _, r in t), t=t, l=days, v=vip, w=new, q=p.get('status') != 2))
    return out

def gate():
    out = []
    uni = {x['currency']: float(x['est_rate']) for x in get('https://api.gateio.ws/api/v4/earn/uni/rate')}
    for c in COINS:
        if c in uni and uni[c] > 0:
            a = pct(uni[c] * 100)
            out.append(dict(c=c, n='자유 대출', a=a, t=[[None, a]], l=0, o='변동 금리'))
    for c in COINS:
        page = 1
        while page <= 10:
            d = get(f'https://api.gateio.ws/api/v4/earn/fixed-term/product?page={page}&limit=100&asset={c}')['data']
            for x in d['list']:
                # 목록에 지난 이벤트가 판매 중으로 남아 있어 상시 상품(show_status 2, 전체 대상)만 쓴다
                if x.get('status') != 2 or x.get('show_status') != 2 or x.get('is_for_all_user') != 1 or x.get('min_vip'):
                    continue
                a = pct(float(x['year_rate']) * 100)
                out.append(dict(c=c, n=f"고정 {x['lock_up_period']}일", a=a, t=[[None, a]], l=int(x['lock_up_period'])))
            if page * 100 >= int(d.get('total', 0)):
                break
            page += 1
            time.sleep(.2)
    return out

# ---- 이벤트 공지: 종료일과 조건 ----
MONTH = {m: i + 1 for i, m in enumerate('January February March April May June July August September October November December'.split())}
DATE = r'(?:\d{4}-\d\d-\d\d(?:[ T]\d\d:\d\d(?::\d\d)?)?|\d{1,2} [A-Z][a-z]+ \d{4}(?:, *\d\d:\d\d)?|[A-Z][a-z]+ \d{1,2}, \d{4}(?:,? *\d\d:\d\d)?)'
PERIOD = re.compile(r'[Pp]eriod:? *(' + DATE + r')[^0-9]{0,20}?(?:to|–|-|—)[^0-9]{0,6}(' + DATE + r')')

def stamp(t):
    m = re.match(r'(\d{4})-(\d\d)-(\d\d)(?:[ T](\d\d):(\d\d))?', t)
    if m:
        y, mo, d, h, mi = m.groups()
    else:
        m = re.match(r'(\d{1,2}) ([A-Z][a-z]+) (\d{4})(?:, *(\d\d):(\d\d))?', t)
        if m and m.group(2) in MONTH:
            d, mo, y, h, mi = m.groups()
        else:
            m = re.match(r'([A-Z][a-z]+) (\d{1,2}), (\d{4})(?:,? *(\d\d):(\d\d))?', t)
            if not m or m.group(1) not in MONTH:
                return None
            mo, d, y, h, mi = m.groups()
        mo = MONTH[mo]
    return calendar.timegm((int(y), int(mo), int(d), int(h or 23), int(mi or 59), 59))

def ends(text, now=None):
    now = now or time.time()
    # 공지 맨 앞의 기간이 본 행사다. 뒤쪽 부대 행사나 주간 구간에 끌려가지 않게 앞에서부터 본다
    v = [x for x in (stamp(b) for _, b in PERIOD.findall(text)) if x and x > now]
    return v[0] if v else None

def conds(title, text):
    both = title + ' ' + text
    out = []
    if re.search(r'new users?\b|newly registered', both, re.I):
        out.append('신규 전용' if re.search(r'new users?', title, re.I) else '신규 혜택 있음')
    if re.search(r'holding VIP status|VIP users? only|VIP-only|exclusive(?:ly)? (?:to|for) VIP', both, re.I):
        out.append('VIP 전용')
    elif 'VIP' in both:
        out.append('VIP 우대')
    if re.search(r'net deposit', both, re.I):
        out.append('순입금 조건')
    if re.search(r'trading volume', text, re.I):
        out.append('거래량 조건')
    m = re.search(r'(?:hold(?: minimally| at least)?|minimum (?:holding|balance) of) ([\d,]{4,}) (?:USDT|USDC|USD)', text, re.I)
    if m:
        out.append(f'최소 {m.group(1)} 보유')
    if re.search(r'first[- ]come', text, re.I):
        out.append('선착순')
    return out

def strip(h):
    return re.sub(r'\s+', ' ', html.unescape(re.sub(r'<script.*?</script>|<style.*?</style>|<[^>]+>', ' ', h, flags=re.S)))

def nodes(n, o):
    if isinstance(n, dict):
        if n.get('node') == 'text':
            o.append(n.get('text', ''))
        for c in n.get('child', []):
            nodes(c, o)
    return o

def coins_in(t):
    return [c for c in COINS if re.search(r'(?<![A-Za-z0-9])' + c + r'(?![A-Za-z0-9])', t)]

def bn_live(keep, now):
    out = []
    for v in keep.values():
        fut = [x for x in v.get('ends', []) if x > now]
        if fut and v['c']:
            e = {k: w for k, w in v.items() if k != 'ends'}
            # Hold 행사는 주간 구간을 나열하므로 마지막 날이 종료일이다
            e['end'] = fut[-1] if re.match(r'hold\b', v['ti'], re.I) else fut[0]
            out.append(e)
    return out

def ev_binance(now, cache):
    # 공지 본문은 한 번만 읽고 결과를 저장한다(요청이 많으면 429로 막힌다)
    base = 'https://www.binance.com/bapi/composite/v1/public/cms/article'
    skip = re.compile(r'referral|p2p|cashback|leaderboard|tournament|learn |brazil|latam|cis |mena|loan|\btrade\b', re.I)
    keep = {}
    for page in (1, 2, 3):
        for a in get(f'{base}/list/query?type=1&pageNo={page}&pageSize=50&catalogId=93')['data']['catalogs'][0]['articles']:
            t = a['title']
            if now - a['releaseDate'] / 1000 > 60 * 86400 or skip.search(t) or not re.search(r'earn|flexible|locked|\bapr\b|\bapy\b|\bhold\b', t, re.I):
                continue
            code = a['code']
            if code in cache:
                keep[code] = cache[code]
                continue
            try:
                body = get(f'{base}/detail/query?articleCode={code}')['data']['body']
            except Exception as e:
                print('바이낸스 공지 중단:', repr(e)[:80])
                cache.update(keep)
                return bn_live(keep, now), keep
            text = re.sub(r'\s+', ' ', html.unescape(' '.join(nodes(json.loads(body), []))))
            coins = coins_in(t) or sorted(set(re.findall(r'\b(' + '|'.join(COINS) + r') Flexible', text)))
            keep[code] = dict(x='binance', ti=t, c=coins, ends=[x for x in (stamp(b) for _, b in PERIOD.findall(text)) if x], cd=conds(t, text), url='https://www.binance.com/en/support/announcement/' + code, bon=sorted(set(re.findall(r'\+? ?(\d+(?:\.\d+)?)% Bonus', text))))
            time.sleep(.6)
    return bn_live(keep, now), keep

def ev_okx(now):
    out = []
    for page in (1, 2, 3):
        for a in get(f'https://www.okx.com/api/v5/support/announcements?page={page}&annType=latest-events')['data'][0]['details']:
            t = a['title']
            held = [w for w in re.findall(r'hold (\w+)', t, re.I) if w in COINS]
            flash = re.search(r'flash earn', t, re.I) and not held
            if not (held or flash or re.search(r'simple earn|savings', t, re.I)):
                continue
            if re.search(r'trade[- ]to[- ]earn', t, re.I):
                continue
            text = strip(urllib.request.urlopen(urllib.request.Request(a['url'], headers=UA), timeout=25).read().decode('utf8', 'ignore'))
            end = ends(text)
            if end and end > now:
                dep = sorted(set(re.findall(r'\b(BTC|ETH|OKB|XRP|SOL|USDT|USDC)\b', re.split(r'\bshare\b', re.sub(r'\(.*?\)', '', t), flags=re.I)[0])))
                if flash:
                    m = re.search(r'share ([\d,]+ \w+)', t, re.I)
                    ps = PERIOD.findall(text)
                    out.append(dict(x='okx', k='pool', ti=t, c=dep, end=end, start=stamp(ps[0][0]) if ps else None, cd=conds(t, text), url=a['url'], rw=m.group(1) if m else ''))
                else:
                    out.append(dict(x='okx', ti=t, c=held or coins_in(t), end=end, cd=conds(t, text), url=a['url']))
            time.sleep(.2)
    return out

def ev_bitget(now):
    # PoolX(런치풀): status 2가 진행 중
    d = get('https://www.bitget.com/v1/finance/poolx/product/page/list/new', {'pre': '0', 'pageNo': 1, 'pageSize': 20, 'status': 2})['data']['items']
    px = {x['symbol']: float(x['lastPr']) for x in get('https://api.bitget.com/api/v2/spot/market/tickers')['data'] if x.get('lastPr')}
    price = lambda c: 1.0 if c in COINS else px.get(c + 'USDT')
    out = []
    for p in d:
        start, end = int(p['startTime']) / 1000, int(p['endTime']) / 1000
        days = max((end - start) / 86400, 1e-9)
        pools = []
        for q in p['productSubList']:
            stake, rew = float(q['totalStakedAmount'] or 0), float(q['totalRewards'] or 0)
            a, b = price(p['productCoinName']), price(q['productSubCoinName'])
            exp = round(rew * a / (stake * b) * 365 / days * 100, 2) if a and b and stake else None
            pools.append(dict(c=q['productSubCoinName'], ap=float(q['apr'] or 0), exp=exp, rew=rew, st=stake, cap=float(q['userMaxAmount'] or 0), v=bool(q.get('vipPool'))))
        out.append(dict(x='bitget', k='pool', ti=f"{p['productCoinName']} PoolX", rc=p['productCoinName'], rw=f"{float(p['totalRewards']):,.0f} {p['productCoinName']}", c=[q['c'] for q in pools], end=end, start=start, cd=[], url=p['productDetailLinkUrl'].split('?')[0], pools=pools))
    return out

def events(old, cache, now):
    res = []
    for name, fn in (('binance', lambda: ev_binance(now, cache)), ('okx', lambda: ev_okx(now)), ('bitget', lambda: ev_bitget(now))):
        try:
            v = fn()
            if name == 'binance':
                v, cache = v
            res += v
            print(name, '이벤트 성공', len(v), '개')
        except Exception as e:
            print(name, '이벤트 실패:', repr(e)[:200])
            res += [x for x in old if x['x'] == name and x['end'] > now]
    return res, cache

def link_events(res, evs):
    # 바이낸스 추가 금리 구간을 같은 코인·같은 %를 적은 공지와 잇는다
    for it in res.get('binance', {}).get('items', []):
        if len(it['t']) < 2:
            continue
        extra = it['t'][0][1] - it['t'][-1][1]
        for e in evs:
            if e['x'] == 'binance' and it['c'] in e['c'] and any(abs(float(b) - extra) < .02 for b in e.get('bon', [])):
                it['end'], it['cd'], it['url'] = e['end'], e['cd'], e['url']
                break

def main(path):
    try:
        old = json.load(open(path))
    except Exception:
        old = {}
    res = {}
    now = int(time.time())
    for name, label, fn in (('binance', '바이낸스', binance), ('okx', 'OKX', okx), ('bybit', '바이비트', bybit), ('bitget', '비트겟', bitget), ('gate', '게이트', gate)):
        try:
            items = fn()
            if not items:
                raise ValueError('상품 0개')
            seen, uniq = set(), []
            for it in items:
                key = (it['c'], it['n'], it['a'], it['l'])
                if key not in seen:
                    seen.add(key)
                    uniq.append(it)
            res[name] = dict(at=now, label=label, items=uniq)
            print(name, '성공', len(uniq), '개')
        except Exception as e:
            print(name, '실패:', repr(e)[:200])
            if name in old:
                res[name] = old[name]
    evs, cache = events(old.get('_ev', []), {k: v for k, v in old.get('_bn', {}).items() if 'ends' in v}, now)
    link_events(res, evs)
    res['_ev'] = evs
    res['_bn'] = cache
    with open(path, 'w') as f:
        json.dump(res, f, ensure_ascii=False, separators=(',', ':'))

main(sys.argv[1])
