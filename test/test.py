import requests
import urllib.parse

# [설정] 마이페이지에서 확인한 OC 값을 정확히 입력하세요.
OC_ID = "theman"  # * 포함 실제 인증키 전체 입력
LAW_NAME = "개인정보 보호법"

def debug_law_api():
    encoded_query = urllib.parse.quote(LAW_NAME)
    # 목록 검색 URL
    search_url = f"http://www.law.go.kr/DRF/lawSearch.do?OC={OC_ID}&target=law&query={encoded_query}&type=XML"
    
    print(f"--- 요청 URL ---\n{search_url}\n")
    
    try:
        response = requests.get(search_url)
        print(f"--- 응답 상태 코드 --- \n{response.status_code}\n")
        
        # XML 원문 출력 (중요)
        print("--- XML 응답 원문 ---")
        print(response.text)
        
        if "인증되지 않은" in response.text or "사용할 수 없는" in response.text:
            print("\n[!] 경고: API 인증키(OC)가 아직 승인되지 않았거나 틀렸습니다.")
        elif "<totalCnt>0</totalCnt>" in response.text:
            print("\n[!] 경고: 검색 결과가 0건입니다. 쿼리를 확인하세요.")
            
    except Exception as e:
        print(f"오류 발생: {e}")

if __name__ == "__main__":
    debug_law_api()