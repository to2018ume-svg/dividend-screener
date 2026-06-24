"""
S&P500 Dividend Stock Screener
Fetches data via yfinance and screens by:
  - Dividend yield
  - Consecutive dividend years (streak)
  - Payout ratio
  - Financial health (debt/equity, current ratio)
Results are sent via email.
"""

import os
import smtplib
import time
import logging
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from dataclasses import dataclass, field
from typing import Optional

import requests
import yfinance as yf
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

# ── Screening thresholds (can be overridden via env vars) ──────────────────────
MIN_YIELD       = float(os.getenv("MIN_YIELD",       "2.5"))   # %
MAX_YIELD       = float(os.getenv("MAX_YIELD",      "10.0"))   # % (cap to exclude distressed)
MIN_STREAK      = int(  os.getenv("MIN_STREAK",        "5"))   # consecutive dividend years
MAX_PAYOUT      = float(os.getenv("MAX_PAYOUT",      "75.0"))  # %
MAX_DEBT_EQUITY = float(os.getenv("MAX_DEBT_EQUITY",  "2.0"))  # ratio
MIN_CURRENT     = float(os.getenv("MIN_CURRENT",      "1.0"))  # current ratio

# ── Email config (set as GitHub Secrets / local .env) ─────────────────────────
EMAIL_FROM    = os.getenv("EMAIL_FROM", "")
EMAIL_TO      = os.getenv("EMAIL_TO",   "")
EMAIL_PASS    = os.getenv("EMAIL_PASS", "")
SMTP_HOST     = os.getenv("SMTP_HOST", "smtp.gmail.com")


# ── S&P 500 ticker list ────────────────────────────────────────────────────────

