#!/bin/sh
# uvicorn(FastAPI)을 백그라운드로 먼저 기동 후 streamlit을 포그라운드로 실행.
# streamlit이 PID 1이 되어 컨테이너 수명을 관리한다.
uvicorn api.main:app --host 0.0.0.0 --port 8000 --workers 1 &
exec streamlit run app/main.py \
     --server.port=8501 \
     --server.address=0.0.0.0 \
     --server.headless=true \
     --server.fileWatcherType=none
