# SOP - MuMuPlayer TikTok Lite (1 Instance)

## 1) Mục tiêu
- Dùng cho TikTok và các ứng dụng nhẹ.
- Không chơi game, không cần giả lập GPS.
- Ưu tiên tiết kiệm tài nguyên nhưng vẫn thao tác mượt.

## 2) Cấu hình chuẩn đã chốt
- Tên máy ảo: `TT-Lite-01`
- CPU: `2`
- RAM: `3072 MB` (`3.000000`)
- FPS: `20`
- Độ phân giải: `720 x 1280` (màn hình dọc)
- DPI: `320`
- Thương hiệu/mẫu máy: `Samsung Galaxy A34` (`SM-A346E`)
- Root: `false`
- Ngôn ngữ: `en-US`
- ADB: sử dụng qua `mumu-cli adb`

## 3) Đường dẫn công cụ
- `C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe`

## 3.1) Phân biệt nhanh `mumu-cli` và `adb`
- `mumu-cli`: quản lý máy ảo MuMu từ bên ngoài.
  Dùng khi cần tạo/xóa máy, bật/tắt máy, đổi CPU/RAM/FPS/độ phân giải, cài APK nhanh.
- `adb`: thao tác bên trong hệ điều hành Android.
  Dùng khi cần mở link Play Store, bấm/tap, nhập text, kiểm tra package đã cài.

Ví dụ ngắn:
```powershell
# mumu-cli: bật máy ảo #1
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" control --vmindex 1 launch

# adb: mở trang TikTok trên Google Play trong máy ảo
& "C:\Program Files\Netease\MuMuPlayer\nx_main\adb.exe" -s 127.0.0.1:16416 shell am start -a android.intent.action.VIEW -d "market://details?id=com.zhiliaoapp.musically"
```

## 4) Tạo instance mới
```powershell
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" create --number 1
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" info --vmindex all
```

Ghi nhận `vmindex` mới (ví dụ: `1`), rồi đặt tên:

```powershell
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" rename --vmindex 1 --name "TT-Lite-01"
```

## 5) Áp cấu hình
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

## 6) Khởi động và đặt ngôn ngữ English
```powershell
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" control --vmindex 1 launch
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" adb --vmindex 1 --cmd "shell setprop persist.sys.locale en-US"
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" adb --vmindex 1 --cmd "shell setprop persist.sys.language en"
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" adb --vmindex 1 --cmd "shell setprop persist.sys.country US"
```

## 7) Xác nhận sau cài đặt
```powershell
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" info --vmindex 1
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" setting --vmindex 1 --key max_frame_rate
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" setting --vmindex 1 --key performance_cpu.custom --key performance_mem.custom
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" setting --vmindex 1 --key resolution_width.custom --key resolution_height.custom --key resolution_dpi.custom
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" adb --vmindex 1 --cmd "shell getprop persist.sys.locale"
```

## 8) Quy tắc xử lý lag
1. Tăng RAM lên `4.000000` trước, giữ CPU `2`.
2. Nếu vẫn lag, tăng CPU lên `4`.
3. Chỉ tăng FPS khi cần mượt hơn (`20 -> 30`).

## 9) Mẫu lệnh scale nhiều instance sau này
```powershell
# Tạo thêm 3 máy mới
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" create --number 3

# Áp cấu hình hàng loạt cho vmindex 2,3,4 (ví dụ)
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" setting --vmindex 2,3,4 --key performance_mode --value custom --key performance_cpu.custom --value 2 --key performance_mem.custom --value 3.000000 --key max_frame_rate --value 20
```

## 10) Cài SockDroid (APK chính thức)
- Nguồn release chính thức: `https://github.com/bndeff/socksdroid/releases/latest`
- APK đã dùng trong setup này: `socksdroid-1.0.4.apk`
- Package name: `net.typeblog.socks`

### 10.1) Tải APK
```powershell
$url = "https://github.com/bndeff/socksdroid/releases/download/1.0.4/socksdroid-1.0.4.apk"
$apk = "C:\Users\1\Documents\Codex\2026-05-20\m-y-c-i-mumuplayer-ch\socksdroid-1.0.4.apk"
curl.exe -L "$url" -o "$apk"
```

### 10.2) Xác thực file trước khi cài
```powershell
# Kiểm tra metadata từ URL
Invoke-WebRequest -Uri "https://github.com/bndeff/socksdroid/releases/download/1.0.4/socksdroid-1.0.4.apk" -Method Head -MaximumRedirection 10

# Kiểm tra file local
Get-Item "$apk" | Select-Object Name,Length,LastWriteTime
Get-FileHash "$apk" -Algorithm SHA256
```

Giá trị tham chiếu đã verify:
- `Content-Type`: `application/vnd.android.package-archive`
- `Content-Length`: `790099`
- `SHA256`: `4A92F430648FC4F6EA22ABD0E5F9C0DBFF2E3DAF2220DD51616B3E7C341E2136`

### 10.3) Cài vào MuMu và mở app
```powershell
# Cài app
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" control --vmindex 1 app install --apk "$apk"

# Verify app đã cài
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" control --vmindex 1 app info --package net.typeblog.socks

# Mở app
& "C:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe" control --vmindex 1 app launch --package net.typeblog.socks
```
