"""
데드라 마진 리포트 — Streamlit 웹 앱 Premium v3
"""

import io, csv, sys, os
import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
from dedra_daily_report import (
    preprocess_rows, aggregate,
    detect_price_anomalies, detect_discount_anomalies,
    generate_html, margin, margin_rate, fmt_won, fmt_rate,
)
from dedra_daily_report import (
    recovery_rate, compute_refund_stats,
    safe_float, parse_brand, PENDING_STATUS,
)

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
.g7 { grid-template-columns: repeat(7, 1fr); }

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
    /* 긴 표는 세로 스크롤, 좁은 화면에선 가로 스크롤 */
    max-height: 460px;
    overflow: auto;
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
    /* 스크롤 시 헤더 고정 */
    position: sticky;
    top: 0;
    z-index: 2;
}
/* 합계 행 */
.custom-table tr.total-row td {
    background-color: #f8fafc;
    font-weight: 700;
    color: #0f172a;
    border-top: 2px solid #cbd5e1;
    border-bottom: none;
    position: sticky;
    bottom: 0;
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

/* 좁은 화면 대응: KPI 그리드 열 수 축소 */
@media (max-width: 1200px) {
    .g7 { grid-template-columns: repeat(4, 1fr); }
    .g6 { grid-template-columns: repeat(3, 1fr); }
    .g4 { grid-template-columns: repeat(2, 1fr); }
}
@media (max-width: 640px) {
    .g7, .g6, .g4, .g3, .g2 { grid-template-columns: repeat(1, 1fr); }
}
</style>
""", unsafe_allow_html=True)


# ── 유틸 및 컴포넌트 ──────────────────────────────────────────
def kpi_card(label, value, sub="", accent_class=""):
    # 줄바꿈/들여쓰기 없는 한 줄 HTML 로 반환한다. 선행 개행이 있으면
    # st.markdown 의 dedent 과정에서 부모 템플릿에 공백만 있는 빈 줄이 생겨
    # HTML 블록이 끊기고 태그가 텍스트로 노출될 수 있다. (html_table 과 동일 원인)
    return (
        f'<div class="kpi-card {accent_class}">'
        f'<div class="lbl">{label}</div>'
        f'<div class="val">{value}</div>'
        f'<div class="sub">{sub}</div>'
        f'</div>'
    )

def _set_state(key, value):
    # 버튼 on_click 콜백: 리렌더 전에 상태를 갱신해 한 번 클릭으로 반영되게 한다.
    st.session_state[key] = value

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

# 정렬 iframe 안에 주입할 테이블 CSS (메인 페이지 스타일을 그대로 복제).
# iframe 은 스타일이 격리되므로 표 디자인을 유지하려면 여기에 다시 넣어야 한다.
_TABLE_CSS = """
@import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&family=Noto+Sans+KR:wght@400;500;700&display=swap');
* { box-sizing: border-box; }
html, body { margin:0; padding:0; background:#f8fafc;
    font-family:'Plus Jakarta Sans','Noto Sans KR',sans-serif; }
.custom-table-wrapper { background:white; border-radius:16px; border:1px solid #e2e8f0;
    box-shadow:0 4px 6px -1px rgba(15,23,42,0.02); max-height:460px; overflow:auto; margin-bottom:16px; }
.custom-table { width:100%; border-collapse:collapse; text-align:left; }
.custom-table th { background:#f8fafc; color:#475569; font-weight:600; font-size:12px;
    padding:12px 20px; border-bottom:1px solid #e2e8f0; text-transform:uppercase; letter-spacing:0.5px;
    position:sticky; top:0; z-index:2; cursor:pointer; user-select:none; white-space:nowrap; }
.custom-table th:hover { background:#eef2ff; color:#4f46e5; }
.custom-table tr.total-row td { background:#f8fafc; font-weight:700; color:#0f172a;
    border-top:2px solid #cbd5e1; border-bottom:none; position:sticky; bottom:0; }
.custom-table td { padding:12px 20px; font-size:13px; color:#334155; border-bottom:1px solid #f1f5f9; }
.custom-table tr:last-child td { border-bottom:none; }
.custom-table tbody tr:hover td { background:#f8fafc; }
.sort-ind { margin-left:4px; font-size:10px; color:#4f46e5; }
"""

# 헤더 클릭 시 해당 열을 오름차순↔내림차순 토글 정렬한다.
# 숫자(원·%·개·건·# 등 기호 제거 후 파싱)는 수치 정렬, 그 외는 한글 가나다 정렬.
# 합계행(total-row)은 정렬에서 제외하고 항상 맨 아래에 고정한다.
_SORT_JS = """
<script>
document.querySelectorAll('table.custom-table').forEach(function(table){
  var headers = table.querySelectorAll('thead th');
  headers.forEach(function(th, idx){
    th.addEventListener('click', function(){
      var tbody = table.querySelector('tbody');
      var rows = Array.prototype.slice.call(tbody.querySelectorAll('tr'));
      var totals = rows.filter(function(r){ return r.classList.contains('total-row'); });
      var data   = rows.filter(function(r){ return !r.classList.contains('total-row'); });
      var asc = th.getAttribute('data-asc') !== 'true';
      headers.forEach(function(h){
        if (h !== th){ h.removeAttribute('data-asc');
          var s=h.querySelector('.sort-ind'); if(s) s.textContent=''; }
      });
      th.setAttribute('data-asc', asc ? 'true' : 'false');
      function txt(r){ var c=r.children[idx]; return c ? c.textContent.trim() : ''; }
      function num(v){
        var c=v.replace(/[^0-9.\\-]/g,'');
        if(c===''||c==='-'||c==='.') return null;
        var n=parseFloat(c); return isNaN(n)?null:n;
      }
      data.sort(function(a,b){
        var va=txt(a), vb=txt(b), na=num(va), nb=num(vb), cmp;
        if(na!==null && nb!==null) cmp = na-nb;
        else if(na!==null) cmp = 1;
        else if(nb!==null) cmp = -1;
        else cmp = va.localeCompare(vb,'ko');
        return asc ? cmp : -cmp;
      });
      data.forEach(function(r){ tbody.appendChild(r); });
      totals.forEach(function(r){ tbody.appendChild(r); });
      var ind = th.querySelector('.sort-ind');
      if(!ind){ ind=document.createElement('span'); ind.className='sort-ind'; th.appendChild(ind); }
      ind.textContent = asc ? '▲' : '▼';
    });
  });
});
</script>
"""

def render_sortable_table(table_html):
    # 표 높이를 행 수에 맞춰 추정(헤더+데이터+합계행). 길면 460px wrapper 내부 스크롤.
    n_tr = table_html.count("<tr")
    height = min(n_tr * 43 + 72, 496)
    doc = f"<!DOCTYPE html><html><head><meta charset='utf-8'><style>{_TABLE_CSS}</style></head>" \
          f"<body>{table_html}{_SORT_JS}</body></html>"
    components.html(doc, height=height, scrolling=False)

def render_html(html):
    # st.markdown 은 본문에 textwrap.dedent().strip() 을 적용한다.
    # 동적으로 끼워 넣은 행(rows)들은 사이에 공백만 있는 빈 줄을 만들고,
    # 이 빈 줄이 HTML 블록을 끊어 뒤따르는 들여쓰기된 <tr>/<td> 줄이
    # 마크다운 코드블록으로 인식되어 태그가 그대로 텍스트로 노출된다.
    # 모든 줄의 들여쓰기를 제거하고 빈 줄을 없애 하나의 연속된
    # HTML 블록으로 만들어 항상 정상 렌더링되도록 한다.
    clean = "\n".join(ln.strip() for ln in html.splitlines() if ln.strip())
    # 정렬 가능한 표(custom-table)는 JS 가 동작하도록 격리된 iframe(components.html)에
    # 렌더링한다. st.markdown 은 보안상 <script> 를 제거하기 때문이다.
    # 표가 아닌 일반 HTML(빈 상태 메시지·흐름 카드 등)은 기존대로 마크다운으로 그린다.
    if 'class="custom-table"' in clean:
        render_sortable_table(clean)
    else:
        st.markdown(clean, unsafe_allow_html=True)

def html_table(data_dict, extra_col=None, cat_map=None):
    sorted_items = sorted(data_dict.items(), key=lambda x: -x[1]["revenue"])
    if not sorted_items:
        render_html("<div style='color:#94a3b8;font-size:13px;padding:24px;text-align:center;background:white;border-radius:16px;border:1px solid #e2e8f0;margin-bottom:20px;'>데이터가 없습니다.</div>")
        return

    extra_header = f'<th style="text-align:right;">{extra_col[0]}</th>' if extra_col else ""
    # cat_map(상품명→판매카테고리)이 주어지면 '항목' 옆에 판매카테고리 열을 끼운다.
    cat_header = '<th>판매카테고리</th>' if cat_map is not None else ""

    rows_html = []
    for name, s in sorted_items:
        r = margin_rate(s)
        color = "#10b981" if r>=35 else "#f59e0b" if r>=20 else "#ef4444"

        extra_val = ""
        if extra_col:
            extra_val = f'<td style="text-align:right;font-weight:600;">{extra_col[1](s)}</td>'
        cat_val = f'<td style="color:#64748b;">{cat_map.get(name, "-")}</td>' if cat_map is not None else ""

        rows_html.append(f"""
        <tr>
            <td style="font-weight:600;color:#1e293b;">{name}</td>
            {cat_val}
            <td style="text-align:right;font-weight:500;">{fmt_won(s['revenue'])}</td>
            <td style="text-align:right;color:#64748b;">{fmt_won(s['cost'])}</td>
            <td style="text-align:right;font-weight:600;color:#0f172a;">{fmt_won(margin(s))}</td>
            <td style="text-align:right;font-weight:700;color:{color};">{r:.1f}%</td>
            <td style="text-align:right;color:#64748b;">{int(s['qty']):,}개</td>
            {extra_val}
        </tr>
        """)

    # 합계 행 — 전체 항목을 합산해 맨 아래 고정 표기
    tot = {"revenue": 0.0, "cost": 0.0, "qty": 0.0}
    for _, s in sorted_items:
        tot["revenue"] += s["revenue"]; tot["cost"] += s["cost"]; tot["qty"] += s["qty"]
    tot_r = margin_rate(tot)
    tot_cat = '<td>—</td>' if cat_map is not None else ""
    tot_extra = f'<td style="text-align:right;">{extra_col[1](tot)}</td>' if extra_col else ""
    total_row = f"""
    <tr class="total-row">
        <td>합계</td>
        {tot_cat}
        <td style="text-align:right;">{fmt_won(tot['revenue'])}</td>
        <td style="text-align:right;">{fmt_won(tot['cost'])}</td>
        <td style="text-align:right;">{fmt_won(tot['revenue'] - tot['cost'])}</td>
        <td style="text-align:right;">{tot_r:.1f}%</td>
        <td style="text-align:right;">{int(tot['qty']):,}개</td>
        {tot_extra}
    </tr>
    """

    table_content = f"""
    <div class="custom-table-wrapper">
        <table class="custom-table">
            <thead>
                <tr>
                    <th>항목</th>
                    {cat_header}
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
                {total_row}
            </tbody>
        </table>
    </div>
    """
    render_html(table_content)


# ── 종합일보 (Overview) ───────────────────────────────────────
def _flow_row(label, value, indent=False, op="", val_color="", note="",
              strong=False, big=False, border="1px solid #f1f5f9"):
    pl = "padding-left:16px;" if indent else ""
    fw = "800" if big else ("700" if strong else "600")
    fs = "16px" if big else ("15px" if strong else "14px")
    lbl_color = val_color or "#475569"
    op_html = f'<span style="color:{lbl_color}">{op} </span>' if op else ""
    note_html = f' &nbsp;<small style="font-size:11px;color:#94a3b8;font-weight:normal;">{note}</small>' if note else ""
    vc = val_color or "#0f172a"
    return (
        f'<div style="display:flex;justify-content:space-between;border-bottom:{border};'
        f'padding-bottom:9px;margin-bottom:9px;font-size:{fs};">'
        f'<span style="color:{lbl_color};{pl}">{op_html}{label}</span>'
        f'<span style="font-weight:{fw};color:{vc};">{value}{note_html}</span>'
        f'</div>'
    )

# 종합일보 핵심지표 → 카테고리 1차 분해 → 주문번호 2차 드릴다운용 정의.
# 각 지표는 (행 필터, 값 추출, 값 라벨)로 정의되며 enriched_rows 를 직접 집계한다.
_METRICS = {
    "gross":   (lambda r: True,                    lambda r: safe_float(r.get("상품구매금액")), "주문금액(원)"),
    "refund":  (lambda r: bool(r.get("_skip")),    lambda r: safe_float(r.get("상품구매금액")), "환불금액(원)"),
    "netpur":  (lambda r: not r.get("_skip"),      lambda r: safe_float(r.get("상품구매금액")), "주문금액(원)"),
    "rev":     (lambda r: not r.get("_skip"),      lambda r: r.get("_net_revenue", 0.0),         "순매출(원)"),
    "cost":    (lambda r: not r.get("_skip"),      lambda r: r.get("_cost", 0.0),                "공급원가(원)"),
    "margin":  (lambda r: not r.get("_skip"),      lambda r: r.get("_net_revenue", 0.0) - r.get("_cost", 0.0), "마진(원)"),
    "qty":     (lambda r: not r.get("_skip"),      lambda r: safe_float(r.get("수량")),          "수량"),
    "pending": (lambda r: r.get("주문 상태", "").strip() == PENDING_STATUS,
                lambda r: safe_float(r.get("상품구매금액")), "진행중금액(원)"),
}

def _group_by_cat(enriched, row_filter, value_fn):
    # 필터에 걸린 행을 메인카테고리별로 (값 합계, 건수) 집계.
    agg = {}
    for r in enriched:
        if not row_filter(r):
            continue
        cat = r.get("메인카테고리 이름", "").strip() or "(미분류)"
        a = agg.setdefault(cat, [0.0, 0])
        a[0] += value_fn(r)
        a[1] += 1
    return agg

def _orders_std(enriched, row_filter, cat=None):
    # 필터에 걸린 주문 행을 주문번호 단위로 펼친다.
    # cat 이 주어지면 해당 카테고리만, None 이면 전체를 펼친다(카테고리 열 포함).
    out = []
    for r in enriched:
        if not row_filter(r):
            continue
        c = r.get("메인카테고리 이름", "").strip() or "(미분류)"
        if cat is not None and c != cat:
            continue
        out.append({
            "주문번호": r.get("주문번호", "").strip(),
            "상품명": r.get("상품명(데드라)", "").strip(),
            "브랜드": parse_brand(r.get("브랜드")),
            "카테고리": c,
            "수량": int(safe_float(r.get("수량")) or 0),
            "상품구매금액(원)": round(safe_float(r.get("상품구매금액"))),
            "공급원가(원)": round(r.get("_cost", 0.0)),
            "순매출(원)": round(r.get("_net_revenue", 0.0)),
            "상태": r.get("주문 상태", "").strip(),
        })
    return out


def render_overview(enriched, refund, ds, total_rev, total_cost, total_m, total_rate,
                    total_pg, total_op, total_op_r):
    coup  = ds.get("coupon", 0.0)
    grade = ds.get("grade", 0.0)
    pdisc = ds.get("prod_disc", 0.0)
    pts   = ds.get("points", 0.0)
    dep   = ds.get("deposit", 0.0)
    nvr   = ds.get("naver_pt", 0.0)
    qty   = ds.get("qty", 0.0)
    tot_disc = coup + grade + pdisc

    gross    = refund["amount_all"]      # 환불 전 총 주문금액
    ref_amt  = refund["amount_ref"]      # 환불 금액
    net_pur  = ds.get("purchase", 0.0)   # 환불 후 총 주문금액 (= gross − ref_amt)
    rate_amt = refund["rate_amt"]
    rate_cnt = refund["rate_cnt"]
    cost_pct = (total_cost / total_rev * 100) if total_rev else 0
    disc_pct = (tot_disc / net_pur * 100) if net_pur else 0

    # 지표별 상세 설명(산출 방식) — 클릭 시 팝업 상단에 표시.
    explains = {
        "gross": "업로드된 <b>모든 주문 행(취소·반품 포함)</b>의 <code>상품구매금액</code>을 합산한 값입니다. 할인 적용 전, 고객이 주문한 정가 기준 결제 금액이며 <b>환불 전 총 주문금액 = 환불 후 주문금액 + 환불 금액</b> 입니다.",
        "refund": "주문 상태가 <b>취소 요청 / 교환 신청 / 반품 요청 / 반품 완료-환불완료</b> 인 행의 <code>상품구매금액</code> 합계입니다. (‘반품 처리중-수거전’은 환불 확정 전이라 별도 ‘반품 진행중’으로 집계)",
        "rate": "<b>환불율(금액) = 환불 금액 ÷ 환불 전 총 주문금액 × 100</b><br><b>환불율(건수) = 환불 건수 ÷ 전체 주문 건수 × 100</b>",
        "netpur": "환불 전 총 주문금액에서 환불 금액을 뺀, 실제 유효 주문(정상 + 반품진행중)의 <code>상품구매금액</code> 합계입니다. <b>환불 후 주문금액 = 환불 전 − 환불</b>",
        "disc": "<b>쿠폰 + 회원등급 추가할인 + 상품별 추가할인</b>의 합계입니다. 적립금·예치금은 결제수단이라 할인에서 제외합니다. 주문서 쿠폰·등급 할인은 주문 내 품목에 상품구매금액 비율로 배분해 합산합니다.",
        "rev": "<b>순매출 = 환불 후 주문금액 − 총 할인(쿠폰·등급·상품)</b>. 적립금·예치금·네이버페이 포인트는 결제수단/적립이라 매출에 포함하지 않습니다. (네이버페이 주문은 상품구매금액을 포인트로 결제한 것이라 이미 주문금액에 반영돼 있어 다시 더하지 않습니다.)",
        "cost": "각 주문 품목의 <b>공급원가(단가) × 수량</b> 합계입니다. (취소·반품 제외)",
        "margin": "<b>마진 = 순매출 − 공급원가</b>, <b>마진율 = 마진 ÷ 순매출 × 100</b>",
        "pg": "결제수단별 <b>순매출 × PG 수수료율</b>의 합계입니다. 수수료율은 결제업체·결제수단 조합에 따라 적용됩니다.",
        "op": "<b>영업이익 = 마진 − PG 수수료</b>. 상품 판매로 실제 남는 이익입니다.",
        "qty": "취소·반품을 제외한 정상 판매 품목의 <code>수량</code> 합계입니다.",
        "pending": "주문 상태가 <b>반품 처리중 - 수거전</b> 인 행입니다. 아직 환불이 확정되지 않은 단계라 환불 금액과 분리해 집계합니다.",
    }

    def _drilldown(df1, sel_col, key, build_level2, l2_title):
        # 1차 분해표(df1)를 행 선택 가능한 dataframe 으로 그리고,
        # 행을 클릭하면 build_level2(선택값)로 2차(주문번호) 상세를 펼친다.
        if df1.empty:
            st.info("표시할 내역이 없습니다.")
            return
        ev = st.dataframe(
            df1, hide_index=True, use_container_width=True,
            on_select="rerun", selection_mode="single-row", key=f"l1_{key}",
        )
        if ev.selection.rows:
            sel = df1.iloc[ev.selection.rows[0]][sel_col]
            rows2 = build_level2(sel)
            st.markdown(f"##### ‘{sel}’ {l2_title} · {len(rows2):,}건")
            if rows2:
                st.dataframe(pd.DataFrame(rows2), hide_index=True, use_container_width=True)
            else:
                st.info("해당 항목의 주문 내역이 없습니다.")
        else:
            st.caption("⬆️ 위 표에서 항목(행)을 클릭하면 주문번호별 상세가 펼쳐집니다.")

    @st.dialog("핵심 지표 상세 내역", width="large")
    def _detail(key, title):
        st.markdown(f"#### {title}")
        st.markdown(
            f'<div style="background:#eef2ff;border:1px solid #c7d2fe;border-radius:12px;'
            f'padding:14px 18px;font-size:13px;line-height:1.75;color:#3730a3;margin-bottom:14px;">'
            f'<b>📌 산출 방식</b><br>{explains.get(key, "")}</div>',
            unsafe_allow_html=True,
        )
        # 영업이익: 총계 산식 흐름만 표시 (드릴다운/보기전환 없음)
        if key == "op":
            render_html(
                '<div style="background:white;border-radius:16px;border:1px solid #e2e8f0;padding:20px 28px;">'
                + _flow_row("순매출 (A)", fmt_won(total_rev), strong=True, val_color="#4f46e5")
                + _flow_row("공급원가 (B)", fmt_won(total_cost), indent=True, op="−", val_color="#ef4444")
                + _flow_row("마진 (C = A − B)", fmt_won(total_m), strong=True, note=f"마진율 {total_rate:.1f}%", border="2px solid #cbd5e1")
                + _flow_row("PG 수수료 (D)", fmt_won(total_pg), indent=True, op="−", val_color="#ef4444")
                + _flow_row("영업이익 (E = C − D)", fmt_won(total_op), big=True,
                            val_color=("#10b981" if total_op_r >= 20 else "#ef4444"),
                            note=f"영업이익률 {total_op_r:.1f}%", border="none")
                + '</div>'
            )
            return

        # 보기 전환: 분류별 드릴다운 ↔ 전체 주문 한눈에
        view = st.radio(
            "보기 방식", ["📂 분류별 보기", "📋 전체 한눈에"],
            horizontal=True, key=f"view_{key}", label_visibility="collapsed",
        )
        total_mode = (view == "📋 전체 한눈에")
        st.caption("표 헤더 클릭 → 오름/내림 정렬 · ‘분류별 보기’에선 항목(행) 클릭 → 주문번호별 상세")

        # 총 할인: 할인 유형(쿠폰/등급/상품)별 → 주문번호 드릴다운
        if key == "disc":
            comps = [("쿠폰 할인", "_alloc_coupon"), ("회원등급 할인", "_alloc_grade"),
                     ("상품 즉시 할인", "_disc_product")]
            fld_of = dict(comps)
            if total_mode:
                rows = [{
                    "주문번호": r.get("주문번호", "").strip(),
                    "상품명": r.get("상품명(데드라)", "").strip(),
                    "브랜드": parse_brand(r.get("브랜드")),
                    "카테고리": r.get("메인카테고리 이름", "").strip() or "(미분류)",
                    "쿠폰할인(원)": round(r.get("_alloc_coupon", 0.0)),
                    "등급할인(원)": round(r.get("_alloc_grade", 0.0)),
                    "상품할인(원)": round(r.get("_disc_product", 0.0)),
                    "상품구매금액(원)": round(safe_float(r.get("상품구매금액"))),
                    "쿠폰명": r.get("사용한 쿠폰명", "").strip(),
                    "상태": r.get("주문 상태", "").strip(),
                } for r in enriched if not r.get("_skip")
                  and (r.get("_alloc_coupon", 0.0) + r.get("_alloc_grade", 0.0) + r.get("_disc_product", 0.0)) > 0]
                st.markdown(f"##### 할인 적용 주문 전체 · {len(rows):,}건")
                st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
                return
            df1 = pd.DataFrame([
                {"할인 유형": label,
                 "할인금액(원)": round(sum(r.get(fld, 0.0) for r in enriched if not r.get("_skip"))),
                 "적용건수": sum(1 for r in enriched if not r.get("_skip") and r.get(fld, 0.0) > 0)}
                for label, fld in comps
            ])
            def _l2(sel):
                fld = fld_of[sel]
                return [{
                    "주문번호": r.get("주문번호", "").strip(),
                    "상품명": r.get("상품명(데드라)", "").strip(),
                    "브랜드": parse_brand(r.get("브랜드")),
                    "할인액(원)": round(r.get(fld, 0.0)),
                    "상품구매금액(원)": round(safe_float(r.get("상품구매금액"))),
                    "쿠폰명": r.get("사용한 쿠폰명", "").strip(),
                    "상태": r.get("주문 상태", "").strip(),
                } for r in enriched if not r.get("_skip") and r.get(fld, 0.0) > 0]
            _drilldown(df1, "할인 유형", key, _l2, "적용 주문")
            return

        # PG 수수료: 결제수단별 → 주문번호 드릴다운
        if key == "pg":
            def _pg_row(r):
                return {
                    "주문번호": r.get("주문번호", "").strip(),
                    "결제수단": r.get("_pg_name", "") or "기타",
                    "카테고리": r.get("메인카테고리 이름", "").strip() or "(미분류)",
                    "순매출(원)": round(r.get("_net_revenue", 0.0)),
                    "수수료(원)": round(r.get("_pg_fee", 0.0)),
                    "상태": r.get("주문 상태", "").strip(),
                }
            if total_mode:
                rows = [_pg_row(r) for r in enriched if not r.get("_skip")]
                st.markdown(f"##### 결제 주문 전체 · {len(rows):,}건")
                st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
                return
            agg = {}
            for r in enriched:
                if r.get("_skip"):
                    continue
                nm = r.get("_pg_name", "") or "기타"
                a = agg.setdefault(nm, [0.0, 0.0, 0])
                a[0] += r.get("_net_revenue", 0.0); a[1] += r.get("_pg_fee", 0.0); a[2] += 1
            df1 = pd.DataFrame([
                {"결제수단": k, "순매출(원)": round(v[0]), "수수료(원)": round(v[1]), "건수": v[2]}
                for k, v in agg.items()
            ]).sort_values("수수료(원)", ascending=False).reset_index(drop=True)
            _drilldown(df1, "결제수단", key,
                       lambda sel: [_pg_row(r) for r in enriched
                                    if not r.get("_skip") and (r.get("_pg_name", "") or "기타") == sel],
                       "결제 주문")
            return

        # 카테고리형 지표 (gross/refund/rate/netpur/rev/cost/margin/qty/pending)
        mk = "refund" if key == "rate" else key
        row_filter, value_fn, vlabel = _METRICS[mk]
        if total_mode:
            rows = _orders_std(enriched, row_filter, None)
            st.markdown(f"##### 전체 주문 상세 · {len(rows):,}건")
            st.dataframe(pd.DataFrame(rows), hide_index=True, use_container_width=True)
            return
        agg = _group_by_cat(enriched, row_filter, value_fn)
        if vlabel == "수량":
            df1 = pd.DataFrame([{"카테고리": c, "수량": int(v), "건수": n} for c, (v, n) in agg.items()])
            sort_col = "수량"
        else:
            df1 = pd.DataFrame([{"카테고리": c, vlabel: round(v), "건수": n} for c, (v, n) in agg.items()])
            sort_col = vlabel
        if not df1.empty:
            df1 = df1.sort_values(sort_col, ascending=False).reset_index(drop=True)
        _drilldown(df1, "카테고리", key, lambda sel: _orders_std(enriched, row_filter, sel), "주문번호별 상세")

    # ── 핵심 지표 카드 (클릭 시 상세 팝업) ───────────────────
    section_title("핵심 지표 요약")
    st.caption("각 카드의 ‘📋 상세 내역’ 버튼을 누르면 산출 방식과 분해 내역(정렬 가능)이 팝업으로 표시됩니다.")
    cards = [
        ("gross",   "환불 전 총 주문금액", fmt_won(gross), "취소·반품 포함 결제 기준", ""),
        ("refund",  "환불 금액", fmt_won(ref_amt), f"환불 {refund['refund_cnt']:,}건", "accent-red"),
        ("rate",    "환불율 (금액)", fmt_rate(rate_amt), f"건수 기준 {rate_cnt:.1f}%", "accent-rose"),
        ("netpur",  "환불 후 총 주문금액", fmt_won(net_pur), "할인 차감 전 매출", ""),
        ("disc",    "총 할인 지원액", fmt_won(tot_disc), f"주문금액 대비 {disc_pct:.1f}%", "accent-amber"),
        ("rev",     "순매출", fmt_won(total_rev), "구매금액 − 할인", ""),
        ("cost",    "총 공급원가", fmt_won(total_cost), f"매출 대비 {cost_pct:.1f}%", "accent-amber"),
        ("margin",  "총 마진", fmt_won(total_m), f"마진율 {total_rate:.1f}%", rate_accent(total_rate)),
        ("pg",      "PG 결제 수수료", fmt_won(total_pg), "결제 대행 공제", "accent-rose"),
        ("op",      "최종 영업 이익", fmt_won(total_op), f"영업이익률 {total_op_r:.1f}%", rate_accent(total_op_r)),
        ("qty",     "총 판매 수량", f"{int(qty):,}개", "환불·반품 제외", ""),
        ("pending", "반품 진행중", f"{refund['pending_cnt']:,}건", fmt_won(refund['amount_pend']), "accent-amber"),
    ]
    for i in range(0, len(cards), 4):
        cols = st.columns(4)
        for col, (key, title, val, sub, accent) in zip(cols, cards[i:i+4]):
            with col:
                st.markdown(f'<div style="margin-bottom:8px;">{kpi_card(title, val, sub, accent)}</div>',
                            unsafe_allow_html=True)
                if st.button("📋 상세 내역", key=f"ov_detail_{key}", use_container_width=True):
                    _detail(key, title)

    # ── 매출 → 영업이익 흐름 (워터폴) ─────────────────────────
    section_title("총매출 → 영업이익 종합 흐름")
    flow = (
        _flow_row("환불 전 총 주문금액 (A)", fmt_won(gross), strong=True)
        + _flow_row("환불 금액 (B)", fmt_won(ref_amt), indent=True, op="−",
                    val_color="#ef4444", note=f"환불율 {rate_amt:.1f}% · {refund['refund_cnt']:,}건/{refund['total_cnt']:,}건")
        + _flow_row("환불 후 총 주문금액 (C = A − B)", fmt_won(net_pur), strong=True,
                    border="2px solid #cbd5e1")
        + _flow_row("총 할인 (쿠폰·등급·상품) (D)", fmt_won(tot_disc), indent=True, op="−",
                    val_color="#f59e0b", note=f"주문금액 대비 {disc_pct:.1f}%")
        + _flow_row("순매출 (E = C − D)", fmt_won(total_rev), strong=True,
                    val_color="#4f46e5", border="2px solid #cbd5e1")
        + _flow_row("공급원가 (F)", fmt_won(total_cost), indent=True, op="−",
                    val_color="#ef4444", note=f"원가율 {cost_pct:.1f}%")
        + _flow_row("순 마진 (G = E − F)", fmt_won(total_m), strong=True,
                    val_color=("#10b981" if total_m >= 0 else "#ef4444"),
                    note=f"마진율 {total_rate:.1f}%", border="2px solid #cbd5e1")
        + _flow_row("PG 결제수수료 (H)", fmt_won(total_pg), indent=True, op="−",
                    val_color="#ef4444")
        + _flow_row("최종 영업 이익 (I = G − H)", fmt_won(total_op), big=True,
                    val_color=("#10b981" if total_op_r >= 20 else "#ef4444"),
                    note=f"영업이익률 {total_op_r:.1f}%", border="none")
    )
    render_html(
        '<div style="background:white;border-radius:16px;border:1px solid #e2e8f0;'
        'padding:24px 32px;box-shadow:0 4px 6px -1px rgba(15,23,42,0.02);margin-bottom:20px;">'
        + flow + '</div>'
    )

    # ── 할인·결제수단 사용 상세 ──────────────────────────────
    section_title("할인 · 적립 수단 상세")
    st.markdown(f"""
    <div class="kpi-grid g3">
        {kpi_card("쿠폰 할인", fmt_won(coup))}
        {kpi_card("회원등급 할인", fmt_won(grade))}
        {kpi_card("상품 즉시 할인", fmt_won(pdisc))}
    </div>
    <div class="kpi-grid g3">
        {kpi_card("네이버페이 포인트", fmt_won(nvr), "결제수단/적립 · 매출 미포함")}
        {kpi_card("결제 적립금 사용액", fmt_won(pts), "결제수단 · 매출 미포함")}
        {kpi_card("예치금 사용액", fmt_won(dep), "결제수단 · 매출 미포함")}
    </div>
    """, unsafe_allow_html=True)


# ── 환불 분석 ─────────────────────────────────────────────────
def _refund_table(stats_dict, label_col, min_filter=False, with_qty=False):
    def ref_rate(d):
        return (d["refund"] / d["total"] * 100) if d["total"] else 0.0
    def amt_rate(d):
        return (d["amount_ref"] / d["amount_all"] * 100) if d["amount_all"] else 0.0
    def fmt_set(s):
        vals = sorted(s)
        return vals[0] if len(vals) == 1 else ("복수" if len(vals) > 1 else "-")

    items = stats_dict.items()
    if min_filter:
        items = [(k, d) for k, d in items if k and (d["refund"] >= 1 or d["pending"] >= 1)]
    else:
        items = [(k, d) for k, d in items if k]
    rows_data = sorted(items, key=lambda kv: (-ref_rate(kv[1]), -kv[1]["refund"]))

    if not rows_data:
        render_html("<div style='color:#94a3b8;font-size:13px;padding:24px;text-align:center;background:white;border-radius:16px;border:1px solid #e2e8f0;margin-bottom:20px;'>표시할 환불 내역이 없습니다.</div>")
        return

    rows = []
    for name, d in rows_data:
        rr = ref_rate(d)
        rc = "#ef4444" if rr >= 20 else "#f59e0b" if rr >= 10 else "#64748b"
        pend = (f'<td style="text-align:right;color:#ea580c;font-weight:600;">{d["pending"]}</td>'
                f'<td style="text-align:right;color:#ea580c;">{fmt_won(d["amount_pend"])}</td>'
                if d["pending"] else
                '<td style="text-align:right;color:#cbd5e1;">-</td><td style="text-align:right;color:#cbd5e1;">-</td>')
        meta = ""
        qty_cell = ""
        if with_qty:
            meta = (f'<td style="color:#64748b;white-space:nowrap;">{fmt_set(d["brands"])}</td>'
                    f'<td style="color:#64748b;white-space:nowrap;">{fmt_set(d["cats"])}</td>')
            qty_cell = f'<td style="text-align:right;color:#64748b;">{int(d["qty"]):,}개</td>'
        rows.append(f"""
        <tr>
            <td style="font-weight:600;color:#1e293b;">{name}</td>
            {meta}
            {qty_cell}
            <td style="text-align:right;color:#64748b;">{d['total']:,}건</td>
            <td style="text-align:right;font-weight:600;">{d['refund']:,}건</td>
            <td style="text-align:right;font-weight:700;color:{rc};">{rr:.1f}%</td>
            <td style="text-align:right;font-weight:600;color:#ef4444;">{fmt_won(d['amount_ref'])}</td>
            <td style="text-align:right;color:#64748b;">{amt_rate(d):.1f}%</td>
            {pend}
        </tr>
        """)

    meta_h = '<th>브랜드</th><th>카테고리</th>' if with_qty else ""
    qty_h = '<th style="text-align:right;">판매수량</th>' if with_qty else ""
    render_html(f"""
    <div class="custom-table-wrapper">
        <table class="custom-table">
            <thead>
                <tr>
                    <th>{label_col}</th>
                    {meta_h}
                    {qty_h}
                    <th style="text-align:right;">전체주문</th>
                    <th style="text-align:right;">환불건수</th>
                    <th style="text-align:right;">환불율</th>
                    <th style="text-align:right;">환불금액</th>
                    <th style="text-align:right;">금액비율</th>
                    <th style="text-align:right;">반품진행중</th>
                    <th style="text-align:right;">진행중금액</th>
                </tr>
            </thead>
            <tbody>{"".join(rows)}</tbody>
        </table>
    </div>
    """)

def render_refunds(refund):
    rate_cnt = refund["rate_cnt"]
    rate_amt = refund["rate_amt"]

    section_title("환불 현황 요약")
    if refund["refund_cnt"] == 0 and refund["pending_cnt"] == 0:
        premium_banner("ok", "환불 및 반품진행중 내역이 없습니다.")
        return

    acc = "accent-red" if rate_cnt >= 20 else "accent-amber" if rate_cnt >= 10 else "accent-green"
    st.markdown(f"""
    <div class="kpi-grid g4">
        {kpi_card("환불율 (건수 기준)", fmt_rate(rate_cnt), f"{refund['refund_cnt']:,}건 / 전체 {refund['total_cnt']:,}건", acc)}
        {kpi_card("환불율 (금액 기준)", fmt_rate(rate_amt), "환불액 / 전체 주문액", acc)}
        {kpi_card("총 환불 금액", fmt_won(refund["amount_ref"]), f"환불 전 주문 {fmt_won(refund['amount_all'])}", "accent-red")}
        {kpi_card("반품 진행중", f"{refund['pending_cnt']:,}건", f"{fmt_won(refund['amount_pend'])} (수거전)", "accent-amber")}
    </div>
    """, unsafe_allow_html=True)
    if rate_cnt >= 20:
        premium_banner("err", f"환불율이 {rate_cnt:.1f}%로 높습니다. 브랜드·상품별 원인 점검이 필요합니다.")

    section_title("① 브랜드별 환불율")
    _refund_table(refund["brand_stats"], "브랜드")

    section_title("② 카테고리별 환불율")
    _refund_table(refund["cat_stats"], "카테고리")

    prod_n = sum(1 for _, d in refund["prod_stats"].items() if d["refund"] >= 1 or d["pending"] >= 1)
    section_title(f"③ 상품별 환불율 (환불·반품진행중 1건 이상 · {prod_n}개 상품)")
    _refund_table(refund["prod_stats"], "상품명", min_filter=True, with_qty=True)


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

    # 데이터 처리 — 같은 파일명은 한 번만 반영(중복 업로드 시 이중 합산 방지)
    all_rows, file_names, skipped = [], [], []
    for f in uploaded:
        if f.name in file_names:
            skipped.append(f.name)
            continue
        rows = parse_csv(f)
        if rows:
            all_rows.extend(rows)
            file_names.append(f.name)

    if not all_rows:
        premium_banner("err", "파일 데이터를 읽을 수 없습니다. 인코딩 형식을 확인해 주세요.")
        return

    if skipped:
        premium_banner("warn", f"중복된 파일명은 한 번만 반영했습니다: {', '.join(sorted(set(skipped)))}")

    with st.spinner("주문 내역 정밀 마진 분석 중..."):
        enriched = preprocess_rows(all_rows)
        data = aggregate(enriched)
        price_anomalies, outlet_items = detect_price_anomalies(enriched)
        discount_over, discount_buckets, discount_bucket_products = detect_discount_anomalies(enriched)
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

    # 환불 통계 (취소/반품완료 = _skip, 반품진행중 별도) — 종합일보·환불 탭 공용
    refund = compute_refund_stats(enriched)

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

    # ── 핵심 KPI 대형 카드 그리드 (7열) ─────────────────────────
    cost_pct = (total_cost / total_rev * 100) if total_rev else 0
    st.markdown(f"""
    <div class="kpi-grid g7">
        {kpi_card("총 순매출", fmt_won(total_rev), "재고소진 매출 합산")}
        {kpi_card("총 공급원가", fmt_won(total_cost), f"매출 대비 {cost_pct:.1f}%", "accent-amber")}
        {kpi_card("총 마진", fmt_won(total_m), f"평균 마진율 {total_rate:.1f}%", rate_accent(total_rate))}
        {kpi_card("종합 마진율", fmt_rate(total_rate), "전체 데이터 기준", rate_accent(total_rate))}
        {kpi_card("PG 결제 수수료", fmt_won(total_pg), f"매출 대비 {(total_pg/total_rev*100) if total_rev else 0:.2f}%", "accent-rose")}
        {kpi_card("순 영업 이익", fmt_won(total_op), f"영업 이익률 {total_op_r:.1f}%", rate_accent(total_op_r))}
        {kpi_card("영업 이익률", fmt_rate(total_op_r), "수수료 공제 후", rate_accent(total_op_r))}
    </div>
    """, unsafe_allow_html=True)

    # ── 대시보드 탭 레이아웃 ──────────────────────────────────────
    t0, t6, t1, t2, t3, t4, t5 = st.tabs([
        "📋 종합일보", "🔄 환불 분석",
        "📊 상세 마진 분석", "🔍 판매가 이상 감지", "🏷️ 할인율 입체 분석",
        "💳 PG 수수료 명세", "📦 아울렛 & 재고소진",
    ])

    # ── 탭 0: 종합일보 ────────────────────────────────────────
    with t0:
        render_overview(
            enriched, refund, ds, total_rev, total_cost, total_m, total_rate,
            total_pg, total_op, total_op_r,
        )

    # ── 탭 6: 환불 분석 ───────────────────────────────────────
    with t6:
        render_refunds(refund)

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
        empty_msg = "<div style='color:#94a3b8;font-size:13px;padding:24px;text-align:center;background:white;border-radius:16px;border:1px solid #e2e8f0;'>집계할 상품이 없습니다 (수량 2개 이상 기준).</div>"

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
                render_html(f"""
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
                """)
            else:
                render_html(empty_msg)

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
                render_html(f"""
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
                """)
            else:
                render_html(empty_msg)

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
                        <td style="color:#64748b;">{a['카테고리']}</td>
                        <td style="text-align:right;font-weight:600;">{fmt_won(a['판매가'])}</td>
                        <td style="text-align:right;color:#94a3b8;">{fmt_won(a['공급원가'])}</td>
                        <td style="text-align:right;color:#94a3b8;">{fmt_won(a['기준가'])}</td>
                        <td style="text-align:right;font-weight:700;color:#ef4444;">{fmt_won(a['차이'])}</td>
                    </tr>
                    """)
                render_html(f"""
                <div class="custom-table-wrapper">
                    <table class="custom-table">
                        <thead>
                            <tr>
                                <th>주문번호</th>
                                <th>상품명</th>
                                <th>브랜드</th>
                                <th>판매카테고리</th>
                                <th style="text-align:right;">판매가</th>
                                <th style="text-align:right;">원가</th>
                                <th style="text-align:right;">정상 기준가</th>
                                <th style="text-align:right;">차액</th>
                            </tr>
                        </thead>
                        <tbody>{"".join(rows)}</tbody>
                    </table>
                </div>
                """)
                
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
                        <td style="color:#64748b;">{a['카테고리']}</td>
                        <td style="text-align:right;font-weight:600;">{fmt_won(a['판매가'])}</td>
                        <td style="text-align:right;color:#94a3b8;">{fmt_won(a['공급원가'])}</td>
                        <td style="text-align:right;font-weight:700;color:#4f46e5;">{a['원가회수율']:.1f}%</td>
                    </tr>
                    """)
                render_html(f"""
                <div class="custom-table-wrapper">
                    <table class="custom-table">
                        <thead>
                            <tr>
                                <th>상품명</th>
                                <th>브랜드</th>
                                <th>판매카테고리</th>
                                <th style="text-align:right;">판매가</th>
                                <th style="text-align:right;">원가</th>
                                <th style="text-align:right;">원가회수율</th>
                            </tr>
                        </thead>
                        <tbody>{"".join(rows)}</tbody>
                    </table>
                </div>
                """)

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
                    <td style="color:#64748b;">{w['판매카테고리']}</td>
                    <td>{w['상품명']}</td>
                    <td style="text-align:right;color:#94a3b8;">{fmt_won(w['원가'])}</td>
                    <td style="font-weight:600;color:#ef4444;">{w['쿠폰명']}</td>
                    <td style="text-align:right;font-weight:700;color:#ef4444;">{fmt_won(w['쿠폰할인액'])}</td>
                </tr>
                """)
            render_html(f"""
            <div class="custom-table-wrapper">
                <table class="custom-table">
                    <thead>
                        <tr>
                            <th>주문번호</th>
                            <th>판매카테고리</th>
                            <th>상품명</th>
                            <th style="text-align:right;">원가</th>
                            <th>적용 쿠폰</th>
                            <th style="text-align:right;">쿠폰할인액</th>
                        </tr>
                    </thead>
                    <tbody>{"".join(rows)}</tbody>
                </table>
            </div>
            """)

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
            {kpi_card("네이버페이 포인트", fmt_won(nvr), "결제수단/적립 · 매출 미포함")}
        </div>
        <div class="kpi-grid g3">
            {kpi_card("쿠폰 할인 상세", fmt_won(coup), f"원금 대비 {(coup/pur*100) if pur else 0:.1f}%")}
            {kpi_card("회원등급 할인 상세", fmt_won(grade), f"원금 대비 {(grade/pur*100) if pur else 0:.1f}%")}
            {kpi_card("상품 즉시 할인 상세", fmt_won(pdisc), f"원금 대비 {(pdisc/pur*100) if pur else 0:.1f}%")}
        </div>
        """, unsafe_allow_html=True)

        col_left, col_right = st.columns([1, 2])
        with col_left:
            section_title("상품별 할인율 구간 분포")
            st.caption("구간을 클릭하면 오른쪽에 해당 상품이 할인율 높은 순으로 표시됩니다.")
            sel_bucket = st.session_state.get("disc_bucket", "25% 초과")
            for k, v in discount_buckets.items():
                is_sel = (k == sel_bucket)
                st.button(
                    f"{k}　·　{v}건",
                    key=f"disc_bucket_{k}",
                    use_container_width=True,
                    type=("primary" if is_sel else "secondary"),
                    on_click=_set_state,
                    args=("disc_bucket", k),
                )

        with col_right:
            sel_bucket = st.session_state.get("disc_bucket", "25% 초과")
            items = discount_bucket_products.get(sel_bucket, [])
            section_title(f"‘{sel_bucket}’ 구간 상품 (할인율 높은 순 · {len(items)}건)")
            if sel_bucket == "25% 초과" and items:
                premium_banner("warn", f"25%를 초과하는 고할인율 상품이 {len(items)}건 발견되었습니다.")
            if not items:
                premium_banner("ok", "해당 구간에 표시할 상품이 없습니다.")
            else:
                rows = []
                for o in items:
                    rr = o['할인율']
                    rc = "#ef4444" if rr > 25 else "#f59e0b" if rr > 15 else "#64748b"
                    rows.append(f"""
                    <tr>
                        <td style="font-weight:600;color:#4f46e5;">{o['주문번호']}</td>
                        <td>{o['상품명']}</td>
                        <td style="color:#64748b;">{o['브랜드']}</td>
                        <td style="color:#64748b;">{o['판매카테고리']}</td>
                        <td style="text-align:right;">{fmt_won(o['판매가'])}</td>
                        <td style="text-align:right;color:#94a3b8;">{fmt_won(o['원가'])}</td>
                        <td style="text-align:right;font-weight:600;color:{rc};">{fmt_won(o['할인금액'])}</td>
                        <td style="text-align:right;font-weight:600;color:#0f172a;">{fmt_won(o['판매가'] - o['할인금액'])}</td>
                        <td style="text-align:right;font-weight:700;color:{rc};">{rr:.1f}%</td>
                        <td style="font-size:11px;color:#64748b;">{o['쿠폰명']}</td>
                    </tr>
                    """)
                render_html(f"""
                <div class="custom-table-wrapper">
                    <table class="custom-table">
                        <thead>
                            <tr>
                                <th>주문번호</th>
                                <th>상품명</th>
                                <th>브랜드</th>
                                <th>판매카테고리</th>
                                <th style="text-align:right;">판매가</th>
                                <th style="text-align:right;">원가</th>
                                <th style="text-align:right;">할인액</th>
                                <th style="text-align:right;">실구매가</th>
                                <th style="text-align:right;">할인율</th>
                                <th>적용쿠폰</th>
                            </tr>
                        </thead>
                        <tbody>{"".join(rows)}</tbody>
                    </table>
                </div>
                """)

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
            t_rev = t_fee = t_cnt = 0.0
            for name, s in pg_rows:
                t_rev += s['revenue']; t_fee += s['pg_fee']; t_cnt += s['count']
                rows.append(f"""
                <tr>
                    <td style="font-weight:600;color:#0f172a;">{name}</td>
                    <td style="text-align:right;font-weight:500;">{fmt_won(s['revenue'])}</td>
                    <td style="text-align:right;color:#64748b;">{s['rate']*100:.2f}%</td>
                    <td style="text-align:right;font-weight:600;color:#ef4444;">{fmt_won(s['pg_fee'])}</td>
                    <td style="text-align:right;color:#64748b;">{s['count']:,}건</td>
                </tr>
                """)
            avg_rate = (t_fee / t_rev * 100) if t_rev else 0
            total_row = f"""
            <tr class="total-row">
                <td>합계</td>
                <td style="text-align:right;">{fmt_won(t_rev)}</td>
                <td style="text-align:right;">{avg_rate:.2f}%</td>
                <td style="text-align:right;">{fmt_won(t_fee)}</td>
                <td style="text-align:right;">{int(t_cnt):,}건</td>
            </tr>
            """
            render_html(f"""
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
                    <tbody>{"".join(rows)}{total_row}</tbody>
                </table>
            </div>
            """)
        else:
            premium_banner("ok", "표시할 PG 수수료 내역이 없습니다.")

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
                # 상품명 → 판매카테고리(메인카테고리 이름) 매핑
                prod_cat = {}
                for rr in enriched:
                    if rr.get("_skip"):
                        continue
                    pn = rr.get("상품명(데드라)", "").strip()
                    if pn and pn not in prod_cat:
                        prod_cat[pn] = rr.get("메인카테고리 이름", "").strip()
                html_table(
                    products,
                    extra_col=("원가회수율", lambda s: fmt_rate(recovery_rate(s))),
                    cat_map=prod_cat,
                )


if __name__ == "__main__":
    main()
