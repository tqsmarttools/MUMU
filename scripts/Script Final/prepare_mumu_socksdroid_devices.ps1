param(
    [string]$AdbPath = "D:\Program Files\Netease\MuMuPlayer\nx_main\adb.exe",
    [string]$MumuCliPath = "D:\Program Files\Netease\MuMuPlayer\nx_main\mumu-cli.exe",
    [string]$VmIndex = "all",
    [string]$WhoerUrl = "https://whoer.net",
    [string]$IpCheckUrl = "https://api.ipify.org",
    [string]$ReadyStatePath = "",
    [string]$LogPath = "",
    [int]$LaunchTimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"

$SocksDroidPackage = "net.typeblog.socks"
$ChromeComponent = "com.android.chromium/com.google.android.apps.chrome.IntentDispatcher"
$BaseWidth = 540
$BaseHeight = 960

if ([string]::IsNullOrWhiteSpace($ReadyStatePath)) {
    $ReadyStatePath = Join-Path $PSScriptRoot "state\mumu_device_ready.json"
}

if ([string]::IsNullOrWhiteSpace($LogPath)) {
    $LogPath = Join-Path $PSScriptRoot ("logs\prepare_mumu_socksdroid_{0}.log" -f (Get-Date -Format "yyyyMMdd"))
}

foreach ($path in @($ReadyStatePath, $LogPath)) {
    $parent = Split-Path -Parent $path
    if (-not [string]::IsNullOrWhiteSpace($parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
}

function Write-Log {
    param([string]$Message)

    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -Path $LogPath -Value $line -Encoding UTF8
}

function Invoke-Mumu {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)

    if (-not (Test-Path $MumuCliPath)) {
        throw "MuMu CLI not found: $MumuCliPath"
    }

    & $MumuCliPath @Args
}

function Invoke-AdbProcess {
    param([string[]]$CommandArgs)

    $previousErrorActionPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = "Continue"
        $output = & $AdbPath @CommandArgs 2>&1 | ForEach-Object { $_.ToString() }
        $exitCode = $LASTEXITCODE
    }
    finally {
        $ErrorActionPreference = $previousErrorActionPreference
    }

    [PSCustomObject]@{
        Output = $output
        ExitCode = $exitCode
    }
}

function Invoke-Adb {
    param(
        [string]$Serial,
        [Alias("Args")]
        [string[]]$AdbArgs
    )

    if (-not (Test-Path $AdbPath)) {
        throw "ADB not found: $AdbPath"
    }

    $result = Invoke-AdbProcess -CommandArgs (@("-s", $Serial) + $AdbArgs)
    if ($result.ExitCode -eq 0) {
        return $result.Output
    }

    Invoke-AdbProcess -CommandArgs @("disconnect", $Serial) | Out-Null
    Start-Sleep -Seconds 1
    Invoke-AdbProcess -CommandArgs @("connect", $Serial) | Out-Null
    Start-Sleep -Seconds 1

    $retryResult = Invoke-AdbProcess -CommandArgs (@("-s", $Serial) + $AdbArgs)
    if ($retryResult.ExitCode -ne 0) {
        throw ("ADB command failed for {0}: {1}" -f $Serial, ($retryResult.Output -join " "))
    }

    return $retryResult.Output
}

function Invoke-AdbNoSerial {
    param(
        [Alias("Args")]
        [string[]]$AdbArgs
    )

    if (-not (Test-Path $AdbPath)) {
        throw "ADB not found: $AdbPath"
    }

    $result = Invoke-AdbProcess -CommandArgs $AdbArgs
    if ($result.ExitCode -ne 0) {
        throw ("ADB command failed: {0}" -f ($result.Output -join " "))
    }

    return $result.Output
}

function Get-MumuInfo {
    $raw = (Invoke-Mumu info --vmindex all) -join "`n"
    return $raw | ConvertFrom-Json
}

function Get-SelectedDevices {
    param($Info)

    $indices =
        if ($VmIndex -eq "all") {
            $Info.PSObject.Properties.Name
        } else {
            $VmIndex -split "," | ForEach-Object { $_.Trim() } | Where-Object { $_ -ne "" }
        }

    foreach ($index in $indices) {
        $device = $Info.PSObject.Properties[$index].Value
        if ($null -ne $device) {
            $device
        }
    }
}

function Get-Scale {
    param([string]$Serial)

    $scale = [PSCustomObject]@{ X = 1.0; Y = 1.0 }
    $sizeText = (Invoke-Adb -Serial $Serial -Args @("shell", "wm", "size")) -join "`n"
    if ($sizeText -match "(\d+)x(\d+)") {
        $scale.X = [double]$Matches[1] / $BaseWidth
        $scale.Y = [double]$Matches[2] / $BaseHeight
    }
    return $scale
}

function Tap-Point {
    param(
        [string]$Serial,
        [object]$Scale,
        [int]$X,
        [int]$Y,
        [int]$Jitter = 6,
        [string]$Name = "tap"
    )

    $jx = Get-Random -Minimum (-1 * $Jitter) -Maximum ($Jitter + 1)
    $jy = Get-Random -Minimum (-1 * $Jitter) -Maximum ($Jitter + 1)
    $tx = [int][Math]::Round(($X + $jx) * $Scale.X)
    $ty = [int][Math]::Round(($Y + $jy) * $Scale.Y)
    Write-Log ("{0} {1}: {2},{3}" -f $Serial, $Name, $tx, $ty)
    Invoke-Adb -Serial $Serial -Args @("shell", "input", "tap", $tx, $ty) | Out-Null
}

function Test-VpnActive {
    param([string]$Serial)

    $connectivity = (Invoke-Adb -Serial $Serial -Args @("shell", "dumpsys", "connectivity")) -join "`n"
    return ($connectivity -match "VPN CONNECTED" -and $connectivity -match "InterfaceName:\s*tun0")
}

function Wait-ForVpnActive {
    param(
        [string]$Serial,
        [int]$TimeoutSeconds = 45,
        [int]$IntervalSeconds = 5
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        if (Test-VpnActive -Serial $Serial) {
            return $true
        }
        Start-Sleep -Seconds $IntervalSeconds
    } while ((Get-Date) -lt $deadline)

    return $false
}

function Accept-VpnDialogIfPresent {
    param(
        [string]$Serial,
        [object]$Scale
    )

    try {
        Invoke-Adb -Serial $Serial -Args @("shell", "uiautomator", "dump", "/sdcard/current_window.xml") | Out-Null
        $ui = (Invoke-Adb -Serial $Serial -Args @("shell", "cat", "/sdcard/current_window.xml")) -join "`n"
        if ($ui -match "com\.android\.vpndialogs" -or $ui -match "Connection request|OK|Allow|Cho phép") {
            Write-Log "$Serial VPN dialog visible; accepting"

            $button = [regex]::Match(
                $ui,
                'resource-id="android:id/button1".*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
                [Text.RegularExpressions.RegexOptions]::Singleline
            )

            if ($button.Success) {
                $left = [int]$button.Groups[1].Value
                $top = [int]$button.Groups[2].Value
                $right = [int]$button.Groups[3].Value
                $bottom = [int]$button.Groups[4].Value
                $x = [int][Math]::Round(($left + $right) / 2)
                $y = [int][Math]::Round(($top + $bottom) / 2)
                Write-Log ("{0} accept VPN dialog: {1},{2}" -f $Serial, $x, $y)
                Invoke-Adb -Serial $Serial -Args @("shell", "input", "tap", $x, $y) | Out-Null
            } else {
                Tap-Point -Serial $Serial -Scale $Scale -X 455 -Y 875 -Jitter 8 -Name "accept VPN dialog (fallback)"
            }

            Start-Sleep -Seconds 2
        }
    } catch {
        Write-Log ("{0} VPN dialog check skipped: {1}" -f $Serial, $_.Exception.Message)
    }
}

function Wait-ForPackageFocus {
    param(
        [string]$Serial,
        [string]$Package,
        [int]$TimeoutSeconds = 20
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $focus = (Invoke-Adb -Serial $Serial -Args @("shell", "dumpsys", "window")) -join "`n"
        if ($focus -match [regex]::Escape($Package)) {
            return $true
        }
        Start-Sleep -Seconds 1
    } while ((Get-Date) -lt $deadline)

    return $false
}

function Get-SocksDroidSwitch {
    param([string]$Serial)

    Invoke-Adb -Serial $Serial -Args @("shell", "uiautomator", "dump", "/sdcard/socksdroid_window.xml") | Out-Null
    $ui = (Invoke-Adb -Serial $Serial -Args @("shell", "cat", "/sdcard/socksdroid_window.xml")) -join "`n"
    $match = [regex]::Match(
        $ui,
        'resource-id="net\.typeblog\.socks:id/switch_action_button".*?checked="([^"]+)".*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
        [Text.RegularExpressions.RegexOptions]::Singleline
    )

    if (-not $match.Success) {
        return $null
    }

    $left = [int]$match.Groups[2].Value
    $top = [int]$match.Groups[3].Value
    $right = [int]$match.Groups[4].Value
    $bottom = [int]$match.Groups[5].Value

    return [PSCustomObject]@{
        Checked = ([string]$match.Groups[1].Value -eq "true")
        X = [int][Math]::Round(($left + $right) / 2)
        Y = [int][Math]::Round(($top + $bottom) / 2)
    }
}

function Open-LauncherIcon {
    param(
        [string]$Serial,
        [string]$Label,
        [int]$TimeoutSeconds = 12
    )

    Write-Log "$Serial opening launcher icon: $Label"
    Invoke-Adb -Serial $Serial -Args @("shell", "input", "keyevent", "3") | Out-Null
    Start-Sleep -Seconds 2

    try {
        Invoke-Adb -Serial $Serial -Args @("shell", "uiautomator", "dump", "/sdcard/launcher_window.xml") | Out-Null
        $ui = (Invoke-Adb -Serial $Serial -Args @("shell", "cat", "/sdcard/launcher_window.xml")) -join "`n"
        $match = [regex]::Match(
            $ui,
            ('content-desc="{0}".*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"' -f [regex]::Escape($Label)),
            [Text.RegularExpressions.RegexOptions]::Singleline
        )

        if ($match.Success) {
            $left = [int]$match.Groups[1].Value
            $top = [int]$match.Groups[2].Value
            $right = [int]$match.Groups[3].Value
            $bottom = [int]$match.Groups[4].Value
            $x = [int][Math]::Round(($left + $right) / 2)
            $y = [int][Math]::Round(($top + $bottom) / 2)
            Write-Log ("{0} tapping launcher icon {1} at {2},{3}" -f $Serial, $Label, $x, $y)
            Invoke-Adb -Serial $Serial -Args @("shell", "input", "tap", $x, $y) | Out-Null
        } else {
            Write-Log "$Serial launcher icon $Label not found"
            return $false
        }
    } catch {
        Write-Log ("{0} launcher icon open failed: {1}" -f $Serial, $_.Exception.Message)
        return $false
    }

    return (Wait-ForPackageFocus -Serial $Serial -Package $SocksDroidPackage -TimeoutSeconds $TimeoutSeconds)
}

function Open-SocksDroid {
    param(
        [string]$Serial,
        [int]$TimeoutSeconds = 20
    )

    Write-Log "$Serial launching SocksDroid"
    Invoke-Adb -Serial $Serial -Args @("shell", "am", "start", "-n", "$SocksDroidPackage/.MainActivity") | Out-Null
    if (Wait-ForPackageFocus -Serial $Serial -Package $SocksDroidPackage -TimeoutSeconds $TimeoutSeconds) {
        Start-Sleep -Seconds 2
        return $true
    }

    Write-Log "$Serial SocksDroid did not reach foreground; trying launcher icon"
    if (Open-LauncherIcon -Serial $Serial -Label "SocksDroid" -TimeoutSeconds 15) {
        Start-Sleep -Seconds 2
        return $true
    }

    Write-Log "$Serial launcher icon fallback failed; retrying monkey launcher intent"
    Invoke-Adb -Serial $Serial -Args @("shell", "monkey", "-p", $SocksDroidPackage, "-c", "android.intent.category.LAUNCHER", "1") | Out-Null
    Start-Sleep -Seconds 6
    return (Wait-ForPackageFocus -Serial $Serial -Package $SocksDroidPackage -TimeoutSeconds $TimeoutSeconds)
}

function Enable-SocksDroid {
    param(
        [string]$Serial,
        [object]$Scale
    )

    if (Test-VpnActive -Serial $Serial) {
        Write-Log "$Serial SocksDroid VPN already active"
        return $true
    }

    if (-not (Open-SocksDroid -Serial $Serial -TimeoutSeconds 20)) {
        Write-Log "$Serial unable to open SocksDroid before toggling"
    }

    $switch = Get-SocksDroidSwitch -Serial $Serial
    if ($null -ne $switch) {
        Write-Log ("{0} SocksDroid switch checked={1} at {2},{3}" -f $Serial, $switch.Checked, $switch.X, $switch.Y)
        if (-not $switch.Checked) {
            Invoke-Adb -Serial $Serial -Args @("shell", "input", "tap", $switch.X, $switch.Y) | Out-Null
        }
    } else {
        Write-Log "$Serial SocksDroid switch not found in UI; using fallback tap"
        Tap-Point -Serial $Serial -Scale $Scale -X 445 -Y 78 -Jitter 4 -Name "SocksDroid main switch"
    }

    Start-Sleep -Seconds 3
    Accept-VpnDialogIfPresent -Serial $Serial -Scale $Scale

    $active = Wait-ForVpnActive -Serial $Serial -TimeoutSeconds 45
    if (-not $active) {
        Write-Log "$Serial VPN did not become active after first toggle; retrying SocksDroid switch"
        if (-not (Open-SocksDroid -Serial $Serial -TimeoutSeconds 20)) {
            Write-Log "$Serial SocksDroid did not reach foreground for retry"
        }

        $retrySwitch = Get-SocksDroidSwitch -Serial $Serial
        if ($null -ne $retrySwitch -and $retrySwitch.Checked) {
            Write-Log ("{0} SocksDroid switch is checked but VPN inactive; toggling off before retry" -f $Serial)
            Invoke-Adb -Serial $Serial -Args @("shell", "input", "tap", $retrySwitch.X, $retrySwitch.Y) | Out-Null
            Start-Sleep -Seconds 3
            $retrySwitch = Get-SocksDroidSwitch -Serial $Serial
        }

        if ($null -ne $retrySwitch) {
            Write-Log ("{0} retry SocksDroid switch checked={1} at {2},{3}" -f $Serial, $retrySwitch.Checked, $retrySwitch.X, $retrySwitch.Y)
            if (-not $retrySwitch.Checked) {
                Invoke-Adb -Serial $Serial -Args @("shell", "input", "tap", $retrySwitch.X, $retrySwitch.Y) | Out-Null
            }
        } else {
            Write-Log "$Serial retry SocksDroid switch not found; using fallback tap"
            Tap-Point -Serial $Serial -Scale $Scale -X 445 -Y 78 -Jitter 4 -Name "retry SocksDroid main switch"
        }

        Start-Sleep -Seconds 3
        Accept-VpnDialogIfPresent -Serial $Serial -Scale $Scale
        $active = Wait-ForVpnActive -Serial $Serial -TimeoutSeconds 45
    }

    Write-Log ("{0} VPN active={1}" -f $Serial, $active)
    return $active
}

function Get-HostIp {
    try {
        return (Invoke-RestMethod -Uri "https://api.ipify.org" -TimeoutSec 10).Trim()
    } catch {
        Write-Log ("host IP lookup failed: {0}" -f $_.Exception.Message)
        return ""
    }
}

function Open-UrlInChrome {
    param(
        [string]$Serial,
        [string]$Url,
        [string]$Label = "URL"
    )

    Write-Log ("{0} opening {1} in Chrome: {2}" -f $Serial, $Label, $Url)
    Invoke-Adb -Serial $Serial -Args @("shell", "am", "start", "-n", $ChromeComponent, "-a", "android.intent.action.VIEW", "-d", $Url) | Out-Null
    Start-Sleep -Seconds 15
}

function Open-WhoerInChrome {
    param([string]$Serial)

    Open-UrlInChrome -Serial $Serial -Url $WhoerUrl -Label "Whoer"
}

function Get-BrowserIpFromTextPage {
    param([string]$Serial)

    try {
        Open-UrlInChrome -Serial $Serial -Url $IpCheckUrl -Label "browser IP check"

        for ($attempt = 1; $attempt -le 8; $attempt++) {
            Invoke-Adb -Serial $Serial -Args @("shell", "uiautomator", "dump", "/sdcard/browser_ip_check.xml") | Out-Null
            $ui = (Invoke-Adb -Serial $Serial -Args @("shell", "cat", "/sdcard/browser_ip_check.xml")) -join "`n"
            $match = [regex]::Match($ui, "\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
            if ($match.Success) {
                Write-Log ("{0} browser IP detected on attempt {1}: {2}" -f $Serial, $attempt, $match.Value)
                return $match.Value
            }

            Write-Log ("{0} browser IP not visible yet; attempt {1}/8" -f $Serial, $attempt)
            Start-Sleep -Seconds 5
        }

        Write-Log "$Serial browser IP text not found in UI dump"
    } catch {
        Write-Log ("{0} browser IP check failed: {1}" -f $Serial, $_.Exception.Message)
    }

    return ""
}

function Return-ToHomeScreen {
    param([string]$Serial)

    try {
        Write-Log ("{0} returning to Home screen" -f $Serial)
        Invoke-Adb -Serial $Serial -Args @("shell", "input", "keyevent", "3") | Out-Null
        Start-Sleep -Seconds 2
        Invoke-Adb -Serial $Serial -Args @("shell", "input", "keyevent", "3") | Out-Null
        Start-Sleep -Seconds 1
    } catch {
        Write-Log ("{0} return-to-home failed: {1}" -f $Serial, $_.Exception.Message)
    }
}

function Wait-ForAdbOnline {
    param(
        [string]$Serial,
        [int]$TimeoutSeconds = 120
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        $stateResult = Invoke-AdbProcess -CommandArgs @("-s", $Serial, "get-state")
        if ($stateResult.ExitCode -eq 0) {
            $state = (($stateResult.Output -join " ").Trim()).ToLowerInvariant()
            if ($state -eq "device") {
                return $true
            }
        }
        Start-Sleep -Seconds 3
    } while ((Get-Date) -lt $deadline)

    return $false
}

function Wait-ForVmReadyByIndex {
    param(
        [string]$Index,
        [int]$TimeoutSeconds = 180
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    do {
        try {
            $info = Get-MumuInfo
            $vm = $info.PSObject.Properties[$Index].Value
            if ($null -ne $vm -and [bool]$vm.is_process_started -and [bool]$vm.is_android_started -and $null -ne $vm.adb_port) {
                return $vm
            }
        } catch {
            Write-Log ("wait vm={0} ready check failed: {1}" -f $Index, $_.Exception.Message)
        }
        Start-Sleep -Seconds 6
    } while ((Get-Date) -lt $deadline)

    return $null
}

function Handle-RuntimeErrorPopup {
    param(
        [string]$Serial,
        [string]$DeviceIndex
    )

    $ui = ""
    try {
        Invoke-Adb -Serial $Serial -Args @("shell", "uiautomator", "dump", "/sdcard/runtime_check.xml") | Out-Null
        $ui = (Invoke-Adb -Serial $Serial -Args @("shell", "cat", "/sdcard/runtime_check.xml")) -join "`n"
    } catch {
        Write-Log ("{0} runtime dialog check skipped: {1}" -f $Serial, $_.Exception.Message)
        return $Serial
    }

    if ($ui -notmatch "Runtime error|Please restart your Android Device|Restart now") {
        return $Serial
    }

    Write-Log ("{0} runtime error popup detected; attempting auto-restart" -f $Serial)
    $clicked = $false

    $match = [regex]::Match(
        $ui,
        'text="Restart now".*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"',
        [Text.RegularExpressions.RegexOptions]::Singleline
    )
    if ($match.Success) {
        $x = [int][Math]::Round(([int]$match.Groups[1].Value + [int]$match.Groups[3].Value) / 2)
        $y = [int][Math]::Round(([int]$match.Groups[2].Value + [int]$match.Groups[4].Value) / 2)
        Write-Log ("{0} tapping runtime Restart now at {1},{2}" -f $Serial, $x, $y)
        Invoke-Adb -Serial $Serial -Args @("shell", "input", "tap", $x, $y) | Out-Null
        $clicked = $true
    } else {
        # Fallback location for MuMu runtime popup left button.
        Write-Log ("{0} runtime Restart now bounds not found; fallback tap" -f $Serial)
        Invoke-Adb -Serial $Serial -Args @("shell", "input", "tap", "168", "582") | Out-Null
        $clicked = $true
    }

    if ($clicked) {
        Start-Sleep -Seconds 6
    }

    if (Wait-ForAdbOnline -Serial $Serial -TimeoutSeconds 120) {
        Write-Log ("{0} adb online after runtime popup restart" -f $Serial)
        return $Serial
    }

    Write-Log ("{0} still offline after popup restart; forcing vm={1} restart via mumu-cli" -f $Serial, $DeviceIndex)
    Invoke-Mumu control --vmindex $DeviceIndex restart | Out-Null

    $vm = Wait-ForVmReadyByIndex -Index $DeviceIndex -TimeoutSeconds 220
    if ($null -eq $vm -or $null -eq $vm.adb_port) {
        Write-Log ("vm={0} failed to recover after forced restart" -f $DeviceIndex)
        return $Serial
    }

    $newSerial = "127.0.0.1:{0}" -f [int]$vm.adb_port
    Invoke-AdbNoSerial -Args @("connect", $newSerial) | Out-Null
    if (Wait-ForAdbOnline -Serial $newSerial -TimeoutSeconds 90) {
        Write-Log ("vm={0} recovered with serial={1}" -f $DeviceIndex, $newSerial)
        return $newSerial
    }

    Write-Log ("vm={0} restart completed but adb still offline on serial={1}" -f $DeviceIndex, $newSerial)
    return $newSerial
}

function Restart-VmAndReconnect {
    param(
        [string]$DeviceIndex,
        [string]$CurrentSerial = ""
    )

    Write-Log ("restarting vm={0} for recovery (serial={1})" -f $DeviceIndex, $CurrentSerial)
    Invoke-Mumu control --vmindex $DeviceIndex restart | Out-Null

    $vm = Wait-ForVmReadyByIndex -Index $DeviceIndex -TimeoutSeconds 220
    if ($null -eq $vm -or $null -eq $vm.adb_port) {
        Write-Log ("vm={0} failed to become ready after restart" -f $DeviceIndex)
        return ""
    }

    $serial = "127.0.0.1:{0}" -f [int]$vm.adb_port
    Invoke-AdbNoSerial -Args @("connect", $serial) | Out-Null
    if (Wait-ForAdbOnline -Serial $serial -TimeoutSeconds 90) {
        Write-Log ("vm={0} reconnect success serial={1}" -f $DeviceIndex, $serial)
        return $serial
    }

    Write-Log ("vm={0} reconnect failed serial={1}" -f $DeviceIndex, $serial)
    return ""
}

function Save-WhoerScreenshot {
    param(
        [string]$Serial,
        [string]$Index
    )

    $screenshotDir = Join-Path $PSScriptRoot "screenshots"
    New-Item -ItemType Directory -Path $screenshotDir -Force | Out-Null
    $safeSerial = $Serial -replace "[:\\\/]", "_"
    $localPath = Join-Path $screenshotDir ("whoer_vm{0}_{1}_{2}.png" -f $Index, $safeSerial, (Get-Date -Format "yyyyMMdd_HHmmss"))

    try {
        Invoke-Adb -Serial $Serial -Args @("shell", "screencap", "-p", "/sdcard/whoer_check.png") | Out-Null
        & $AdbPath -s $Serial pull /sdcard/whoer_check.png $localPath | Out-Null
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $localPath)) {
            throw "adb pull failed for $localPath"
        }
        return $localPath
    } catch {
        Write-Log ("{0} screenshot failed: {1}" -f $Serial, $_.Exception.Message)
        return ""
    }
}

function Save-IpCheckScreenshot {
    param(
        [string]$Serial,
        [string]$Index
    )

    $screenshotDir = Join-Path $PSScriptRoot "screenshots"
    New-Item -ItemType Directory -Path $screenshotDir -Force | Out-Null
    $safeSerial = $Serial -replace "[:\\\/]", "_"
    $localPath = Join-Path $screenshotDir ("ipcheck_vm{0}_{1}_{2}.png" -f $Index, $safeSerial, (Get-Date -Format "yyyyMMdd_HHmmss"))

    try {
        Invoke-Adb -Serial $Serial -Args @("shell", "screencap", "-p", "/sdcard/ip_check.png") | Out-Null
        & $AdbPath -s $Serial pull /sdcard/ip_check.png $localPath | Out-Null
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path $localPath)) {
            throw "adb pull failed for $localPath"
        }
        return $localPath
    } catch {
        Write-Log ("{0} IP screenshot failed: {1}" -f $Serial, $_.Exception.Message)
        return ""
    }
}

