$env:Path = 'D:\Program Files\Netease\MuMuPlayer\nx_main;' + $env:Path
Start-Sleep -Seconds 120
& 'C:\Users\TQFix\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' 'D:\MUMU\scripts\Script Final\TT-G1-Standard-Final.py' --serial 127.0.0.1:16448 *> 'D:\MUMU\scripts\Script Final\logs\TT-G1-Standard-Final_scheduled_20260514_224816.log'
