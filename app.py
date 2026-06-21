"""
데드라 마진 리포트 — Streamlit 웹 앱 v2
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

# ── 페이지 설정 ───────────────────────────────────────────────
st.set_page_config(
    page_title="데드라 마진 리포트",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 전역 CSS ─────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+KR:wght@400;500;600;700&display=swap');
*, [class*="css"] { font-family: 'Noto Sans KR', sans-serif !important; }

/* 전체 배경 */
[data-testid="stAppViewContainer"] { background: #f0f2f8; }
[data-testid="stSidebar"] { background: #1a1a2e !important; }
[data-testid="stSidebar"] * { color: #e0e0e0 !important; }
[data-testid="stSidebar"] h1, [data-testid="stSidebar"] h2, [data-testid="stSidebar"] h3 { color: white !important; }

/* 사이드바 업로드 위젯 */
[data-testid="stSidebar"] [data-testid="stFileUploader"] section {
    background: rgba(255,255,255,0.08);
    border: 1.5px dashed rgba(255,255,255,0.3) !important;
    border-radius: 10px;
}
[data-testid="stSidebar"] [data-testid="stFileUploader"] section:hover {
    border-color: rgba(255,255,255,0.6) !important;
    background: rgba(255,255,255,0.12);
}

/* KPI 카드 */
.kpi-grid { display: grid; gap: 10px; margin-bottom: 16px; }
.g2 { grid-template-columns: repeat(2, 1fr); }
.g3 { grid-template-columns: repeat(3, 1fr); }
.g4 { grid-template-columns: repeat(4, 1fr); }
.g6 { grid-template-columns: repeat(6, 1fr); }
.kc {
    background: white;
    border-radius: 10px;
    padding: 14px 16px;
    border-left: 3px solid #1a1a2e;
    box-shadow: 0 1px 4px rgba(0,0,0,.06);
}
.kc .lbl { font-size: 10px; color: #999; font-weight: 600; text-transform: uppercase; letter-spacing: .5px; margin-bottom: 4px; }
.kc .val { font-size: 18px; font-weight: 700; color: #1a1a2e; line-height: 1.2; }
.kc .sub { font-size: 10px; color: #bbb; margin-top: 3px; }

/* 섹션 헤더 */
.sh {
    font-size: 13px; font-weight: 700; color: #455a64;
    border-left: 3px solid #455a64; padding: 3px 0 3px 10px;
    margin: 16px 0 8px; text-transform: uppercase; letter-spacing: .5px;
}

/* 알림 배너 */
.ok   { background:#e8f5e9; border-left:3px solid #2e7d32; padding:8px 14px; border-radius:0 6px 6px 0; font-size:12px; color:#1b5e20; }
.warn { background:#fff8e1; border-left:3px solid #f9a825; padding:8px 14px; border-radius:0 6px 6px 0; font-size:12px; color:#6d4c00; }
.err  { background:#ffebee; border-left:3px solid #c62828; padding:8px 14px; border-radius:0 6px 6px 0; font-size:12px; color:#b71c1c; }

/* 테이블 스타일 개선 */
[data-testid="stDataFrame"] { border-radius: 8px; overflow: hidden; }

/* 로그인 */
.login-box {
    max-width: 380px; margin: 100px auto 0;
    background: white; border-radius: 16px;
    padding: 40px 32px; box-shadow: 0 8px 32px rgba(0,0,0,.12);
    text-align: center;
}

/* 탭 스타일 */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    background: white;
    border-radius: 10px;
    padding: 4px;
    gap: 2px;
    margin-bottom: 12px;
    box-shadow: 0 1px 4px rgba(0,0,0,.06);
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    border-radius: 7px !important;
    font-size: 13px !important;
    font-weight: 600 !important;
    padding: 6px 14px !important;
}

/* 여백 최소화 */
.block-container { padding-top: 1rem !important; padding-bottom: 1rem !important; }
[data-testid="stVerticalBlock"] > div { gap: 8px !important; }
</style>
""", unsafe_allow_html=True)


# ── 유틸 ─────────────────────────────────────────────────────
def kc(label, value, sub="", accent="#1a1a2e"):
    return (f'<div class="kc" style="border-left-color:{accent}">'
            f'<div class="lbl">{label}</div>'
            f'<div class="val" style="color:{accent}">{value}</div>'
            f'{"<div class=sub>" + sub + "</div>" if sub else ""}'
            f'</div>')

