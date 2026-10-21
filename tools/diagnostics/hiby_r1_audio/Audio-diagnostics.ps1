param(
    [ValidateSet('Check', 'Enable', 'Collect', 'Restore')][string]$Mode = 'Check',
    [string]$CardRoot
)

$ErrorActionPreference = 'Stop'
$script:KitRoot = $PSScriptRoot

function Assert-RegularPath([string]$Path) {
    $item = Get-Item -LiteralPath $Path -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        throw "Dowiązanie jest niedozwolone / Linked path is not allowed: $Path"
    }
    return $item.FullName
}

function Get-Digest([string]$Path) {
    $null = Assert-RegularPath $Path
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Get-KitManifest([string]$Directory) {
    $manifest = Get-Content -LiteralPath (Join-Path $Directory 'manifest.json') -Raw -Encoding UTF8 | ConvertFrom-Json
    foreach ($entry in $manifest.files.PSObject.Properties) {
        if ($entry.Name -match '[\\/]' -or $entry.Name -eq '..' -or
            (Get-Digest (Join-Path $Directory $entry.Name)) -ne $entry.Value) {
            throw 'Uszkodzona paczka diagnostyczna / Diagnostic kit integrity failure'
        }
    }
    return $manifest
}

function Get-RockboxDirectory([string]$Root) {
    $null = Assert-RegularPath $Root
    $directory = Assert-RegularPath (Join-Path $Root '.rockbox')
    $info = Join-Path $directory 'rockbox-info.txt'
    $null = Assert-RegularPath $info
    if (-not ((Get-Content -LiteralPath $info -Encoding UTF8) -match '^Target: hibyr1$')) {
        throw 'To nie jest paczka R1 / This is not a HiBy R1 installation'
    }
    return $directory
}

function Assert-PlayerFiles([string]$Directory, $Manifest, [bool]$Diagnostic) {
    $application = Join-Path $Directory 'rockbox.r1'
    if ($Diagnostic) {
        if ((Get-Digest $application) -ne $Manifest.files.'launcher.sh' -or
            (Get-Digest (Join-Path $Directory 'r1-audio-trace.so')) -ne $Manifest.files.'r1-audio-trace.so') {
            throw 'Nieznana diagnostyka; nic nie zmieniono / Unknown diagnostic files; nothing changed'
        }
        $application = Join-Path $Directory 'rockbox.r1.audio-original'
    }
    if ((Get-Digest $application) -ne $Manifest.application_sha256 -or
        (Get-Digest (Join-Path $Directory 'libasound.so.2')) -ne $Manifest.alsa_sha256) {
        throw 'Inny lub niekompletny build R1; nic nie zmieniono / Different or incomplete R1 build; nothing changed'
    }
}

function Enable-AudioDiagnostics([string]$Directory, [string]$Kit, $Manifest) {
    Assert-PlayerFiles $Directory $Manifest $false
    foreach ($name in @('rockbox.r1.audio-original', 'rockbox.r1.audio-new', 'r1-audio-trace.so',
                        'r1-audio-diagnostic.log', 'r1-audio-launcher.log')) {
        if (Test-Path -LiteralPath (Join-Path $Directory $name)) {
            throw "Istnieje plik; nie nadpisuję / File exists; refusing overwrite: $name"
        }
    }
    $application = Join-Path $Directory 'rockbox.r1'
    $backup = Join-Path $Directory 'rockbox.r1.audio-original'
    $staged = Join-Path $Directory 'rockbox.r1.audio-new'
    Copy-Item -LiteralPath (Join-Path $Kit 'r1-audio-trace.so') -Destination (Join-Path $Directory 'r1-audio-trace.so')
    Copy-Item -LiteralPath (Join-Path $Kit 'launcher.sh') -Destination $staged
    if ((Get-Digest $staged) -ne $Manifest.files.'launcher.sh' -or
        (Get-Digest (Join-Path $Directory 'r1-audio-trace.so')) -ne $Manifest.files.'r1-audio-trace.so') {
        throw 'Błąd kopiowania; oryginalny program pozostał / Copy failure; original application retained'
    }
    Move-Item -LiteralPath $application -Destination $backup
    try {
        Move-Item -LiteralPath $staged -Destination $application
        Assert-PlayerFiles $Directory $Manifest $true
    } catch {
        if ((Test-Path -LiteralPath $application) -and
            (Get-Digest $application) -eq $Manifest.files.'launcher.sh' -and
            -not (Test-Path -LiteralPath $staged)) {
            Move-Item -LiteralPath $application -Destination $staged
        }
        if (-not (Test-Path -LiteralPath $application)) {
            Move-Item -LiteralPath $backup -Destination $application
        }
        throw
    }
}

function Save-CardReport([string]$Directory, [string]$Kit, $Manifest, [bool]$Collect) {
    $destination = Join-Path $Kit ('Reports\' + (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssfffffffZ'))
    $null = New-Item -ItemType Directory -Path $destination
    $report = [ordered]@{ target = 'hibyr1'; card = $Directory; files = @{}; settings = @{}; logs = @{} }
    foreach ($name in @('rockbox.r1', 'rockbox.r1.audio-original', 'libasound.so.2', 'r1-audio-trace.so')) {
        $path = Join-Path $Directory $name
        if (Test-Path -LiteralPath $path) { $report.files[$name] = Get-Digest $path }
    }
    $report.application_matches = $report.files['rockbox.r1'] -eq $Manifest.application_sha256
    $report.alsa_matches = $report.files['libasound.so.2'] -eq $Manifest.alsa_sha256
    foreach ($name in @('config.cfg', 'config.cfg.new', '.resume.cfg', '.resume.cfg.new')) {
        $path = Join-Path $Directory $name
        if (Test-Path -LiteralPath $path) {
            $null = Assert-RegularPath $path
            $report.settings[$name] = @([IO.File]::ReadAllLines($path, [Text.Encoding]::UTF8) |
                Where-Object { $_ -match '^(tts enabled|tts volume|tts language|volume|lang|talk menu):' })
        }
    }
    foreach ($name in @('r1-audio-diagnostic.log', 'r1-audio-launcher.log')) {
        $path = Join-Path $Directory $name
        if (Test-Path -LiteralPath $path) {
            $checksum = Get-Digest $path
            $report.logs[$name] = $checksum
            if ($Collect) {
                Write-Host "Kopia logu do raportu / Copying diagnostic log: $path -> $destination"
                Copy-Item -LiteralPath $path -Destination (Join-Path $destination $name)
                if ((Get-Digest (Join-Path $destination $name)) -ne $checksum) {
                    throw 'Log zmienił się podczas kopiowania / Diagnostic log changed during collection'
                }
            }
        }
    }
    $report | ConvertTo-Json -Depth 6 | Set-Content -LiteralPath (Join-Path $destination 'report.json') -Encoding UTF8
    return $destination
}

