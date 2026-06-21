"""
데드라 마진 리포트 — Streamlit 웹 앱 Premium v3
"""

import io, csv, sys, os
import streamlit as st
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from dedra_daily_report import (
    preprocess_rows, aggregate,
    detect_price_anomalies, detect_discount_anomalies,
    generate_html, margin, margin_rate, fmt_won, fmt_rate,
)
from dedra_daily_report import recovery_rate

# ── 페이지 설정 ───────────────────────────────────────────────
st.set_page_config(
    page_title="데드라 마진 리포트",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 프리미엄 CSS 스타일링 ──────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@300;400;500;600;700&family=Noto+Sans+KR:wght@300;400;500;700&display=swap');

/* 전체 글꼴 및 톤앤매너 */
html, body, [class*="css"] {
    font-family: 'Plus Jakarta Sans', 'Noto Sans KR', sans-serif !important;
}

[data-testid="stAppViewContainer"] {
    background-color: #f8fafc;
}

[data-testid="stSidebar"] {
    background-color: #0f172a !important; /* Deep Slate */
}
[data-testid="stSidebar"] * {
    color: #cbd5e1 !important;
}
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 {
    color: #ffffff !important;
    font-weight: 700 !important;
}

/* 메인 대시보드 헤더 */
.dashboard-header {
    background: linear-gradient(135deg, #1e1b4b 0%, #312e81 100%);
    padding: 24px 32px;
    border-radius: 16px;
    color: white;
    margin-bottom: 24px;
    box-shadow: 0 10px 25px -5px rgba(49, 46, 129, 0.12);
    display: flex;
    justify-content: space-between;
    align-items: center;
}
.header-title h1 {
    color: white !important;
    font-size: 24px !important;
    font-weight: 800 !important;
    margin: 0 0 6px 0 !important;
    letter-spacing: -0.5px;
}
.header-title p {
    color: #c7d2fe !important;
    font-size: 13px !important;
    margin: 0 !important;
    opacity: 0.9;
}

/* 프리미엄 카드 디자인 */
.kpi-grid {
    display: grid;
    gap: 16px;
    margin-bottom: 24px;
}
.g2 { grid-template-columns: repeat(2, 1fr); }
.g3 { grid-template-columns: repeat(3, 1fr); }
.g4 { grid-template-columns: repeat(4, 1fr); }
.g6 { grid-template-columns: repeat(6, 1fr); }

.kpi-card {
    background: white;
    border-radius: 16px;
    padding: 20px;
    box-shadow: 0 4px 6px -1px rgba(15, 23, 42, 0.03), 0 2px 4px -2px rgba(15, 23, 42, 0.02);
    border: 1px solid #e2e8f0;
    transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
    position: relative;
    overflow: hidden;
}
.kpi-card:hover {
    transform: translateY(-2px);
    box-shadow: 0 12px 20px -8px rgba(15, 23, 42, 0.08);
    border-color: #cbd5e1;
}
.kpi-card::before {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    width: 4px;
    height: 100%;
    background: #4f46e5; /* 기본 Indigo 포인트 */
}
.kpi-card.accent-green::before { background: #10b981; }
.kpi-card.accent-amber::before { background: #f59e0b; }
.kpi-card.accent-red::before { background: #ef4444; }
.kpi-card.accent-rose::before { background: #f43f5e; }

.kpi-card .lbl {
    font-size: 11px;
    color: #64748b;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 8px;
}
.kpi-card .val {
    font-size: 22px;
    font-weight: 700;
    color: #0f172a;
    line-height: 1.2;
}
.kpi-card .sub {
    font-size: 11px;
    color: #94a3b8;
    margin-top: 6px;
}

/* 섹션 타이틀 */
.section-title {
    font-size: 14px;
    font-weight: 700;
    color: #1e293b;
    margin: 24px 0 12px;
    display: flex;
    align-items: center;
    gap: 8px;
}
.section-title::before {
    content: '';
    display: inline-block;
    width: 6px;
    height: 14px;
    background: #6366f1;
    border-radius: 2px;
}

/* 커스텀 프리미엄 테이블 */
.custom-table-wrapper {
    background: white;
    border-radius: 16px;
    border: 1px solid #e2e8f0;
    box-shadow: 0 4px 6px -1px rgba(15, 23, 42, 0.02);
    overflow: hidden;
    margin-bottom: 20px;
}
.custom-table {
    width: 100%;
    border-collapse: collapse;
    text-align: left;
}
.custom-table th {
    background-color: #f8fafc;
    color: #475569;
    font-weight: 600;
    font-size: 12px;
    padding: 12px 20px;
    border-bottom: 1px solid #e2e8f0;
    text-transform: uppercase;
    letter-spacing: 0.5px;
}
.custom-table td {
    padding: 12px 20px;
    font-size: 13px;
    color: #334155;
    border-bottom: 1px solid #f1f5f9;
}
.custom-table tr:last-child td {
    border-bottom: none;
}
.custom-table tr:hover td {
    background-color: #f8fafc;
}

/* 알림 배너 */
.banner-premium {
    padding: 12px 20px;
    border-radius: 12px;
    font-size: 13px;
    font-weight: 500;
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 16px;
    border: 1px solid transparent;
}
.banner-premium.ok {
    background-color: #ecfdf5;
    border-color: #a7f3d0;
    color: #065f46;
}
.banner-premium.warn {
    background-color: #fffbef;
    border-color: #fde68a;
    color: #92400e;
}
.banner-premium.err {
    background-color: #fef2f2;
    border-color: #fca5a5;
    color: #991b1b;
}

/* 탭 스타일링 */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    background: #f1f5f9;
    border-radius: 12px;
    padding: 6px;
    gap: 4px;
    margin-bottom: 20px;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    background-color: transparent !important;
    color: #64748b !important;
    border-radius: 8px !important;
    font-size: 13px !important;
    font-weight: 600 !important;
    padding: 8px 18px !important;
    border: none !important;
    transition: all 0.2s ease !important;
}
[data-testid="stTabs"] [data-baseweb="tab"]:hover {
    color: #0f172a !important;
}
[data-testid="stTabs"] [aria-selected="true"] {
    background-color: white !important;
    color: #4f46e5 !important;
    box-shadow: 0 4px 10px -2px rgba(15, 23, 42, 0.05) !important;
}

/* 로그인 화면 */
.login-container {
    max-width: 420px;
    margin: 120px auto 0;
    background: white;
    border-radius: 24px;
    padding: 48px 40px;
    box-shadow: 0 20px 25px -5px rgba(15, 23, 42, 0.08), 0 10px 10px -5px rgba(15, 23, 42, 0.04);
    border: 1px solid #e2e8f0;
    text-align: center;
}
.login-logo {
    font-size: 48px;
    margin-bottom: 16px;
}
.login-title {
    font-size: 22px;
    font-weight: 800;
    color: #0f172a;
    margin-bottom: 8px;
    letter-spacing: -0.5px;
}
.login-sub {
    font-size: 13px;
    color: #64748b;
    margin-bottom: 32px;
}

/* 파일 업로더 커스텀 */
[data-testid="stSidebar"] [data-testid="stFileUploader"] section {
    background: rgba(255, 255, 255, 0.04);
    border: 1px dashed rgba(255, 255, 255, 0.2) !important;
    border-radius: 12px;
    padding: 16px;
}
[data-testid="stSidebar"] [data-testid="stFileUploader"] section:hover {
    border-color: rgba(255, 255, 255, 0.4) !important;
    background: rgba(255, 255, 255, 0.08);
}

.block-container {
    padding-top: 2rem !important;
    padding-bottom: 2rem !important;
}
</style>
""", unsafe_allow_html=True)


# ── 유틸 및 컴포넌트 ──────────────────────────────────────────
def kpi_card(label, value, sub="", accent_class=""):
    return f"""
    <div class="kpi-card {accent_class}">
        <div class="lbl">{label}</div>
        <div class="val">{value}</div>
        <div class="sub">{sub}</div>
    </div>
    """

def rate_accent(r):
    if r >= 35: return "accent-green"
    elif r >= 20: return "accent-amber"
    elif r >= 0: return "accent-rose"
    else: return "accent-red"

def section_title(text):
    st.markdown(f'<div class="section-title">{text}</div>', unsafe_allow_html=True)

def premium_banner(cls, text):
    emoji = "✅" if cls == "ok" else "⚠️" if cls == "warn" else "❌"
    st.markdown(f'<div class="banner-premium {cls}">{emoji} {text}</div>', unsafe_allow_html=True)

def parse_csv(f):
    content = f.read()
    for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            text = content.decode(enc)
            rows = list(csv.DictReader(io.StringIO(text)))
            if rows: return rows
        except: pass
    return []

def html_table(data_dict, extra_col=None):
    sorted_items = sorted(data_dict.items(), key=lambda x: -x[1]["revenue"])
    if not sorted_items:
        return "<div style='color:#94a3b8;font-size:13px;padding:24px;text-align:center;'>데이터가 없습니다.</div>"
        
    extra_header = f'<th style="text-align:right;">{extra_col[0]}</th>' if extra_col else ""
    
    rows_html = []
    for name, s in sorted_items:
        r = margin_rate(s)
        color = "#10b981" if r>=35 else "#f59e0b" if r>=20 else "#ef4444"
        
        extra_val = ""
        if extra_col:
            extra_val = f'<td style="text-align:right;font-weight:600;">{extra_col[1](s)}</td>'
            
        rows_html.append(f"""
        <tr>
            <td style="font-weight:600;color:#1e293b;">{name}</td>
            <td style="text-align:right;font-weight:500;">{fmt_won(s['revenue'])}</td>
            <td style="text-align:right;color:#64748b;">{fmt_won(s['cost'])}</td>
            <td style="text-align:right;font-weight:600;color:#0f172a;">{fmt_won(margin(s))}</td>
            <td style="text-align:right;font-weight:700;color:{color};">{r:.1f}%</td>
            <td style="text-align:right;color:#64748b;">{int(s['qty']):,}개</td>
            {extra_val}
        </tr>
        """)
        
    table_content = f"""
    <div class="custom-table-wrapper">
        <table class="custom-table">
            <thead>
                <tr>
                    <th>항목</th>
                    <th style="text-align:right;">순매출</th>
                    <th style="text-align:right;">공급원가</th>
                    <th style="text-align:right;">마진</th>
                    <th style="text-align:right;">마진율</th>
                    <th style="text-align:right;">수량</th>
                    {extra_header}
                </tr>
            </thead>
            <tbody>
                {"".join(rows_html)}
            </tbody>
        </table>
    </div>
    """
    st.markdown(table_content, unsafe_allow_html=True)


# ── 로그인 화면 ───────────────────────────────────────────────
def check_password():
    if st.session_state.get("auth"): return True
    
    st.markdown("""
    <div class="login-container">
        <div class="login-logo">📊</div>
        <div class="login-title">데드라 마진 리포트</div>
        <div class="login-sub">정밀 분석 대시보드 시스템</div>
    </div>
    """, unsafe_allow_html=True)
    
    _, col, _ = st.columns([1.2, 1, 1.2])
    with col:
        pw = st.text_input("비밀번호", type="password", label_visibility="collapsed", placeholder="비밀번호를 입력하세요")
        if st.button("보안 로그인", use_container_width=True, type="primary"):
            if pw == st.secrets.get("password", ""):
                st.session_state["auth"] = True
                st.rerun()
            else:
                st.error("비밀번호가 일치하지 않습니다.")
    return False


# ── 사이드바 ──────────────────────────────────────────────────
def sidebar():
    with st.sidebar:
        st.markdown("<div style='padding:10px 0 20px 0;'><h2 style='margin:0;'>📊 DEDRA Report</h2><p style='font-size:12px;color:#64748b;margin:4px 0 0 0;'>Margin Analyzer Pro</p></div>", unsafe_allow_html=True)
        st.markdown("<hr style='border-color:rgba(255,255,255,0.1);margin:0 0 20px 0'>", unsafe_allow_html=True)
        
        st.markdown("<p style='font-size:12px;font-weight:600;margin-bottom:8px;color:#94a3b8;'>주문 내역 파일 업로드</p>", unsafe_allow_html=True)
        uploaded = st.file_uploader(
            "CSV 업로드",
            type=["csv"],
            accept_multiple_files=True,
            help="카페24 주문 내역 CSV 파일을 선택하세요",
            label_visibility="collapsed",
        )
        st.caption("여러 개 파일을 드래그하여 한 번에 업로드할 수 있습니다.")
        st.markdown("<hr style='border-color:rgba(255,255,255,0.1);margin:20px 0'>", unsafe_allow_html=True)

        if st.button("🔓 시스템 로그아웃", use_container_width=True):
            st.session_state.clear()
            st.rerun()

        st.markdown(f"""
        <div style="margin-top:100px;font-size:11px;color:#475569;text-align:center;border-top:1px solid rgba(255,255,255,0.05);padding-top:16px;">
            DEDRA Dashboard v3.0<br>{datetime.now().strftime('%Y-%m-%d')}
        </div>
        """, unsafe_allow_html=True)
    return uploaded


# ── 메인 화면 ──────────────────────────────────────────────────
def main():
    if not check_password(): return
    uploaded = sidebar()

    if not uploaded:
        st.markdown("""
        <div style="text-align:center;padding:120px 0;background:white;border-radius:24px;border:1px dashed #cbd5e1;margin-top:20px;">
            <div style="font-size:64px;margin-bottom:20px;">📂</div>
            <div style="font-size:20px;font-weight:700;color:#334155">분석할 파일을 등록해 주세요</div>
            <div style="font-size:13px;color:#64748b;margin-top:8px;max-width:320px;margin-left:auto;margin-right:auto;line-height:1.5;">
                왼쪽 사이드바에서 카페24 주문 내역 CSV 파일을 업로드하면 정밀 마진 대시보드가 즉시 구성됩니다.
            </div>
        </div>
        """, unsafe_allow_html=True)
        return

    # 데이터 처리
    all_rows, file_names = [], []
    for f in uploaded:
        rows = parse_csv(f)
        if rows:
            all_rows.extend(rows)
            file_names.append(f.name)

    if not all_rows:
        premium_banner("err", "파일 데이터를 읽을 수 없습니다. 인코딩 형식을 확인해 주세요.")
        return

    with st.spinner("주문 내역 정밀 마진 분석 중..."):
        enriched = preprocess_rows(all_rows)
        data = aggregate(enriched)
        price_anomalies, outlet_items = detect_price_anomalies(enriched)
        discount_over, discount_buckets = detect_discount_anomalies(enriched)
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 상단 대시보드 헤더
    n = data["normal"]
    c = data["clearance"]
    total_rev  = n["revenue"]  + c["revenue"]
    total_cost = n["cost"]     + c["cost"]
    total_pg   = n["pg_fee"]   + c["pg_fee"]
    total_m    = total_rev - total_cost
    total_rate = (total_m / total_rev * 100) if total_rev else 0
    total_op   = total_m - total_pg
    total_op_r = (total_op / total_rev * 100) if total_rev else 0
    ds = data.get("ds", {})

    st.markdown(f"""
    <div class="dashboard-header">
        <div class="header-title">
            <h1>데드라 마진 분석 리포트</h1>
            <p>{len(file_names)}개 주문 파일 분석 완료 • 총 {len(all_rows):,}개 주문 항목</p>
        </div>
        <div style="font-size: 12px; color: #a5b4fc; text-align: right;">
            생성 시각: {generated_at}
        </div>
    </div>
    """, unsafe_allow_html=True)

    # 정보 배너 및 다운로드 버튼
    col_info, col_dl = st.columns([3, 1])
    with col_info:
        premium_banner("ok", f"분석 성공: {' / '.join(file_names)}")
    with col_dl:
        html_content = generate_html(
            data, price_anomalies, outlet_items,
            discount_over, discount_buckets,
            file_names[0] if file_names else "upload.csv",
            generated_at, enriched_rows=enriched
        )
        st.download_button(
            "⬇️ 원본 HTML 보고서 다운로드",
            data=html_content.encode("utf-8"),
            file_name=f"{datetime.now().strftime('%Y%m%d')}_마진리포트.html",
            mime="text/html",
            use_container_width=True,
        )

    # ── 핵심 KPI 대형 카드 그리드 (6열) ─────────────────────────
    st.markdown(f"""
    <div class="kpi-grid g6">
        {kpi_card("총 순매출", fmt_won(total_rev), "재고소진 매출 합산")}
        {kpi_card("총 마진", fmt_won(total_m), f"평균 마진율 {total_rate:.1f}%", rate_accent(total_rate))}
        {kpi_card("종합 마진율", fmt_rate(total_rate), "전체 데이터 기준", rate_accent(total_rate))}
        {kpi_card("PG 결제 수수료", fmt_won(total_pg), f"매출 대비 {(total_pg/total_rev*100) if total_rev else 0:.2f}%", "accent-rose")}
        {kpi_card("순 영업 이익", fmt_won(total_op), f"영업 이익률 {total_op_r:.1f}%", rate_accent(total_op_r))}
        {kpi_card("영업 이익률", fmt_rate(total_op_r), "수수료 공제 후", rate_accent(total_op_r))}
    </div>
    """, unsafe_allow_html=True)

    # ── 대시보드 탭 레이아웃 ──────────────────────────────────────
    t1, t2, t3, t4, t5 = st.tabs(["📊 상세 마진 분석", "🔍 판매가 이상 감지", "🏷️ 할인율 입체 분석", "💳 PG 수수료 명세", "📦 아울렛 & 재고소진"])

    # ── 탭 1: 상세 마진 분석 ──────────────────────────────────
    with t1:
        # 일반 / 재고소진 마진 성과 비교
        col_n, col_c = st.columns(2)
        with col_n:
            section_title("정상 판매 마진 성과")
            st.markdown(f"""
            <div class="kpi-grid g3">
                {kpi_card("순매출", fmt_won(n["revenue"]))}
                {kpi_card("평균 마진율", fmt_rate(margin_rate(n)), "정상 판매 기준", rate_accent(margin_rate(n)))}
                {kpi_card("판매 수량", f"{int(n['qty']):,}개")}
            </div>""", unsafe_allow_html=True)
            
            section_title("정상 판매 카테고리 성과 TOP")
            html_table(data["cat_normal"])
            
            section_title("정상 판매 공급처별 성과 TOP")
            html_table(data["supplier_normal"])
            
        with col_c:
            section_title("재고소진(아울렛/균일가) 마진 성과")
            st.markdown(f"""
            <div class="kpi-grid g3">
                {kpi_card("순매출", fmt_won(c["revenue"]))}
                {kpi_card("평균 마진율", fmt_rate(margin_rate(c)), "재고소진 기준", rate_accent(margin_rate(c)))}
                {kpi_card("판매 수량", f"{int(c['qty']):,}개")}
            </div>""", unsafe_allow_html=True)
            
            section_title("재고소진 카테고리 성과 TOP")
            html_table(data["cat_clearance"])
            
            section_title("재고소진 공급처별 성과 TOP")
            html_table(data["supplier_clearance"])

        # TOP/BOT 10
        st.markdown("<hr style='border-color:#e2e8f0;margin:24px 0'>", unsafe_allow_html=True)
        c1, c2 = st.columns(2)
        items = [(k, v) for k, v in data.get("product_normal", {}).items() if v["qty"] >= 2]
        
        with c1:
            section_title("최우수 상품 마진율 TOP 10 (정상 판매)")
            top = sorted(items, key=lambda x: -margin_rate(x[1]))[:10]
            if top:
                table_rows = []
                for idx, (n_p, s_p) in enumerate(top):
                    table_rows.append(f"""
                    <tr>
                        <td style="font-weight:600;width:40px;color:#6366f1;">#{idx+1}</td>
                        <td>{n_p}</td>
                        <td style="text-align:right;font-weight:500;">{fmt_won(s_p['revenue'])}</td>
                        <td style="text-align:right;font-weight:700;color:#10b981;">{margin_rate(s_p):.1f}%</td>
                        <td style="text-align:right;color:#64748b;">{int(s_p['qty'])}개</td>
                    </tr>
                    """)
                st.markdown(f"""
                <div class="custom-table-wrapper">
                    <table class="custom-table">
                        <thead>
                            <tr>
                                <th>순위</th>
                                <th>상품명</th>
                                <th style="text-align:right;">순매출</th>
                                <th style="text-align:right;">마진율</th>
                                <th style="text-align:right;">수량</th>
                            </tr>
                        </thead>
                        <tbody>{"".join(table_rows)}</tbody>
                    </table>
                </div>
                """, unsafe_allow_html=True)
                
        with c2:
            section_title("마진 저조/경고 상품 BOT 10 (정상 판매)")
            bot = sorted(items, key=lambda x: margin_rate(x[1]))[:10]
            if bot:
                table_rows = []
                for idx, (n_p, s_p) in enumerate(bot):
                    mr = margin_rate(s_p)
                    color = "#ef4444" if mr < 10 else "#f59e0b"
                    table_rows.append(f"""
                    <tr>
                        <td style="font-weight:600;width:40px;color:#f43f5e;">#{idx+1}</td>
                        <td>{n_p}</td>
                        <td style="text-align:right;font-weight:500;">{fmt_won(s_p['revenue'])}</td>
                        <td style="text-align:right;font-weight:700;color:{color};">{mr:.1f}%</td>
                        <td style="text-align:right;color:#64748b;">{int(s_p['qty'])}개</td>
                    </tr>
                    """)
                st.markdown(f"""
                <div class="custom-table-wrapper">
                    <table class="custom-table">
                        <thead>
                            <tr>
                                <th>순위</th>
                                <th>상품명</th>
                                <th style="text-align:right;">순매출</th>
                                <th style="text-align:right;">마진율</th>
                                <th style="text-align:right;">수량</th>
                            </tr>
                        </thead>
                        <tbody>{"".join(table_rows)}</tbody>
                    </table>
                </div>
                """, unsafe_allow_html=True)

    # ── 탭 2: 판매가 이상 감지 ────────────────────────────────
    with t2:
        col1, col2 = st.columns(2)
        with col1:
            section_title("이상 판매가 탐지 내역 (정가 미달 등)")
            if not price_anomalies:
                premium_banner("ok", "비정상 가격으로 결제된 주문 건이 없습니다.")
            else:
                premium_banner("err", f"총 {len(price_anomalies)}건의 비정상 가격 결제 건이 발견되었습니다.")
                rows = []
                for a in price_anomalies:
                    rows.append(f"""
                    <tr>
                        <td style="font-weight:600;color:#4f46e5;">{a['주문번호']}</td>
                        <td>{a['상품명']}</td>
                        <td style="color:#64748b;">{a['브랜드']}</td>
                        <td style="text-align:right;font-weight:600;">{fmt_won(a['판매가'])}</td>
                        <td style="text-align:right;color:#94a3b8;">{fmt_won(a['기준가'])}</td>
                        <td style="text-align:right;font-weight:700;color:#ef4444;">{fmt_won(a['차이'])}</td>
                    </tr>
                    """)
                st.markdown(f"""
                <div class="custom-table-wrapper">
                    <table class="custom-table">
                        <thead>
                            <tr>
                                <th>주문번호</th>
                                <th>상품명</th>
                                <th>브랜드</th>
                                <th style="text-align:right;">판매가</th>
                                <th style="text-align:right;">정상 기준가</th>
                                <th style="text-align:right;">차액</th>
                            </tr>
                        </thead>
                        <tbody>{"".join(rows)}</tbody>
                    </table>
                </div>
                """, unsafe_allow_html=True)
                
        with col2:
            section_title("아울렛 전용 상품 판매 현황")
            if not outlet_items:
                premium_banner("ok", "아울렛 전용 상품 판매 내역이 없습니다.")
            else:
                rows = []
                for a in outlet_items:
                    rows.append(f"""
                    <tr>
                        <td style="font-weight:600;color:#1e293b;">{a['상품명']}</td>
                        <td style="color:#64748b;">{a['브랜드']}</td>
                        <td style="text-align:right;font-weight:600;">{fmt_won(a['판매가'])}</td>
                        <td style="text-align:right;font-weight:700;color:#4f46e5;">{a['원가회수율']:.1f}%</td>
                    </tr>
                    """)
                st.markdown(f"""
                <div class="custom-table-wrapper">
                    <table class="custom-table">
                        <thead>
                            <tr>
                                <th>상품명</th>
                                <th>브랜드</th>
                                <th style="text-align:right;">판매가</th>
                                <th style="text-align:right;">원가회수율</th>
                            </tr>
                        </thead>
                        <tbody>{"".join(rows)}</tbody>
                    </table>
                </div>
                """, unsafe_allow_html=True)

        # 쿠폰 오남용 경고
        st.markdown("<hr style='border-color:#e2e8f0;margin:24px 0'>", unsafe_allow_html=True)
        section_title("재고소진 쿠폰 오남용 위험 주문")
        cw = data.get("coupon_warnings", [])
        if not cw:
            premium_banner("ok", "원가 회수 범위를 넘어서는 부적절한 쿠폰 사용 건이 없습니다.")
        else:
            premium_banner("err", f"총 {len(cw)}건의 원가 미회수 위험 주문이 검출되었습니다. (아울렛에 쿠폰 중복 적용 등)")
            rows = []
            for w in cw:
                rows.append(f"""
                <tr>
                    <td style="font-weight:600;color:#4f46e5;">{w['주문번호']}</td>
                    <td style="color:#64748b;">{w['카테고리']}</td>
                    <td>{w['상품명']}</td>
                    <td style="font-weight:600;color:#ef4444;">{w['쿠폰명']}</td>
                    <td style="text-align:right;font-weight:700;color:#ef4444;">{fmt_won(w['쿠폰할인액'])}</td>
                </tr>
                """)
            st.markdown(f"""
            <div class="custom-table-wrapper">
                <table class="custom-table">
                    <thead>
                        <tr>
                            <th>주문번호</th>
                            <th>카테고리</th>
                            <th>상품명</th>
                            <th>적용 쿠폰</th>
                            <th style="text-align:right;">쿠폰할인액</th>
                        </tr>
                    </thead>
                    <tbody>{"".join(rows)}</tbody>
                </table>
            </div>
            """, unsafe_allow_html=True)

    # ── 탭 3: 할인율 입체 분석 ────────────────────────────────
    with t3:
        pur   = ds.get("purchase", 0.0)
        coup  = ds.get("coupon", 0.0)
        grade = ds.get("grade", 0.0)
        pdisc = ds.get("prod_disc", 0.0)
        pts   = ds.get("points", 0.0)
        nvr   = ds.get("naver_pt", 0.0)
        tot_disc = coup + grade + pdisc
        disc_pct = (tot_disc / pur * 100) if pur else 0.0

        st.markdown(f"""
        <div class="kpi-grid g4">
            {kpi_card("총 주문액 (소비자가)", fmt_won(pur), "할인 전 원금")}
            {kpi_card("총 할인 지원액", fmt_won(tot_disc), f"평균 할인율 {disc_pct:.1f}%", "accent-amber")}
            {kpi_card("결제 적립금 사용액", fmt_won(pts), "매출 분석 제외")}
            {kpi_card("네이버페이 포인트", fmt_won(nvr), "순매출에 정상 합산", "accent-green")}
        </div>
        <div class="kpi-grid g3">
            {kpi_card("쿠폰 할인 상세", fmt_won(coup), f"원금 대비 {(coup/pur*100) if pur else 0:.1f}%")}
            {kpi_card("회원등급 할인 상세", fmt_won(grade), f"원금 대비 {(grade/pur*100) if pur else 0:.1f}%")}
            {kpi_card("상품 즉시 할인 상세", fmt_won(pdisc), f"원금 대비 {(pdisc/pur*100) if pur else 0:.1f}%")}
        </div>
        """, unsafe_allow_html=True)

        col_left, col_right = st.columns([1, 2])
        with col_left:
            section_title("주문별 할인율 구간 분포")
            rows = []
            for k, v in discount_buckets.items():
                rows.append(f"""
                <tr>
                    <td style="font-weight:600;">{k}</td>
                    <td style="text-align:right;font-weight:600;color:#4f46e5;">{v}건</td>
                </tr>
                """)
            st.markdown(f"""
            <div class="custom-table-wrapper">
                <table class="custom-table">
                    <thead>
                        <tr>
                            <th>할인율 범위</th>
                            <th style="text-align:right;">주문 건수</th>
                        </tr>
                    </thead>
                    <tbody>{"".join(rows)}</tbody>
                </table>
            </div>
            """, unsafe_allow_html=True)
            
        with col_right:
            section_title("고할인율 경고 주문 (25% 초과)")
            if not discount_over:
                premium_banner("ok", "25%를 초과하는 고할인율 결제 건이 없습니다.")
            else:
                premium_banner("warn", f"25%를 초과하는 고할인율 주문이 {len(discount_over)}건 발견되었습니다.")
                rows = []
                for o in discount_over:
                    rows.append(f"""
                    <tr>
                        <td style="font-weight:600;color:#4f46e5;">{o['주문번호']}</td>
                        <td>{o['상품명']}</td>
                        <td style="color:#64748b;">{o['브랜드']}</td>
                        <td style="text-align:right;">{fmt_won(o['판매가'])}</td>
                        <td style="text-align:right;font-weight:600;color:#ef4444;">{fmt_won(o['할인금액'])}</td>
                        <td style="text-align:right;font-weight:700;color:#ef4444;">{o['할인율']:.1f}%</td>
                        <td style="font-size:11px;color:#64748b;">{o['쿠폰명']}</td>
                    </tr>
                    """)
                st.markdown(f"""
                <div class="custom-table-wrapper">
                    <table class="custom-table">
                        <thead>
                            <tr>
                                <th>주문번호</th>
                                <th>상품명</th>
                                <th>브랜드</th>
                                <th style="text-align:right;">실구매가</th>
                                <th style="text-align:right;">할인액</th>
                                <th style="text-align:right;">할인율</th>
                                <th>적용쿠폰</th>
                            </tr>
                        </thead>
                        <tbody>{"".join(rows)}</tbody>
                    </table>
                </div>
                """, unsafe_allow_html=True)

    # ── 탭 4: PG 수수료 명세 ──────────────────────────────────
    with t4:
        pg_by = data.get("pg_by_payment", {})
        pg_pct = (total_pg / total_rev * 100) if total_rev else 0

        st.markdown(f"""
        <div class="kpi-grid g4">
            {kpi_card("총 PG 결제 대행 수수료", fmt_won(total_pg), f"평균 수수료율 {pg_pct:.2f}%", "accent-rose")}
            {kpi_card("영업 이익 (수수료 공제 후)", fmt_won(total_op), f"실제 이익률 {total_op_r:.1f}%", rate_accent(total_op_r))}
            {kpi_card("분석 대상 순매출", fmt_won(total_rev))}
            {kpi_card("소요 공급 원가", fmt_won(total_cost))}
        </div>
        """, unsafe_allow_html=True)

        section_title("결제 수단 및 대행사별 상세 PG 수수료")
        pg_rows = sorted(pg_by.items(), key=lambda x: -x[1]["revenue"])
        if pg_rows:
            rows = []
            for name, s in pg_rows:
                rows.append(f"""
                <tr>
                    <td style="font-weight:600;color:#0f172a;">{name}</td>
                    <td style="text-align:right;font-weight:500;">{fmt_won(s['revenue'])}</td>
                    <td style="text-align:right;color:#64748b;">{s['rate']*100:.2f}%</td>
                    <td style="text-align:right;font-weight:600;color:#ef4444;">{fmt_won(s['pg_fee'])}</td>
                    <td style="text-align:right;color:#64748b;">{s['count']:,}건</td>
                </tr>
                """)
            st.markdown(f"""
            <div class="custom-table-wrapper">
                <table class="custom-table">
                    <thead>
                        <tr>
                            <th>결제 수단 / 대행사</th>
                            <th style="text-align:right;">결제액(순매출)</th>
                            <th style="text-align:right;">대행 수수료율</th>
                            <th style="text-align:right;">공제 수수료</th>
                            <th style="text-align:right;">결제 건수</th>
                        </tr>
                    </thead>
                    <tbody>{"".join(rows)}</tbody>
                </table>
            </div>
            """, unsafe_allow_html=True)

        # 영업이익 산식 도식화
        section_title("실 영업이익 산출 공식 흐름")
        st.markdown(f"""
        <div style="background:white;border-radius:16px;border:1px solid #e2e8f0;padding:24px 32px;font-size:14px;line-height:2.2;box-shadow:0 4px 6px -1px rgba(15,23,42,0.02)">
            <div style="display:flex; justify-content:space-between; border-bottom:1px solid #f1f5f9; padding-bottom:8px; margin-bottom:8px;">
                <span style="color:#475569">주문 순매출 합계 (A)</span>
                <span style="font-weight:700; color:#0f172a;">{fmt_won(total_rev)}</span>
            </div>
            <div style="display:flex; justify-content:space-between; border-bottom:1px solid #f1f5f9; padding-bottom:8px; margin-bottom:8px;">
                <span style="color:#ef4444; padding-left:16px;">− 공급원가 합계 (B)</span>
                <span style="font-weight:700; color:#ef4444;">{fmt_won(total_cost)}</span>
            </div>
            <div style="display:flex; justify-content:space-between; border-bottom:2px solid #cbd5e1; padding-bottom:10px; margin-bottom:10px; font-size:15px; font-weight:600;">
                <span style="color:#0f172a;">= 순 마진 총액 (C = A − B)</span>
                <span style="color:#4f46e5;">{fmt_won(total_m)} &nbsp;<small style="font-size:11px;color:#94a3b8;font-weight:normal;">(평균 마진율: {total_rate:.1f}%)</small></span>
            </div>
            <div style="display:flex; justify-content:space-between; border-bottom:1px solid #f1f5f9; padding-bottom:8px; margin-bottom:8px;">
                <span style="color:#ef4444; padding-left:16px;">− PG 결제수수료 공제 (D)</span>
                <span style="font-weight:700; color:#ef4444;">{fmt_won(total_pg)} &nbsp;<small style="font-size:11px;color:#94a3b8;font-weight:normal;">(실질 수수료율: {pg_pct:.2f}%)</small></span>
            </div>
            <div style="display:flex; justify-content:space-between; font-size:16px; font-weight:800; padding-top:4px;">
                <span style="color:#0f172a;">= 최종 영업 이익 (E = C − D)</span>
                <span style="color:{'#10b981' if total_op_r>=20 else '#ef4444'}; font-size:18px;">{fmt_won(total_op)} &nbsp;<small style="font-size:12px;color:#94a3b8;font-weight:normal;">(최종 이익률: {total_op_r:.1f}%)</small></span>
            </div>
        </div>
        """, unsafe_allow_html=True)

    # ── 탭 5: 아울렛 & 재고소진 ────────────────────────────────
    with t5:
        for cat in ["아울렛", "▶균일가 모음전◀"]:
            cat_stat = data["cat_clearance"].get(cat)
            if not cat_stat: continue
            
            section_title(f"📦 재고소진 특별 분류 : {cat}")
            r = margin_rate(cat_stat)
            rec_r = recovery_rate(cat_stat)
            
            st.markdown(f"""
            <div class="kpi-grid g4" style="margin-bottom:16px;">
                {kpi_card("순매출", fmt_won(cat_stat["revenue"]))}
                {kpi_card("순마진", fmt_won(margin(cat_stat)), f"마진율: {r:.1f}%", rate_accent(r))}
                {kpi_card("원가 회수율", fmt_rate(rec_r), "목표 100% 대비 수치", "accent-green" if rec_r>=100 else "accent-amber")}
                {kpi_card("판매 수량", f"{int(cat_stat['qty']):,}개")}
            </div>
            """, unsafe_allow_html=True)
            
            products = data["product_by_clearance_cat"].get(cat, {})
            if products:
                section_title(f"{cat} 카테고리 내 상품별 상세 실적")
                html_table(products, extra_col=("원가회수율", lambda s: fmt_rate(recovery_rate(s))))


if __name__ == "__main__":
    main()