def rate_color(r):
    return "#2e7d32" if r>=35 else "#f57f17" if r>=20 else "#e65100" if r>=0 else "#c62828"

def sh(text):  # 섹션 헤더
    st.markdown(f'<div class="sh">{text}</div>', unsafe_allow_html=True)

def banner(cls, text):
    st.markdown(f'<div class="{cls}">{text}</div>', unsafe_allow_html=True)

def parse_csv(f):
    content = f.read()
    for enc in ("utf-8-sig", "utf-8", "cp949", "euc-kr"):
        try:
            text = content.decode(enc)
            rows = list(csv.DictReader(io.StringIO(text)))
            if rows: return rows
        except: pass
    return []

def margin_table(data_dict, extra_col=None):
    rows = []
    for name, s in sorted(data_dict.items(), key=lambda x: -x[1]["revenue"]):
        r = margin_rate(s)
        row = {
            "항목": name,
            "순매출": f"{s['revenue']:,.0f}",
            "공급원가": f"{s['cost']:,.0f}",
            "마진": f"{margin(s):,.0f}",
            "마진율": f"{r:.1f}%",
            "수량": f"{int(s['qty']):,}개",
        }
        if extra_col:
            row[extra_col[0]] = extra_col[1](s)
        rows.append(row)
    if rows:
        st.dataframe(rows, use_container_width=True, hide_index=True, height=min(200, 36 + 35*len(rows)))


# ── 인증 ─────────────────────────────────────────────────────
def check_password():
    if st.session_state.get("auth"): return True
    st.markdown("""
    <div class="login-box">
        <div style="font-size:44px">📊</div>
        <h2 style="font-size:20px;font-weight:700;color:#1a1a2e;margin:8px 0 4px">데드라 마진 리포트</h2>
        <p style="font-size:12px;color:#aaa;margin-bottom:20px">팀 내부 전용 시스템</p>
    </div>
    """, unsafe_allow_html=True)
    _, col, _ = st.columns([1, 1.2, 1])
    with col:
        pw = st.text_input("비밀번호", type="password", label_visibility="collapsed", placeholder="비밀번호 입력")
        if st.button("로그인", use_container_width=True, type="primary"):
            if pw == st.secrets.get("password", ""):
                st.session_state["auth"] = True
                st.rerun()
            else:
                st.error("비밀번호가 틀렸습니다.")
    return False


# ── 사이드바 ──────────────────────────────────────────────────
def sidebar():
    with st.sidebar:
        st.markdown("## 📊 데드라 리포트")
        st.markdown("<hr style='border-color:rgba(255,255,255,0.15);margin:8px 0 16px'>", unsafe_allow_html=True)
        uploaded = st.file_uploader(
            "CSV 업로드",
            type=["csv"],
            accept_multiple_files=True,
            help="카페24 주문 내역 CSV",
            label_visibility="collapsed",
        )
        st.caption("카페24 주문 내역 CSV 파일을\n드래그하거나 클릭하여 업로드")
        st.markdown("<hr style='border-color:rgba(255,255,255,0.1);margin:16px 0'>", unsafe_allow_html=True)

        if st.button("🔓 로그아웃", use_container_width=True):
            st.session_state.clear()
            st.rerun()

        st.markdown(f"""
        <div style="margin-top:auto;padding-top:20px;font-size:11px;color:rgba(255,255,255,0.3);text-align:center">
            데드라 마진 리포트 v2.0<br>{datetime.now().strftime('%Y-%m-%d')}
        </div>
        """, unsafe_allow_html=True)
    return uploaded


