@echo off
REM ── 註冊「開機自動啟動」排程工作（只需執行一次）────────────
REM 用法：滑鼠右鍵這個檔案 → 「以系統管理員身分執行」
REM 效果：伺服器開機後（不需任何人登入）就會自動啟動 ESS 後端，
REM       並且 app.py 若當機，start_backend.bat 內建的迴圈也會自動重啟。

setlocal
cd /d "%~dp0"
set TASK_NAME=ESS-Backend-AutoStart
set SCRIPT_PATH=%~dp0start_backend.bat

echo 正在註冊排程工作：%TASK_NAME%
echo 啟動腳本：%SCRIPT_PATH%
echo.

schtasks /create ^
    /tn "%TASK_NAME%" ^
    /tr "\"%SCRIPT_PATH%\"" ^
    /sc onstart ^
    /ru SYSTEM ^
    /rl HIGHEST ^
    /f

if %ERRORLEVEL%==0 (
    echo.
    echo [完成] 已註冊成功！伺服器重開機後會自動啟動 ESS 後端。
    echo 現在要不要立刻測試啟動一次？輸入 Y 立即執行，或按 Enter 略過。
    set /p RUNNOW=
    if /i "%RUNNOW%"=="Y" schtasks /run /tn "%TASK_NAME%"
) else (
    echo.
    echo [失敗] 註冊失敗，請確認是否用「系統管理員」身分執行本檔案。
)

echo.
echo 之後管理方式：
echo   查看狀態： schtasks /query /tn "%TASK_NAME%"
echo   手動啟動： schtasks /run /tn "%TASK_NAME%"
echo   停止工作： schtasks /end /tn "%TASK_NAME%"
echo   移除工作： schtasks /delete /tn "%TASK_NAME%" /f
echo.
pause
