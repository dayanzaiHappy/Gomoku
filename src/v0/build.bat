@echo off
cd /d "%~dp0"
echo === Building src/v0 solver.exe ===
g++ -std=c++11 -O3 -static -o solver.exe solver.cpp
if %errorlevel% neq 0 (
  echo Build failed.
  exit /b %errorlevel%
)
echo Built %cd%\solver.exe