# Static fallback list (as of mid-2025). Used when Wikipedia is unreachable.
_SP500_STATIC: list[str] = [
    "A","AAL","AAP","AAPL","ABBV","ABC","ABMD","ABT","ACN","ACVA","ADI","ADM",
    "ADP","ADSK","AEE","AEP","AES","AFL","AIG","AIZ","AJG","AKAM","ALB","ALGN",
    "ALK","ALL","ALLE","AMAT","AMCR","AMD","AME","AMGN","AMP","AMT","AMZN","ANET",
    "ANF","AON","AOS","APA","APD","APH","APTV","ARE","ATO","AVB","AVGO","AVY",
    "AWK","AXP","AZO","BA","BAC","BAX","BBWI","BBY","BDX","BEN","BF-B","BG",
    "BIIB","BIO","BK","BKNG","BKR","BLK","BMY","BR","BRK-B","BRO","BSX","BWA",
    "BXP","C","CAG","CAH","CARR","CAT","CB","CBOE","CBRE","CCI","CCL","CDNS",
    "CDW","CE","CF","CFG","CHD","CHRW","CHTR","CI","CINF","CL","CLX","CMA","CMCSA",
    "CME","CMG","CMI","CMS","CNC","CNP","COF","COO","COP","COST","CPB","CPRT",
    "CPT","CRL","CRM","CSCO","CSGP","CSX","CTAS","CTLT","CTRA","CTSH","CTVA",
    "CVS","CVX","CZR","D","DAL","DAY","DD","DE","DECK","DFS","DG","DGX","DHI",
    "DHR","DIS","DISH","DLR","DLTR","DOV","DOW","DPZ","DRI","DTE","DUK","DVA",
    "DVN","DXC","DXCM","EA","EBAY","ECL","ED","EFX","EIX","EL","ELV","EMN","EMR",
    "ENPH","EOG","EPAM","EQIX","EQR","EQT","ES","ESS","ETN","ETR","ETSY","EVRG",
    "EW","EXC","EXPD","EXPE","EXR","F","FANG","FAST","FBHS","FCX","FDS","FDX",
    "FE","FFIV","FI","FICO","FIS","FITB","FLT","FMC","FOX","FOXA","FRC","FRT",
    "FTNT","FTV","GD","GE","GEHC","GEN","GILD","GIS","GL","GLW","GM","GNRC",
    "GOOG","GOOGL","GPC","GPN","GRMN","GS","GWW","HAL","HAS","HBAN","HCA","HD",
    "HES","HIG","HII","HLT","HOLX","HON","HPE","HPQ","HRL","HSIC","HST","HSY",
    "HUBB","HUM","HWM","IBM","ICE","IDXX","IEX","IFF","ILMN","INCY","INTC",
    "INTU","INVH","IP","IPG","IQV","IR","IRM","ISRG","IT","ITW","IVZ","J","JBHT",
    "JBL","JCI","JKHY","JNJ","JNPR","JPM","K","KDP","KEY","KEYS","KHC","KIM",
    "KLAC","KMB","KMI","KMX","KO","KR","L","LDOS","LEN","LH","LHX","LIN","LKQ",
    "LLY","LMT","LNC","LNT","LOW","LRCX","LUMN","LUV","LVS","LW","LYB","LYV",
    "MA","MAA","MAR","MAS","MCD","MCHP","MCK","MCO","MDLZ","MDT","MET","META",
    "MGM","MHK","MKC","MKTX","MLM","MMC","MMM","MNST","MO","MOH","MOS","MPC",
    "MPWR","MRK","MRNA","MRO","MS","MSCI","MSFT","MSI","MTB","MTCH","MTD","MU",
    "NCLH","NDAQ","NEE","NEM","NFLX","NI","NKE","NOC","NOW","NRG","NSC","NTAP",
    "NTRS","NUE","NVDA","NVR","NWL","NWS","NWSA","NXPI","O","OKE","OMC","ON",
    "ORCL","ORLY","OXY","PARA","PAYC","PAYX","PCAR","PCG","PEAK","PEG","PEP",
    "PFE","PFG","PG","PGR","PH","PHM","PKG","PLD","PM","PNC","PNR","PNW","POOL",
    "PPG","PPL","PRU","PSA","PSX","PTC","PWR","PXD","PYPL","QCOM","QRVO","RCL",
    "RE","REG","REGN","RF","RHI","RJF","RL","RMD","ROK","ROL","ROP","ROST","RSG",
    "RTX","SBAC","SBUX","SEDG","SHW","SJM","SLB","SNA","SNPS","SO","SPG","SPGI",
    "SRE","STE","STT","STX","STZ","SWK","SWKS","SYF","SYK","SYY","T","TAP","TDG",
    "TDY","TECH","TEL","TER","TFC","TFX","TGT","TJX","TMO","TMUS","TPR","TRMB",
    "TROW","TRV","TSCO","TSLA","TSN","TT","TTWO","TXN","TXT","TYL","UAL","UDR",
    "UHS","ULTA","UNH","UNP","UPS","URI","USB","V","VFC","VICI","VLO","VMC","VNO",
    "VRSK","VRSN","VRTX","VTR","VTRS","VZ","WAB","WAT","WBA","WBD","WEC","WELL",
    "WFC","WHR","WM","WMB","WMT","WRB","WRK","WST","WTW","WY","WYNN","XEL","XOM",
    "XRAY","XYL","YUM","ZBH","ZBRA","ZION","ZTS",
]


def get_sp500_tickers() -> list[str]:
    """Return S&P 500 tickers, preferring a live Wikipedia fetch with fallback to static list."""
    url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
    try:
        resp = requests.get(url, headers=headers, timeout=15)
        resp.raise_for_status()
        df = pd.read_html(resp.text)[0]
        tickers = df["Symbol"].str.replace(".", "-", regex=False).tolist()
        log.info("Fetched %d S&P 500 tickers from Wikipedia", len(tickers))
        return tickers
    except Exception as exc:
        log.warning("Wikipedia fetch failed (%s) — using static ticker list (%d tickers)", exc, len(_SP500_STATIC))
        return _SP500_STATIC


# ── Per-stock data fetching ────────────────────────────────────────────────────

@dataclass
class StockData:
    ticker: str
    name: str = ""
    sector: str = ""
    price: float = 0.0
    div_yield: float = 0.0        # %
    payout_ratio: float = 0.0     # %
    streak_years: int = 0         # consecutive years with dividend
    debt_equity: float = 0.0
    current_ratio: float = 0.0
    eps_growth_5y: float = 0.0    # % CAGR (approximated)
    passed: bool = False
    fail_reasons: list[str] = field(default_factory=list)


