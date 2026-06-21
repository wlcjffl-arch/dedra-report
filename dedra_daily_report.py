#!/usr/bin/env python3
"""
데드라 일일 마진 분석 리포트 생성기
~/Desktop/claude 폴더의 가장 최근 카페24 주문 CSV를 읽어 HTML 리포트를 생성합니다.
"""

import csv
import glob
import html
import os
import sys
from collections import defaultdict
from datetime import datetime

FOLDER = os.path.expanduser("~/Desktop/claude")
SKIP_STATUSES = {"취소 요청", "교환 신청", "반품 요청", "반품 완료 - 환불완료"}
CLEARANCE_CATS = {"아울렛", "▶균일가 모음전◀"}

# 브랜드 분류 (CSV HTML 엔티티 디코딩 후 비교 — parse_brand() 사용)
SELF_MADE_BRANDS = {"DEDRA", "D'eL"}
SAIP_BRANDS = {"SELECT SHOP", "THE BLACK", "THE BLACK_D'eL", "THE BLACK_DEDRA"}

DISCOUNT_WARN_THRESHOLD = 25.0  # 할인율 경고 기준 (%)

# PG 수수료율 — 결제업체 컬럼 기준 (긴 이름 먼저 매칭)
PG_RATE_TABLE = [
    ("토스페이먼츠", 0.0363),
    ("네이버페이",   0.0374),
    ("카카오페이",   0.0352),
    ("삼성페이",    0.0385),
    ("토스",       0.0352),
    ("다날",       0.0385),
    ("페이코",      0.0363),
]
# 결제업체가 비어있고 결제수단이 이것들만 있으면 PG 없음
FREE_PAY_KEYWORDS = {"무통장입금", "계좌이체", "선불금", "쿠폰", "적립금", "예치금"}
DEFAULT_PG_RATE = 0.0363  # 기타


# ── 유틸 ──────────────────────────────────────────────────────

def find_latest_csv(folder):
    files = glob.glob(os.path.join(folder, "*.csv"))
    if not files:
        print("❌ CSV 파일을 찾을 수 없습니다:", folder)
        sys.exit(1)
    return max(files, key=os.path.getmtime)


def safe_float(v):
    try:
        return float(str(v).replace(",", "").strip()) if v else 0.0
    except ValueError:
        return 0.0


def load_rows(path):
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


def parse_brand(raw):
    return html.unescape((raw or "").strip())


def fmt_won(v):
    return f"{v:,.0f}원"


def fmt_rate(v):
    return f"{v:.1f}%"


def get_pg_info(pg_company, pay_method):
    """(PG사명, 수수료율) 반환. 결제업체 우선, 없으면 결제수단으로 판별."""
    co = (pg_company or "").strip()
    for name, rate in PG_RATE_TABLE:
        if name in co:
            return name, rate
    # 결제업체 없음 → 결제수단이 모두 무료 채널이면 수수료 0
    if not co:
        methods = {m.strip() for m in (pay_method or "").split(",")}
        if methods <= FREE_PAY_KEYWORDS:
            return "무통장/선불금", 0.0
    return "기타", DEFAULT_PG_RATE


def margin(s):
    return s["revenue"] - s["cost"]


def margin_rate(s):
    return (margin(s) / s["revenue"] * 100) if s["revenue"] else 0.0


def op_profit(s):
    return s["revenue"] - s["cost"] - s["pg_fee"]


def op_profit_rate(s):
    return (op_profit(s) / s["revenue"] * 100) if s["revenue"] else 0.0


def recovery_rate(s):
    return (s["revenue"] / s["cost"] * 100) if s["cost"] else 0.0


def _new_stat():
    return {"revenue": 0.0, "cost": 0.0, "discount": 0.0, "pg_fee": 0.0, "qty": 0.0, "count": 0}


def _add(stat, net, cost, discount, pg_fee, qty):
    stat["revenue"] += net
    stat["cost"] += cost
    stat["discount"] += discount
    stat["pg_fee"] += pg_fee
    stat["qty"] += qty
    stat["count"] += 1


# ── 할인 배분 전처리 ───────────────────────────────────────────

def preprocess_rows(rows):
    """
    주문번호 기준으로 그룹핑하여 쿠폰/등급할인/적립금/예치금을 첫 번째 행 값만
    사용한 뒤 상품구매금액 비율로 배분.

    순매출(메인) = 구매금액 - 상품별할인 - 쿠폰 - 등급할인 - 적립금 - 예치금
    할인율 이상감지용  = 구매금액 - 상품별할인 - 쿠폰 - 등급할인  (적립금·예치금 제외)
    """
    # 1차 패스: 주문별 총 구매금액 & 첫 행 정보 수집 (취소/교환 포함 전체)
    order_total = {}   # order_no → 총 상품구매금액
    order_first = {}   # order_no → 첫 행의 주문단위 필드

    for r in rows:
        no = r.get("주문번호", "").strip()
        purchase = safe_float(r.get("상품구매금액"))
        if no not in order_total:
            order_total[no] = 0.0
            order_first[no] = {
                "coupon":   safe_float(r.get("주문서 쿠폰 할인금액")),
                "grade":    safe_float(r.get("회원등급 추가할인금액")),
                "points":   safe_float(r.get("사용한 적립금액(최초)")),
                "deposit":  safe_float(r.get("예치금(최초)")),
                "naver_pt": safe_float(r.get("네이버 포인트")),
                "pg_co":    r.get("결제업체", "").strip(),
                "pay":      r.get("결제수단", "").strip(),
            }
        order_total[no] += purchase

    # 2차 패스: 행별 배분 계산 (취소/교환 포함 전체 — _skip=True 행도 계산)
    result = []
    for r in rows:
        r = dict(r)
        status = r.get("주문 상태", "").strip()
        r["_skip"] = status in SKIP_STATUSES

        no = r.get("주문번호", "").strip()
        purchase = safe_float(r.get("상품구매금액"))
        total_pur = order_total.get(no, purchase) or 1.0
        ratio = purchase / total_pur if total_pur else 0.0

        fi = order_first.get(no, {})
        alloc_coupon   = fi.get("coupon",   0.0) * ratio
        alloc_grade    = fi.get("grade",    0.0) * ratio
        alloc_points   = fi.get("points",   0.0) * ratio
        alloc_deposit  = fi.get("deposit",  0.0) * ratio
        alloc_naver_pt = fi.get("naver_pt", 0.0) * ratio

        disc_product   = safe_float(r.get("상품별 추가할인금액"))
        # 순매출 = 구매금액 - (쿠폰+등급+상품추가할인) + 네이버포인트 (매출 처리)
        # 적립금·예치금은 결제수단이므로 순매출에서 제외
        total_discount   = disc_product + alloc_coupon + alloc_grade
        net_revenue      = purchase - total_discount + alloc_naver_pt
        disc_for_anomaly = disc_product + alloc_coupon + alloc_grade

        pg_name, pg_rate = get_pg_info(fi.get("pg_co", ""), fi.get("pay", ""))
        pg_fee = max(0.0, net_revenue) * pg_rate

        qty  = safe_float(r.get("수량")) or 1.0
        cost = safe_float(r.get("공급원가")) * qty  # 단가 × 수량

        r["_alloc_coupon"]     = alloc_coupon
        r["_alloc_grade"]      = alloc_grade
        r["_alloc_points"]     = alloc_points
        r["_alloc_deposit"]    = alloc_deposit
        r["_alloc_naver_pt"]   = alloc_naver_pt
        r["_disc_product"]     = disc_product
        r["_disc_for_anomaly"] = disc_for_anomaly
        r["_total_discount"]   = total_discount
        r["_net_revenue"]      = net_revenue
        r["_pg_name"]          = pg_name
        r["_pg_rate"]          = pg_rate
        r["_pg_fee"]           = pg_fee
        r["_cost"]             = cost
        r["_op_profit"]        = net_revenue - cost - pg_fee
        result.append(r)

    return result


# ── 이상감지 ──────────────────────────────────────────────────

def detect_price_anomalies(enriched_rows):
    """
    판매가 이상감지: 브랜드 분류별 마진 최소 기준 미달 상품 탐지.
    자체분류에 '아울렛' 포함 상품은 이상감지에서 제외하고 별도 목록으로 반환.
    반환: (anomalies, outlet_items)
    """
    anomalies = []
    outlet_items = []

    for r in enriched_rows:
        if r.get("_skip"):
            continue

        purchase = safe_float(r.get("상품구매금액"))
        unit_cost = safe_float(r.get("공급원가"))  # CSV 공급원가는 단가
        qty = safe_float(r.get("수량")) or 1
        brand = parse_brand(r.get("브랜드"))
        own_cat = r.get("자체분류", "").strip()

        unit_price = purchase / qty

        if unit_cost == 0:
            continue

        # 아울렛 상품 → 이상감지 제외, 별도 현황으로 분리
        main_cat = r.get("메인카테고리 이름", "").strip()

        if "아울렛" in own_cat:
            if brand in SELF_MADE_BRANDS:
                분류 = "자체제작"
                threshold = unit_cost * 2
            elif brand in SAIP_BRANDS:
                분류 = "사입"
                threshold = unit_cost * 2 - (300 if unit_price < 100_000 else 3_000)
            else:
                분류 = "기타"
                threshold = unit_cost * 2
            outlet_items.append({
                "주문번호": r.get("주문번호", ""),
                "상품명": r.get("상품명(데드라)", "").strip(),
                "브랜드": brand,
                "카테고리": main_cat,
                "분류": 분류,
                "판매가": unit_price,
                "공급원가": unit_cost,
                "기준가": threshold,
                "원가회수율": (unit_price / unit_cost * 100) if unit_cost else 0,
                "상품별추가할인": safe_float(r.get("상품별 추가할인금액")),
                # 주문서 쿠폰은 주문 전체에 1건 걸리지만 CSV 는 모든 품목 행에
                # 같은 금액을 반복 기재한다(3개 구매 시 3행 모두 15000).
                # 원본 값을 그대로 쓰면 품목마다 중복 표기되므로,
                # preprocess_rows 가 판매가(상품구매금액) 비율로 배분해 둔
                # _alloc_coupon 을 사용한다.
                "쿠폰할인": r.get("_alloc_coupon", 0.0),
            })
            continue

        if brand in SELF_MADE_BRANDS:
            threshold = unit_cost * 2
            if unit_price < threshold:
                anomalies.append({
                    "주문번호": r.get("주문번호", ""),
                    "상품명": r.get("상품명(데드라)", "").strip(),
                    "브랜드": brand,
                    "카테고리": main_cat,
                    "분류": "자체제작",
                    "판매가": unit_price,
                    "공급원가": unit_cost,
                    "기준가": threshold,
                    "차이": unit_price - threshold,
                })

        elif brand in SAIP_BRANDS:
            if unit_price < 100_000:
                threshold = unit_cost * 2 - 300
            else:
                threshold = unit_cost * 2 - 3_000
            if unit_price < threshold:
                anomalies.append({
                    "주문번호": r.get("주문번호", ""),
                    "상품명": r.get("상품명(데드라)", "").strip(),
                    "브랜드": brand,
                    "카테고리": main_cat,
                    "분류": "사입",
                    "판매가": unit_price,
                    "공급원가": unit_cost,
                    "기준가": threshold,
                    "차이": unit_price - threshold,
                })

    anomalies.sort(key=lambda x: x["차이"])
    outlet_items.sort(key=lambda x: x["원가회수율"])
    return anomalies, outlet_items


