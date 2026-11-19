import re
import requests
from bs4 import BeautifulSoup
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt
from matplotlib import font_manager


# 1. 웹페이지 HTML을 가져오는 함수
def fetch_html(url):
    # 수업 실습용임을 밝히는 User-Agent 헤더 설정
    headers = {
        "User-Agent": "Mozilla/5.0 (Educational Practice; Python Web Scraping Class)"
    }
    # 10초 제한 시간(timeout)을 두고 페이지 요청
    response = requests.get(url, headers=headers, timeout=10)
    # 404, 500 등 HTTP 상태 코드 오류 발생 시 예외 처리
    response.raise_for_status()
    # 한글 깨짐 방지를 위해 응답 본문의 인코딩을 자동 감지하여 지정
    response.encoding = response.apparent_encoding
    return response.text


# 2. 시스템에 설치된 한글 폰트를 찾아 설정하는 함수
def set_korean_font():
    # 우선순위로 사용할 한글 폰트 이름 후보 목록
    candidates = ["Malgun Gothic", "AppleGothic", "NanumGothic", "NanumBarunGothic", "Noto Sans CJK KR", "Batang"]
    available_fonts = {f.name: f.fname for f in font_manager.fontManager.ttflist}

    for name in candidates:
        if name in available_fonts:
            # 폰트 파일을 직접 등록해 Streamlit 환경에서도 안정적으로 적용
            font_manager.fontManager.addfont(available_fonts[name])
            plt.rcParams["font.family"] = name
            plt.rcParams["axes.unicode_minus"] = False
            return name

    # 후보 폰트가 없을 경우 시스템 내 한글 포함 폰트 자동 탐색
    for font in font_manager.fontManager.ttflist:
        if any("\uac00" <= ch <= "\ud7a3" for ch in font.name):
            font_manager.fontManager.addfont(font.fname)
            plt.rcParams["font.family"] = font.name
            plt.rcParams["axes.unicode_minus"] = False
            return font.name

    plt.rcParams["axes.unicode_minus"] = False
    return None


# 3. HTML에서 조건에 맞는 표를 찾아 DataFrame으로 변환하는 함수
def parse_movie_table(html):
    soup = BeautifulSoup(html, "html.parser")
    # class가 wikitable인 모든 표 찾기
    tables = soup.find_all("table", class_="wikitable")

    target_table = None
    for table in tables:
        first_row = table.find("tr")
        if first_row:
            # 첫 줄의 제목 칸(th) 텍스트 추출
            headers = [th.get_text(strip=True) for th in first_row.find_all("th")]
            # 첫 줄에 '관객수'와 '감독'이 모두 포함된 첫 번째 표 선택
            if any("관객수" in h for h in headers) and any("감독" in h for h in headers):
                target_table = table
                break

    if target_table is None:
        return pd.DataFrame()

    # 표 내부의 각주 번호(sup 태그) 모두 제거
    for sup in target_table.find_all("sup"):
        sup.decompose()

    rows = target_table.find_all("tr")
    # 첫 줄(tr)에서 열 이름 추출
    col_names = [th.get_text(strip=True) for th in rows[0].find_all("th")]

    # 나머지 줄(tr)에서 데이터 칸(td) 추출
    data = []
    for row in rows[1:]:
        cells = row.find_all("td")
        if cells:
            row_data = [cell.get_text(strip=True) for cell in cells]
            # 열 개수와 데이터 칸 개수가 일치하는 행만 추가
            if len(row_data) == len(col_names):
                data.append(row_data)

    return pd.DataFrame(data, columns=col_names)


# 4. 추출한 데이터를 분석하기 좋게 정제하는 함수
def clean_movie_data(df):
    if df.empty:
        return df

    # 실제 표의 열 이름과 필요한 표준 열 이름 매핑
    col_map = {}
    for col in df.columns:
        if "제목" in col or "작품" in col:
            col_map[col] = "제목"
        elif "감독" in col:
            col_map[col] = "감독"
        elif "개봉" in col:
            col_map[col] = "개봉일"
        elif "관객" in col:
            col_map[col] = "관객수"

    df = df.rename(columns=col_map)

    # 필요한 4개 열만 선택
    required_cols = ["제목", "감독", "개봉일", "관객수"]
    df = df[required_cols].copy()

    # 제목에서 《 》 기호 제거
    df["제목"] = df["제목"].str.replace("《", "", regex=False).str.replace("》", "", regex=False).str.strip()

    # 관객수에서 숫자만 추출하여 정수형으로 변환
    df["관객수"] = df["관객수"].apply(lambda x: int(re.sub(r"[^0-9]", "", str(x))) if re.search(r"[0-9]", str(x)) else 0)

    # 천만 관객(10,000,000명) 이상인 영화만 필터링
    df = df[df["관객수"] >= 10000000].copy()

    # 개봉일에서 4자리 연도 추출
    df["개봉연도"] = df["개봉일"].str.extract(r"(\d{4})")
    # 개봉일에서 월(1~2자리 숫자) 추출
    df["개봉월"] = df["개봉일"].str.extract(r"\d{4}[^\d]+(\d{1,2})")

    # 추출한 연도와 월을 숫자(결측치 허용 정수형)로 변환
    df["개봉연도"] = pd.to_numeric(df["개봉연도"], errors="coerce").astype("Int64")
    df["개봉월"] = pd.to_numeric(df["개봉월"], errors="coerce").astype("Int64")

    # 관객수 기준 내림차순 정렬 및 인덱스 초기화
    df = df.sort_values(by="관객수", ascending=False).reset_index(drop=True)
    return df


