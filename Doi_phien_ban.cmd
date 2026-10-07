@echo off
setlocal
chcp 65001 >nul
title SoilFirm Pro - Doi phien ban
set "SOILFIRM_SCRIPT=%~f0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -STA -Command "$raw=[IO.File]::ReadAllText($env:SOILFIRM_SCRIPT,[Text.Encoding]::UTF8); $marker=[char]35+' POWERSHELL_SCRIPT'; $parts=$raw.Split([string[]]@($marker),[StringSplitOptions]::None); if($parts.Count -ne 2){throw 'Khong doc duoc noi dung CMD'}; Invoke-Expression $parts[1]"
echo.
pause
exit /b

# POWERSHELL_SCRIPT
$ErrorActionPreference = 'Stop'
try {
    $names = @('app.py', 'splash.py', 'build_app.py')
    $root = Split-Path -Parent $env:SOILFIRM_SCRIPT
    $present = @($names | Where-Object { Test-Path -LiteralPath (Join-Path $root $_) -PathType Leaf })
    if ($present.Count -ne $names.Count) {
        Add-Type -AssemblyName System.Windows.Forms
        $dialog = New-Object System.Windows.Forms.FolderBrowserDialog
        $dialog.Description = 'Chon thu muc chua app.py, splash.py va build_app.py'
        $dialog.ShowNewFolderButton = $false
        if ($dialog.ShowDialog() -ne [System.Windows.Forms.DialogResult]::OK) {
            throw 'Ban chua chon thu muc ma nguon.'
        }
        $root = $dialog.SelectedPath
    }

    $original = @{}
    foreach ($name in $names) {
        $path = Join-Path $root $name
        if (!(Test-Path -LiteralPath $path -PathType Leaf)) { throw ('Khong tim thay ' + $name + ' trong ' + $root) }
        $original[$name] = [System.IO.File]::ReadAllText($path, [System.Text.Encoding]::UTF8)
    }
    $quote = [char]34
    $found = [regex]::Match($original['build_app.py'], '(?m)^APP_VERSION\s*=\s*' + $quote + '([0-9.]+)' + $quote)
    if (!$found.Success) { throw 'Khong tim thay APP_VERSION trong build_app.py.' }
    $old = $found.Groups[1].Value
    if (!$original['app.py'].Contains('CURRENT_VERSION = ' + $quote + $old + $quote)) {
        throw 'Phien ban cua app.py khong khop build_app.py.'
    }
    if (!$original['splash.py'].Contains('text=' + $quote + 'v' + $old + $quote)) {
        throw 'Phien ban cua splash.py khong khop build_app.py.'
    }

    Write-Host ('Thu muc: ' + $root)
    Write-Host ('Phien ban hien tai: ' + $old)
    $new = (Read-Host 'Nhap phien ban moi, vi du 2026.11').Trim()
    if ($new -notmatch '^[0-9]{4}\.[0-9]+(\.[0-9]+)?$') {
        throw 'Phien ban phai co dang 2026.11 hoac 2026.11.1.'
    }
    if ($new -eq $old) {
        Write-Host ('Khong thay doi: phien ban da la ' + $old)
    } else {
        $backup = Join-Path $root ('Sao_luu_phien_ban_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
        [System.IO.Directory]::CreateDirectory($backup) | Out-Null
        foreach ($name in $names) {
            Copy-Item -LiteralPath (Join-Path $root $name) -Destination (Join-Path $backup $name)
        }
        $utf8 = New-Object System.Text.UTF8Encoding($false)
        try {
            foreach ($name in $names) {
                $updated = $original[$name].Replace($old, $new)
                [System.IO.File]::WriteAllText((Join-Path $root $name), $updated, $utf8)
            }
        } catch {
            foreach ($name in $names) {
                Copy-Item -LiteralPath (Join-Path $backup $name) -Destination (Join-Path $root $name) -Force
            }
            throw
        }
        Write-Host ('DA DOI PHIEN BAN: ' + $old + ' -> ' + $new) -ForegroundColor Green
        Write-Host ('Ban sao luu: ' + $backup)
    }
    if (Test-Path -LiteralPath (Join-Path $root 'main.py') -PathType Leaf) {
        $answer = Read-Host 'Dong goi lai EXE va dat ten theo phien ban nay? (Enter = Co, N = Bo qua)'
        if ($answer -notmatch '^[nN]$') {
            $python = Get-Command py -ErrorAction SilentlyContinue
            if ($python) {
                $command = $python.Source
                $arguments = @('-3', 'build_app.py')
            } else {
                $python = Get-Command python -ErrorAction SilentlyContinue
                if (!$python) { throw 'Khong tim thay Python. Hay cai Python hoac tu chay build_app.py.' }
                $command = $python.Source
                $arguments = @('build_app.py')
            }
            Write-Host 'Dang dong goi lai EXE, vui long doi...'
            Push-Location $root
            try {
                & $command @arguments
                if ($LASTEXITCODE -ne 0) { throw 'Dong goi EXE khong thanh cong.' }
            } finally { Pop-Location }
            $exe = Join-Path $root 'dist\SoilFirm_Professional.exe'
            if (!(Test-Path -LiteralPath $exe -PathType Leaf)) { throw 'Khong tim thay EXE sau khi dong goi.' }
            $named = Join-Path $root ('dist\SoilFirm_Professional_v' + $new + '.exe')
            Copy-Item -LiteralPath $exe -Destination $named -Force
            Write-Host ('EXE phien ban moi: ' + $named) -ForegroundColor Green
        }
    } else {
        Write-Host 'Khong co main.py nen chi doi phien ban trong 3 tep nguon.'
    }
} catch {
    Write-Host ('LOI: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}
