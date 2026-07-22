$vbsPath = "C:\Users\bhara\.gemini\antigravity\scratch\smart_hospital_system\silent_start.vbs"
$startupFolder = [System.Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupFolder "AuraCare Hospital Server.lnk"

Write-Host "Startup folder: $startupFolder" -ForegroundColor Cyan

$WshShell = New-Object -ComObject WScript.Shell
$shortcut = $WshShell.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "wscript.exe"
$shortcut.Arguments = "`"$vbsPath`""
$shortcut.WorkingDirectory = "C:\Users\bhara\.gemini\antigravity\scratch\smart_hospital_system"
$shortcut.Description = "AuraCare Smart Hospital Appointment System - Auto Start"
$shortcut.WindowStyle = 7
$shortcut.Save()

Write-Host "SUCCESS! Auto-start shortcut registered in Startup folder." -ForegroundColor Green