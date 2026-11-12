import unittest

from dedra_daily_report import preprocess_rows, detect_discount_anomalies, build_discount_detail_html


class SaleDiscountTests(unittest.TestCase):
    def test_detail_preserves_titles_and_app_evidence_per_product(self):
        rows = [self.row(**{"상품별 추가할인 상세": "겨울 세일 <10%>",
                            "사용한 쿠폰명": "VIP <쿠폰>", "앱상품할인금액": "500"}),
                self.row(**{"상품별 추가할인 상세": "다른 상품 할인"})]
        _, _, groups = detect_discount_anomalies(preprocess_rows(rows))
        items = [item for group in groups.values() for item in group]
        first = next(item for item in items if item["할인상세"] == "겨울 세일 <10%>")
        rendered = build_discount_detail_html(first)
        self.assertIn("겨울 세일 &lt;10%&gt;", rendered)
        self.assertIn("VIP &lt;쿠폰&gt;", rendered)
        self.assertIn("앱상품할인금액: 500", rendered)
        self.assertNotIn("다른 상품 할인", rendered)
        self.assertEqual(first["할인금액"], 1500)
        missing = build_discount_detail_html({"주문번호": "T2"})
        self.assertIn("CSV에 앱상품할인 별도 항목이 없습니다", missing)
        self.assertIn("CSV에 쿠폰 이름이 제공되지 않았습니다", missing)

    def row(self, **changes):
        row = {
            "주문번호": "T1", "상품구매금액": "10000", "공급원가": "3000",
            "수량": "1", "상품별 추가할인금액": "1000",
            "주문서 쿠폰 할인금액": "500", "회원등급 추가할인금액": "500",
            "사용한 적립금액(최초)": "1000", "예치금(최초)": "500",
        }
        row.update(changes)
        return row

    def test_payment_credits_do_not_trigger_sale_warning(self):
        enriched = preprocess_rows([self.row()])
        over, buckets, products = detect_discount_anomalies(enriched)
        self.assertEqual(over, [])
        self.assertEqual(buckets["16~25%"], 1)
        self.assertEqual(products["16~25%"][0]["할인율"], 20)
        self.assertEqual(enriched[0]["_total_discount"], 3500)
        self.assertEqual(enriched[0]["_net_revenue"], 6500)
        self.assertEqual(enriched[0]["_op_profit"], 6500 - 3000 - 6500 * .0363)

    def test_only_payment_credits_is_zero_sale_discount(self):
        row = self.row(**{"상품별 추가할인금액": "0", "주문서 쿠폰 할인금액": "0",
                          "회원등급 추가할인금액": "0"})
        _, buckets, _ = detect_discount_anomalies(preprocess_rows([row]))
        self.assertEqual(buckets["0%"], 1)

    def test_order_discounts_are_allocated_and_warning_remains(self):
        rows = [self.row(), self.row(**{"상품구매금액": "30000",
                                      "상품별 추가할인금액": "9000"})]
        enriched = preprocess_rows(rows)
        over, buckets, products = detect_discount_anomalies(enriched)
        self.assertEqual(buckets["11~15%"], 1)
        self.assertEqual(products["11~15%"][0]["할인율"], 12.5)
        self.assertEqual(len(over), 1)
        self.assertEqual(over[0]["할인율"], 32.5)
        self.assertEqual(over[0]["쿠폰할인"], 375)
        self.assertEqual(over[0]["회원등급할인"], 375)
        self.assertEqual(over[0]["즉시할인"], 9000)
        for items in products.values():
            for item in items:
                self.assertEqual(item["쿠폰할인"] + item["회원등급할인"] + item["즉시할인"],
                                 item["할인금액"])
        self.assertEqual(sum(r["_disc_for_anomaly"] for r in enriched), 11000)
        self.assertEqual(sum(r["_net_revenue"] for r in enriched), 27500)


if __name__ == "__main__":
    unittest.main()
