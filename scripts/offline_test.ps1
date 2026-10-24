# Offline capability test for NICS Video Studio.
# Disables all active network adapters, runs a full pipeline job (fresh
# analysis, forced recompute, captions, render), then re-enables the
# adapters again — even if the test fails.

$ErrorActionPreference = "Continue"
$logPath = "D:\NICS-VIDEO\logs\offline_test.log"
New-Item -ItemType Directory -Force -Path "D:\NICS-VIDEO\logs" | Out-Null

$adapters = Get-NetAdapter | Where-Object { $_.Status -eq "Up" }
Write-Output "Adapters to disable: $($adapters.Name -join ', ')" | Tee-Object -FilePath $logPath

try {
    foreach ($a in $adapters) {
        Disable-NetAdapter -Name $a.Name -Confirm:$false
    }
    Write-Output "Network disabled. Waiting 3s..." | Tee-Object -FilePath $logPath -Append
    Start-Sleep -Seconds 3

    Write-Output "--- Running pipeline (forced fresh analysis + render) ---" | Tee-Object -FilePath $logPath -Append
    Push-Location "D:\NICS-VIDEO\scripts"
    & "D:\NICS-VIDEO\venv\Scripts\python.exe" run.py `
        --prompt "Offline test run" --style travel --duration 15 --format 9:16 `
        --mode auto --force-analysis --job-id offline_test `
        *>> $logPath
    $exitCode = $LASTEXITCODE
    Pop-Location
    Write-Output "Pipeline exit code: $exitCode" | Tee-Object -FilePath $logPath -Append
}
finally {
    Write-Output "--- Re-enabling network adapters ---" | Tee-Object -FilePath $logPath -Append
    foreach ($a in $adapters) {
        Enable-NetAdapter -Name $a.Name -Confirm:$false
    }
    Write-Output "Network re-enabled." | Tee-Object -FilePath $logPath -Append
}

Write-Output "`nDone. Full log at $logPath"