def detect_discount_anomalies(enriched_rows):
    """
    상품(주문 내 품목) 단위 할인율 이상감지 (25% 초과) 및 구간별 집계.
    할인율 = (상품별할인 + 배분된 쿠폰 + 배분된 등급할인) / 상품구매금액 × 100

    주문서 쿠폰·회원등급 할인은 주문 전체에 1건만 부과되지만 CSV 는 모든 품목 행에
    같은 금액을 반복 기재한다(예: 2품목 주문에 9,200원 쿠폰이 두 행 모두 9,200).
    그대로 합산하면 중복되므로, preprocess_rows 가 판매가(상품구매금액) 비율로
    배분해 둔 _disc_for_anomaly(상품별할인 + 배분쿠폰 + 배분등급)를 그대로 사용한다.
    적립금·예치금은 순수 할인이 아니라 _disc_for_anomaly 에서 이미 제외돼 있다.

    이전에는 주문 단위로 합산해 첫 품목 이름만 붙였더니, 다품목 주문이
    엉뚱한 한 상품에 주문 전체 금액으로 표시됐다. 이제 품목별로 평가한다.
    """
    buckets = {"0%": 0, "1~10%": 0, "11~15%": 0, "16~25%": 0, "25% 초과": 0}
    # 구간별 상품 목록(드릴다운용). 각 구간을 클릭하면 해당 상품들을 보여준다.
    bucket_products = {k: [] for k in buckets}

    def _bucket_of(rate):
        if rate <= 0:  return "0%"
        if rate <= 10: return "1~10%"
        if rate <= 15: return "11~15%"
        if rate <= 25: return "16~25%"
        return "25% 초과"

    for r in enriched_rows:
        if r.get("_skip"):
            continue
        purchase = safe_float(r.get("상품구매금액"))
        if purchase == 0:
            continue
        discount = r.get("_disc_for_anomaly", 0.0)
        disc_rate = discount / purchase * 100

        label = _bucket_of(disc_rate)
        buckets[label] += 1
        bucket_products[label].append({
            "주문번호": r.get("주문번호", "").strip(),
            "상품명": r.get("상품명(데드라)", "").strip(),
            "브랜드": parse_brand(r.get("브랜드")),
            "판매카테고리": r.get("메인카테고리 이름", "").strip(),
            "판매가": purchase,
            "원가": r.get("_cost", 0.0),
            "할인금액": discount,
            "할인율": disc_rate,
            "쿠폰명": r.get("사용한 쿠폰명", "").strip(),
            "할인상세": r.get("상품별 추가할인 상세", "").strip(),
        })

    # 각 구간을 할인율 높은 순으로 정렬
    for k in bucket_products:
        bucket_products[k].sort(key=lambda x: -x["할인율"])

    over_threshold = bucket_products["25% 초과"]
    return over_threshold, buckets, bucket_products


# ── 마진 집계 ─────────────────────────────────────────────────

def aggregate(enriched_rows):
    """전처리된 행 기준으로 배분된 할인·PG수수료를 사용해 집계."""
    normal = _new_stat()
    clearance_total = _new_stat()
    cat_normal = defaultdict(lambda: _new_stat())
    cat_clearance = defaultdict(lambda: _new_stat())
    product_by_clearance_cat = defaultdict(lambda: defaultdict(lambda: _new_stat()))
    supplier_normal = defaultdict(lambda: _new_stat())
    supplier_clearance = defaultdict(lambda: _new_stat())
    product_normal = defaultdict(lambda: _new_stat())
    pg_by_payment = defaultdict(lambda: {"revenue": 0.0, "pg_fee": 0.0, "count": 0, "rate": 0.0})
    coupon_warnings = []

    ds = {  # 할인 요약 (discount summary) — 취소 제외, 전체 합산
        "purchase":    0.0,  # 총 주문금액 (상품구매금액 합계)
        "coupon":      0.0,  # 쿠폰 할인
        "grade":       0.0,  # 회원등급 할인
        "prod_disc":   0.0,  # 상품별 추가할인
        "points":      0.0,  # 적립금
        "deposit":     0.0,  # 예치금
        "naver_pt":    0.0,  # 네이버포인트
        "qty":         0.0,  # 총 판매수량
    }

    for r in enriched_rows:
        if r.get("_skip"):
            continue

        net      = r["_net_revenue"]
        cost     = r["_cost"]
        discount = r["_total_discount"]
        pg_fee   = r["_pg_fee"]
        pg_name  = r["_pg_name"]
        qty      = safe_float(r.get("수량"))

        ds["purchase"]  += safe_float(r.get("상품구매금액"))
        ds["coupon"]    += r.get("_alloc_coupon",   0.0)
        ds["grade"]     += r.get("_alloc_grade",    0.0)
        ds["prod_disc"] += r.get("_disc_product",   0.0)
        ds["points"]    += r.get("_alloc_points",   0.0)
        ds["deposit"]   += r.get("_alloc_deposit",  0.0)
        ds["naver_pt"]  += r.get("_alloc_naver_pt", 0.0)
        ds["qty"]       += qty

        cat      = r.get("메인카테고리 이름", "").strip()
        prod     = r.get("상품명(데드라)", "").strip()
        supplier = r.get("공급사명", "").strip()
        order_no = r.get("주문번호", "").strip()

        # PG별 집계
        pg_by_payment[pg_name]["revenue"] += net
        pg_by_payment[pg_name]["pg_fee"]  += pg_fee
        pg_by_payment[pg_name]["count"]   += 1
        pg_by_payment[pg_name]["rate"]     = r["_pg_rate"]

        if cat in CLEARANCE_CATS:
            alloc_coupon = r["_alloc_coupon"]
            coupon_name  = r.get("사용한 쿠폰명", "").strip()
            if alloc_coupon > 0 or coupon_name:
                coupon_warnings.append({
                    "주문번호": order_no,
                    "판매카테고리": cat,
                    "상품명": prod,
                    "원가": r["_cost"],
                    "쿠폰명": coupon_name,
                    "쿠폰할인액": alloc_coupon,
                })
            _add(clearance_total, net, cost, discount, pg_fee, qty)
            _add(cat_clearance[cat], net, cost, discount, pg_fee, qty)
            _add(supplier_clearance[supplier], net, cost, discount, pg_fee, qty)
            _add(product_by_clearance_cat[cat][prod], net, cost, discount, pg_fee, qty)
        else:
            _add(normal, net, cost, discount, pg_fee, qty)
            _add(cat_normal[cat], net, cost, discount, pg_fee, qty)
            _add(supplier_normal[supplier], net, cost, discount, pg_fee, qty)
            _add(product_normal[prod], net, cost, discount, pg_fee, qty)

    return {
        "normal": normal,
        "clearance": clearance_total,
        "cat_normal": dict(cat_normal),
        "cat_clearance": dict(cat_clearance),
        "product_by_clearance_cat": {k: dict(v) for k, v in product_by_clearance_cat.items()},
        "supplier_normal": dict(supplier_normal),
        "supplier_clearance": dict(supplier_clearance),
        "product_normal": dict(product_normal),
        "pg_by_payment": dict(pg_by_payment),
        "coupon_warnings": coupon_warnings,
        "ds": ds,
    }


# ── 터미널 요약 출력 ───────────────────────────────────────────

