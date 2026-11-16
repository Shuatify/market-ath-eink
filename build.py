#!/usr/bin/env python3
"""Render a static 800x480 ETF price-vs-ATH page using unofficial Yahoo data.

The current price can be a recent five-minute bar; the ATH reference is based
ONLY on previous completed DAILY closes. Today's provisional intraday high
never changes the historical ATH reference.
"""
from __future__ import annotations

import argparse
import html
import json
import math
from dataclasses import dataclass
from datetime import date, datetime, timedelta, time
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import exchange_calendars as xcals

ET = ZoneInfo('America/New_York')
SYMBOLS = (
    ('VOO', 'S&P 500 ETF'),
    ('QQQ', 'NASDAQ-100 ETF'),
    ('QLD', '2x NASDAQ-100'),
    ('SMH', 'SEMICONDUCTORS'),
)
OUT = Path(__file__).resolve().parent / 'site'


@dataclass(frozen=True)
class Card:
    ticker: str
    label: str
    price: float
    reference_ath: float
    ath_date: date
    change: float
    days: int
    is_breakout: bool
    price_time: datetime
    kind: str  # 5M BAR / DAILY CLOSE / PRIOR CLOSE


def compute_card(ticker: str, label: str, previous_daily: list[tuple[date, float]],
                 price: float, price_time: datetime, kind: str) -> Card:
    """Compare a current price to closes strictly earlier than price_time date."""
    if not previous_daily or previous_daily != sorted(previous_daily):
        raise ValueError(f'{ticker}: missing or unsorted previous daily closes')
    if len({d for d, _ in previous_daily}) != len(previous_daily):
        raise ValueError(f'{ticker}: duplicated history dates')
    if any(not math.isfinite(p) or p <= 0 for _, p in previous_daily):
        raise ValueError(f'{ticker}: invalid daily close')
    if not math.isfinite(price) or price <= 0 or price_time.tzinfo is None:
        raise ValueError(f'{ticker}: invalid quote')
    quote_day = price_time.astimezone(ET).date()
    if previous_daily[-1][0] >= quote_day:
        raise ValueError(f'{ticker}: ATH reference includes quote day')
    ath = max(v for _, v in previous_daily)
    ath_day = max(d for d, v in previous_daily if math.isclose(v, ath, rel_tol=1e-10, abs_tol=1e-9))
    delta = 100 * (price / ath - 1)
    breakout = delta > 1e-9
    days = (quote_day - ath_day).days
    # Touching the old closing ATH today means age zero, without a breakout.
    if math.isclose(price, ath, rel_tol=1e-10, abs_tol=1e-9):
        days = 0
        delta = 0.0
    return Card(ticker, label, price, ath, ath_day, delta, days,
                breakout, price_time.astimezone(ET), kind)


def exchange_session(now: datetime):
    cal = xcals.get_calendar('XNYS')
    d = pd.Timestamp(now.astimezone(ET).date())
    if not cal.is_session(d):
        return None
    return (cal.session_open(d).to_pydatetime().astimezone(ET),
            cal.session_close(d).to_pydatetime().astimezone(ET))


def market_window(now: datetime) -> bool:
    """Runs only for genuine NYSE sessions, also on early-close days."""
    window = exchange_session(now)
    if not window:
        return False
    opened, closed = window
    local = now.astimezone(ET)
    return opened <= local <= closed + timedelta(minutes=30)


