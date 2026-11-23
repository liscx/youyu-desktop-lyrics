@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

set PY=.build-venv\Scripts\python.exe
if not exist "%PY%" (
    echo [ERROR] 构建环境不存在，请先执行：
    echo   E:\Python\Python312\python.exe -m venv .build-venv
    echo   .build-venv\Scripts\python.exe -m pip install -r requirements.txt pyinstaller
    exit /b 1
)

echo [1/3] 清理旧产物...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [2/3] 打包（内置依赖，文件夹版）...
"%PY%" -m PyInstaller --noconfirm --clean build.spec
if errorlevel 1 (
    echo [ERROR] 打包失败
    exit /b 1
)

echo [3/3] 放入默认配置...
copy /y config.json dist\youyu-desktop-lyrics\config.json >nul

echo.
echo 完成：dist\youyu-desktop-lyrics\youyu.exe
echo 补丁工具：dist\youyu-desktop-lyrics\cdp_patch.exe
endlocal
