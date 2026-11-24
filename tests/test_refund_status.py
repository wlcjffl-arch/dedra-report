import unittest

from dedra_daily_report import preprocess_rows, compute_refund_stats


class RefundStatusTests(unittest.TestCase):
    def row(self, status, amount="10000"):
        return {"주문번호": status, "주문 상태": status, "상품구매금액": amount,
                "공급원가": "3000", "수량": "1", "상품명(데드라)": "테스트상품"}

    def test_current_cafe24_spacing_is_counted(self):
        refunds = ["취소완료", "취소 요청", "취소처리중 - 환불전", "입금전취소 - 관리자",
                   "반품 요청", "반품처리중 - 환불전", "반품완료 - 환불완료", "교환신청"]
        normal = ["배송완료", "배송중", "교환완료", "교환처리중 - 수거전"]
        rows = [self.row(s) for s in refunds + normal + ["반품처리중 - 수거전"]]
        stats = compute_refund_stats(preprocess_rows(rows))
        self.assertEqual(stats["refund_cnt"], len(refunds))
        self.assertEqual(stats["pending_cnt"], 1)
        self.assertEqual(stats["amount_ref"], 10000 * len(refunds))

    def test_legacy_spacing_still_counted(self):
        rows = [self.row("반품 완료 - 환불완료"), self.row("반품 처리중 - 수거전")]
        stats = compute_refund_stats(preprocess_rows(rows))
        self.assertEqual(stats["refund_cnt"], 1)
        self.assertEqual(stats["pending_cnt"], 1)


if __name__ == "__main__":
    unittest.main()
