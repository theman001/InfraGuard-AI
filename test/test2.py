import requests
from bs4 import BeautifulSoup

OC_ID = "theman"
MST_ID = "270351"  # 개인정보 보호법 MST

def get_full_law():
    url = f"http://www.law.go.kr/DRF/lawService.do?OC={OC_ID}&target=law&MST={MST_ID}&type=XML"
    
    try:
        response = requests.get(url)
        response.raise_for_status()
        
        # lxml-xml 파서 사용
        soup = BeautifulSoup(response.content, "lxml-xml")
        
        # 1. 법령명 추출 (에러 방지를 위해 .find() 결과 체크)
        law_name_tag = soup.find("법령명한글")
        law_name = law_name_tag.text if law_name_tag else "알 수 없는 법령"
        print(f"--- {law_name} 파싱 시작 ---")
        
        # 2. 조문 추출
        articles = soup.find_all("조문단위")
        
        if not articles:
            print("조문 데이터를 찾을 수 없습니다. MST 번호나 API 승인 상태를 확인하세요.")
            # 데이터 확인을 위해 응답 일부 출력
            print(f"응답 요약: {response.text[:200]}")
            return

        print(f"총 {len(articles)}개의 조문을 발견했습니다.\n")
        
        for article in articles[:5]:  # 상위 5개 조문 출력
            # 조문번호와 제목 추출
            no_tag = article.find("조문번호")
            title_tag = article.find("조문제목")
            content_tag = article.find("조문내용")
            
            no = no_tag.text if no_tag else "?"
            title = title_tag.text if title_tag else ""
            content = content_tag.text.strip() if content_tag else "내용 없음"
            
            print(f"📌 제{no}조 {title}")
            # 불필요한 공백 및 줄바꿈 정제하여 출력
            clean_content = " ".join(content.split())
            print(f"내용: {clean_content[:100]}...")
            print("-" * 40)

    except Exception as e:
        print(f"실행 중 오류 발생: {e}")

if __name__ == "__main__":
    get_full_law()