"""
투자환경 & 반도체 지표 대시보드
Streamlit Cloud 배포용 단일 파일 앱 (yfinance + plotly)

참고 (티커 관련 메모)
- ^TNX  : 미국 10년 국채금리. Yahoo에서는 실제 금리 * 10 으로 표시되어 코드에서 10으로 나눠줍니다.
- DX-Y.NYB : ICE 달러 인덱스
- CL=F  : WTI 원유 선물
- IPO   : Renaissance IPO ETF (신규상장주 ETF, 투자심리 프록시)
- RINF  : ProShares Inflation Expectations ETF (기대 인플레이션 프록시). Yahoo Finance에는
          CPI 지수 자체가 없어 시장 기반 인플레이션 기대치로 대체했습니다. 필요시 TIP 등으로 교체 가능.
- SOXL / SOXS : Direxion Daily Semiconductor Bull/Bear 3X Shares (필라델피아 반도체지수 연동 레버리지/인버스 ETF)
- SK하이닉스 ADR : 2026년 7월 나스닥 상장 티커 SKHY 사용. 상장 초기라 데이터가 짧을 수 있어
          SKHY 조회 실패 시 OTC 티커 HXSCL, 그래도 실패하면 한국거래소 원주(000660.KS) 순으로 자동 대체합니다.
          000660.KS는 원화(KRW) 표시이므로 USD/KRW 환율(KRW=X)로 나눠 달러로 환산해 표시합니다.
          (SKHY, HXSCL은 이미 달러 표시 ADR이라 환산이 필요 없습니다.)
- 그 외 지표(국채금리·VIX·유가·달러인덱스·ETF·SOX·SOXL/SOXS·MU·NVDA·AMD·ASML)는 모두 달러 또는
          지수 포인트 기준이라 별도 환산이 필요 없습니다. 원화가 아닌 다른 통화의 티커를 추가할 경우
          아래 TICKER_FX_PAIR에 {"티커": "환율티커"} 형태로 추가하면 자동으로 달러 환산됩니다.

티커나 지표를 바꾸고 싶으면 아래 MACRO_ITEMS / SEMI_ITEMS 딕셔너리(리스트)만 수정하면 됩니다.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st
import yfinance as yf
import pandas as pd
import plotly.graph_objects as go

# ------------------------------------------------------------
# 기본 설정
# ------------------------------------------------------------
st.set_page_config(page_title="투자 지표 대시보드", page_icon="📊", layout="wide")

st.markdown("ck-stock_260720")

st.title("📊 투자환경 & 반도체 지표 대시보드")
st.caption("데이터 출처: Yahoo Finance (yfinance) · 실시간이 아닌 지연 데이터이며 투자 참고용입니다.")

# ------------------------------------------------------------
# 사이드바 옵션
# ------------------------------------------------------------
st.sidebar.header("⚙️ 조회 설정")

period = st.sidebar.selectbox(
    "조회 기간",
    ["1mo", "3mo", "6mo", "1y", "2y", "5y", "max"],
    index=3,
)
interval = st.sidebar.selectbox(
    "데이터 간격",
    ["1d", "1wk", "1mo"],
    index=0,
)

if st.sidebar.button("🔄 데이터 새로고침"):
    st.cache_data.clear()

st.sidebar.markdown("---")
st.sidebar.caption(
    "SK하이닉스는 2026년 7월 나스닥 ADR(SKHY) 상장 초기라 기간이 짧게 보일 수 있습니다. "
    "이 경우 OTC(HXSCL) 또는 한국거래소 원주(000660.KS) 데이터로 자동 대체됩니다."
)

# ------------------------------------------------------------
# 데이터 fetch 유틸
# ------------------------------------------------------------


def fetch_time_text() -> str:
    """현재 조회 시각을 한국시간(KST)·미국 동부시간(ET) 동시 표기로 반환"""
    now_utc = datetime.now(ZoneInfo("UTC"))
    kst = now_utc.astimezone(ZoneInfo("Asia/Seoul"))
    est = now_utc.astimezone(ZoneInfo("America/New_York"))
    return (
        f"🕒 조회시각(KST) {kst.strftime('%Y-%m-%d %H:%M')} "
        f"| 조회시각(미국 ET) {est.strftime('%Y-%m-%d %H:%M %Z')}"
    )


@st.cache_data(ttl=600, show_spinner=False)
def fetch_history(ticker: str, period: str, interval: str) -> pd.DataFrame:
    try:
        df = yf.Ticker(ticker).history(period=period, interval=interval)
        if df is None or df.empty:
            return pd.DataFrame()
        return df
    except Exception:
        return pd.DataFrame()


def fetch_with_fallback(tickers: list, period: str, interval: str):
    """리스트 순서대로 시도해서 처음으로 데이터가 있는 티커를 반환"""
    for t in tickers:
        df = fetch_history(t, period, interval)
        if not df.empty:
            return df, t
    return pd.DataFrame(), None


# 달러가 아닌 통화로 표시되는 티커 -> 환산에 쓸 환율 티커 매핑
# (KRW=X 는 "1달러 = X원"을 의미하는 USD/KRW 환율)
TICKER_FX_PAIR = {
    "000660.KS": "KRW=X",  # SK하이닉스 한국거래소 원주 (원화 표시)
}


def to_usd(df: pd.DataFrame, ticker: str, period: str, interval: str):
    """ticker가 TICKER_FX_PAIR에 있으면 환율로 나눠 달러 환산. 없으면(=이미 달러) 그대로 반환."""
    fx_pair = TICKER_FX_PAIR.get(ticker)
    if not fx_pair:
        return df, False
    fx_df = fetch_history(fx_pair, period, interval)
    if fx_df.empty:
        return df, False
    fx_series = fx_df["Close"].reindex(df.index).ffill().bfill()
    converted = df.copy()
    converted["Close"] = df["Close"] / fx_series
    return converted, True


def single_line_chart(series: pd.Series, height: int = 280, color: str = "#2563eb") -> go.Figure:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=series.index, y=series, mode="lines", line=dict(width=2, color=color)))
    fig.update_layout(
        title=dict(
            text=f"<span style='font-size:10.5px;color:#6b7280'>{fetch_time_text()}</span>",
            x=0.0, xanchor="left", y=0.99, yanchor="top",
        ),
        template="plotly_white",
        height=height,
        margin=dict(l=30, r=10, t=34, b=30),
        hovermode="x unified",
        showlegend=False,
    )
    return fig


def normalized_multi_chart(series_dict: dict, title: str, height: int = 430, colors: dict = None) -> go.Figure:
    """서로 다른 가격 스케일의 자산을 시작점=100 기준 상대 수익률로 비교"""
    fig = go.Figure()
    for name, s in series_dict.items():
        if s is None or s.empty:
            continue
        norm = s / s.iloc[0] * 100
        line_kwargs = dict(width=2)
        if colors and name in colors:
            line_kwargs["color"] = colors[name]
        fig.add_trace(go.Scatter(x=norm.index, y=norm, mode="lines", name=name, line=line_kwargs))
    fig.update_layout(
        title=dict(
            text=f"{title}<br><span style='font-size:10.5px;color:#6b7280'>{fetch_time_text()}</span>",
        ),
        template="plotly_white",
        height=height,
        margin=dict(l=40, r=20, t=65, b=30),
        hovermode="x unified",
        yaxis_title="상대 수익률 (시작일=100)",
        xaxis_title="날짜",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
    )
    return fig


def render_metric_and_chart(label: str, ticker: str, unit: str, divide_by: float = 1):
    df = fetch_history(ticker, period, interval)
    if df.empty:
        st.warning(f"⚠️ {label} ({ticker}) 데이터를 불러오지 못했습니다.")
        return
    close = df["Close"] / divide_by
    last = close.iloc[-1]
    prev = close.iloc[-2] if len(close) > 1 else last
    pct = (last - prev) / prev * 100 if prev else 0
    st.metric(label, f"{last:,.2f} {unit}", f"{pct:+.2f}%")
    st.plotly_chart(single_line_chart(close), use_container_width=True)


# ------------------------------------------------------------
# 1. 투자환경 및 심리에 영향을 미치는 지표
# ------------------------------------------------------------
st.header("1️⃣ 투자환경 및 심리에 영향을 미치는 지표")

MACRO_ITEMS = [
    ("미국 10년 국채금리", "^TNX", "%", 10),
    ("VIX 변동성지수", "^VIX", "pt", 1),
    ("WTI 유가", "CL=F", "$/배럴", 1),
    ("달러 인덱스 (DXY)", "DX-Y.NYB", "pt", 1),
    ("IPO ETF (Renaissance)", "IPO", "$", 1),
    ("기대 인플레이션 (RINF)", "RINF", "$", 1),
]

for row_start in range(0, len(MACRO_ITEMS), 3):
    cols = st.columns(3)
    for col, (label, ticker, unit, div) in zip(cols, MACRO_ITEMS[row_start:row_start + 3]):
        with col:
            render_metric_and_chart(label, ticker, unit, div)

st.markdown("---")

# ------------------------------------------------------------
# 2. 주력 반도체 주가에 영향을 주는 지표
# ------------------------------------------------------------
st.header("2️⃣ 주력 반도체 주가에 영향을 주는 지표")

# 2-1. 필라델피아 반도체지수
st.subheader("필라델피아 반도체지수 (^SOX)")
sox_df = fetch_history("^SOX", period, interval)
if not sox_df.empty:
    last = sox_df["Close"].iloc[-1]
    prev = sox_df["Close"].iloc[-2] if len(sox_df) > 1 else last
    pct = (last - prev) / prev * 100 if prev else 0
    st.metric("SOX 지수", f"{last:,.2f} pt", f"{pct:+.2f}%")
    st.plotly_chart(single_line_chart(sox_df["Close"], height=350), use_container_width=True)
else:
    st.warning("⚠️ ^SOX 데이터를 불러오지 못했습니다.")

# 2-2. SOX vs SOXL vs SOXS
st.subheader("필라델피아 반도체지수(SOX) vs SOXL(3배 롱) vs SOXS(3배 숏) 움직임")
st.caption("종가 스케일이 서로 달라(지수 포인트 vs ETF 주가) 시작일=100 기준 상대 수익률로 비교합니다.")
soxl_df = fetch_history("SOXL", period, interval)
soxs_df = fetch_history("SOXS", period, interval)
sox_soxls_series = {
    "필라델피아 반도체지수 (SOX)": sox_df["Close"] if not sox_df.empty else pd.Series(dtype=float),
    "SOXL": soxl_df["Close"] if not soxl_df.empty else pd.Series(dtype=float),
    "SOXS": soxs_df["Close"] if not soxs_df.empty else pd.Series(dtype=float),
}
sox_soxls_colors = {
    "필라델피아 반도체지수 (SOX)": "#2563eb",
    "SOXL": "#16a34a",
    "SOXS": "#dc2626",
}
if any(not s.empty for s in sox_soxls_series.values()):
    st.plotly_chart(
        normalized_multi_chart(
            sox_soxls_series,
            "SOX · SOXL · SOXS 상대 수익률 비교",
            height=400,
            colors=sox_soxls_colors,
        ),
        use_container_width=True,
    )
else:
    st.warning("⚠️ SOX/SOXL/SOXS 데이터를 불러오지 못했습니다.")

# 2-3. SK하이닉스 ADR vs 마이크론
st.subheader("SK하이닉스 ADR vs 마이크론(MU) 주가 동향")
skhynix_df, skhynix_ticker = fetch_with_fallback(["SKHY", "HXSCL", "000660.KS"], period, interval)
micron_df = fetch_history("MU", period, interval)

if skhynix_ticker:
    skhynix_df, was_converted = to_usd(skhynix_df, skhynix_ticker, period, interval)
    note = " · 원화→달러 환산 적용 (USD/KRW 기준)" if was_converted else ""
    st.caption(f"SK하이닉스 데이터 소스: {skhynix_ticker}{note}")
else:
    st.warning("⚠️ SK하이닉스 관련 티커(SKHY/HXSCL/000660.KS) 데이터를 모두 불러오지 못했습니다.")

series_map = {}
if not skhynix_df.empty:
    series_map[f"SK하이닉스 ({skhynix_ticker})"] = skhynix_df["Close"]
if not micron_df.empty:
    series_map["마이크론 (MU)"] = micron_df["Close"]

if series_map:
    st.plotly_chart(normalized_multi_chart(series_map, "SK하이닉스 vs 마이크론 (상대 수익률)"), use_container_width=True)
else:
    st.warning("⚠️ 표시할 데이터가 없습니다.")

# 2-4. 빅테크 (엔비디아, AMD, ASML)
st.subheader("빅테크 반도체 주가 동향 (엔비디아 · AMD · ASML)")
bigtech_tickers = {"엔비디아 (NVDA)": "NVDA", "AMD (AMD)": "AMD", "ASML (ASML)": "ASML"}
bigtech_series = {}
cols = st.columns(3)
for col, (name, ticker) in zip(cols, bigtech_tickers.items()):
    df = fetch_history(ticker, period, interval)
    with col:
        if not df.empty:
            last = df["Close"].iloc[-1]
            prev = df["Close"].iloc[-2] if len(df) > 1 else last
            pct = (last - prev) / prev * 100 if prev else 0
            st.metric(name, f"${last:,.2f}", f"{pct:+.2f}%")
            bigtech_series[name] = df["Close"]
        else:
            st.warning(f"⚠️ {name} 데이터를 불러오지 못했습니다.")

if bigtech_series:
    st.plotly_chart(normalized_multi_chart(bigtech_series, "빅테크 반도체 3종 상대 수익률 비교"), use_container_width=True)

st.markdown("---")
st.caption("본 대시보드는 정보 제공 목적이며 투자 조언이 아닙니다. 데이터는 Yahoo Finance 기준으로 지연·오차가 있을 수 있습니다.")
