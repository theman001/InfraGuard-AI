@echo off
cd /d C:\Users\thema\Desktop\Develope\InfraGuard-AI
.venv\Scripts\streamlit.exe run app/main.py --server.port 8501 --server.headless true --browser.gatherUsageStats false
