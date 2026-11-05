# 거래소 예치 상품 수집: 바이낸스·OKX·바이비트·비트겟·게이트의 스테이블코인 상품을 키 없이 받아 earn.json으로 합친다.
# 거래소 하나가 실패하면 그 거래소만 지난번 값을 유지한다(at에 마지막 성공 시각).
import json, sys, time, urllib.request

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
            d1 = v[:24]
            a = sum(v) / len(v)
            out.append(dict(c=c, n='심플 언 자유', a=pct(a), t=[[None, pct(a)]], l=0, o=f'변동 금리, {len(v) // 24}일 평균 (지난 24시간 {sum(d1) / len(d1):.2f}%)'))
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
                out.append(dict(c=c, n=f'고정 {days}일' if days else '자유', a=max(r for _, r in t), t=t, l=days, q=p.get('status') != 2))
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
    with open(path, 'w') as f:
        json.dump(res, f, ensure_ascii=False, separators=(',', ':'))

main(sys.argv[1])
