@echo off
chcp 65001 >nul
echo ============================================================
echo  汇天 LIN 上位机控制软件 — 打包脚本
echo ============================================================
echo.

:: 激活虚拟环境（根据实际路径调整）
set VENV=d:\Python_QT\.venv\Scripts\activate.bat
if exist "%VENV%" (
    call "%VENV%"
    echo [OK] 已激活虚拟环境
) else (
    echo [WARN] 未找到虚拟环境，使用系统 Python
)
echo.

:: 清理上次构建产物
echo [1/3] 清理旧构建目录...
if exist "dist\HuiTianLIN" rmdir /s /q "dist\HuiTianLIN"
if exist "build\HuiTianLIN" rmdir /s /q "build\HuiTianLIN"
echo       完成
echo.

:: 执行打包
echo [2/3] 开始打包（请耐心等待 1~3 分钟）...
pyinstaller HuiTianLIN.spec --noconfirm
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] 打包失败！请查看上方错误信息。
    pause
    exit /b 1
)
echo.

:: 复制说明文档
echo [3/3] 复制 README...
if exist "README.md" copy /y "README.md" "dist\HuiTianLIN\README.md" >nul
echo       完成
echo.

echo ============================================================
echo  打包成功！输出目录：dist\HuiTianLIN\
echo  运行程序：dist\HuiTianLIN\HuiTianLIN.exe
echo ============================================================
echo.
pause
