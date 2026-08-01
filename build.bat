@echo off
chcp 65001 >nul
echo ============================================
echo  ScreenLingo - 打包单文件 exe
echo ============================================
echo.

where pyinstaller >nul 2>nul
if errorlevel 1 (
    echo [1/3] 未检测到 PyInstaller，正在安装...
    pip install pyinstaller
) else (
    echo [1/3] PyInstaller 已安装
)

echo [2/3] 打包中（约 1-3 分钟）...
pyinstaller --onefile --windowed --name ScreenLingo ^
    --hidden-import tkinter ^
    --collect-all pystray ^
    main.py

echo [3/3] 完成！
echo 输出文件：dist\ScreenLingo.exe
echo 提示：把 exe 拷到没装 Python 的电脑上即可直接运行。
pause