def print_summary(data, price_anomalies, outlet_items, discount_over, csv_path, html_path):
    n = data["normal"]
    c = data["clearance"]
    total_rev  = n["revenue"]  + c["revenue"]
    total_cost = n["cost"]     + c["cost"]
    total_pg   = n["pg_fee"]   + c["pg_fee"]
    total_m    = total_rev - total_cost
    total_rate = (total_m   / total_rev * 100) if total_rev else 0
    total_op   = total_m - total_pg
    total_op_r = (total_op  / total_rev * 100) if total_rev else 0

    print("\n" + "=" * 62)
    print(f"  데드라 마진 리포트  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print(f"  원본: {os.path.basename(csv_path)}")
    print("=" * 62)
    print(f"  {'항목':<20} {'일반':>13}  {'재고소진':>10}")
    print(f"  {'-'*47}")
    print(f"  {'순매출':<20} {n['revenue']:>13,.0f}  {c['revenue']:>10,.0f}")
    print(f"  {'공급원가':<20} {n['cost']:>13,.0f}  {c['cost']:>10,.0f}")
    print(f"  {'마진':<20} {margin(n):>13,.0f}  {margin(c):>10,.0f}")
    print(f"  {'마진율':<20} {margin_rate(n):>12.1f}%  {margin_rate(c):>9.1f}%")
    print(f"  {'PG수수료':<20} {n['pg_fee']:>13,.0f}  {c['pg_fee']:>10,.0f}")
    print(f"  {'영업이익':<20} {op_profit(n):>13,.0f}  {op_profit(c):>10,.0f}")
    print(f"  {'영업이익률':<20} {op_profit_rate(n):>12.1f}%  {op_profit_rate(c):>9.1f}%")
    print(f"  {'판매수량':<20} {int(n['qty']):>12,}개  {int(c['qty']):>8,}개")
    print(f"  {'-'*47}")
    print(f"  {'전체 마진율':<20} {total_rate:>12.1f}%")
    print(f"  {'전체 영업이익률':<20} {total_op_r:>12.1f}%  ({total_op:,.0f}원)")
    print()
    print(f"  ── 이상감지 ──────────────────────────────────────")
    print(f"  {'⚠️ ' if price_anomalies else '✅ '} 판매가 이상 상품      : {len(price_anomalies)}건  (아울렛 제외 {len(outlet_items)}건 별도 표시)")
    print(f"  {'⚠️ ' if discount_over   else '✅ '} 할인율 25% 초과 주문  : {len(discount_over)}건")
    print(f"  {'⚠️ ' if data['coupon_warnings'] else '✅ '} 재고소진 쿠폰 적용    : {len(data['coupon_warnings'])}건")
    print(f"\n  📄 리포트: {html_path}")
    print("=" * 62 + "\n")


# ── HTML 컴포넌트 ──────────────────────────────────────────────

def margin_bg(rate):
    if rate >= 50:   return "#d4edda"
    elif rate >= 35: return "#e8f5e9"
    elif rate >= 20: return "#fff9c4"
    elif rate >= 0:  return "#ffe0b2"
    else:            return "#ffcdd2"


def margin_color_css(rate):
    if rate >= 35:   return "#2e7d32"
    elif rate >= 20: return "#f57f17"
    elif rate >= 0:  return "#e65100"
    else:            return "#c62828"


def stat_row_html(name, s, extra_val=None, badge=None):
    r = margin_rate(s)
    tc = margin_color_css(r)
    badge_html = f'<span class="badge badge-{badge}">{badge}</span>' if badge else ""
    extra_td = f'<td class="num">{extra_val}</td>' if extra_val is not None else ""
    return (
        f'<tr style="background:{margin_bg(r)}">'
        f'<td>{name}{badge_html}</td>'
        f'<td class="num">{fmt_won(s["revenue"])}</td>'
        f'<td class="num">{fmt_won(s["cost"])}</td>'
        f'<td class="num">{fmt_won(s["discount"])}</td>'
        f'<td class="num" style="color:{tc};font-weight:700">{fmt_won(margin(s))}</td>'
        f'<td class="num" style="color:{tc};font-weight:700">{fmt_rate(r)}</td>'
        f'<td class="num">{int(s["qty"]):,}개</td>'
        f'{extra_td}'
        f'</tr>'
    )


def build_margin_table(title, data_dict, top_n=None, show_recovery=False):
    if not data_dict:
        return ""
    items = sorted(data_dict.items(), key=lambda x: -x[1]["revenue"])
    if top_n:
        items = items[:top_n]
    extra_th = '<th>원가회수율</th>' if show_recovery else ''
    rows = "".join(
        stat_row_html(name, s, extra_val=fmt_rate(recovery_rate(s)) if show_recovery else None)
        for name, s in items
    )
    return f"""
    <div class="section">
        <h2>{title}</h2>
        <div class="table-wrap"><table>
            <thead><tr>
                <th>항목</th><th>순매출</th><th>공급원가</th><th>총 할인액</th>
                <th>마진</th><th>마진율</th><th>수량</th>{extra_th}
            </tr></thead>
            <tbody>{rows}</tbody>
        </table></div>
    </div>"""


def build_top_products(title, product_dict, top_n=10, bottom=False):
    if not product_dict:
        return ""
    items = [(k, v) for k, v in product_dict.items() if v["qty"] >= 2]
    items.sort(key=lambda x: margin_rate(x[1]), reverse=not bottom)
    items = items[:top_n]
    if not items:
        return ""
    rows = ""
    for name, s in items:
        r = margin_rate(s)
        tc = margin_color_css(r)
        rows += (
            f'<tr style="background:{margin_bg(r)}">'
            f'<td>{name}</td>'
            f'<td class="num">{fmt_won(s["revenue"])}</td>'
            f'<td class="num">{fmt_won(s["cost"])}</td>'
            f'<td class="num" style="color:{tc};font-weight:700">{fmt_rate(r)}</td>'
            f'<td class="num">{int(s["qty"]):,}개</td>'
            f'</tr>'
        )
    return f"""
    <div class="section">
        <h2>{title} <span class="sub-label">(판매 2개 이상)</span></h2>
        <div class="table-wrap"><table>
            <thead><tr><th>상품명</th><th>순매출</th><th>공급원가</th><th>마진율</th><th>수량</th></tr></thead>
            <tbody>{rows}</tbody>
        </table></div>
    </div>"""


def build_clearance_section(data):
    sections = ""
    for cat in ["아울렛", "▶균일가 모음전◀"]:
        cat_stat = data["cat_clearance"].get(cat)
        products = data["product_by_clearance_cat"].get(cat, {})
        if not cat_stat:
            continue
        r = margin_rate(cat_stat)
        tc = margin_color_css(r)
        prod_rows = "".join(
            stat_row_html(name, s, extra_val=fmt_rate(recovery_rate(s)))
            for name, s in sorted(products.items(), key=lambda x: -margin(x[1]))
        )
        prod_table = f"""
        <div class="table-wrap"><table>
            <thead><tr>
                <th>상품명</th><th>순매출</th><th>공급원가</th><th>총 할인액</th>
                <th>마진</th><th>마진율</th><th>수량</th><th>원가회수율</th>
            </tr></thead>
            <tbody>{prod_rows}</tbody>
        </table></div>""" if prod_rows else ""

        sections += f"""
        <div class="section">
            <h2>📦 {cat}</h2>
            <div class="clearance-kpi">
                <span>순매출 <b>{fmt_won(cat_stat['revenue'])}</b></span>
                <span>원가 <b>{fmt_won(cat_stat['cost'])}</b></span>
                <span>마진 <b style="color:{tc}">{fmt_won(margin(cat_stat))}</b></span>
                <span>마진율 <b style="color:{tc}">{fmt_rate(r)}</b></span>
                <span>원가회수율 <b>{fmt_rate(recovery_rate(cat_stat))}</b></span>
                <span>수량 <b>{int(cat_stat['qty']):,}개</b></span>
            </div>
            {prod_table}
        </div>"""
    return sections


def build_price_anomaly_html(anomalies):
    if not anomalies:
        return '<div class="section ok-section"><h2>✅ 판매가 이상감지 — 이상 없음</h2></div>'
    rows = ""
    for a in anomalies:
        rows += (
            f'<tr>'
            f'<td>{a["주문번호"]}</td>'
            f'<td>{a["상품명"]}</td>'
            f'<td><span class="badge badge-{a["분류"]}">{a["브랜드"]}</span></td>'
            f'<td>{a["카테고리"]}</td>'
            f'<td class="num">{fmt_won(a["판매가"])}</td>'
            f'<td class="num">{fmt_won(a["공급원가"])}</td>'
            f'<td class="num">{fmt_won(a["기준가"])}</td>'
            f'<td class="num warn-val">{fmt_won(a["차이"])}</td>'
            f'</tr>'
        )
    return f"""
    <div class="section warn-section">
        <h2>⚠️ 판매가 이상 의심 상품 ({len(anomalies)}건)</h2>
        <p class="warn-desc">
            <b>자체제작(DEDRA·D'eL)</b>: 판매가 &lt; 공급원가 × 2&nbsp;&nbsp;|&nbsp;&nbsp;
            <b>사입(SELECT SHOP·THE BLACK)</b>: 판매가 &lt; 공급원가 × 2 − (10만원 미만 300원 / 이상 3,000원)<br>
            아래 상품은 설정된 기준가보다 낮게 판매되고 있습니다. 판매가 또는 원가 데이터를 확인하세요.
        </p>
        <div class="table-wrap"><table>
            <thead><tr>
                <th>주문번호</th><th>상품명</th><th>브랜드</th><th>판매카테고리</th>
                <th>판매가(단가)</th><th>공급원가(단가)</th><th>기준가</th><th>차이금액</th>
            </tr></thead>
            <tbody>{rows}</tbody>
        </table></div>
    </div>"""


def build_outlet_price_html(outlet_items):
    """아울렛 판매가 현황 — 경고가 아닌 참고용 섹션 (주황색)"""
    if not outlet_items:
        return ""
    rows = ""
    for a in outlet_items:
        rec = a["원가회수율"]
        if rec >= 100:
            rec_color = "#2e7d32"
        elif rec >= 70:
            rec_color = "#f57f17"
        else:
            rec_color = "#c62828"
        prod_disc = a.get("상품별추가할인", 0.0)
        coupon    = a.get("쿠폰할인", 0.0)
        rows += (
            f'<tr>'
            f'<td style="font-size:11px;color:#888;white-space:nowrap">{a["주문번호"]}</td>'
            f'<td>{a["상품명"]}</td>'
            f'<td><span class="badge badge-{a["분류"]}">{a["브랜드"]}</span></td>'
            f'<td>{a["카테고리"]}</td>'
            f'<td class="num">{fmt_won(a["판매가"])}</td>'
            f'<td class="num">{fmt_won(a["공급원가"])}</td>'
            f'<td class="num" style="color:{rec_color};font-weight:700">{fmt_rate(rec)}</td>'
            f'<td class="num">{fmt_won(prod_disc) if prod_disc else "-"}</td>'
            f'<td class="num">{fmt_won(coupon) if coupon else "-"}</td>'
            f'</tr>'
        )
    return f"""
    <div class="section outlet-section">
        <h2>🏷️ 아울렛 판매가 현황 ({len(outlet_items)}건)</h2>
        <p class="outlet-desc">자체분류 '아울렛' 상품은 재고소진 목적으로 기준가 이하 판매가 허용됩니다. 판매가 이상감지에서 제외되며 아래에 현황만 표시합니다.</p>
        <div class="table-wrap"><table>
            <thead><tr>
                <th>주문번호</th><th>상품명</th><th>브랜드</th><th>판매카테고리</th>
                <th class="num">판매가(단가)</th><th class="num">공급원가(단가)</th><th class="num">원가회수율</th>
                <th class="num">상품별 추가할인</th><th class="num">주문서 쿠폰 할인(배분)</th>
            </tr></thead>
            <tbody>{rows}</tbody>
        </table></div>
    </div>"""


def build_discount_anomaly_html(over_threshold, buckets):
    total_count = sum(buckets.values())
    bucket_rows = ""
    bucket_colors = {
        "0%": "#e8f5e9", "1~10%": "#f1f8e9", "11~15%": "#fff9c4",
        "16~25%": "#ffe0b2", "25% 초과": "#ffcdd2"
    }
    for label, cnt in buckets.items():
        pct = (cnt / total_count * 100) if total_count else 0
        bar_w = int(pct * 1.5)
        bucket_rows += (
            f'<tr style="background:{bucket_colors[label]}">'
            f'<td><b>{label}</b></td>'
            f'<td class="num">{cnt:,}건</td>'
            f'<td class="num">{pct:.1f}%</td>'
            f'<td><div class="bar" style="width:{bar_w}px"></div></td>'
            f'</tr>'
        )

    if not over_threshold:
        order_table = '<p style="color:#2e7d32;margin-top:12px">✅ 25% 초과 상품 없음</p>'
    else:
        order_rows = ""
        for o in over_threshold:
            order_rows += (
                f'<tr>'
                f'<td>{o["주문번호"]}</td>'
                f'<td>{o["상품명"]}</td>'
                f'<td>{o["브랜드"]}</td>'
                f'<td>{o["판매카테고리"]}</td>'
                f'<td class="num">{fmt_won(o["판매가"])}</td>'
                f'<td class="num">{fmt_won(o["원가"])}</td>'
                f'<td class="num warn-val">{fmt_won(o["할인금액"])}</td>'
                f'<td class="num warn-val"><b>{fmt_rate(o["할인율"])}</b></td>'
                f'<td>{o["쿠폰명"]}</td>'
                f'<td>{o["할인상세"]}</td>'
                f'</tr>'
            )
        order_table = f"""
        <h3 style="margin:16px 0 8px;font-size:14px;color:#c62828">할인율 25% 초과 상품 ({len(over_threshold)}건)</h3>
        <div class="table-wrap"><table>
            <thead><tr>
                <th>주문번호</th><th>상품명</th><th>브랜드</th><th>판매카테고리</th>
                <th>판매가</th><th>원가</th><th>할인금액</th><th>할인율</th><th>쿠폰명</th><th>상품별 추가할인 상세</th>
            </tr></thead>
            <tbody>{order_rows}</tbody>
        </table></div>"""

    section_class = "warn-section" if over_threshold else "section"
    icon = "⚠️" if over_threshold else "✅"
    return f"""
    <div class="{section_class} section">
        <h2>{icon} 할인율 이상감지</h2>
        <p class="warn-desc" style="margin-bottom:12px">기준: 총 할인액 / 상품구매금액 × 100 &nbsp;|&nbsp; 경고 기준: 25% 초과</p>
        <div class="table-wrap"><table style="max-width:500px">
            <thead><tr><th>할인율 구간</th><th>건수</th><th>비율</th><th>분포</th></tr></thead>
            <tbody>{bucket_rows}</tbody>
        </table></div>
        {order_table}
    </div>"""


def build_coupon_warning_html(warnings):
    if not warnings:
        return '<div class="section ok-section"><h2>✅ 재고소진 쿠폰 경고 — 이상 없음</h2></div>'
    rows = "".join(
        f'<tr>'
        f'<td>{w["주문번호"]}</td><td>{w["판매카테고리"]}</td><td>{w["상품명"]}</td>'
        f'<td class="num">{fmt_won(w["원가"])}</td>'
        f'<td>{w["쿠폰명"]}</td><td class="num warn-val">{fmt_won(w["쿠폰할인액"])}</td>'
        f'</tr>'
        for w in warnings
    )
    return f"""
    <div class="section warn-section">
        <h2>⚠️ 재고소진 카테고리 쿠폰 적용 경고 ({len(warnings)}건)</h2>
        <p class="warn-desc">재고소진 카테고리에 쿠폰이 적용되어 원가를 회수하지 못할 수 있습니다. 해당 카테고리의 쿠폰 적용 제외 처리를 권장합니다.</p>
        <div class="table-wrap"><table>
            <thead><tr><th>주문번호</th><th>판매카테고리</th><th>상품명</th><th class="num">원가</th><th>쿠폰명</th><th>쿠폰할인액(배분)</th></tr></thead>
            <tbody>{rows}</tbody>
        </table></div>
    </div>"""


def build_pg_section(data):
    """PG수수료 & 영업이익 섹션"""
    n = data["normal"]
    c = data["clearance"]
    pg_by = data.get("pg_by_payment", {})

    total_rev  = n["revenue"] + c["revenue"]
    total_cost = n["cost"]    + c["cost"]
    total_pg   = n["pg_fee"]  + c["pg_fee"]
    total_m    = total_rev - total_cost
    total_op   = total_m - total_pg
    total_m_r  = (total_m  / total_rev * 100) if total_rev else 0
    total_op_r = (total_op / total_rev * 100) if total_rev else 0
    pg_pct     = (total_pg / total_rev * 100) if total_rev else 0

    # 결제업체별 테이블
    pg_rows = ""
    for pg_name, s in sorted(pg_by.items(), key=lambda x: -x[1]["revenue"]):
        rate_pct = s["rate"] * 100
        pg_rows += (
            f'<tr>'
            f'<td>{pg_name}</td>'
            f'<td class="num">{fmt_won(s["revenue"])}</td>'
            f'<td class="num">{rate_pct:.2f}%</td>'
            f'<td class="num" style="color:#c62828">{fmt_won(s["pg_fee"])}</td>'
            f'<td class="num">{s["count"]:,}건</td>'
            f'</tr>'
        )

    op_color = margin_color_css(total_op_r)
    return f"""
    <div class="section">
        <h2>💳 PG수수료 및 영업이익</h2>
        <div class="pg-kpi">
            <div class="pg-kpi-item">
                <div class="label">총 PG수수료</div>
                <div class="value" style="color:#c62828">{fmt_won(total_pg)}</div>
                <div class="sub">순매출 대비 {pg_pct:.2f}%</div>
            </div>
            <div class="pg-kpi-item">
                <div class="label">총 영업이익</div>
                <div class="value" style="color:{op_color}">{fmt_won(total_op)}</div>
                <div class="sub">영업이익률 {total_op_r:.1f}%</div>
            </div>
        </div>
        <div class="op-calc">
            <div>순매출 &nbsp;<b>{fmt_won(total_rev)}</b></div>
            <div class="op-minus">− 공급원가 &nbsp;<b>{fmt_won(total_cost)}</b></div>
            <div class="op-eq">= 매출총이익(마진) &nbsp;<b>{fmt_won(total_m)}</b>
                <span class="op-rate">({total_m_r:.1f}%)</span></div>
            <div class="op-minus">− PG수수료 &nbsp;<b>{fmt_won(total_pg)}</b>
                <span class="op-rate">({pg_pct:.2f}%)</span></div>
            <div class="op-eq op-final" style="color:{op_color}">= 영업이익 &nbsp;<b>{fmt_won(total_op)}</b>
                <span class="op-rate">({total_op_r:.1f}%)</span></div>
        </div>
        <h3 style="font-size:13px;margin:16px 0 8px;color:#555">결제업체별 PG수수료</h3>
        <div class="table-wrap"><table style="max-width:680px">
            <thead><tr>
                <th>결제업체</th><th>순매출</th><th>수수료율</th><th>PG수수료</th><th>건수</th>
            </tr></thead>
            <tbody>{pg_rows}</tbody>
        </table></div>
    </div>"""


# ── HTML 전체 조립 ────────────────────────────────────────────

CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: 'Apple SD Gothic Neo', 'Noto Sans KR', sans-serif; background: #f4f5f9; color: #333; font-size: 14px; }
header { background: #1a1a2e; color: white; padding: 24px 32px; }
header h1 { font-size: 22px; font-weight: 700; }
header p { margin-top: 6px; color: #aaa; font-size: 13px; }
.container { max-width: 1200px; margin: 0 auto; padding: 24px 16px 48px; }

/* 할인 요약 카드 (최상단) */
.ds-section { background: white; border-radius: 12px; padding: 22px 24px; margin-bottom: 24px; box-shadow: 0 1px 6px rgba(0,0,0,.1); }
.ds-section-title { font-size: 13px; font-weight: 700; color: #455a64; margin-bottom: 16px; letter-spacing: .3px; }
.ds-group { margin-bottom: 18px; }
.ds-group-label { font-size: 11px; font-weight: 700; color: #bbb; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 10px; }
.ds-grid { display: grid; gap: 10px; }
.ds-grid-main  { grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); }
.ds-grid-disc  { grid-template-columns: repeat(auto-fit, minmax(130px, 1fr)); }
.ds-card { border-radius: 8px; padding: 14px 16px; }
.ds-card .ds-label { font-size: 11px; color: #888; margin-bottom: 5px; font-weight: 500; }
.ds-card .ds-value { font-size: 16px; font-weight: 700; color: #1a1a2e; white-space: nowrap; }
.ds-card .ds-sub { font-size: 11px; color: #aaa; margin-top: 3px; }
.ds-c-neutral  { background: #f8f9fa; border: 1px solid #e9ecef; }
.ds-c-discount { background: #fff8e1; border: 1px solid #ffecb3; }
.ds-c-rev      { background: #e3f2fd; border: 1px solid #bbdefb; }
.ds-c-cost     { background: #fafafa; border: 1px solid #eeeeee; }
.ds-c-profit   { border: 1px solid #c8e6c9; }
.ds-c-pg       { background: #fce4ec; border: 1px solid #f8bbd0; }
.ds-c-op       { border: 1px solid #b2dfdb; }
.ds-c-qty      { background: #ede7f6; border: 1px solid #d1c4e9; }

/* 요약 카드 */
.kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 28px; }
.card { background: white; border-radius: 10px; padding: 18px 20px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
.card .label { font-size: 12px; color: #888; margin-bottom: 6px; }
.card .value { font-size: 20px; font-weight: 700; color: #1a1a2e; }
.card .sub { font-size: 11px; color: #aaa; margin-top: 4px; }

/* 섹션 */
.section { background: white; border-radius: 10px; padding: 20px 24px; margin-bottom: 20px; box-shadow: 0 1px 4px rgba(0,0,0,.08); }
.section h2 { font-size: 15px; font-weight: 700; margin-bottom: 14px; color: #1a1a2e; border-left: 4px solid #1a1a2e; padding-left: 10px; }
.section h2 .sub-label { font-size: 12px; font-weight: 400; color: #999; }
.warn-section { border: 2px solid #ef9a9a; }
.warn-section h2 { border-left-color: #c62828; }
.ok-section h2 { border-left-color: #2e7d32; color: #2e7d32; }
.outlet-section { border: 2px solid #ffb74d; }
.outlet-section h2 { border-left-color: #e65100; color: #e65100; }
.outlet-desc { color: #e65100; font-size: 12px; margin-bottom: 12px; line-height: 1.7; }

/* 테이블 */
.table-wrap { overflow-x: auto; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
thead tr { background: #f0f2f8; }
th { padding: 9px 12px; text-align: left; font-weight: 600; color: #555; white-space: nowrap; }
td { padding: 8px 12px; border-bottom: 1px solid rgba(0,0,0,.04); vertical-align: middle; }
.num { text-align: right; font-variant-numeric: tabular-nums; }
tr:last-child td { border-bottom: none; }
.warn-val { color: #c62828 !important; font-weight: 700; }

/* 배지 */
.badge { display: inline-block; margin-left: 6px; padding: 2px 7px; border-radius: 4px; font-size: 10px; font-weight: 700; vertical-align: middle; }
.badge-재고소진, .badge-아울렛, .badge-드맘 { background: #ff7043; color: white; }
.badge-자체제작 { background: #7b1fa2; color: white; }
.badge-사입 { background: #1565c0; color: white; }

/* 경고 설명 */
.warn-desc { color: #c62828; font-size: 12px; margin-bottom: 12px; line-height: 1.7; }

/* 재고소진 KPI */
.clearance-kpi { display: flex; flex-wrap: wrap; gap: 16px; background: #fff3e0; border-radius: 8px; padding: 12px 16px; margin-bottom: 14px; font-size: 13px; }
.clearance-kpi span { color: #555; }
.clearance-kpi b { color: #1a1a2e; }

/* 범례 */
.legend { display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 16px; align-items: center; }
.legend-label { font-size: 12px; color: #888; font-weight: 600; }
.legend-item { display: flex; align-items: center; gap: 5px; font-size: 12px; color: #555; }
.legend-dot { width: 14px; height: 14px; border-radius: 3px; flex-shrink: 0; }

/* 구분선 */
.divider { border: none; border-top: 2px dashed #e0e0e0; margin: 28px 0 20px; }
.divider-title { font-size: 16px; font-weight: 700; color: #e65100; margin-bottom: 16px; padding-left: 4px; }

/* 막대 */
.bar { height: 10px; background: #ef9a9a; border-radius: 3px; min-width: 2px; }

/* PG 섹션 */
.pg-kpi { display: flex; gap: 32px; margin-bottom: 16px; flex-wrap: wrap; }
.pg-kpi-item .label { font-size: 12px; color: #888; margin-bottom: 4px; }
.pg-kpi-item .value { font-size: 22px; font-weight: 700; }
.pg-kpi-item .sub { font-size: 11px; color: #aaa; margin-top: 2px; }
.op-calc { background: #f8f9fa; border-radius: 8px; padding: 14px 18px; margin-bottom: 16px; font-size: 13px; line-height: 2.2; }
.op-calc div { color: #555; }
.op-calc b { color: #1a1a2e; }
.op-minus { padding-left: 20px; }
.op-eq { font-weight: 600; color: #1a1a2e !important; }
.op-rate { font-size: 12px; font-weight: 400; color: #888; margin-left: 6px; }
.op-final { font-size: 15px; border-top: 1px solid #ddd; padding-top: 6px; margin-top: 2px; }

footer { text-align: center; color: #bbb; font-size: 12px; padding: 24px; }

/* 전체 상품 마진 분석 */
.all-section { border: 1px solid #e0e0e0; }
.all-section h2 { border-left-color: #455a64; color: #455a64; }
tr.row-cancelled td { background: #f5f5f5; color: #9e9e9e; }
tr.row-exchange td { background: #fff8e1; color: #795548; }
.status-chip { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 600; white-space: nowrap; }
.status-normal { background: #e8f5e9; color: #2e7d32; }
.status-cancelled { background: #eeeeee; color: #757575; }
.status-exchange { background: #fff3e0; color: #e65100; }
.status-other { background: #e3f2fd; color: #1565c0; }

/* 필터 버튼 */
.f-wrap { margin-bottom: 18px; }
.f-row { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-bottom: 8px; }
.f-label { font-size: 11px; color: #888; font-weight: 700; min-width: 90px; flex-shrink: 0; }
.f-btn { background: #f0f2f8; border: 1px solid #e0e0e0; border-radius: 16px; padding: 4px 12px; font-size: 12px; cursor: pointer; color: #555; transition: all .15s; white-space: nowrap; line-height: 1.5; }
.f-btn:hover { background: #e0e4f0; border-color: #c5cae9; }
.f-btn.f-active { background: #1a1a2e; color: white; border-color: #1a1a2e; font-weight: 600; }

/* 필터 요약 */
.f-summary { background: #f8f9fa; border-left: 3px solid #455a64; border-radius: 0 6px 6px 0; padding: 10px 16px; margin-bottom: 16px; font-size: 13px; color: #555; display: flex; gap: 20px; flex-wrap: wrap; }
.f-summary b { color: #1a1a2e; }

/* 섹션 접기/펼치기 */
.collapse-btn { float: right; background: none; border: 1px solid #ccc; border-radius: 4px; padding: 2px 10px; font-size: 11px; cursor: pointer; color: #888; margin-left: 12px; line-height: 1.6; transition: all .15s; }
.collapse-btn:hover { background: #f0f2f8; color: #333; border-color: #aaa; }
.ds-collapse-btn { float: right; background: none; border: 1px solid #b0bec5; border-radius: 4px; padding: 2px 10px; font-size: 11px; cursor: pointer; color: #78909c; line-height: 1.6; transition: all .15s; }
.ds-collapse-btn:hover { background: #eceff1; color: #455a64; }
.section-body-hidden > *:not(h2):not(.ds-section-title) { display: none; }

/* 환불율 분석 */
.refund-section h2 { border-left-color: #7b1fa2; color: #4a148c; }
.refund-kpi { display: flex; gap: 20px; flex-wrap: wrap; background: #f3e5f5; border-radius: 8px; padding: 12px 18px; margin-bottom: 20px; font-size: 13px; color: #555; }
.refund-kpi b { color: #1a1a2e; }
.refund-sub { font-size: 13px; font-weight: 700; color: #4a148c; margin: 20px 0 8px; padding-left: 8px; border-left: 3px solid #ce93d8; }
.ref-hi  { color: #c62828 !important; font-weight: 700; }
.ref-mid { color: #e65100 !important; font-weight: 700; }
td.ref-hi  { background: #ffcdd2; }
td.ref-mid { background: #fff3e0; }

/* 테이블 헤더 정렬 */
th.th-sort { cursor: pointer; user-select: none; white-space: nowrap; }
th.th-sort:hover { background: #e4e8f4; }
th.th-sort::after { content: ' ⇅'; color: #ccc; font-size: 10px; }
th.th-asc::after  { content: ' ▲'; color: #1a1a2e; font-size: 10px; }
th.th-desc::after { content: ' ▼'; color: #1a1a2e; font-size: 10px; }

/* 상품별 판매수량 분석 */
.prod-sales-section h2 { border-left-color: #1565c0; color: #0d47a1; }
.psd-inner { padding: 12px 16px 14px; background: #f0f4ff; border-radius: 6px; margin: 2px 0; }
.osd-inner { padding: 8px 14px 10px; background: #e8eaf6; border-radius: 4px; }
.psd-tabs { display: flex; gap: 4px; margin-bottom: 10px; }
.psd-tab { background: #e8edf8; border: 1px solid #c5cae9; border-radius: 4px 4px 0 0; padding: 4px 14px; font-size: 12px; font-weight: 600; color: #5c6bc0; cursor: pointer; transition: all .15s; }
.psd-tab:hover { background: #d1d9f5; }
.psd-tab-active { background: #fff; border-bottom-color: #fff; color: #3949ab; box-shadow: 0 -1px 3px rgba(0,0,0,.07); }
.psd-sub-title { font-size: 12px; font-weight: 700; color: #37474f; margin: 0 0 8px; }
table.psd-tbl { font-size: 12px; width: 100%; border-collapse: collapse; }
table.psd-tbl thead tr { background: #dde3f5; }
table.psd-tbl th { padding: 7px 10px; font-weight: 600; color: #555; text-align: left; white-space: nowrap; }
table.psd-tbl td { padding: 6px 10px; border-bottom: 1px solid rgba(0,0,0,.04); }
table.psd-tbl tr:last-child td { border-bottom: none; }
.psr-btn, .osr-btn { background: none; border: 1px solid #b0bec5; border-radius: 3px; padding: 1px 6px; cursor: pointer; font-size: 11px; color: #455a64; transition: all .15s; line-height: 1.4; }
.psr-btn:hover, .osr-btn:hover { background: #e3e8f8; border-color: #3949ab; color: #1a237e; }
.trend-up { color: #c62828; font-weight: 700; }
.trend-dn { color: #1565c0; font-weight: 700; }
.mini-bar { display: inline-block; height: 10px; background: #90caf9; border-radius: 2px; vertical-align: middle; min-width: 2px; }
"""


JS = """
<script>
(function(){
'use strict';

/* ── 섹션 접기/펼치기 ─────────────────────────────────── */
function addToggle(section, heading, btnClass, defaultExpanded) {
  var btn = document.createElement('button');
  btn.className = btnClass;
  btn.textContent = defaultExpanded ? '접기' : '펼치기';
  var getContent = function() {
    return Array.from(section.children).filter(function(c){ return c !== heading; });
  };
  if (!defaultExpanded) {
    getContent().forEach(function(c){ c.style.display='none'; });
  }
  btn.addEventListener('click', function(e){
    e.stopPropagation();
    var contents = getContent();
    var nowHidden = contents.length > 0 && contents[0].style.display === 'none';
    contents.forEach(function(c){ c.style.display = nowHidden ? '' : 'none'; });
    btn.textContent = nowHidden ? '접기' : '펼치기';
  });
  heading.appendChild(btn);
}

document.querySelectorAll('.ds-section').forEach(function(sec){
  var h = sec.querySelector('.ds-section-title');
  if (h) addToggle(sec, h, 'ds-collapse-btn', true);
});
document.querySelectorAll('.section').forEach(function(sec){
  var h = sec.querySelector('h2');
  if (h) addToggle(sec, h, 'collapse-btn', false);
});

/* ── 테이블 헤더 클릭 정렬 ────────────────────────────── */
function cellVal(td) {
  if (!td) return '';
  var raw = td.textContent.replace(/[,원개%\\s▲▼📈📉]/g,'').trim();
  var n = parseFloat(raw);
  return isNaN(n) ? td.textContent.trim() : n;
}

function sortPaired(tbody, rows, mainCls, detSelector, idx, newDir) {
  /* 메인 행과 연결된 detail 행을 쌍으로 유지하며 정렬 */
  var mains = rows.filter(function(r){ return r.classList.contains(mainCls); });
  mains.sort(function(a, b){
    var av = cellVal(a.querySelectorAll('td')[idx]);
    var bv = cellVal(b.querySelectorAll('td')[idx]);
    if (typeof av === 'number' && typeof bv === 'number')
      return newDir === 'asc' ? av - bv : bv - av;
    var cmp = String(av).localeCompare(String(bv), 'ko');
    return newDir === 'asc' ? cmp : -cmp;
  });
  mains.forEach(function(r){
    tbody.appendChild(r);
    var det = detSelector(r);
    if (det) tbody.appendChild(det);
  });
}

document.querySelectorAll('table').forEach(function(tbl){
  var ths = Array.from(tbl.querySelectorAll('thead th'));
  var sortCol = -1, sortDir = 'none';

  ths.forEach(function(th, idx){
    th.classList.add('th-sort');
    th.addEventListener('click', function(){
      var newDir = (sortCol === idx && sortDir === 'asc') ? 'desc' : 'asc';
      sortCol = idx; sortDir = newDir;
      ths.forEach(function(h){ h.classList.remove('th-asc','th-desc'); });
      th.classList.add(newDir === 'asc' ? 'th-asc' : 'th-desc');

      var tbody = tbl.querySelector('tbody');
      if (!tbody) return;
      var rows = Array.from(tbody.querySelectorAll(':scope > tr'));

      /* 상품별 판매수량 메인 테이블 */
      if (tbl.id === 'prod-sales-tbl') {
        sortPaired(tbody, rows, 'psr', function(r){
          return tbody.querySelector('.psd[data-pidx="'+r.dataset.pidx+'"]');
        }, idx, newDir);
        return;
      }

      /* 옵션 sub-table (psr/psd 쌍) */
      if (tbl.classList.contains('psd-opt-tbl')) {
        sortPaired(tbody, rows, 'osr', function(r){
          var btn = r.querySelector('.osr-btn');
          return btn ? document.getElementById('osd-'+btn.dataset.key) : null;
        }, idx, newDir);
        return;
      }

      /* 일반 테이블 */
      rows.sort(function(a, b){
        var av = cellVal(a.querySelectorAll('td')[idx]);
        var bv = cellVal(b.querySelectorAll('td')[idx]);
        if (typeof av === 'number' && typeof bv === 'number')
          return newDir === 'asc' ? av - bv : bv - av;
        var cmp = String(av).localeCompare(String(bv), 'ko');
        return newDir === 'asc' ? cmp : -cmp;
      });
      rows.forEach(function(r){ tbody.appendChild(r); });
    });
  });
});

/* ── 상품/옵션 행 Expand 버튼 ────────────────────────── */
document.addEventListener('click', function(e){
  var pBtn = e.target.closest('.psr-btn');
  if (pBtn) {
    var pidx = pBtn.dataset.pidx;
    var det = document.querySelector('.psd[data-pidx="'+pidx+'"]');
    if (det) {
      var open = det.style.display !== 'none';
      det.style.display = open ? 'none' : '';
      pBtn.textContent = open ? '▶' : '▼';
    }
    return;
  }
  var oBtn = e.target.closest('.osr-btn');
  if (oBtn) {
    var key = oBtn.dataset.key;
    var det = document.getElementById('osd-'+key);
    if (det) {
      var open = det.style.display !== 'none';
      det.style.display = open ? 'none' : '';
      oBtn.textContent = open ? '▶' : '▼';
    }
    return;
  }

  /* 옵션별/일자별 탭 전환 */
  var tabBtn = e.target.closest('.psd-tab');
  if (tabBtn) {
    var paneId = tabBtn.dataset.pane;
    var sibId  = tabBtn.dataset.sibling;
    var pane   = document.getElementById(paneId);
    var sib    = document.getElementById(sibId);
    var sibPane= sib ? document.getElementById(sib.dataset.pane) : null;
    if (!pane) return;
    pane.style.display = '';
    tabBtn.classList.add('psd-tab-active');
    if (sibPane) sibPane.style.display = 'none';
    if (sib) sib.classList.remove('psd-tab-active');
    return;
  }
});

})();
</script>
"""


def _status_chip(status):
    if "취소" in status:
        return f'<span class="status-chip status-cancelled">{status}</span>'
    if "교환" in status:
        return f'<span class="status-chip status-exchange">{status}</span>'
    if status in ("배송 완료", "배송중", "배송 준비중", "결제 완료", "상품 준비중"):
        return f'<span class="status-chip status-normal">{status}</span>'
    return f'<span class="status-chip status-other">{status}</span>'


def _row_class(status):
    if "취소" in status:
        return ' class="row-cancelled"'
    if "교환" in status:
        return ' class="row-exchange"'
    return ""


def build_unified_sales_section(enriched_rows):
    if not enriched_rows:
        return ""

    def get_date(r):
        for col in ("주문일시", "결제일시(입금확인일)", "결제일시", "결제일", "주문일", "주문 일시"):
            v = r.get(col, "").strip()
            if v:
                return v[:10]
        return ""

    def get_opt(r):
        v = (r.get("상품옵션") or r.get("옵션명") or r.get("옵션") or r.get("상품 옵션") or "").strip()
        return v or "기본"

    # ── 데이터 집계 ────────────────────────────────────────────────
    prod_stats = {}  # (prod, brand) → stats dict

    for r in enriched_rows:
        prod     = r.get("상품명(데드라)", "").strip()
        if not prod:
            continue
        brand    = parse_brand(r.get("브랜드"))
        cat      = r.get("메인카테고리 이름", "").strip()
        supplier = r.get("공급사명", "").strip()
        qty      = safe_float(r.get("수량"))
        amount   = safe_float(r.get("상품구매금액"))
        is_ref   = bool(r.get("_skip", False))
        opt      = get_opt(r)
        date     = get_date(r)
        net_rev  = r.get("_net_revenue", 0.0)
        cost     = r.get("_cost", 0.0)
        discount = r.get("_total_discount", 0.0)

        key = (prod, brand)
        if key not in prod_stats:
            prod_stats[key] = {"qty": 0.0, "orders": 0, "refund_cnt": 0,
                               "refund_amt": 0.0, "net_rev": 0.0, "cost": 0.0,
                               "discount": 0.0, "opts": {},
                               "cat_qty": {}, "suppliers": set()}
        ps = prod_stats[key]
        ps["orders"] += 1
        if cat:
            ps["cat_qty"][cat] = ps["cat_qty"].get(cat, 0.0) + (qty if not is_ref else 0)
        if supplier:
            ps["suppliers"].add(supplier)

        if is_ref:
            ps["refund_cnt"] += 1
            ps["refund_amt"] += amount
        else:
            ps["qty"]      += qty
            ps["net_rev"]  += net_rev
            ps["cost"]     += cost
            ps["discount"] += discount

        if opt not in ps["opts"]:
            ps["opts"][opt] = {"qty": 0.0, "orders": 0, "refund_cnt": 0,
                               "refund_amt": 0.0, "net_rev": 0.0, "cost": 0.0,
                               "discount": 0.0, "daily": {}}
        oi = ps["opts"][opt]
        oi["orders"] += 1
        if is_ref:
            oi["refund_cnt"] += 1
            oi["refund_amt"] += amount
        else:
            oi["qty"]      += qty
            oi["net_rev"]  += net_rev
            oi["cost"]     += cost
            oi["discount"] += discount
            if date:
                oi["daily"][date] = oi["daily"].get(date, 0.0) + qty

    # ── 트렌드 계산 ────────────────────────────────────────────────
    def calc_trend(ps):
        daily = {}
        for oi in ps["opts"].values():
            for d, q in oi["daily"].items():
                daily[d] = daily.get(d, 0.0) + q
        if len(daily) < 4:
            return ""
        dates   = sorted(daily.keys())
        qtys    = [daily[d] for d in dates]
        overall = sum(qtys) / len(qtys)
        last3   = sum(qtys[-3:]) / 3
        if last3 > overall * 1.05:
            return "📈"
        if last3 < overall * 0.95:
            return "📉"
        return ""

    # ── HTML 헬퍼 ─────────────────────────────────────────────────
    def ref_cls(rate):
        return "ref-hi" if rate >= 20 else ("ref-mid" if rate >= 10 else "")

    def mk_daily_rows(opt_daily):
        if not opt_daily:
            return "<tr><td colspan='5' style='text-align:center;color:#999;padding:8px'>날짜 정보 없음</td></tr>"
        dates    = sorted(opt_daily.keys())
        max_qty  = max(opt_daily.values()) or 1
        cum      = 0.0
        prev_qty = None
        rows     = []
        for d in dates:
            q    = opt_daily[d]
            cum += q
            if prev_qty is None:
                tr_sym = '<span style="color:#bbb">-</span>'
            elif q > prev_qty:
                tr_sym = '<span style="color:#c62828;font-weight:700">▲</span>'
            elif q < prev_qty:
                tr_sym = '<span style="color:#1565c0;font-weight:700">▼</span>'
            else:
                tr_sym = '<span style="color:#bbb">-</span>'
            bar_w = max(2, int(q / max_qty * 80))
            bar   = f'<span class="mini-bar" style="width:{bar_w}px"></span>'
            rows.append(
                f'<tr>'
                f'<td style="white-space:nowrap;font-size:12px">{d}</td>'
                f'<td class="num">{q:,.0f}</td>'
                f'<td class="num" style="color:#888">{cum:,.0f}</td>'
                f'<td style="text-align:center">{tr_sym}</td>'
                f'<td style="min-width:90px">{bar}</td>'
                f'</tr>'
            )
            prev_qty = q
        return "".join(rows)

    def mk_prod_daily_rows(ps):
        """상품 전체 일자별 집계 (옵션 합산)"""
        daily = {}
        for oi in ps["opts"].values():
            for d, q in oi["daily"].items():
                daily[d] = daily.get(d, 0.0) + q
        return mk_daily_rows(daily)

    def mk_option_rows(ps_opts, pidx):
        sorted_opts = sorted(ps_opts.items(), key=lambda x: -x[1]["net_rev"])
        parts = []
        for oidx, (opt_name, oi) in enumerate(sorted_opts):
            orate     = (oi["refund_cnt"] / oi["orders"] * 100) if oi["orders"] else 0.0
            omgn      = oi["net_rev"] - oi["cost"]
            omgn_rate = (omgn / oi["net_rev"] * 100) if oi["net_rev"] else 0.0
            okey      = f"{pidx}-{oidx}"
            daily_html = mk_daily_rows(oi["daily"])
            parts.append(
                f'<tr class="osr">'
                f'<td><button class="osr-btn" data-key="{okey}">▶</button></td>'
                f'<td>{html.escape(opt_name)}</td>'
                f'<td class="num">{oi["qty"]:,.0f}</td>'
                f'<td class="num">{oi["refund_cnt"]}</td>'
                f'<td class="num {ref_cls(orate)}">{orate:.1f}%</td>'
                f'<td class="num">{oi["refund_amt"]:,.0f}원</td>'
                f'<td class="num">{oi["net_rev"]:,.0f}원</td>'
                f'<td class="num">{oi["cost"]:,.0f}원</td>'
                f'<td class="num">{oi["discount"]:,.0f}원</td>'
                f'<td class="num">{omgn:,.0f}원</td>'
                f'<td class="num {("warn-val" if omgn_rate < 0 else "")}">{omgn_rate:.1f}%</td>'
                f'</tr>'
                f'<tr class="osd" id="osd-{okey}" style="display:none">'
                f'<td colspan="11" style="padding:0">'
                f'<div class="osd-inner">'
                f'<div class="psd-sub-title" style="margin:6px 0 6px">📅 일자별 판매수량</div>'
                f'<table class="psd-tbl">'
                f'<thead><tr>'
                f'<th>날짜</th><th class="num">판매수량</th><th class="num">누적수량</th>'
                f'<th style="text-align:center">추세</th><th>추이</th>'
                f'</tr></thead>'
                f'<tbody>{daily_html}</tbody>'
                f'</table></div></td></tr>'
            )
        return "".join(parts)

    # ── 상품 정렬 및 메인 테이블 생성 ─────────────────────────────
    sorted_prods = sorted(prod_stats.items(), key=lambda x: -x[1]["net_rev"])
    main_rows    = []

    for pidx, (key, ps) in enumerate(sorted_prods):
        prod_name, brand = key
        trend    = calc_trend(ps)
        rrate    = (ps["refund_cnt"] / ps["orders"] * 100) if ps["orders"] else 0.0
        mgn      = ps["net_rev"] - ps["cost"]
        mgn_rate = (mgn / ps["net_rev"] * 100) if ps["net_rev"] else 0.0
        trend_badge = f' <span style="font-size:13px">{trend}</span>' if trend else ""

        # 카테고리: 가장 많이 팔린 것 하나 + "외 N개"
        cat_qty   = ps["cat_qty"]
        cats_sorted = sorted(cat_qty.items(), key=lambda x: -x[1])
        if not cats_sorted:
            display_cat = "-"
        elif len(cats_sorted) == 1:
            display_cat = cats_sorted[0][0]
        else:
            display_cat = f'{cats_sorted[0][0]} 외 {len(cats_sorted)-1}개'

        # 공급사: 단일이면 그대로, 복수면 대표 하나 + "외 N개"
        suppliers = sorted(ps["suppliers"])
        if not suppliers:
            display_sup = "-"
        elif len(suppliers) == 1:
            display_sup = suppliers[0]
        else:
            display_sup = f'{suppliers[0]} 외 {len(suppliers)-1}개'

        opt_rows_html   = mk_option_rows(ps["opts"], pidx)
        prod_daily_html = mk_prod_daily_rows(ps)

        # 2단계: 탭 구조 (옵션별 | 일자별)
        tab_id_opt  = f"tab-opt-{pidx}"
        tab_id_day  = f"tab-day-{pidx}"
        pane_id_opt = f"pane-opt-{pidx}"
        pane_id_day = f"pane-day-{pidx}"

        detail = (
            f'<div class="psd-inner">'
            f'<div class="psd-tabs">'
            f'<button class="psd-tab psd-tab-active" id="{tab_id_opt}" '
            f'  data-pane="{pane_id_opt}" data-sibling="{tab_id_day}">📦 옵션별</button>'
            f'<button class="psd-tab" id="{tab_id_day}" '
            f'  data-pane="{pane_id_day}" data-sibling="{tab_id_opt}">📅 일자별</button>'
            f'</div>'
            # 옵션별 탭 패널
            f'<div id="{pane_id_opt}">'
            f'<table class="psd-tbl psd-opt-tbl">'
            f'<thead><tr>'
            f'<th style="width:30px"></th>'
            f'<th>옵션명</th><th class="num">판매수량</th>'
            f'<th class="num">환불건수</th><th class="num">환불율</th><th class="num">환불금액</th>'
            f'<th class="num">순매출</th><th class="num">공급원가</th><th class="num">총할인액</th>'
            f'<th class="num">마진</th><th class="num">마진율</th>'
            f'</tr></thead>'
            f'<tbody>{opt_rows_html}</tbody>'
            f'</table></div>'
            # 일자별 탭 패널
            f'<div id="{pane_id_day}" style="display:none">'
            f'<table class="psd-tbl">'
            f'<thead><tr>'
            f'<th>날짜</th><th class="num">판매수량</th><th class="num">누적수량</th>'
            f'<th style="text-align:center">추세</th><th>추이</th>'
            f'</tr></thead>'
            f'<tbody>{prod_daily_html}</tbody>'
            f'</table></div>'
            f'</div>'
        )

        main_rows.append(
            f'<tr class="psr" data-pidx="{pidx}">'
            f'<td><button class="psr-btn" data-pidx="{pidx}">▶</button></td>'
            f'<td>{html.escape(prod_name)}{trend_badge}</td>'
            f'<td style="white-space:nowrap">{html.escape(brand)}</td>'
            f'<td style="white-space:nowrap">{html.escape(display_cat)}</td>'
            f'<td style="white-space:nowrap;font-size:12px;color:#546e7a">{html.escape(display_sup)}</td>'
            f'<td class="num">{ps["qty"]:,.0f}</td>'
            f'<td class="num">{ps["net_rev"]:,.0f}원</td>'
            f'<td class="num">{ps["cost"]:,.0f}원</td>'
            f'<td class="num">{ps["discount"]:,.0f}원</td>'
            f'<td class="num">{mgn:,.0f}원</td>'
            f'<td class="num {("warn-val" if mgn_rate < 0 else "")}">{mgn_rate:.1f}%</td>'
            f'<td class="num">{ps["refund_cnt"]}</td>'
            f'<td class="num {ref_cls(rrate)}">{rrate:.1f}%</td>'
            f'<td class="num">{ps["refund_amt"]:,.0f}원</td>'
            f'</tr>'
            f'<tr class="psd" data-pidx="{pidx}" style="display:none">'
            f'<td colspan="14" style="padding:4px 8px 8px">{detail}</td>'
            f'</tr>'
        )

    body_html   = "".join(main_rows)
    total_prods = len(sorted_prods)

    return f"""
<hr class="divider">
<div class="divider-title">📊 전체 상품 판매 분석</div>
<div class="section prod-sales-section">
  <h2>전체 상품 판매 분석 <span class="sub-label">전체 {total_prods}개 상품 · 순매출 내림차순 · ▶ 클릭 → 옵션별/일자별 탭 → 옵션 ▶ → 일자별 상세</span></h2>
  <div class="table-wrap">
    <table id="prod-sales-tbl">
      <thead>
        <tr>
          <th style="width:30px"></th>
          <th>상품명</th><th>브랜드명</th><th>카테고리</th><th>거래처명</th>
          <th class="num">판매수량</th><th class="num">순매출</th>
          <th class="num">공급원가</th><th class="num">총할인액</th>
          <th class="num">마진</th><th class="num">마진율</th>
          <th class="num">환불건수</th><th class="num">환불율</th><th class="num">환불금액</th>
        </tr>
      </thead>
      <tbody>{body_html}</tbody>
    </table>
  </div>
</div>"""


# ── (removed: build_all_products_section, build_product_sales_section) ──────


# ── 환불율 분석 ────────────────────────────────────────────────

PENDING_STATUS = "반품 처리중 - 수거전"

def build_refund_section(enriched_rows):
    if not enriched_rows:
        return ""

    def new_stat():
        return {"total": 0, "refund": 0, "pending": 0,
                "amount_all": 0.0, "amount_ref": 0.0, "amount_pend": 0.0}

    brand_stats = defaultdict(new_stat)
    cat_stats   = defaultdict(new_stat)
    prod_stats  = {}  # prod_name → stat dict (+ meta sets)

    for r in enriched_rows:
        brand    = parse_brand(r.get("브랜드"))
        cat      = r.get("메인카테고리 이름", "").strip()
        prod     = r.get("상품명(데드라)", "").strip()
        supplier = r.get("공급사명", "").strip()
        amount   = safe_float(r.get("상품구매금액"))
        qty      = safe_float(r.get("수량"))
        status   = r.get("주문 상태", "").strip()
        is_ref   = bool(r.get("_skip", False))
        is_pend  = (status == PENDING_STATUS)

        if prod not in prod_stats:
            prod_stats[prod] = {**new_stat(),
                                "brands": set(), "cats": set(), "suppliers": set(), "qty": 0.0}
        ps = prod_stats[prod]
        if brand:    ps["brands"].add(brand)
        if cat:      ps["cats"].add(cat)
        if supplier: ps["suppliers"].add(supplier)

        for d in (brand_stats[brand], cat_stats[cat], ps):
            d["total"]      += 1
            d["amount_all"] += amount
            if is_ref:
                d["refund"]      += 1
                d["amount_ref"]  += amount
            elif is_pend:
                d["pending"]     += 1
                d["amount_pend"] += amount

        if not is_ref and not is_pend:
            ps["qty"] += qty

    def ref_rate(d):
        return (d["refund"] / d["total"] * 100) if d["total"] else 0.0

    def amt_rate(d):
        return (d["amount_ref"] / d["amount_all"] * 100) if d["amount_all"] else 0.0

    def rate_td(rate):
        cls = "ref-hi" if rate >= 20 else ("ref-mid" if rate >= 10 else "")
        return f'<td class="num {cls}">{rate:.1f}%</td>'

    def pend_td(cnt, amt):
        if cnt == 0:
            return '<td class="num" style="color:#bbb">-</td><td class="num" style="color:#bbb">-</td>'
        return (f'<td class="num" style="color:#e65100;font-weight:600">{cnt}</td>'
                f'<td class="num" style="color:#e65100">{amt:,.0f}원</td>')

    def sort_key(item):
        return (-ref_rate(item[1]), -item[1]["refund"])

    # 브랜드별
    brand_rows = sorted(((k, v) for k, v in brand_stats.items() if k), key=sort_key)
    brand_html = "".join(
        f'<tr><td style="white-space:nowrap">{name}</td>'
        f'<td class="num">{d["total"]}</td>'
        f'<td class="num">{d["refund"]}</td>'
        f'{rate_td(ref_rate(d))}'
        f'<td class="num">{d["amount_ref"]:,.0f}원</td>'
        f'<td class="num">{amt_rate(d):.1f}%</td>'
        f'{pend_td(d["pending"], d["amount_pend"])}</tr>'
        for name, d in brand_rows
    )

    # 카테고리별
    cat_rows = sorted(((k, v) for k, v in cat_stats.items() if k), key=sort_key)
    cat_html = "".join(
        f'<tr><td style="white-space:nowrap">{name}</td>'
        f'<td class="num">{d["total"]}</td>'
        f'<td class="num">{d["refund"]}</td>'
        f'{rate_td(ref_rate(d))}'
        f'<td class="num">{d["amount_ref"]:,.0f}원</td>'
        f'<td class="num">{amt_rate(d):.1f}%</td>'
        f'{pend_td(d["pending"], d["amount_pend"])}</tr>'
        for name, d in cat_rows
    )

    # 상품별 (환불 1건 이상 또는 반품진행중 1건 이상) — 상품명 기준 집계
    prod_rows = sorted(
        ((name, d) for name, d in prod_stats.items() if name and (d["refund"] >= 1 or d["pending"] >= 1)),
        key=sort_key,
    )

    def fmt_set(s):
        vals = sorted(s)
        return vals[0] if len(vals) == 1 else ("복수카테고리" if len(vals) > 1 else "-")

    def fmt_set_plain(s):
        vals = sorted(s)
        return vals[0] if len(vals) == 1 else (", ".join(vals) if vals else "-")

    prod_html = "".join(
        f'<tr>'
        f'<td>{html.escape(name)}</td>'
        f'<td style="white-space:nowrap">{html.escape(fmt_set_plain(d["brands"]))}</td>'
        f'<td style="white-space:nowrap">{html.escape(fmt_set(d["cats"]))}</td>'
        f'<td style="white-space:nowrap;font-size:12px;color:#546e7a">{html.escape(fmt_set_plain(d["suppliers"]))}</td>'
        f'<td class="num">{d["qty"]:,.0f}</td>'
        f'<td class="num">{d["refund"]}</td>'
        f'{rate_td(ref_rate(d))}'
        f'<td class="num">{d["amount_ref"]:,.0f}원</td>'
        f'{pend_td(d["pending"], d["amount_pend"])}</tr>'
        for name, d in prod_rows
    )

    # 전체 요약
    total_cnt    = sum(d["total"]       for d in brand_stats.values())
    refund_cnt   = sum(d["refund"]      for d in brand_stats.values())
    pending_cnt  = sum(d["pending"]     for d in brand_stats.values())
    total_amt    = sum(d["amount_all"]  for d in brand_stats.values())
    refund_amt   = sum(d["amount_ref"]  for d in brand_stats.values())
    pending_amt  = sum(d["amount_pend"] for d in brand_stats.values())
    overall_rate = (refund_cnt / total_cnt * 100) if total_cnt else 0.0
    rate_cls     = "ref-hi" if overall_rate >= 20 else ("ref-mid" if overall_rate >= 10 else "")

    pend_kpi = (
        f'<span>반품진행중: <b style="color:#e65100">{pending_cnt}건 / {pending_amt:,.0f}원</b></span>'
        if pending_cnt else ""
    )

    return f"""
<hr class="divider">
<div class="divider-title">🔄 환불율 분석</div>
<div class="section refund-section">
  <h2>환불율 분석 <span class="sub-label">SKIP_STATUSES 기준 · 반품진행중(수거전) 별도 표시</span></h2>

  <div class="refund-kpi">
    <span>전체 환불율: <b class="{rate_cls}">{overall_rate:.1f}%</b></span>
    <span>환불 건수: <b>{refund_cnt}건</b> / 전체 {total_cnt}건</span>
    <span>환불 금액: <b>{refund_amt:,.0f}원</b></span>
    <span>전체 주문금액 대비: <b>{(refund_amt / total_amt * 100) if total_amt else 0:.1f}%</b></span>
    {pend_kpi}
  </div>

  <div class="refund-sub">① 브랜드별 환불율</div>
  <div class="table-wrap">
    <table>
      <thead><tr>
        <th>브랜드</th><th class="num">전체주문수</th><th class="num">환불건수</th>
        <th class="num">환불율</th><th class="num">환불금액</th><th class="num">환불금액비율</th>
        <th class="num" style="color:#e65100">반품진행중</th><th class="num" style="color:#e65100">진행중금액</th>
      </tr></thead>
      <tbody>{brand_html}</tbody>
    </table>
  </div>

  <div class="refund-sub">② 카테고리별 환불율</div>
  <div class="table-wrap">
    <table>
      <thead><tr>
        <th>카테고리</th><th class="num">전체주문수</th><th class="num">환불건수</th>
        <th class="num">환불율</th><th class="num">환불금액</th><th class="num">환불금액비율</th>
        <th class="num" style="color:#e65100">반품진행중</th><th class="num" style="color:#e65100">진행중금액</th>
      </tr></thead>
      <tbody>{cat_html}</tbody>
    </table>
  </div>

  <div class="refund-sub">③ 상품별 환불율 <span style="font-size:12px;font-weight:400;color:#999">환불·반품진행중 1건 이상 · {len(prod_rows)}개 상품</span></div>
  <div class="table-wrap">
    <table>
      <thead><tr>
        <th>상품명</th><th>브랜드명</th><th>카테고리</th><th>거래처명</th>
        <th class="num">판매수량</th><th class="num">환불건수</th>
        <th class="num">환불율</th><th class="num">환불금액</th>
        <th class="num" style="color:#e65100">반품진행중</th><th class="num" style="color:#e65100">진행중금액</th>
      </tr></thead>
      <tbody>{prod_html}</tbody>
    </table>
  </div>
</div>"""


def generate_html(data, price_anomalies, outlet_items, discount_over, discount_buckets, csv_path, generated_at, enriched_rows=None):
    n = data["normal"]
    c = data["clearance"]
    total_rev  = n["revenue"] + c["revenue"]
    total_cost = n["cost"]    + c["cost"]
    total_pg   = n["pg_fee"]  + c["pg_fee"]
    total_m    = total_rev - total_cost
    total_rate = (total_m / total_rev * 100) if total_rev else 0
    total_op   = total_m - total_pg
    total_op_r = (total_op / total_rev * 100) if total_rev else 0
    normal_rate = margin_rate(n)

    # ── 할인 요약 카드 ─────────────────────────────────────────
    ds = data.get("ds", {})
    pur    = ds.get("purchase",  0.0)
    coup   = ds.get("coupon",    0.0)
    grade  = ds.get("grade",     0.0)
    pdisc  = ds.get("prod_disc", 0.0)
    pts    = ds.get("points",    0.0)
    dep    = ds.get("deposit",   0.0)
    nvr    = ds.get("naver_pt",  0.0)
    d_qty  = ds.get("qty",       0.0)
    tot_disc = coup + grade + pdisc
    disc_pct = (tot_disc / pur * 100) if pur else 0.0
    pg_pct   = (total_pg / total_rev * 100) if total_rev else 0.0

    def _pct(v):  # 주문금액 대비 비율
        return f"주문금액 대비 {(v / pur * 100) if pur else 0:.1f}%"

    def dscard(label, val, sub="", cls="ds-c-neutral", val_color=""):
        vc = f' style="color:{val_color}"' if val_color else ""
        sb = f'<div class="ds-sub">{sub}</div>' if sub else ""
        return (f'<div class="ds-card {cls}">'
                f'<div class="ds-label">{label}</div>'
                f'<div class="ds-value"{vc}>{val}</div>{sb}</div>')

    mgn_col = margin_color_css(total_rate)
    op_col  = margin_color_css(total_op_r)
    mgn_bg  = "ds-c-profit" if total_m  >= 0 else "ds-c-pg"
    op_bg   = "ds-c-op"     if total_op >= 0 else "ds-c-pg"

    discount_summary_html = f"""
<div class="ds-section">
  <div class="ds-section-title">📊 할인 및 매출 총합 요약</div>

  <div class="ds-group">
    <div class="ds-group-label">매출 흐름</div>
    <div class="ds-grid ds-grid-main">
      {dscard("총 주문금액",  f"{pur:,.0f}원",       cls="ds-c-neutral")}
      {dscard("총 할인금액",  f"{tot_disc:,.0f}원",  sub=f"쿠폰+등급+추가할인 | {disc_pct:.1f}% 할인",
              cls="ds-c-discount")}
      {dscard("순매출",      f"{total_rev:,.0f}원",  sub="구매금액 − 쿠폰·등급·추가할인 + 네이버포인트",
              cls="ds-c-rev")}
      {dscard("공급원가",    f"{total_cost:,.0f}원",  cls="ds-c-cost")}
      {dscard("마진",        f"{total_m:,.0f}원",    sub=f"마진율 {total_rate:.1f}%",
              cls=mgn_bg, val_color=mgn_col)}
      {dscard("마진율",      f"{total_rate:.1f}%",
              cls=mgn_bg, val_color=mgn_col)}
      {dscard("PG수수료",    f"{total_pg:,.0f}원",   sub=f"순매출 대비 {pg_pct:.2f}%",
              cls="ds-c-pg")}
      {dscard("영업이익",    f"{total_op:,.0f}원",   sub=f"영업이익률 {total_op_r:.1f}%",
              cls=op_bg, val_color=op_col)}
      {dscard("영업이익률",  f"{total_op_r:.1f}%",
              cls=op_bg, val_color=op_col)}
      {dscard("총 판매수량", f"{d_qty:,.0f}개",      cls="ds-c-qty")}
    </div>
  </div>

  <div class="ds-group" style="margin-bottom:0">
    <div class="ds-group-label">할인 항목별 상세</div>
    <div class="ds-grid ds-grid-disc">
      {dscard("쿠폰 할인",       f"{coup:,.0f}원",  sub=_pct(coup),  cls="ds-c-discount")}
      {dscard("회원등급 할인",   f"{grade:,.0f}원", sub=_pct(grade), cls="ds-c-discount")}
      {dscard("상품별 추가할인", f"{pdisc:,.0f}원", sub=_pct(pdisc), cls="ds-c-discount")}
      {dscard("적립금 사용",           f"{pts:,.0f}원", sub="결제수단 — 순매출 미포함", cls="ds-c-neutral")}
      {dscard("예치금 사용",           f"{dep:,.0f}원", sub="결제수단 — 순매출 미포함", cls="ds-c-neutral")}
      {dscard("네이버포인트 (매출 포함)", f"{nvr:,.0f}원", sub="순매출에 가산",             cls="ds-c-rev")}
    </div>
  </div>
</div>"""

    kpi_cards = f"""
    <div class="kpi-grid">
        <div class="card">
            <div class="label">전체 순매출</div>
            <div class="value">{total_rev:,.0f}원</div>
            <div class="sub">재고소진 포함</div>
        </div>
        <div class="card">
            <div class="label">전체 공급원가</div>
            <div class="value">{total_cost:,.0f}원</div>
        </div>
        <div class="card" style="background:{margin_bg(total_rate)}">
            <div class="label">전체 마진율</div>
            <div class="value" style="color:{margin_color_css(total_rate)}">{total_rate:.1f}%</div>
            <div class="sub">마진 {total_m:,.0f}원</div>
        </div>
        <div class="card" style="background:{margin_bg(normal_rate)}">
            <div class="label">일반 마진율</div>
            <div class="value" style="color:{margin_color_css(normal_rate)}">{normal_rate:.1f}%</div>
            <div class="sub">재고소진 제외</div>
        </div>
        <div class="card">
            <div class="label">총 PG수수료</div>
            <div class="value" style="color:#c62828">{total_pg:,.0f}원</div>
            <div class="sub">순매출 대비 {(total_pg/total_rev*100) if total_rev else 0:.2f}%</div>
        </div>
        <div class="card" style="background:{margin_bg(total_op_r)}">
            <div class="label">영업이익</div>
            <div class="value" style="color:{margin_color_css(total_op_r)}">{total_op:,.0f}원</div>
            <div class="sub">영업이익률 {total_op_r:.1f}%</div>
        </div>
        <div class="card" style="background:{'#ffcdd2' if price_anomalies else '#e8f5e9'}">
            <div class="label">판매가 이상 감지</div>
            <div class="value" style="color:{'#c62828' if price_anomalies else '#2e7d32'}">{len(price_anomalies)}건</div>
            <div class="sub">{'확인 필요' if price_anomalies else '이상 없음'}</div>
        </div>
        <div class="card" style="background:{'#ffcdd2' if discount_over else '#e8f5e9'}">
            <div class="label">할인율 25% 초과</div>
            <div class="value" style="color:{'#c62828' if discount_over else '#2e7d32'}">{len(discount_over)}건</div>
            <div class="sub">{'확인 필요' if discount_over else '이상 없음'}</div>
        </div>
    </div>"""

    legend = """
    <div class="legend">
        <span class="legend-label">마진율 색상:</span>
        <div class="legend-item"><div class="legend-dot" style="background:#d4edda"></div>50% 이상</div>
        <div class="legend-item"><div class="legend-dot" style="background:#e8f5e9"></div>35~50%</div>
        <div class="legend-item"><div class="legend-dot" style="background:#fff9c4"></div>20~35%</div>
        <div class="legend-item"><div class="legend-dot" style="background:#ffe0b2"></div>0~20%</div>
        <div class="legend-item"><div class="legend-dot" style="background:#ffcdd2"></div>0% 미만</div>
    </div>"""

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>데드라 마진 리포트 — {generated_at}</title>
<style>{CSS}</style>
</head>
<body>
<header>
  <h1>데드라 마진 리포트</h1>
  <p>생성일시: {generated_at} &nbsp;|&nbsp; 원본 파일: {os.path.basename(csv_path)}</p>
</header>
<div class="container">

  {discount_summary_html}
  {kpi_cards}
  {legend}

  <!-- 이상감지 -->
  {build_price_anomaly_html(price_anomalies)}
  {build_outlet_price_html(outlet_items)}
  {build_discount_anomaly_html(discount_over, discount_buckets)}
  {build_coupon_warning_html(data["coupon_warnings"])}

  <!-- PG수수료 & 영업이익 -->
  {build_pg_section(data)}

  <!-- 마진 분석 -->
  {build_margin_table("카테고리별 마진 분석 (일반)", data["cat_normal"])}
  {build_margin_table("공급사별 마진 분석 (일반)", data["supplier_normal"])}
  {build_top_products("마진율 TOP 10 상품", data["product_normal"], top_n=10, bottom=False)}
  {build_top_products("마진율 하위 10 상품 ⚠️", data["product_normal"], top_n=10, bottom=True)}

  <!-- 재고소진 -->
  <hr class="divider">
  <div class="divider-title">📦 재고소진 카테고리 분리 집계</div>
  <div class="section" style="background:#fff8f0;border:1px solid #ffe0b2">
    <p style="font-size:13px;color:#bf360c;line-height:1.8">
      아래 카테고리는 <b>재고소진 목적</b>으로 운영되어 마진율이 낮거나 음수일 수 있습니다.<br>
      전체 마진 집계에서 분리하여 <b>원가 회수율</b>을 별도 기준으로 평가하세요.<br>
      ⚠️ 재고소진 상품에 쿠폰이 함께 적용되면 원가도 회수하지 못할 수 있으니 쿠폰 적용 제외 설정을 권장합니다.
    </p>
  </div>
  {build_clearance_section(data)}

  {build_unified_sales_section(enriched_rows or [])}

  {build_refund_section(enriched_rows or [])}

</div>
<footer>자동 생성: dedra_daily_report.py &nbsp;|&nbsp; {generated_at}</footer>
{JS}
</body>
</html>"""


# ── 메인 ──────────────────────────────────────────────────────

def main():
    csv_path = find_latest_csv(FOLDER)
    print(f"📂 파일 발견: {os.path.basename(csv_path)}")

    rows = load_rows(csv_path)
    print(f"   총 {len(rows)}행 로드 완료")

    enriched = preprocess_rows(rows)
    data = aggregate(enriched)
    price_anomalies, outlet_items = detect_price_anomalies(enriched)
    discount_over, discount_buckets, _ = detect_discount_anomalies(enriched)

    generated_at = datetime.now().strftime("%Y-%m-%d %H:%M")
    date_prefix = datetime.now().strftime("%Y%m%d")
    html_path = os.path.join(FOLDER, f"{date_prefix}_마진리포트.html")

    html_content = generate_html(data, price_anomalies, outlet_items, discount_over, discount_buckets, csv_path, generated_at, enriched_rows=enriched)
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    print_summary(data, price_anomalies, outlet_items, discount_over, csv_path, html_path)

    try:
        os.system(f'open "{html_path}"')
    except Exception:
        pass


if __name__ == "__main__":
    main()