function Get-WhoerIpFromChromeDevTools {
    param(
        [string]$Serial,
        [int]$LocalPort
    )

    try {
        Invoke-AdbNoSerial -Args @("-s", $Serial, "forward", "tcp:$LocalPort", "localabstract:chrome_devtools_remote") | Out-Null
        Start-Sleep -Seconds 1
        $pages = Invoke-RestMethod -Uri "http://127.0.0.1:$LocalPort/json" -TimeoutSec 5
        $page = @($pages | Where-Object { $_.url -match "whoer\.net" } | Select-Object -First 1)
        if (-not $page -or [string]::IsNullOrWhiteSpace($page.webSocketDebuggerUrl)) {
            return ""
        }

        Add-Type -AssemblyName System.Net.WebSockets.Client
        $ws = [System.Net.WebSockets.ClientWebSocket]::new()
        $ct = [Threading.CancellationToken]::None
        $ws.ConnectAsync([Uri]$page.webSocketDebuggerUrl, $ct).Wait(5000) | Out-Null

        $payload = @{
            id = 1
            method = "Runtime.evaluate"
            params = @{
                expression = "document.body ? document.body.innerText : ''"
                returnByValue = $true
            }
        } | ConvertTo-Json -Depth 5 -Compress

        $bytes = [Text.Encoding]::UTF8.GetBytes($payload)
        $segment = [ArraySegment[byte]]::new($bytes)
        $ws.SendAsync($segment, [Net.WebSockets.WebSocketMessageType]::Text, $true, $ct).Wait(5000) | Out-Null

        $buffer = New-Object byte[] 65536
        $received = [Text.StringBuilder]::new()
        do {
            $result = $ws.ReceiveAsync([ArraySegment[byte]]::new($buffer), $ct).Result
            if ($result.Count -gt 0) {
                [void]$received.Append([Text.Encoding]::UTF8.GetString($buffer, 0, $result.Count))
            }
        } while (-not $result.EndOfMessage)

        $ws.Dispose()
        $response = $received.ToString() | ConvertFrom-Json
        $text = [string]$response.result.result.value
        $match = [regex]::Match($text, "\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
        if ($match.Success) {
            return $match.Value
        }
    } catch {
        Write-Log ("{0} Chrome DevTools IP check failed: {1}" -f $Serial, $_.Exception.Message)
    } finally {
        try {
            Invoke-AdbNoSerial -Args @("-s", $Serial, "forward", "--remove", "tcp:$LocalPort") | Out-Null
        } catch {}
    }

    return ""
}

function Wait-ForDevicesStarted {
    $deadline = (Get-Date).AddSeconds($LaunchTimeoutSeconds)

    do {
        $info = Get-MumuInfo
        $selected = @(Get-SelectedDevices -Info $info)
        $notReady = @($selected | Where-Object { -not $_.is_process_started -or -not $_.is_android_started })

        if ($notReady.Count -eq 0 -and $selected.Count -gt 0) {
            return $selected
        }

        $names = ($notReady | ForEach-Object { "{0}:{1}" -f $_.index, $_.player_state }) -join ", "
        Write-Log ("waiting for Android start: {0}" -f $names)
        Start-Sleep -Seconds 8
    } while ((Get-Date) -lt $deadline)

    $info = Get-MumuInfo
    return @(Get-SelectedDevices -Info $info)
}

try {
    Write-Log "======== MuMu SocksDroid preparation started ========"
    Write-Log ("target vmindex={0}" -f $VmIndex)

    $hostIp = Get-HostIp
    if (-not [string]::IsNullOrWhiteSpace($hostIp)) {
        Write-Log ("host public IP={0}" -f $hostIp)
    }

    $initialInfo = Get-MumuInfo
    $initialDevices = @(Get-SelectedDevices -Info $initialInfo)
    $devicesToLaunch = @($initialDevices | Where-Object { $_.is_process_started -ne $true })

    if ($devicesToLaunch.Count -gt 0) {
        $launchIndices = ($devicesToLaunch | ForEach-Object { [string]$_.index }) -join ","
        Write-Log ("launching stopped MuMu devices: {0}" -f $launchIndices)
        Invoke-Mumu control --vmindex $launchIndices launch | Out-Null
    } else {
        Write-Log "selected MuMu devices are already process-started; skipping launch"
    }

    $devices = @(Wait-ForDevicesStarted)

    $results = @()
    foreach ($device in $devices) {
        $index = [string]$device.index
        $name = [string]$device.name
        if (-not [bool]$device.is_process_started -or -not [bool]$device.is_android_started -or $null -eq $device.adb_port) {
            Write-Log ("vm={0} name={1} is not started; ready=false" -f $index, $name)
            $results += [PSCustomObject]@{
                index = $index
                name = $name
                serial = ""
                adbPort = $null
                vpnActive = $false
                hostIp = $hostIp
                whoerIp = ""
                ipLooksFake = $false
                ready = $false
                screenshot = ""
                checkedAt = (Get-Date).ToString("s")
            }
            continue
        }

        $adbPort = [int]$device.adb_port
        $serial = "127.0.0.1:$adbPort"

        Write-Log ("preparing vm={0} name={1} serial={2}" -f $index, $name, $serial)
        Invoke-AdbNoSerial -Args @("connect", $serial) | Out-Null
        if (-not (Wait-ForAdbOnline -Serial $serial -TimeoutSeconds 35)) {
            Write-Log ("{0} adb offline/not found before prepare; restarting vm={1}" -f $serial, $index)
            $recoveredSerial = Restart-VmAndReconnect -DeviceIndex $index -CurrentSerial $serial
            if ([string]::IsNullOrWhiteSpace($recoveredSerial)) {
                throw ("ADB still offline after vm restart for {0}" -f $serial)
            }
            $serial = $recoveredSerial
        }
        $serial = Handle-RuntimeErrorPopup -Serial $serial -DeviceIndex $index
        if (-not (Wait-ForAdbOnline -Serial $serial -TimeoutSeconds 45)) {
            throw ("ADB offline after runtime-popup handling on {0}" -f $serial)
        }
        if ($serial -match "^\d+\.\d+\.\d+\.\d+:(\d+)$") {
            $adbPort = [int]$Matches[1]
        }

        $scale = Get-Scale -Serial $serial
        $vpnActive = Enable-SocksDroid -Serial $serial -Scale $scale

        $whoerIp = ""
        $screenshot = ""
        if ($vpnActive) {
            $whoerIp = Get-BrowserIpFromTextPage -Serial $serial
            $screenshot = Save-IpCheckScreenshot -Serial $serial -Index $index
            # Keep the flow stable: avoid opening heavy pages after IP check.
        }
        Return-ToHomeScreen -Serial $serial
        $serial = Handle-RuntimeErrorPopup -Serial $serial -DeviceIndex $index
        if (-not (Wait-ForAdbOnline -Serial $serial -TimeoutSeconds 30)) {
            Write-Log ("{0} offline after return-home; recovering vm={1} and re-applying VPN check" -f $serial, $index)
            $recoveredSerial = Restart-VmAndReconnect -DeviceIndex $index -CurrentSerial $serial
            if ([string]::IsNullOrWhiteSpace($recoveredSerial)) {
                Write-Log ("vm={0} recovery failed after return-home; marking not ready" -f $index)
                $vpnActive = $false
                $whoerIp = ""
            } else {
                $serial = $recoveredSerial
                if ($serial -match "^\d+\.\d+\.\d+\.\d+:(\d+)$") {
                    $adbPort = [int]$Matches[1]
                }
                $scale = Get-Scale -Serial $serial
                $vpnActive = Enable-SocksDroid -Serial $serial -Scale $scale
                if ($vpnActive) {
                    $whoerIp = Get-BrowserIpFromTextPage -Serial $serial
                    $screenshot = Save-IpCheckScreenshot -Serial $serial -Index $index
                } else {
                    $whoerIp = ""
                }
                Return-ToHomeScreen -Serial $serial
                $serial = Handle-RuntimeErrorPopup -Serial $serial -DeviceIndex $index
            }
        }
        if ($serial -match "^\d+\.\d+\.\d+\.\d+:(\d+)$") {
            $adbPort = [int]$Matches[1]
        }

        $ipLooksFake =
            $vpnActive -and
            -not [string]::IsNullOrWhiteSpace($whoerIp) -and
            (
                [string]::IsNullOrWhiteSpace($hostIp) -or
                $whoerIp -ne $hostIp
            )

        $ready = [bool]($vpnActive -and $ipLooksFake)
        Write-Log ("vm={0} ready={1} vpn={2} whoerIp={3} screenshot={4}" -f $index, $ready, $vpnActive, $whoerIp, $screenshot)

        $results += [PSCustomObject]@{
            index = $index
            name = $name
            serial = $serial
            adbPort = $adbPort
            vpnActive = [bool]$vpnActive
            hostIp = $hostIp
            whoerIp = $whoerIp
            ipLooksFake = [bool]$ipLooksFake
            ready = [bool]$ready
            screenshot = $screenshot
            checkedAt = (Get-Date).ToString("s")
        }
    }

    $state = [PSCustomObject]@{
        generatedAt = (Get-Date).ToString("s")
        whoerUrl = $WhoerUrl
        ipCheckUrl = $IpCheckUrl
        devices = $results
    }

    $state | ConvertTo-Json -Depth 6 | Set-Content -Path $ReadyStatePath -Encoding UTF8
    Write-Log ("ready state written: {0}" -f $ReadyStatePath)
    Write-Log "======== MuMu SocksDroid preparation finished ========"

    if (@($results | Where-Object { $_.ready }).Count -eq 0) {
        exit 2
    }
    exit 0
} catch {
    Write-Log ("ERROR: {0}" -f $_.Exception.Message)
    exit 1
}
