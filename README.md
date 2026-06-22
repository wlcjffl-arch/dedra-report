# 데드라 마진 리포트

카페24 주문 내역 CSV를 업로드하면 마진·원가·환불·할인·PG 수수료를
한눈에 보는 Streamlit 대시보드입니다.

## 주요 기능
- **종합일보** — 환불 전 총주문 → 환불 → 순매출 → 원가 → 마진 → 수수료 → 영업이익 흐름
  - 핵심 지표 카드 클릭 → 산출 방식 설명 + 분해표(카테고리별 / 전체) + 주문번호 드릴다운
- **환불 분석** — 환불율(건수·금액), 브랜드·카테고리·상품별 환불 내역
- **상세 마진 / 판매가 이상감지 / 할인율 / PG 수수료 / 아울렛** 탭
- 모든 표 헤더 클릭 정렬(오름/내림)

## 로컬 실행 (Mac)
```bash
./데드라_마진리포트_실행.command      # 최초 1회 가상환경·패키지 자동 설치
# 또는
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
```
브라우저에서 http://localhost:8501 로 열립니다.

## 직원 공유 배포 — Streamlit Community Cloud
1. https://share.streamlit.io 접속 → GitHub 계정으로 로그인
2. **New app** → 이 저장소(`wlcjffl-arch/dedra-report`), 브랜치 `main`, 파일 `app.py` 선택
3. **Advanced settings → Secrets** 에 로그인 비밀번호 입력:
   ```toml
   password = "직원과 공유할 비밀번호"
   ```
4. **Deploy** → 생성된 URL을 직원에게 공유. 직원은 URL 접속 후 비밀번호만 입력하면 사용.

> 데이터는 세션마다 CSV를 직접 업로드하는 방식이라 별도 DB·서버가 필요 없습니다.

## 비밀번호 설정
- 로컬: `.streamlit/secrets.toml` 의 `password` (이 파일은 `.gitignore`로 저장소에 올라가지 않음)
- 클라우드: 위 3번처럼 Streamlit Cloud의 **Secrets** 에 입력