function Restore-AudioDiagnostics([string]$Directory, [string]$Kit, $Manifest) {
    Assert-PlayerFiles $Directory $Manifest $true
    $destination = Save-CardReport $Directory $Kit $Manifest $false
    $application = Join-Path $Directory 'rockbox.r1'
    $savedLauncher = Join-Path $destination 'launcher.sh'
    Move-Item -LiteralPath $application -Destination $savedLauncher
    try {
        Move-Item -LiteralPath (Join-Path $Directory 'rockbox.r1.audio-original') -Destination $application
    } catch {
        if (-not (Test-Path -LiteralPath $application)) {
            Move-Item -LiteralPath $savedLauncher -Destination $application
        }
        throw
    }
    if ((Get-Digest (Join-Path $Directory 'rockbox.r1')) -ne $Manifest.application_sha256) {
        throw 'Błąd odtworzenia programu / Application restore integrity failure'
    }
    foreach ($name in @('r1-audio-trace.so', 'r1-audio-diagnostic.log', 'r1-audio-launcher.log')) {
        $path = Join-Path $Directory $name
        if (Test-Path -LiteralPath $path) {
            $checksum = Get-Digest $path
            Move-Item -LiteralPath $path -Destination (Join-Path $destination $name)
            if ((Get-Digest (Join-Path $destination $name)) -ne $checksum) {
                throw 'Błąd zachowania diagnostyki / Diagnostic preservation failure'
            }
        }
    }
    return $destination
}

function Invoke-AudioDiagnostics {
    if (-not $CardRoot) { $CardRoot = Read-Host 'Litera karty w czytniku, np. E:\ / Card root, e.g. E:\' }
    $root = [IO.Path]::GetFullPath($CardRoot)
    if ($root -ne [IO.Path]::GetPathRoot($root) -or $root.StartsWith('\\') -or
        $root.TrimEnd('\') -eq $env:SystemDrive) {
        throw 'Wymagany katalog główny karty, nie dysk systemowy / A card drive root is required, not the system drive'
    }
    $manifest = Get-KitManifest $script:KitRoot
    $directory = Get-RockboxDirectory $root
    if ($Mode -eq 'Enable' -or $Mode -eq 'Restore') {
        $answer = Read-Host 'R1 musi być wyłączony, karta w czytniku. Wpisz TAK / R1 must be off, card in reader. Type YES'
        if ($answer -notin @('TAK', 'YES')) { throw 'Anulowano bez zmian / Cancelled without changes' }
    }
    switch ($Mode) {
        'Enable' {
            Write-Host 'Oryginalny program zostanie przeniesiony bez kopii; ustawienia bez zmian / Moving original application without copying; settings unchanged'
            Enable-AudioDiagnostics $directory $script:KitRoot $manifest
            Write-Host 'Diagnostyka gotowa. Uruchom R1, po próbie wyłącz i zbierz logi / Ready. Boot R1, then shut down and collect logs'
        }
        'Restore' { Write-Host (Restore-AudioDiagnostics $directory $script:KitRoot $manifest) }
        'Collect' { Write-Host (Save-CardReport $directory $script:KitRoot $manifest $true) }
        'Check' { Write-Host (Save-CardReport $directory $script:KitRoot $manifest $false) }
    }
}

if ($MyInvocation.InvocationName -ne '.') { Invoke-AudioDiagnostics }
