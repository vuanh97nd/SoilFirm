$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
try {
    $venvPython = Join-Path $PSScriptRoot '.venv\Scripts\python.exe'
    if (-not (Test-Path $venvPython)) {
        Write-Host 'Tao moi truong Python rieng cho ban chay thu...'
        if (Get-Command py -ErrorAction SilentlyContinue) {
            & py -3 -m venv (Join-Path $PSScriptRoot '.venv')
        } elseif (Get-Command python -ErrorAction SilentlyContinue) {
            & python -m venv (Join-Path $PSScriptRoot '.venv')
        } else { throw 'Cai Python 3.10 tro len, gom tkinter, roi chay lai.' }
        if ($LASTEXITCODE -ne 0) { throw 'Khong tao duoc moi truong Python.' }
    }
    & $venvPython -m pip install -r (Join-Path $PSScriptRoot 'requirements.txt')
    if ($LASTEXITCODE -ne 0) { throw 'Khong cai duoc thu vien. Kiem tra Internet.' }
    $provider = Read-Host 'Chon AI: deepseek hoac openai (Enter = deepseek)'
    if ([string]::IsNullOrWhiteSpace($provider)) { $provider = 'deepseek' }
    $provider = $provider.Trim().ToLowerInvariant()
    if ($provider -notin @('deepseek', 'openai')) { throw 'Chi chon deepseek hoac openai.' }
    $env:GEOTECH_PROVIDER = $provider
    $keyName = if ($provider -eq 'openai') { 'OPENAI_API_KEY' } else { 'DEEPSEEK_API_KEY' }
    if ([string]::IsNullOrWhiteSpace([Environment]::GetEnvironmentVariable($keyName, 'Process'))) {
        $secret = Read-Host "Nhap khoa $provider (an ky tu)" -AsSecureString
        $credential = [System.Net.NetworkCredential]::new('', $secret)
        if ([string]::IsNullOrWhiteSpace($credential.Password)) { throw 'Chua nhap khoa API.' }
        [Environment]::SetEnvironmentVariable($keyName, $credential.Password, 'Process')
    }
    & $venvPython (Join-Path $PSScriptRoot 'demo_tkinter.py')
    if ($LASTEXITCODE -ne 0) { throw 'Giao dien chay thu da dung do loi.' }
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}