def _safe(val, default=0.0):
    """Return val if it's a finite number, else default."""
    try:
        v = float(val)
        return v if pd.notna(v) and abs(v) < 1e15 else default
    except (TypeError, ValueError):
        return default


def compute_streak(dividends: pd.Series) -> int:
    """Count consecutive calendar years with at least one dividend payment."""
    if dividends.empty:
        return 0
    years = sorted(dividends.index.year.unique(), reverse=True)
    current_year = pd.Timestamp.now().year
    streak = 0
    expected = current_year
    for y in years:
        if y == expected or y == expected - 1:
            # allow current year to be in progress
            streak += 1
            expected = y - 1
        else:
            break
    return streak


def fetch_stock(ticker: str) -> Optional[StockData]:
    try:
        t = yf.Ticker(ticker)
        info = t.info or {}

        price       = _safe(info.get("currentPrice") or info.get("regularMarketPrice"))
        div_yield   = _safe(info.get("dividendYield"), 0.0) * 100
        payout_raw  = _safe(info.get("payoutRatio"),   0.0)
        payout      = payout_raw * 100 if payout_raw <= 1.5 else payout_raw  # normalize
        debt_eq     = _safe(info.get("debtToEquity"),  0.0)
        curr_ratio  = _safe(info.get("currentRatio"),  0.0)
        name        = info.get("shortName", ticker)
        sector      = info.get("sector",    "Unknown")

        # EPS growth proxy: compare trailingEps vs forwardEps
        trailing_eps = _safe(info.get("trailingEps"), 0.0)
        forward_eps  = _safe(info.get("forwardEps"),  0.0)
        eps_growth = 0.0
        if trailing_eps > 0 and forward_eps > 0:
            eps_growth = (forward_eps / trailing_eps - 1) * 100

        # Dividend streak from historical data
        hist_div = t.dividends
        streak = compute_streak(hist_div)

        return StockData(
            ticker=ticker,
            name=name,
            sector=sector,
            price=price,
            div_yield=div_yield,
            payout_ratio=payout,
            streak_years=streak,
            debt_equity=debt_eq,
            current_ratio=curr_ratio,
            eps_growth_5y=eps_growth,
        )
    except Exception as exc:
        log.debug("Skip %s: %s", ticker, exc)
        return None


# ── Screening logic ────────────────────────────────────────────────────────────

def screen(stock: StockData) -> StockData:
    reasons = []
    if stock.div_yield < MIN_YIELD:
        reasons.append(f"yield {stock.div_yield:.1f}% < {MIN_YIELD}%")
    if stock.div_yield > MAX_YIELD:
        reasons.append(f"yield {stock.div_yield:.1f}% > {MAX_YIELD}% (distressed?)")
    if stock.streak_years < MIN_STREAK:
        reasons.append(f"streak {stock.streak_years}yr < {MIN_STREAK}yr")
    if 0 < stock.payout_ratio > MAX_PAYOUT:
        reasons.append(f"payout {stock.payout_ratio:.1f}% > {MAX_PAYOUT}%")
    if stock.debt_equity > MAX_DEBT_EQUITY:
        reasons.append(f"D/E {stock.debt_equity:.2f} > {MAX_DEBT_EQUITY}")
    if stock.current_ratio > 0 and stock.current_ratio < MIN_CURRENT:
        reasons.append(f"current ratio {stock.current_ratio:.2f} < {MIN_CURRENT}")

    stock.fail_reasons = reasons
    stock.passed = len(reasons) == 0
    return stock


# ── Report generation ──────────────────────────────────────────────────────────

