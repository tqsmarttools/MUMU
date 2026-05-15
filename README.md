# MuMu + TikTok Lite Two-Step Workflow

Root folder:

```text
D:\MUMU
```

## One-step scheduled workflow

For `PHONE_002`, use this wrapper when you want Step 2 to start automatically after Step 1 confirms IP is ready:

```text
D:\MUMU\run_prepare_then_tiktok_PHONE_002.bat
```

PowerShell equivalent:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\MUMU\run_prepare_then_tiktok_PHONE_002.ps1" -VmIndex 2
```

This wrapper:

- Runs Step 1.
- Reads `D:\MUMU\scripts\state\mumu_device_ready.json`.
- Starts Step 2 only if `PHONE_002` is `ready=true`.

## Step 1: prepare MuMu devices and fake IP

Script:

```powershell
D:\MUMU\scripts\prepare_mumu_socksdroid_devices.ps1
```

Run all MuMu devices:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\MUMU\scripts\prepare_mumu_socksdroid_devices.ps1"
```

Run only `PHONE_002` / VM index `2`:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\MUMU\scripts\prepare_mumu_socksdroid_devices.ps1" -VmIndex 2
```

Quick BAT shortcut:

```text
D:\MUMU\run_prepare_PHONE_002.bat
```

This step:

- Opens selected MuMu device(s).
- Waits for Android to start.
- Opens SocksDroid and turns on the main switch if VPN is not active.
- Opens Chrome/Chromium to `https://whoer.net`.
- Tries to read the Whoer IP.
- Saves screenshots under `D:\MUMU\scripts\screenshots`.
- Writes readiness state to `D:\MUMU\scripts\state\mumu_device_ready.json`.

## Step 2: run TikTok Lite session

Script:

```powershell
D:\MUMU\scripts\run_tiktok_lite_sampling.ps1
```

Run for `PHONE_002` after Step 1:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\MUMU\scripts\run_tiktok_lite_sampling.ps1" -VmIndex 2
```

Quick BAT shortcut:

```text
D:\MUMU\run_tiktok_PHONE_002.bat
```

This step:

- Reads the readiness state from Step 1.
- Runs only if the selected VM is marked `ready`.
- Opens TikTok Lite.
- Randomly picks one of five content-sampling scenarios.
- Randomly picks construction/tool keywords.
- Runs about 8-10 minutes from TikTok open to TikTok close.
- Returns to Android Home and force-stops TikTok Lite.

Logs are saved under:

```text
D:\MUMU\scripts\logs
```

Short test run:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\MUMU\scripts\run_tiktok_lite_sampling.ps1" -VmIndex 2 -MinSessionMinutes 2 -MaxSessionMinutes 3
```

Run TikTok without requiring Step 1 readiness:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "D:\MUMU\scripts\run_tiktok_lite_sampling.ps1" -VmIndex 2 -RequireReady:$false
```
