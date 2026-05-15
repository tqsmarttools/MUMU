@echo off
setlocal EnableExtensions EnableDelayedExpansion
set "PY=C:\Users\Admin\AppData\Local\Programs\Python\Python314\python.exe"
set "SCRIPT=D:\MUMU\scripts\TT-G1.1.py"
set "SERIAL=127.0.0.1:16448"
set "LOG=D:\MUMU\scripts\logs\tt_g1_1_run.log"
set "PYTHONIOENCODING=utf-8"
set "PYTHONUTF8=1"

if not exist "D:\MUMU\scripts\logs" mkdir "D:\MUMU\scripts\logs"
echo ==== START %DATE% %TIME% ====>> "%LOG%"
"%PY%" "%SCRIPT%" --serial %SERIAL% --delay-multiplier 1.25 >> "%LOG%" 2>&1
set "RC=%ERRORLEVEL%"
>> "%LOG%" echo EXIT_CODE=!RC!
>> "%LOG%" echo ==== END %DATE% %TIME% ====
exit /b !RC!
