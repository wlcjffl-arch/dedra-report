"""Synthetic uploads exercise reruns without retaining customer data."""
import sys
import unittest
from pathlib import Path
from streamlit.testing.v1 import AppTest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
SOURCE = (ROOT / 'app.py').read_text()
HOOK = '''
_original_analyze = analyze_uploads
def analyze_uploads(payloads):
    st.session_state['_runs'] = st.session_state.get('_runs', 0) + 1
    return _original_analyze(payloads)
def sidebar():
    files = []
    for name, raw in st.session_state.get('_test_files', []):
        f = io.BytesIO(raw)
        f.name = name
        files.append(f)
    return files
'''
SOURCE = SOURCE.replace('if __name__ == "__main__":', HOOK + '\nif __name__ == "__main__":')
CSV = '주문번호,상품구매금액,공급원가,수량,상품명,브랜드,자체분류,주문 상태\nT1,10000,3000,1,테스트,DEDRA,상의,배송완료\n'.encode()

class PerformanceFlow(unittest.TestCase):
    def test_menu_cache_report_and_invalidation(self):
        at = AppTest.from_string(SOURCE, default_timeout=30)
        at.session_state['auth'] = True
        at.session_state['_test_files'] = [('test.csv', CSV)]
        at.run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['_runs'], 1)
        self.assertNotIn('_report_html', at.session_state)
        expected = at.session_state['_analysis']['result'][4]
        for option in at.radio(key='analysis_section').options:
            at.radio(key='analysis_section').set_value(option).run()
            self.assertFalse(at.exception, option)
            self.assertEqual(at.session_state['_runs'], 1)
            self.assertEqual(at.session_state['_analysis']['result'][4], expected)
        next(b for b in at.button if b.label == '📄 다운로드 보고서 준비').click().run()
        self.assertFalse(at.exception)
        self.assertIn(b'<html', at.session_state['_report_html'])
        at.session_state['_test_files'] = [('test.csv', CSV.replace(b'10000', b'20000'))]
        at.run()
        self.assertFalse(at.exception)
        self.assertEqual(at.session_state['_runs'], 2)
        self.assertNotIn('_report_html', at.session_state)
        self.assertNotEqual(at.session_state['_analysis']['result'][4], expected)
        at.session_state['_test_files'] = []
        at.run()
        self.assertNotIn('_analysis', at.session_state)

    def test_login_and_empty_csv(self):
        at = AppTest.from_string(SOURCE, default_timeout=30).run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.text_input), 1)
        at.session_state['auth'] = True
        at.session_state['_test_files'] = [('empty.csv', b'')]
        at.run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.radio), 0)

if __name__ == '__main__':
    unittest.main()
