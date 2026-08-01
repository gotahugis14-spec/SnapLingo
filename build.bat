@echo off
chcp 65001 >nul
echo ============================================
echo   ScreenLingo - 一键打包 exe
echo ============================================
echo.

echo [1/4] 创建干净构建环境 (venv_build) ...
if not exist venv_build (
    python -m venv venv_build
)

echo [2/4] 安装依赖 ...
venv_build\Scripts\python -m pip install --quiet --upgrade pip
venv_build\Scripts\python -m pip install --quiet pyinstaller mss pillow pystray keyboard requests pytesseract

echo [3/4] 打包中（约 1-3 分钟）...
venv_build\Scripts\python -m PyInstaller ^
    --onefile --windowed --name ScreenLingo ^
    --hidden-import tkinter ^
    --collect-all pystray ^
    --icon icon.ico ^
    main.py

echo [4/4] 完成！
echo.
echo 输出文件：dist\ScreenLingo.exe
echo 把 exe 拷到没装 Python 的电脑上即可直接运行。
echo 也可以复制到项目根目录，打开文件夹就能双击。
pause
