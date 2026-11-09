@echo off
cd /d "%~dp0"
set ORT=..\..\third_party\onnxruntime
echo === Building src/v1 solver.exe ===
g++ -std=c++17 -O2 -municode -I "%ORT%\include" solver.cpp -L "%ORT%\lib" -lonnxruntime -static-libgcc -static-libstdc++ -o solver.exe
if %errorlevel% neq 0 (
  echo Build failed.
  exit /b %errorlevel%
)
copy /Y "%ORT%\bin\onnxruntime.dll" onnxruntime.dll >nul
echo Built %cd%\solver.exe
