# Market / All-Time Highs — E1001 intraday dashboard (v2)

Four ETF cards: VOO, QQQ, QLD, SMH. 800 × 480 black/white HTML. No Yahoo account or API key required.

## Important: prototype limits

- Source: unofficial Yahoo Finance via `yfinance`. It can lag, become unavailable, or throttle requests. This prototype is for **personal reference, not trading**.
- 5-minute price bars are **not** guaranteed live. The header displays the **earliest source timestamp among the four instruments**. This is a bar timestamp, not an execution quote guarantee.
- Historical **price** ATH = maximum **split-adjusted but dividend-unadjusted** *completed daily closing price* (not intraday high and not total return). Positive percent means the current bar or close is above the previous ATH. The previously recorded daily ATH stays unchanged until a new daily close is completed.
- On breakthrough, `Xd SINCE PRIOR ATH` reports the calendar days elapsed since the **previous closing ATH**, not zero days.
- Source terms and data-distribution rights matter. **GitHub Pages is publicly accessible**; do not assume Yahoo market data may be publicly redistributed merely because the unofficial endpoint is accessible. For private use, consider local NAS hosting instead, and test Seeedash LAN rendering first.
- Github's cron can be delayed or skipped. Seeedash Web Content may not re-render automatically after site updates. Verify the device refresh by checking the displayed time after 20–30 minutes. If it does not re-render, the same code can be deployed locally with a different display path.

## Start here: GitHub Pages version (easy test)

1. Make a **public** empty GitHub repository, e.g. `market-ath-eink` (do not initialize with README).
2. Upload the **contents** of this directory at the repository root — **including `.github/workflows/publish.yml`** (a hidden directory). If uploading via macOS Finder, use Cmd+Shift+. to reveal hidden directories, or use `git push`.
3. Go to repository `Settings → Pages → Build and deployment → Source`, choose **GitHub Actions**.
4. Go to `Actions → Publish Market ATH Dashboard → Run workflow`. If `Actions` is disabled, enable workflows for the repo. A successful deploy gives a Pages site like `https://USERNAME.github.io/market-ath-eink/`.
5. Check the page on a laptop. It must display four cards with real numbers, a current `AS OF` date, and **no DEMO watermark**.
6. In [SenseCraft Seeedash](https://sensecraft.seeed.cc/hmi), choose your device and `Web Content` (or `Workspace → Web Content`), paste your Pages URL, then `Set → Preview → Save → Deploy`. Official guide: https://sensecraft-hmi-docs-test.seeed.cc/en/guides/sensecraft-hmi-web/
7. Set your E1001's refresh interval to **10 minutes** if the UI offers it. Verify the e-ink display actually changes its `AS OF` label during a trading session; web content re-rendering is not guaranteed simply by scheduling GitHub updates.

**Expected schedule:** NYSE trading weekdays 09:30–16:30 New York time, each 10 minutes, with no data requests on weekends/NYSE holidays. Special early-close dates are checked with the XNYS calendar and skipped after the early close plus 30 minutes. The last post-close request attempts to capture the actual closing bar. Market data may lag and GitHub Actions scheduling is best-effort.

**Device wake-ups:** Original Seeedash firmware has an interval setting but has not been verified to support NYSE-session-only wake-up. The background task stops after close; the device may still wake at fixed intervals. Consider USB-C power or a later ESPHome implementation if battery life is inadequate.

## Local test (Mac / NAS)

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python build.py --demo
open site/index.html
python build.py
open site/index.html
```

The demo creates fake prices and labels the entire page. The real command requires Internet access to Yahoo Finance; the `build` step fails if Yahoo provides no suitable data.

Run unit tests: `python -m unittest discover -s tests -v`.

## Hosting privately on Synology (optional later)

`python build.py` updates `site/index.html`; any local web server can serve `site/`, e.g. `python3 -m http.server 8088 --directory site` (foreground only). For true 24/7 use, put the script behind a Synology Task Scheduler job and the page behind a LAN web server. Seeedash documentation mentions LAN web content, but confirm your particular screen, firmware and network can use it before relying on this mode.
