@echo off
rem Atualiza os dados da ANEEL neste computador e envia os resumos ao GitHub.
rem Dois cliques neste arquivo. Precisa do ambiente virtual .venv desta pasta.
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Nao achei a pasta .venv. Crie o ambiente virtual antes: python -m venv .venv
  pause
  exit /b 1
)
".venv\Scripts\python.exe" atualizar_local.py
if errorlevel 1 (
  echo.
  echo Algo deu errado. Leia as mensagens acima.
) else (
  echo.
  echo Terminou.
)
pause
