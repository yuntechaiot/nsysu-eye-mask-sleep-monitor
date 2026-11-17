# Explicit local demo task only; never modifies production reminder settings.
param(
    [Parameter(Mandatory=$true)][string]$PythonPath,
    [string]$TaskName = 'NSYSU_Local_LINE_Demo_Worker'
)
$ErrorActionPreference = 'Stop'
$projectPath = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$resolvedPython = (Resolve-Path -LiteralPath $PythonPath).Path
$windowlessPython = Join-Path (Split-Path -Parent $resolvedPython) 'pythonw.exe'
if (-not (Test-Path -LiteralPath $windowlessPython)) { throw 'Windowless pythonw.exe is required beside the selected Python; no console task was installed.' }
$workerPath = Join-Path $projectPath 'tools\live_line_demo.py'
if (-not (Test-Path -LiteralPath $workerPath)) { throw 'Local demo worker missing' }
$action = New-ScheduledTaskAction -Execute $windowlessPython -Argument ('"' + $workerPath + '" --worker') -WorkingDirectory $projectPath
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 1)
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Seconds 90) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -Hidden
# No StartWhenAvailable: overdue jobs are handled only inside the business grace.
$principal = New-ScheduledTaskPrincipal -UserId ([System.Security.Principal.WindowsIdentity]::GetCurrent().Name) -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $TaskName -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Description 'Local single-recipient LINE demo only; private config defaults sending off.' -Force | Select-Object TaskName,State
