# ⚖️ 한국 법 자문 서비스

AI 기반 한국 법령 검색 및 법률 자문 플랫폼.  
Claude LLM + 국가법령정보 API + ChromaDB RAG를 결합한 Streamlit 웹 서비스.

---

## 🚀 빠른 시작 (Docker)

### 1. 저장소 클론

```bash
git clone <repo-url>
cd InfraGuard-AI
```

### 2. 환경변수 설정

```bash
cp .env.example .env
# .env 파일을 열어 ENCRYPTION_KEY 등 필수 항목 입력
```

`.env` 필수 항목:

| 변수 | 설명 |
|------|------|
| `ENCRYPTION_KEY` | API 키 암호화용 Fernet 키 (필수) |
| `DB_PATH` | SQLite DB 경로 (기본: `/app/db/app.db`) |
| `CHROMA_PATH` | ChromaDB 경로 (기본: `/app/data/chroma_db`) |

Fernet 키 생성:
```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

### 3. 실행

```bash
docker compose up -d
```

브라우저에서 `http://localhost:8501` 접속.

### 4. 초기 설정

1. `admin` 계정으로 최초 로그인 → OTP 등록
2. **마이페이지** → API 키 등록
   - 국가법령정보 API 키: https://open.law.go.kr 에서 발급
   - Claude API 키: https://console.anthropic.com 에서 발급
3. **관리자 패널** → RAG 데이터 → **초기화 + 재수집** 실행  
   (법령 벡터 DB 초기 구축, 수 분 소요)

---

## 📂 볼륨 구조

```
# 컨테이너 내부           # 호스트 (기본값)
/app/db/app.db        ← ./db/app.db          (SQLite DB)
/app/data/chroma_db/  ← ./data/chroma_db/    (벡터 DB)
```

NAS 등 외부 경로로 변경하려면 `docker-compose.yml`의 `volumes` 섹션 수정:

```yaml
volumes:
  - /mnt/nas/infra-guard/db:/app/db
  - /mnt/nas/infra-guard/chroma_db:/app/data/chroma_db
```

---

## 🔄 업데이트

```bash
git pull
docker compose build --no-cache
docker compose up -d
```

---

## 🛠 기술 스택

- **Frontend**: Streamlit
- **LLM**: Anthropic Claude (claude-3-7-sonnet)
- **RAG**: ChromaDB + sentence-transformers
- **법령 API**: 국가법령정보 공동활용 (open.law.go.kr)
- **DB**: SQLite
- **Auth**: TOTP (Google Authenticator)
- **PDF**: ReportLab
