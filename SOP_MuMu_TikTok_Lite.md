# SOP - MuMuPlayer TikTok Lite (1 Instance)

## 1) Muc tieu
- Dung cho TikTok va app nhe.
- Khong game, khong can GPS gia lap.
- Uu tien tiet kiem tai nguyen, van thao tac muot.

## 2) Cau hinh chuan da chot
- Instance name: `TT-Lite-01`
- CPU: `2`
- RAM: `3072 MB` (`3.000000`)
- FPS: `20`
- Resolution: `720 x 1280` (doc)
- DPI: `320`
- Brand/Model: `Samsung Galaxy A34` (`SM-A346E`)
- Root: `false`
- Locale: `en-US`
- ADB: su dung qua `mumu-cli adb`

## 3) Duong dan cong cu
- `C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe`

## 4) Tao instance moi
```powershell
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" create --number 1
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" info --vmindex all
```

Ghi nhan `vmindex` moi (vi du: `1`), roi dat ten:

```powershell
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" rename --vmindex 1 --name "TT-Lite-01"
```

## 5) Ap cau hinh
```powershell
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" setting --vmindex 1 `
  --key performance_mode --value custom `
  --key performance_cpu.custom --value 2 `
  --key performance_mem.custom --value 3.000000 `
  --key max_frame_rate --value 20 `
  --key resolution_mode --value custom `
  --key resolution_width.custom --value 720.000000 `
  --key resolution_height.custom --value 1280.000000 `
  --key resolution_dpi.custom --value 320.000000 `
  --key phone_brand --value Samsung `
  --key phone_model --value "Galaxy A34" `
  --key phone_miit --value SM-A346E `
  --key root_permission --value false
```

## 6) Khoi dong va set English
```powershell
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" control --vmindex 1 launch
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" adb --vmindex 1 --cmd "shell setprop persist.sys.locale en-US"
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" adb --vmindex 1 --cmd "shell setprop persist.sys.language en"
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" adb --vmindex 1 --cmd "shell setprop persist.sys.country US"
```

## 7) Xac nhan sau cai dat
```powershell
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" info --vmindex 1
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" setting --vmindex 1 --key max_frame_rate
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" setting --vmindex 1 --key performance_cpu.custom --key performance_mem.custom
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" setting --vmindex 1 --key resolution_width.custom --key resolution_height.custom --key resolution_dpi.custom
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" adb --vmindex 1 --cmd "shell getprop persist.sys.locale"
```

## 8) Rule xu ly lag
1. Tang RAM len `4.000000` truoc, giu CPU `2`.
2. Neu van lag, tang CPU len `4`.
3. Chi tang FPS khi can muot hon (`20 -> 30`).

## 9) Mau lenh scale nhieu instance sau nay
```powershell
# Tao them 3 may moi
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" create --number 3

# Ap cau hinh hang loat cho vmindex 2,3,4 (vi du)
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" setting --vmindex 2,3,4 --key performance_mode --value custom --key performance_cpu.custom --value 2 --key performance_mem.custom --value 3.000000 --key max_frame_rate --value 20
```

## 10) Cai SockDroid (APK chinh thuc)
- Nguon release chinh thuc: `https://github.com/bndeff/socksdroid/releases/latest`
- APK da dung trong setup nay: `socksdroid-1.0.4.apk`
- Package name: `net.typeblog.socks`

### 10.1) Tai APK
```powershell
$url = "https://github.com/bndeff/socksdroid/releases/download/1.0.4/socksdroid-1.0.4.apk"
$apk = "C:\Users\1\Documents\Codex\2026-05-20\m-y-c-i-mumuplayer-ch\socksdroid-1.0.4.apk"
curl.exe -L "$url" -o "$apk"
```

### 10.2) Xac thuc file truoc khi cai
```powershell
# Kiem tra metadata tu URL
Invoke-WebRequest -Uri "https://github.com/bndeff/socksdroid/releases/download/1.0.4/socksdroid-1.0.4.apk" -Method Head -MaximumRedirection 10

# Kiem tra file local
Get-Item "$apk" | Select-Object Name,Length,LastWriteTime
Get-FileHash "$apk" -Algorithm SHA256
```

Gia tri tham chieu da verify:
- `Content-Type`: `application/vnd.android.package-archive`
- `Content-Length`: `790099`
- `SHA256`: `4A92F430648FC4F6EA22ABD0E5F9C0DBFF2E3DAF2220DD51616B3E7C341E2136`

### 10.3) Cai vao MuMu va mo app
```powershell
# Cai app
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" control --vmindex 1 app install --apk "$apk"

# Verify app da cai
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" control --vmindex 1 app info --package net.typeblog.socks

# Mo app
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" control --vmindex 1 app launch --package net.typeblog.socks
```