# 5. 지표, 표, 차트를 화면에 출력하는 함수
def display_dashboard(df):
    # 차트 출력 전 시스템 한글 폰트 설정
    applied_font = set_korean_font()
    if applied_font is None:
        st.info("시스템에 한글 글꼴이 없어 차트 글자가 네모로 보일 수 있습니다. 나눔고딕 등을 설치해 주세요.")

    # 주요 지표 계산
    total_count = len(df)
    top_movie = df.iloc[0]["제목"]
    top_audience = df.iloc[0]["관객수"]

    # 3개의 열로 나누어 지표(metric) 표시
    col1, col2, col3 = st.columns(3)
    col1.metric("천만 영화 수", f"{total_count}편")
    col2.metric("역대 1위 작품", top_movie)
    col3.metric("1위 관객 수", f"{top_audience:,}명")

    # 전체 천만 영화 데이터 표 출력
    st.subheader("천만 관객 돌파 한국 영화 목록")
    st.dataframe(df, use_container_width=True)

    # 관객 수 상위 10편 가로 막대차트
    st.subheader("관객 수 상위 10편")
    top10_df = df.head(10).sort_values(by="관객수", ascending=True)
    fig1, ax1 = plt.subplots(figsize=(10, 5))
    ax1.barh(top10_df["제목"], top10_df["관객수"] / 10000, color="steelblue")
    ax1.set_xlabel("관객 수 (단위: 만 명)")
    ax1.set_title("한국 영화 흥행 상위 10편")
    st.pyplot(fig1)

    # 개봉 연도별 천만 영화 편수 막대차트
    st.subheader("개봉 연도별 천만 영화 편수")
    year_counts = df["개봉연도"].dropna().value_counts().sort_index()
    fig2, ax2 = plt.subplots(figsize=(10, 4))
    ax2.bar(year_counts.index.astype(str), year_counts.values, color="coral")
    ax2.set_xlabel("개봉 연도")
    ax2.set_ylabel("영화 편수")
    ax2.set_title("연도별 천만 관객 돌파 영화 수")
    plt.xticks(rotation=45)
    st.pyplot(fig2)


# 6. 전체 앱 실행을 제어하는 메인 함수
def main():
    st.title("대한민국 천만 관객 영화 흥행 분석")

    default_url = "https://ko.wikipedia.org/wiki/%EB%8C%80%ED%95%9C%EB%AF%BC%EA%B5%AD%EC%9D%98_%EC%98%81%ED%99%94_%ED%9D%A5%ED%96%89_%EA%B8%B0%EB%A1%9D"
    # 사용자에게 웹페이지 주소를 입력받는 텍스트 창
    url = st.text_input("위키백과 주소를 입력하세요", value=default_url)

    # 버튼을 눌렀을 때 수집 및 시각화 실행
    if st.button("데이터 수집 및 분석 실행"):
        if not url.strip():
            st.warning("주소를 입력해 주세요.")
            return

        try:
            with st.spinner("데이터를 불러오는 중입니다..."):
                html = fetch_html(url)
                raw_df = parse_movie_table(html)
                clean_df = clean_movie_data(raw_df)

            # 조건에 맞는 영화 데이터를 하나도 찾지 못한 경우 처리
            if clean_df.empty:
                st.warning("조건에 맞는 영화를 하나도 찾지 못했습니다. 주소나 표 구조를 확인해 주세요.")
            else:
                display_dashboard(clean_df)

        # 네트워크 연결 실패 에러 처리
        except requests.exceptions.ConnectionError:
            st.error("인터넷 연결에 실패했습니다. 네트워크 상태를 확인해 주세요.")
        # 요청 제한 시간 초과 에러 처리
        except requests.exceptions.Timeout:
            st.error("요청 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.")
        # HTTP 응답 코드 오류(404, 500 등) 에러 처리
        except requests.exceptions.HTTPError as e:
            st.error(f"페이지를 불러오는 중 HTTP 오류가 발생했습니다: {e}")
        # 그 외 예상치 못한 오류 처리
        except Exception as e:
            st.error(f"데이터 처리 중 오류가 발생했습니다: {e}")


if __name__ == "__main__":
    main()