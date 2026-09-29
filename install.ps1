# Wooting Desktop Sync - installer. Run from the repo folder in PowerShell 7 (no admin needed).
#   pwsh -File .\install.ps1
$ErrorActionPreference = 'Stop'
$dir = $PSScriptRoot

# 1. Python 3.10+
$ok = $false
try { $ok = ((& python --version 2>&1) -match '3\.1[0-9]') } catch {}
if (-not $ok) {
    Write-Host "Installing Python 3.12 via winget..."
    winget install -e --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements
    $env:Path = [Environment]::GetEnvironmentVariable('Path','User') + ';' + [Environment]::GetEnvironmentVariable('Path','Machine')
}
python --version

# 2. hidapi
python -m pip install --user --quiet -r "$dir\requirements.txt"
python -c "import hid"; if ($LASTEXITCODE -ne 0) { throw "hidapi failed to install" }

# 3. VirtualDesktopAccessor.dll (Ciantic, MIT) - downloaded on first install
$dll = "$dir\VirtualDesktopAccessor.dll"
if (-not (Test-Path $dll)) {
    Write-Host "Downloading VirtualDesktopAccessor.dll..."
    Invoke-WebRequest -Uri 'https://github.com/Ciantic/VirtualDesktopAccessor/releases/latest/download/VirtualDesktopAccessor.dll' -OutFile $dll
}
Unblock-File $dll

# 4. config.json from the example if you haven't made one
if (-not (Test-Path "$dir\config.json")) { Copy-Item "$dir\config.example.json" "$dir\config.json" }

# 5. Run at logon via Task Scheduler, hidden (pythonw), restart if it dies
$pyw = (Get-Command pythonw).Source
$action   = New-ScheduledTaskAction -Execute $pyw -Argument "`"$dir\wooting_desktop_sync.py`"" -WorkingDirectory $dir
$trigger  = New-ScheduledTaskTrigger -AtLogOn -User $env:USERNAME
$settings = New-ScheduledTaskSettingsSet -ExecutionTimeLimit 0 -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -MultipleInstances IgnoreNew -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Unregister-ScheduledTask -TaskName 'Wooting Desktop Sync' -Confirm:$false -ErrorAction SilentlyContinue
Register-ScheduledTask -TaskName 'Wooting Desktop Sync' -Action $action -Trigger $trigger -Settings $settings -RunLevel Limited | Out-Null
Start-ScheduledTask -TaskName 'Wooting Desktop Sync'

Start-Sleep 3
Write-Host "`nInstalled. Log:"
Get-Content "$dir\sync.log" -Tail 8 -ErrorAction SilentlyContinue
Write-Host "`nStop:    Stop-ScheduledTask 'Wooting Desktop Sync'"
Write-Host "Restart: Stop-ScheduledTask 'Wooting Desktop Sync'; Start-ScheduledTask 'Wooting Desktop Sync'"
Write-Host "Remove:  Unregister-ScheduledTask 'Wooting Desktop Sync' -Confirm:`$false"
