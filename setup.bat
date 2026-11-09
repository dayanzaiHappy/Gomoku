@echo off
cd /d "%~dp0"

echo === Packaging game with PyInstaller ===
echo.

pyinstaller ^
  --noconfirm ^
  --clean ^
  --name Gomoku ^
  --windowed ^
  --icon game\Gomoku.ico ^
  --add-data "game\Gomoku.ico;." ^
  --add-data "src\v0\solver.exe;solvers\v0" ^
  --add-data "src\v2\solver.exe;solvers\v2" ^
  --add-data "src\v2\model.onnx;solvers\v2" ^
  --add-data "src\v2\onnxruntime.dll;solvers\v2" ^
  main.py

if %errorlevel% neq 0 (
  echo PyInstaller failed - is it installed? Try: pip install pyinstaller
  pause
  exit /b %errorlevel%
)

echo.
echo === Done ===
echo Game packaged to dist\Gomoku\Gomoku.exe
pause