# ── 메인 ─────────────────────────────────────────────────────
def main():
    if not check_password(): return
    uploaded = sidebar()

    if not uploaded:
        st.markdown("""
        <div style="text-align:center;padding:80px 0;color:#bbb">
            <div style="font-size:56px;margin-bottom:16px">📂</div>
            <div style="font-size:18px;font-weight:600;color:#888">왼쪽 사이드바에서 CSV를 업로드하세요</div>
            <div style="font-size:13px;margin-top:8px">카페24 주문 내역 CSV 파일을 지원합니다</div>
        </div>
        """, unsafe_allow_html=True)
        return

    # 데이터 로드
    all_rows, file_names = [], []
    for f in uploaded:
        rows = parse_csv(f)
        if rows:
            all_rows.extend(rows)
            file_names.append(f.name)

    if not all_rows:
        banner("err", "❌ 읽을 수 있는 데이터가 없습니다. 파일 인코딩을 확인하세요.")
        return

    with st.spinner("리포트 생성 중..."):
        enriched = preprocess_rows(all_rows)
        data = aggregate(enriched)
        price_anomalies, outlet_items = detect_price_anomalies(enriched)
        discount_over, discount_buckets = detect_discount_anomalies(enriched)
        generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    # 상단 바
    n = data["normal"];  c = data["clearance"]
    total_rev  = n["revenue"]  + c["revenue"]
    total_cost = n["cost"]     + c["cost"]
    total_pg   = n["pg_fee"]   + c["pg_fee"]
    total_m    = total_rev - total_cost
    total_rate = (total_m / total_rev * 100) if total_rev else 0
    total_op   = total_m - total_pg
    total_op_r = (total_op / total_rev * 100) if total_rev else 0
    ds = data.get("ds", {})

    # 파일 정보 + 다운로드 버튼
    col_info, col_dl = st.columns([3, 1])
    with col_info:
        banner("ok", f"✅ {len(file_names)}개 파일 · {len(all_rows):,}행 · {generated_at} 생성")
    with col_dl:
        html_content = generate_html(
            data, price_anomalies, outlet_items,
            discount_over, discount_buckets,
            file_names[0] if file_names else "upload.csv",
            generated_at, enriched_rows=enriched
        )
        st.download_button(
            "⬇️ HTML 다운로드",
            data=html_content.encode("utf-8"),
            file_name=f"{datetime.now().strftime('%Y%m%d')}_마진리포트.html",
            mime="text/html",
            use_container_width=True,
        )

    # ── 핵심 KPI 6칸 ──────────────────────────────────────────
    st.markdown(f"""
    <div class="kpi-grid g6">
        {kc("순매출", fmt_won(total_rev), "재고소진 포함")}
        {kc("마진", fmt_won(total_m), f"마진율 {total_rate:.1f}%", rate_color(total_rate))}
        {kc("마진율", fmt_rate(total_rate), "전체 기준", rate_color(total_rate))}
        {kc("PG수수료", fmt_won(total_pg), f"순매출 대비 {(total_pg/total_rev*100) if total_rev else 0:.2f}%", "#c62828")}
        {kc("영업이익", fmt_won(total_op), f"영업이익률 {total_op_r:.1f}%", rate_color(total_op_r))}
        {kc("영업이익률", fmt_rate(total_op_r), "순매출 기준", rate_color(total_op_r))}
    </div>
    """, unsafe_allow_html=True)

    # ── 탭 ────────────────────────────────────────────────────
    t1, t2, t3, t4, t5 = st.tabs(["📊 마진 분석", "🔍 이상 감지", "🏷️ 할인 분석", "💳 PG수수료", "📦 재고소진"])

    # ── 탭1: 마진 분석 ────────────────────────────────────────
    with t1:
        # 일반 / 재고소진 비교
        c1, c2 = st.columns(2)
        with c1:
            st.markdown(f"""
            <div class="kpi-grid g3">
                {kc("순매출(일반)", fmt_won(n["revenue"]))}
                {kc("마진율", fmt_rate(margin_rate(n)), rate_color(margin_rate(n))+" 기준", rate_color(margin_rate(n)))}
                {kc("수량", f"{int(n['qty']):,}개")}
            </div>""", unsafe_allow_html=True)
            sh("카테고리별 마진 (일반)")
            margin_table(data["cat_normal"])
            sh("공급사별 마진 (일반)")
            margin_table(data["supplier_normal"])
        with c2:
            st.markdown(f"""
            <div class="kpi-grid g3">
                {kc("순매출(재고소진)", fmt_won(c["revenue"]))}
                {kc("마진율", fmt_rate(margin_rate(c)), rate_color(margin_rate(c))+" 기준", rate_color(margin_rate(c)))}
                {kc("수량", f"{int(c['qty']):,}개")}
            </div>""", unsafe_allow_html=True)
            sh("카테고리별 마진 (재고소진)")
            margin_table(data["cat_clearance"])
            sh("공급사별 마진 (재고소진)")
            margin_table(data["supplier_clearance"])

        # TOP/BOT 10
        c1, c2 = st.columns(2)
        items = [(k,v) for k,v in data.get("product_normal",{}).items() if v["qty"]>=2]
        with c1:
            sh("마진율 TOP 10 상품")
            top = sorted(items, key=lambda x: -margin_rate(x[1]))[:10]
            if top:
                st.dataframe([{"상품명":n,"순매출":f"{s['revenue']:,.0f}","마진율":f"{margin_rate(s):.1f}%","수량":f"{int(s['qty']):,}개"} for n,s in top],
                             use_container_width=True, hide_index=True, height=390)
        with c2:
            sh("마진율 하위 10 상품 ⚠️")
            bot = sorted(items, key=lambda x: margin_rate(x[1]))[:10]
            if bot:
                st.dataframe([{"상품명":n,"순매출":f"{s['revenue']:,.0f}","마진율":f"{margin_rate(s):.1f}%","수량":f"{int(s['qty']):,}개"} for n,s in bot],
                             use_container_width=True, hide_index=True, height=390)

    # ── 탭2: 이상 감지 ────────────────────────────────────────
    with t2:
        c1, c2 = st.columns(2)
        with c1:
            sh("판매가 이상 감지")
            if not price_anomalies:
                banner("ok", "✅ 이상 없음")
            else:
                banner("err", f"⚠️ {len(price_anomalies)}건 발견")
                st.dataframe([{
                    "주문번호": a["주문번호"], "상품명": a["상품명"], "브랜드": a["브랜드"],
                    "판매가": f"{a['판매가']:,.0f}", "기준가": f"{a['기준가']:,.0f}",
                    "차이": f"{a['차이']:,.0f}",
                } for a in price_anomalies], use_container_width=True, hide_index=True)
        with c2:
            sh("아울렛 판매가 현황")
            if not outlet_items:
                banner("ok", "✅ 아울렛 판매 없음")
            else:
                st.dataframe([{
                    "상품명": a["상품명"], "브랜드": a["브랜드"],
                    "판매가": f"{a['판매가']:,.0f}", "원가회수율": f"{a['원가회수율']:.1f}%",
                } for a in outlet_items], use_container_width=True, hide_index=True)

        cw = data.get("coupon_warnings", [])
        sh("재고소진 쿠폰 경고")
        if not cw:
            banner("ok", "✅ 재고소진 쿠폰 적용 없음")
        else:
            banner("err", f"⚠️ {len(cw)}건 — 원가 미회수 위험")
            st.dataframe([{"주문번호":w["주문번호"],"카테고리":w["카테고리"],"상품명":w["상품명"],
                           "쿠폰명":w["쿠폰명"],"쿠폰할인액":f"{w['쿠폰할인액']:,.0f}"} for w in cw],
                        use_container_width=True, hide_index=True)

    # ── 탭3: 할인 분석 ────────────────────────────────────────
    with t3:
        pur   = ds.get("purchase", 0.0)
        coup  = ds.get("coupon", 0.0)
        grade = ds.get("grade", 0.0)
        pdisc = ds.get("prod_disc", 0.0)
        pts   = ds.get("points", 0.0)
        dep   = ds.get("deposit", 0.0)
        nvr   = ds.get("naver_pt", 0.0)
        tot_disc = coup + grade + pdisc
        disc_pct = (tot_disc / pur * 100) if pur else 0.0

        st.markdown(f"""
        <div class="kpi-grid g4">
            {kc("총 주문금액", fmt_won(pur))}
            {kc("총 할인금액", fmt_won(tot_disc), f"할인율 {disc_pct:.1f}%", "#f57f17")}
            {kc("적립금 사용", fmt_won(pts), "결제수단")}
            {kc("네이버포인트", fmt_won(nvr), "순매출 가산", "#2e7d32")}
        </div>
        <div class="kpi-grid g3">
            {kc("쿠폰 할인", fmt_won(coup), f"{(coup/pur*100) if pur else 0:.1f}%", "#ef6c00")}
            {kc("회원등급 할인", fmt_won(grade), f"{(grade/pur*100) if pur else 0:.1f}%", "#ef6c00")}
            {kc("상품별 추가할인", fmt_won(pdisc), f"{(pdisc/pur*100) if pur else 0:.1f}%", "#ef6c00")}
        </div>
        """, unsafe_allow_html=True)

        c1, c2 = st.columns([1, 2])
        with c1:
            sh("할인율 구간 분포")
            st.dataframe([{"구간":k,"건수":v} for k,v in discount_buckets.items()],
                        use_container_width=True, hide_index=True, height=220)
        with c2:
            sh("할인율 25% 초과 주문")
            if not discount_over:
                banner("ok", "✅ 25% 초과 주문 없음")
            else:
                banner("warn", f"⚠️ {len(discount_over)}건")
                st.dataframe([{
                    "주문번호":o["주문번호"],"상품명":o["상품명"],"브랜드":o["브랜드"],
                    "판매가":f"{o['판매가']:,.0f}","할인금액":f"{o['할인금액']:,.0f}",
                    "할인율":f"{o['할인율']:.1f}%","쿠폰명":o["쿠폰명"],
                } for o in discount_over], use_container_width=True, hide_index=True)

    # ── 탭4: PG수수료 ─────────────────────────────────────────
    with t4:
        pg_by = data.get("pg_by_payment", {})
        pg_pct = (total_pg / total_rev * 100) if total_rev else 0

        st.markdown(f"""
        <div class="kpi-grid g4">
            {kc("총 PG수수료", fmt_won(total_pg), f"순매출 대비 {pg_pct:.2f}%", "#c62828")}
            {kc("영업이익", fmt_won(total_op), f"영업이익률 {total_op_r:.1f}%", rate_color(total_op_r))}
            {kc("순매출", fmt_won(total_rev))}
            {kc("공급원가", fmt_won(total_cost))}
        </div>
        """, unsafe_allow_html=True)

        sh("결제업체별 PG수수료")
        pg_rows = sorted(pg_by.items(), key=lambda x: -x[1]["revenue"])
        if pg_rows:
            st.dataframe([{
                "결제업체": name,
                "순매출": f"{s['revenue']:,.0f}",
                "수수료율": f"{s['rate']*100:.2f}%",
                "PG수수료": f"{s['pg_fee']:,.0f}",
                "건수": f"{s['count']:,}건",
            } for name, s in pg_rows], use_container_width=True, hide_index=True)

        # 영업이익 계산식
        sh("영업이익 계산")
        st.markdown(f"""
        <div style="background:white;border-radius:10px;padding:16px 20px;font-size:13px;line-height:2.2;box-shadow:0 1px 4px rgba(0,0,0,.06)">
            <span style="color:#555">순매출</span> &nbsp;<b>{fmt_won(total_rev)}</b><br>
            <span style="color:#555;padding-left:16px">− 공급원가</span> &nbsp;<b>{fmt_won(total_cost)}</b><br>
            <span style="color:#1a1a2e;font-weight:700">= 마진</span> &nbsp;<b>{fmt_won(total_m)}</b> &nbsp;<span style="color:#aaa;font-size:11px">({total_rate:.1f}%)</span><br>
            <span style="color:#555;padding-left:16px">− PG수수료</span> &nbsp;<b>{fmt_won(total_pg)}</b> &nbsp;<span style="color:#aaa;font-size:11px">({pg_pct:.2f}%)</span><br>
            <span style="font-weight:700;color:{rate_color(total_op_r)}">= 영업이익</span> &nbsp;<b style="color:{rate_color(total_op_r)}">{fmt_won(total_op)}</b> &nbsp;<span style="color:#aaa;font-size:11px">({total_op_r:.1f}%)</span>
        </div>
        """, unsafe_allow_html=True)

    # ── 탭5: 재고소진 ─────────────────────────────────────────
    with t5:
        for cat in ["아울렛", "▶균일가 모음전◀"]:
            cat_stat = data["cat_clearance"].get(cat)
            if not cat_stat: continue
            r = margin_rate(cat_stat)
            from dedra_daily_report import recovery_rate
            c1, c2, c3, c4 = st.columns(4)
            sh(f"📦 {cat}")
            st.markdown(f"""
            <div class="kpi-grid g4">
                {kc("순매출", fmt_won(cat_stat["revenue"]))}
                {kc("마진", fmt_won(margin(cat_stat)), f"마진율 {r:.1f}%", rate_color(r))}
                {kc("원가회수율", fmt_rate(recovery_rate(cat_stat)))}
                {kc("수량", f"{int(cat_stat['qty']):,}개")}
            </div>
            """, unsafe_allow_html=True)
            products = data["product_by_clearance_cat"].get(cat, {})
            if products:
                margin_table(products, extra_col=("원가회수율", lambda s: fmt_rate(recovery_rate(s))))


if __name__ == "__main__":
    main()