def get_data(ticker: str, label: str, now: datetime) -> Card:
    import yfinance as yf
    tk = yf.Ticker(ticker)
    daily = tk.history(period='max', interval='1d', auto_adjust=False,
                       actions=False, prepost=False, timeout=25, raise_errors=True)
    if daily is None or daily.empty or 'Close' not in daily:
        raise RuntimeError(f'{ticker}: Yahoo returned no daily history')
    closes = []
    today = now.astimezone(ET).date()
    for idx, row in daily.iterrows():
        day = idx.date()
        val = float(row['Close'])
        if day <= today and math.isfinite(val) and val > 0:
            closes.append((day, val))
    if len(closes) < 2 or closes != sorted(closes):
        raise RuntimeError(f'{ticker}: incomplete or invalid daily history')
    if (today - closes[-1][0]).days > 7:
        raise RuntimeError(f'{ticker}: daily history is stale')

    window = exchange_session(now)
    active = bool(window and window[0] <= now.astimezone(ET) <= window[1] + timedelta(minutes=30))
    is_final_close = bool(window and now.astimezone(ET) >= window[1] + timedelta(minutes=20)
                          and closes[-1][0] == today)
    if is_final_close or not active:
        day, price = closes[-1]
        if day == today and active and is_final_close:
            # First final close of the session is only confirmed when Yahoo
            # publishes that daily bar after market close.
            kind = 'DAILY CLOSE'
        else:
            kind = 'DAILY CLOSE'
        previous = [(d, v) for d, v in closes if d < day]
        if not previous:
            raise RuntimeError(f'{ticker}: no prior ATH reference')
        stamp = datetime.combine(day, time(16, 0), tzinfo=ET)
        return compute_card(ticker, label, previous, price, stamp, kind)

    # During market hours: use the newest regular-session 5m bar, including
    # values delayed by Yahoo.  Ignore any developing daily bar from today.
    intra = tk.history(period='5d', interval='5m', auto_adjust=False,
                       actions=False, prepost=False, timeout=25, raise_errors=True)
    candidates = []
    if intra is not None and not intra.empty:
        for idx, row in intra.iterrows():
            moment = idx.to_pydatetime().astimezone(ET)
            val = float(row['Close'])
            if (moment.date() == today and window[0] <= moment < window[1]
                    and moment <= now.astimezone(ET) and math.isfinite(val) and val > 0):
                candidates.append((moment, val))
    previous = [(d, v) for d, v in closes if d < today]
    if not previous:
        raise RuntimeError(f'{ticker}: missing completed daily closes')
    if candidates:
        stamp, price = candidates[-1]
        # If Yahoo has no useful intraday updates for more than 60 minutes,
        # fail instead of silently making yesterday's price look current.
        if now.astimezone(ET) - stamp > timedelta(minutes=60) and now.astimezone(ET) >= window[0] + timedelta(minutes=65):
            raise RuntimeError(f'{ticker}: intraday bar older than 60 minutes')
        return compute_card(ticker, label, previous, price, stamp, '5M BAR')
    # At the opening bell, prior day is the only known price, clearly labeled.
    if now.astimezone(ET) < window[0] + timedelta(minutes=50):
        day, price = previous[-1]
        prev_prev = previous[:-1]
        return compute_card(ticker, label, prev_prev, price,
                            datetime.combine(day, time(16), tzinfo=ET), 'PRIOR CLOSE')
    raise RuntimeError(f'{ticker}: no intraday quote for today')


def demo_cards() -> list[Card]:
    d = date(2026, 11, 13)
    t = datetime(2026, 11, 13, 14, 15, tzinfo=ET)
    return [
        compute_card('VOO', 'S&P 500 ETF', [(d-timedelta(days=49), 610)], 585.6, t, '5M BAR'),
        compute_card('QQQ', 'NASDAQ-100 ETF', [(d-timedelta(days=35), 600)], 492.0, t, '5M BAR'),
        compute_card('QLD', '2x NASDAQ-100', [(d-timedelta(days=21), 120)], 108.0, t, '5M BAR'),
        compute_card('SMH', 'SEMICONDUCTORS', [(d-timedelta(days=83), 350)], 367.5, t, '5M BAR'),
    ]