def build_html_report(passed: list[StockData]) -> str:
    rows = ""
    for s in sorted(passed, key=lambda x: -x.div_yield):
        rows += (
            f"<tr>"
            f"<td><b>{s.ticker}</b></td>"
            f"<td>{s.name}</td>"
            f"<td>{s.sector}</td>"
            f"<td>${s.price:.2f}</td>"
            f"<td>{s.div_yield:.2f}%</td>"
            f"<td>{s.streak_years}</td>"
            f"<td>{s.payout_ratio:.1f}%</td>"
            f"<td>{s.debt_equity:.2f}</td>"
            f"<td>{s.current_ratio:.2f}</td>"
            f"<td>{s.eps_growth_5y:+.1f}%</td>"
            f"</tr>\n"
        )

    criteria_html = (
        f"<li>配当利回り: {MIN_YIELD}% ～ {MAX_YIELD}%</li>"
        f"<li>連続配当年数: {MIN_STREAK}年以上</li>"
        f"<li>配当性向: {MAX_PAYOUT}%以下</li>"
        f"<li>負債資本比率 (D/E): {MAX_DEBT_EQUITY}以下</li>"
        f"<li>流動比率: {MIN_CURRENT}以上</li>"
    )

    return f"""
<html><body style="font-family:sans-serif;color:#222">
<h2>📊 S&P500 配当株スクリーニング結果</h2>
<p>実行日時: {pd.Timestamp.now().strftime('%Y-%m-%d %H:%M UTC')}</p>
<h3>スクリーニング条件</h3>
<ul>{criteria_html}</ul>
<h3>通過銘柄: {len(passed)} 件</h3>
<table border="1" cellpadding="6" cellspacing="0"
       style="border-collapse:collapse;font-size:13px">
  <tr style="background:#2c3e50;color:#fff">
    <th>Ticker</th><th>銘柄名</th><th>セクター</th><th>株価</th>
    <th>配当利回り</th><th>連続配当年数</th><th>配当性向</th>
    <th>D/E比率</th><th>流動比率</th><th>EPS成長(1yr)</th>
  </tr>
  {rows}
</table>
<p style="color:#888;font-size:11px">
  Data source: Yahoo Finance (yfinance). 投資判断はご自身の責任で行ってください。
</p>
</body></html>
"""


def build_text_report(passed: list[StockData]) -> str:
    lines = [
        f"S&P500 配当株スクリーニング結果 — {pd.Timestamp.now().strftime('%Y-%m-%d')}",
        f"通過銘柄数: {len(passed)}",
        "",
        f"{'Ticker':<8} {'Yield':>7} {'Streak':>7} {'Payout':>8} {'D/E':>6} {'CR':>5}  銘柄名",
        "-" * 70,
    ]
    for s in sorted(passed, key=lambda x: -x.div_yield):
        lines.append(
            f"{s.ticker:<8} {s.div_yield:>6.2f}% {s.streak_years:>6}yr "
            f"{s.payout_ratio:>7.1f}% {s.debt_equity:>5.2f} {s.current_ratio:>4.2f}  {s.name}"
        )
    return "\n".join(lines)


# ── Email sending ──────────────────────────────────────────────────────────────

def send_email(subject: str, html_body: str, text_body: str) -> None:
    if not all([EMAIL_FROM, EMAIL_TO, EMAIL_PASS]):
        log.warning("Email env vars not set — printing report to stdout instead.")
        print(text_body)
        return

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"]    = EMAIL_FROM
    msg["To"]      = EMAIL_TO
    msg.attach(MIMEText(text_body, "plain",  "utf-8"))
    msg.attach(MIMEText(html_body, "html",   "utf-8"))

    recipients = EMAIL_TO.split(",")
    with smtplib.SMTP_SSL(SMTP_HOST, 465) as server:
        server.login(EMAIL_FROM, EMAIL_PASS)
        server.sendmail(EMAIL_FROM, recipients, msg.as_string())

    log.info("Email sent to %s", EMAIL_TO)


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    tickers = get_sp500_tickers()

    results: list[StockData] = []
    for i, ticker in enumerate(tickers):
        if i % 50 == 0:
            log.info("Progress: %d / %d", i, len(tickers))
        data = fetch_stock(ticker)
        if data:
            results.append(screen(data))
        time.sleep(0.3)  # be gentle with Yahoo Finance rate limits

    passed = [s for s in results if s.passed]
    log.info("Screening complete: %d / %d passed", len(passed), len(results))

    subject   = f"[Dividend Screener] {len(passed)}銘柄 通過 — {pd.Timestamp.now().strftime('%Y-%m')}"
    html_body = build_html_report(passed)
    text_body = build_text_report(passed)

    # Also save CSV
    if passed:
        df = pd.DataFrame([vars(s) for s in passed]).drop(columns=["fail_reasons", "passed"])
        df.to_csv("results.csv", index=False)
        log.info("Saved results.csv (%d rows)", len(passed))

    send_email(subject, html_body, text_body)


if __name__ == "__main__":
    main()
