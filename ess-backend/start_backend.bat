@echo off
setlocal

REM ── ESS 戰情版後端啟動器（伺服器常駐用）───────────────────
REM 用 %~dp0 取得本檔案所在資料夾，不寫死路徑，複製到任何機器都能跑。
cd /d "%~dp0"

REM 若日誌超過 20MB 就輪替一份，避免無限長大
set LOGFILE=backend.log
if exist "%LOGFILE%" (
    for %%A in ("%LOGFILE%") do if %%~zA GTR 20971520 (
        move /y "%LOGFILE%" "backend.log.old" >nul
    )
)

echo [%date% %time%] === ESS 後端啟動器 已啟動 === >> "%LOGFILE%"

REM 找 python：優先用 PATH 上的 python，找不到則退回這台機器裝過的路徑
where python >nul 2>nul
if %ERRORLEVEL%==0 (
    set PYEXE=python
) else (
    set PYEXE=C:\Users\user\AppData\Local\Python\pythoncore-3.14-64\python.exe
)

REM 崩潰自動重啟迴圈：app.py 若意外結束，5 秒後自動重跑，不需要人顧著
:loop
echo [%date% %time%] 啟動 app.py ... >> "%LOGFILE%"
"%PYEXE%" app.py >> "%LOGFILE%" 2>&1
echo [%date% %time%] app.py 已結束（結束碼 %ERRORLEVEL%），5 秒後自動重啟 >> "%LOGFILE%"
timeout /t 5 /nobreak >nul
goto loop