def render(cards: list[Card], demo: bool = False) -> str:
    if len(cards) != 4:
        raise ValueError('Expected exactly four cards')
    pieces = []
    for c in cards:
        pct = f'{c.change:+.1f}%' if c.change > 0 else f'{c.change:.1f}%'
        if c.is_breakout:
            status = f'ABOVE PRIOR<br>CLOSING HIGH'
            since = f'BREAKOUT · {c.days}d SINCE PRIOR ATH'
        else:
            status = 'AT CLOSING HIGH' if c.days == 0 and c.change == 0 else 'BELOW CLOSING HIGH'
            since = f'{c.days}d SINCE ATH'
        pieces.append(f'''<article class="card">
          <div class="card-header"><div><div class="ticker">{html.escape(c.ticker)}</div>
          <div class="asset">{html.escape(c.label)}</div></div>
          <div class="price"><span class="dollar">$</span>{c.price:,.2f}</div></div>
          <div class="change-row"><strong class="delta">{pct}</strong><div class="status">{status}</div></div>
          <div class="card-footer"><span>ATH <strong>${c.reference_ath:,.2f}</strong> · {c.ath_date.isoformat()}</span>
          <span><strong>{since}</strong></span></div>
        </article>''')
    first_timestamp = min(c.price_time for c in cards)
    many_times = len({c.price_time for c in cards}) > 1
    label = 'EARLIEST SOURCE' if many_times else 'AS OF'
    stamp = first_timestamp.strftime('%Y-%m-%d %H:%M ET')
    demo_label = '<div class="demo">DEMO · SAMPLE DATA</div>' if demo else ''
    all_intraday = all(c.kind == '5M BAR' for c in cards)
    source = 'YAHOO · 5M BARS · DELAYED / BEST EFFORT' if all_intraday else 'YAHOO · DAILY / INTRADAY · BEST EFFORT'
    return f'''<!doctype html>
<html lang="en"><head><meta charset="UTF-8"><meta name="viewport" content="width=800,initial-scale=1,minimum-scale=1,maximum-scale=1"><meta http-equiv="Cache-Control" content="no-cache"><title>Market / All-Time Highs</title>
<style>
  * {{ box-sizing:border-box; }}
  html,body {{ padding:0;margin:0;width:800px;height:480px;background:#fff;color:#111;overflow:hidden; }}
  body {{ font-family:Arial,Helvetica,sans-serif;-webkit-font-smoothing:antialiased; }}
  main {{ width:800px;height:480px;padding:20px 22px 12px;display:grid;grid-template-rows:53px 1fr 27px;gap:12px;position:relative; }}
  header {{ display:flex;align-items:center;justify-content:space-between;border-bottom:3px solid #111;padding-bottom:8px; }}
  h1 {{ font-size:27px;line-height:1;margin:0;font-weight:800;letter-spacing:.35px; }}
  .head-meta {{ text-align:right;font-size:12px;font-weight:700;letter-spacing:.6px;line-height:1.4; }}
  .grid {{ display:grid;grid-template-columns:repeat(2,1fr);grid-template-rows:repeat(2,1fr);gap:12px;min-height:0; }}
  .card {{ border:2px solid #111;padding:11px 12px 10px;display:flex;flex-direction:column;justify-content:space-between;min-height:0; }}
  .card-header,.change-row,.card-footer {{ display:flex;align-items:center;justify-content:space-between;gap:6px; }}
  .ticker {{ font-size:27px;letter-spacing:.7px;font-weight:800;line-height:1; }}
  .asset {{ font-size:11px;letter-spacing:.3px;font-weight:700;margin-top:5px;white-space:nowrap; }}
  .price {{ font-size:30px;font-weight:750;letter-spacing:-.9px;line-height:1;white-space:nowrap; }}
  .dollar {{ font-size:18px;vertical-align:4px;margin-right:2px; }}
  .change-row {{ align-items:center;min-height:52px; }}
  .delta {{ font-size:52px;line-height:1;letter-spacing:-1.9px;font-weight:850;font-variant-numeric:tabular-nums;white-space:nowrap; }}
  .status {{ text-align:right;font-size:10px;font-weight:800;line-height:1.25;max-width:85px;letter-spacing:.1px; }}
  .card-footer {{ border-top:1px solid #111;padding-top:7px;font-size:11px;white-space:nowrap;font-weight:500;gap:3px; }}
  .card-footer strong {{ font-weight:800; }}
  footer {{ border-top:1px solid #111;padding-top:7px;font-weight:700;display:flex;justify-content:space-between;font-size:10px;letter-spacing:.2px; }}
  .demo {{ position:absolute;right:20px;top:56px;background:#fff;border:1px solid #111;font-size:11px;font-weight:800;padding:2px 6px;transform:rotate(-2deg); }}
</style></head><body><main>
<header><h1>MARKET / ALL-TIME HIGHS</h1><div class="head-meta">PRICE vs PRIOR CLOSING ATH · USD<br>{label}: {stamp}</div></header>
<section class="grid">{''.join(pieces)}</section>
<footer><span>PRICE ATH · SPLIT-ADJUSTED · NO DIVIDENDS</span><span>{source}</span></footer>
{demo_label}</main></body></html>'''


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--demo', action='store_true', help='Generate clearly labeled example data')
    parser.add_argument('--market-only', action='store_true', help='Skip weekends, holidays, and outside NYSE hours')
    args = parser.parse_args()
    now = datetime.now(ET)
    if args.market_only and not market_window(now):
        print(f'Skipping: NYSE closed at {now.isoformat()}')
        return
    cards = demo_cards() if args.demo else [get_data(t, lab, now) for t, lab in SYMBOLS]
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'index.html').write_text(render(cards, demo=args.demo), encoding='utf-8')
    (OUT / '.nojekyll').write_text('', encoding='utf-8')
    (OUT / 'data.json').write_text(json.dumps({
        'demo': args.demo,
        'generated_at_et': now.isoformat(),
        'cards': [dict(ticker=c.ticker, price=c.price, price_time=c.price_time.isoformat(),
                       quote_type=c.kind, prior_closing_ath=c.reference_ath,
                       prior_ath_date=c.ath_date.isoformat(), change_pct=c.change,
                       days_since_prior_ath=c.days, breakout=c.is_breakout) for c in cards],
    }, indent=2), encoding='utf-8')
    print('Generated', OUT / 'index.html')
    for c in cards:
        print(f'  {c.ticker:<4} ${c.price:8.2f}  {c.change:+7.2f}%  {c.days:3}d  {c.kind:<12}  {c.price_time:%Y-%m-%d %H:%M ET}')


if __name__ == '__main__':
    main()
