param(
    [ValidateSet('Check', 'Enable', 'Collect', 'Restore')][string]$Mode = 'Check',
    [string]$CardRoot,
    [ValidateSet('pl', 'en')][string]$Language = 'pl',
    [switch]$Menu
)

Set-StrictMode -Version 2
$ErrorActionPreference = 'Stop'
$script:KitRoot = $PSScriptRoot
$script:Fixture = $false
$script:LauncherHash = 'fb43b43310cabb0ae2357fa0a766a63a46d3e5ff711c05464069bd7add976f19'
$script:Applications = @{
    '7d82d50b88e0bfc3f0fe7bc6882843d047128d5504fc10bbdc72664119058390' = 'alpha8'
    'a536942c7cc6caa68c6dae24c2128e9d623562e2e26e7df10fdb51539684e122' = 'alpha9'
}
$script:AlsaHash = 'e7dd65afbb4209ffda6edea998cd0f4116fe166eb859939553ac6840f964f8ed'
$script:OriginalName = 'rockbox.r1.connectivity-original'
$script:StateName = '.connectivity-state.json'
$script:StageName = '.connectivity-stage'
$script:LogName = 'r1-connectivity.log'

function Say([string]$Polish, [string]$English) {
    if ($Language -eq 'pl') { return $Polish }
    return $English
}

function Read-Answer([string]$Polish, [string]$English) {
    Write-Host (Say $Polish $English)
    return Read-Host
}

function Stop-Diagnostics([string]$Polish, [string]$English) {
    $exception = [InvalidOperationException]::new((Say $Polish $English))
    $exception.Data['ConnectivityDiagnosticsLocalized'] = $true
    throw $exception
}

function Get-FailureText([System.Management.Automation.ErrorRecord]$Failure) {
    $exception = $Failure.Exception
    while ($exception) {
        if ($exception.Data.Contains('ConnectivityDiagnosticsLocalized')) { return $exception.Message }
        if (-not $exception.InnerException) { break }
        $exception = $exception.InnerException
    }
    $reason = Say 'Nie udało się wykonać operacji' 'The operation could not be completed'
    if ($exception -is [UnauthorizedAccessException]) {
        $reason = Say 'Brak uprawnień. Sprawdź dostęp do wskazanej karty i katalogu zestawu' 'Access denied. Check access to the specified card and kit directory'
    } elseif ($exception -is [IO.IOException]) {
        $reason = Say 'Błąd odczytu lub zapisu. Sprawdź wskazaną kartę i katalog zestawu' 'Read or write failure. Check the specified card and kit directory'
    }
    return ('{0} ({1}, 0x{2})' -f $reason, $exception.GetType().Name, $exception.HResult.ToString('X8'))
}

function Assert-PlainPath([string]$Path, [switch]$AllowMissing) {
    $absolute = [IO.Path]::GetFullPath($Path)
    if ($absolute.StartsWith('\\') -or $absolute.Substring(2).Contains(':')) {
        Stop-Diagnostics 'Niedozwolona ścieżka' 'Path not allowed'
    }
    $cursor = $absolute
    while ($cursor) {
        $item = Get-Item -LiteralPath $cursor -Force -ErrorAction SilentlyContinue
        if ($item -and ($item.Attributes -band [IO.FileAttributes]::ReparsePoint)) {
            Stop-Diagnostics "Dowiązanie lub punkt połączenia: $cursor" "Reparse point: $cursor"
        }
        if (-not $item -and -not $AllowMissing) { Stop-Diagnostics "Brak: $cursor" "Missing: $cursor" }
        $parent = [IO.Path]::GetDirectoryName($cursor.TrimEnd('\'))
        if (-not $parent -or $parent -eq $cursor) { break }
        $cursor = $parent
    }
    return $absolute
}

function Get-Digest([string]$Path, [long]$Maximum = 67108864) {
    $null = Assert-PlainPath $Path
    $stream = [IO.File]::Open($Path, 'Open', 'Read', 'Read')
    $algorithm = [Security.Cryptography.SHA256]::Create()
    try {
        if ($stream.Length -gt $Maximum) { Stop-Diagnostics "Plik za duży: $Path" "File too large: $Path" }
        return ([BitConverter]::ToString($algorithm.ComputeHash($stream))).Replace('-', '').ToLowerInvariant()
    } finally {
        $algorithm.Dispose()
        $stream.Dispose()
    }
}

function Read-SmallText([string]$Path, [long]$Maximum = 16384) {
    $null = Assert-PlainPath $Path
    $stream = [IO.File]::Open($Path, 'Open', 'Read', 'Read')
    try {
        if ($stream.Length -gt $Maximum) { Stop-Diagnostics "Plik za duży: $Path" "File too large: $Path" }
        $reader = New-Object IO.StreamReader($stream, [Text.Encoding]::UTF8)
        try { return $reader.ReadToEnd() } finally { $reader.Dispose() }
    } finally { $stream.Dispose() }
}

function Read-BoundedBytes([string]$Path, [int]$Maximum) {
    $null = Assert-PlainPath $Path
    $stream = [IO.File]::Open($Path, 'Open', 'Read', 'Read')
    try {
        if ($stream.Length -gt $Maximum) { Stop-Diagnostics 'Plik za duży' 'File too large' }
        $buffer = New-Object byte[] ([int]$stream.Length)
        $offset = 0
        while ($offset -lt $buffer.Length) {
            $received = $stream.Read($buffer, $offset, $buffer.Length - $offset)
            if ($received -eq 0) { Stop-Diagnostics 'Niepełny odczyt' 'Incomplete read' }
            $offset += $received
        }
        return ,$buffer
    } finally { $stream.Dispose() }
}

function Initialize-Policy {
    $null = Assert-PlainPath $script:KitRoot
    $fixtureRoot = $env:R1_CONNECTIVITY_TEST_FIXTURE
    if ($fixtureRoot) {
        $centralDrive = 'D:'
        if (-not [IO.Directory]::Exists('D:\')) { $centralDrive = 'C:' }
        $prefix = $centralDrive + '\work\Workspace\rockbox\r1-empty-radio-20261017\radio-diagnostics\tests\'
        if (-not $fixtureRoot.StartsWith($prefix, [StringComparison]::OrdinalIgnoreCase) -or
            $fixtureRoot.Substring($prefix.Length) -notmatch '^run-[a-f0-9]{32}\\[a-zA-Z0-9_]+$' -or
            ($script:KitRoot -cne (Join-Path $fixtureRoot 'kit') -and
             $script:KitRoot -cne (Join-Path $fixtureRoot 'kit-Zażółć gęślą jaźń'))) {
            Stop-Diagnostics 'Nieprawidłowa izolacja testu' 'Invalid isolated test fixture'
        }
        $null = Assert-PlainPath $fixtureRoot
        if ((Read-SmallText (Join-Path $fixtureRoot 'fixture.txt') 128) -cne 'R1_CONNECTIVITY_ISOLATED_FIXTURE_V1') {
            Stop-Diagnostics 'Nieprawidłowy znacznik testu' 'Invalid fixture marker'
        }
        if ($CardRoot -cne (Join-Path $fixtureRoot 'card') -and
            $CardRoot -cne (Join-Path $fixtureRoot 'card-Łódź')) {
            Stop-Diagnostics 'Nieprawidłowa karta testowa' 'Invalid fixture card'
        }
        $script:Fixture = $true
    }
    if ((Get-Digest (Join-Path $script:KitRoot 'launcher.sh')) -ne $script:LauncherHash) {
        Stop-Diagnostics 'Niezgodny skrypt uruchamiający zestawu' 'Kit launcher integrity failure'
    }
}

function Get-CardDirectory {
    if (-not $CardRoot) { $script:CardRoot = Read-Answer 'Podaj katalog główny podłączonej karty, np. F:\' 'Enter connected card drive root, for example F:\' }
    if (-not $script:Fixture) {
        if ($CardRoot -notmatch '^[a-zA-Z]:\\$' -or $CardRoot.TrimEnd('\') -ieq $env:SystemDrive) {
            Stop-Diagnostics 'Wymagany jawny katalog główny karty' 'An explicit card drive root is required'
        }
        $drive = New-Object IO.DriveInfo($CardRoot)
        if (-not $drive.IsReady -or $drive.DriveType -ne [IO.DriveType]::Removable) {
            Stop-Diagnostics 'Wymagana gotowa karta wymienna' 'A ready removable card is required'
        }
    }
    $root = Assert-PlainPath $CardRoot
    if ($script:KitRoot.StartsWith($root.TrimEnd('\') + '\', [StringComparison]::OrdinalIgnoreCase)) {
        Stop-Diagnostics 'Zestaw musi być poza kartą' 'Kit must be outside the card'
    }
    $directory = Assert-PlainPath (Join-Path $root '.rockbox')
    if (-not [IO.Directory]::Exists($directory) -or
        (Read-SmallText (Join-Path $directory 'rockbox-info.txt')) -notmatch '(?m)^Target: hibyr1\r?$') {
        Stop-Diagnostics 'Nie jest to instalacja HiBy R1' 'Not a HiBy R1 installation'
    }
    foreach ($name in @('rockbox.r1', $script:OriginalName, $script:StateName, $script:StageName, $script:LogName)) {
        $null = Assert-PlainPath (Join-Path $directory $name) -AllowMissing
    }
    return $directory
}

function Get-Runtime([string]$Directory) {
    $result = @{}
    foreach ($item in Get-ChildItem -LiteralPath $Directory -Force) {
        if ($item.Name -match '\.so($|\.)') {
            if ($item.PSIsContainer) { Stop-Diagnostics 'Katalog zamiast biblioteki' 'Library is a directory' }
            $result[$item.Name] = Get-Digest $item.FullName
        }
    }
    if (-not $result.ContainsKey('libasound.so.2') -or $result['libasound.so.2'] -ne $script:AlsaHash) {
        Stop-Diagnostics 'Niezgodna biblioteka ALSA' 'Unrecognized ALSA runtime'
    }
    return $result
}

function Assert-Runtime([string]$Directory, $Expected) {
    $actual = Get-Runtime $Directory
    $properties = @($Expected.PSObject.Properties)
    if ($actual.Count -ne $properties.Count) { Stop-Diagnostics 'Zmieniony zestaw bibliotek' 'Runtime file set changed' }
    foreach ($property in $properties) {
        if (-not $actual.ContainsKey($property.Name) -or $actual[$property.Name] -cne $property.Value) {
            Stop-Diagnostics 'Zmieniona suma kontrolna biblioteki' 'Runtime hash changed'
        }
    }
}

function Assert-NoAudio([string]$Directory) {
    $application = Join-Path $Directory 'rockbox.r1'
    if ((Test-Path -LiteralPath $application) -and
        (Get-Digest $application) -eq '772f9082f733696a9b606ec7ecd65431f40f5356e2652f0730d60bb64d5ea5f1') {
        Stop-Diagnostics 'Aktywny skrypt diagnostyki audio: najpierw wykonaj Restore dopasowanym zestawem audio alpha8' 'Active audio launcher: first use Restore in the matched alpha8 audio kit'
    }
    foreach ($item in Get-ChildItem -LiteralPath $Directory -Force) {
        if ($item.Name -like 'rockbox.r1.audio-*' -or $item.Name -like 'r1-audio-*') {
            Stop-Diagnostics 'Wykryto diagnostykę audio. Najpierw wykonaj Restore dopasowanym zestawem audio alpha8.' 'Audio diagnostics detected. Run Restore with the matched alpha8 audio kit first.'
        }
    }
}

function Write-NewFile([string]$Path, [byte[]]$Bytes) {
    $null = Assert-PlainPath $Path -AllowMissing
    $stream = [IO.File]::Open($Path, 'CreateNew', 'Write', 'None')
    try {
        $stream.Write($Bytes, 0, $Bytes.Length)
        $stream.Flush($true)
    } catch {
        $stream.Dispose()
        Remove-Item -LiteralPath $Path -ErrorAction Stop
        throw
    } finally { $stream.Dispose() }
}

function Move-CheckedItem([string]$Source, [string]$Destination, [string]$Digest) {
    if ((Get-Digest $Source) -cne $Digest) { Stop-Diagnostics 'Zmieniona suma kontrolna pliku źródłowego' 'Source hash changed' }
    $null = Assert-PlainPath $Destination -AllowMissing
    if (Test-Path -LiteralPath $Destination) { Stop-Diagnostics "Nie nadpisuję: $Destination" "Refusing overwrite: $Destination" }
    [IO.File]::Move($Source, $Destination)
    if ((Test-Path -LiteralPath $Source) -or (Get-Digest $Destination) -cne $Digest) {
        Stop-Diagnostics 'Błąd integralności przeniesienia' 'Move integrity failure'
    }
}

function Move-JournalItem($Journal, [string]$Source, [string]$Destination, [string]$Digest) {
    $null = $Journal.Add(@($Source, $Destination, $Digest))
    Move-CheckedItem $Source $Destination $Digest
}

function New-ReportDirectory {
    $reports = Join-Path $script:KitRoot 'Reports'
    $null = Assert-PlainPath $reports -AllowMissing
    if (-not (Test-Path -LiteralPath $reports)) { $null = New-Item -ItemType Directory -Path $reports }
    $destination = Join-Path $reports ([DateTime]::UtcNow.ToString('yyyyMMddTHHmmssfffffffZ') + '-' + [Guid]::NewGuid().ToString('N'))
    $null = New-Item -ItemType Directory -Path $destination
    return $destination
}

function Save-Report([string]$Destination, $Report) {
    Write-NewFile (Join-Path $Destination 'report.json') ([Text.Encoding]::UTF8.GetBytes(($Report | ConvertTo-Json -Depth 8)))
}

function Check-Card([string]$Directory, [bool]$Collect) {
    $report = [ordered]@{ schema = 1; mode = $Mode; card = $Directory; files = @{}; runtime = @{}; audio_diagnostics = $false; warnings = @() }
    foreach ($item in Get-ChildItem -LiteralPath $Directory -Force) {
        if ($item.Name -like 'rockbox.r1.audio-*' -or $item.Name -like 'r1-audio-*') { $report.audio_diagnostics = $true }
    }
    foreach ($name in @('rockbox.r1', 'rockbox.r1.audio-original', $script:OriginalName, $script:StateName, $script:StageName)) {
        $path = Join-Path $Directory $name
        if (Test-Path -LiteralPath $path) { $report.files[$name] = Get-Digest $path }
    }
    if ($report.files['rockbox.r1'] -eq '772f9082f733696a9b606ec7ecd65431f40f5356e2652f0730d60bb64d5ea5f1') {
        $report.audio_diagnostics = $true
    }
    $report['recognized_applications'] = @{}
    foreach ($name in @('rockbox.r1', 'rockbox.r1.audio-original', $script:OriginalName)) {
        if ($report.files.ContainsKey($name) -and $script:Applications.ContainsKey([string]$report.files[$name])) {
            $report.recognized_applications[$name] = $script:Applications[[string]$report.files[$name]]
        }
    }
    try { $report.runtime = Get-Runtime $Directory } catch { $report.warnings += Get-FailureText $_ }
    if ($report.audio_diagnostics) {
        $report.warnings += Say 'Najpierw wykonaj Restore dopasowanym zestawem audio alpha8' 'First use Restore in the matched alpha8 audio kit'
    }
    $destination = New-ReportDirectory
    $path = Join-Path $Directory $script:LogName
    if (Test-Path -LiteralPath $path) {
        $checksum = Get-Digest $path 65536
        $report.files[$script:LogName] = $checksum
        if ($Collect) {
            Write-Host (Say 'Kopiuję tylko ograniczony log diagnostyczny do Reports; kopia pozostanie po zadaniu.' 'Copying only the bounded diagnostic log to Reports; this copy remains after collection.')
            $bytes = Read-BoundedBytes $path 65536
            $target = Join-Path $destination $script:LogName
            Write-NewFile $target $bytes
            if ((Get-Digest $target 65536) -ne $checksum -or (Get-Digest $path 65536) -ne $checksum) {
                Stop-Diagnostics 'Log zmienił się podczas zbierania' 'Log changed during collection'
            }
        }
    }
    Save-Report $destination $report
    foreach ($warning in $report.warnings) { Write-Host $warning }
    Write-Host $destination
}

function Enable-Card([string]$Directory) {
    Assert-NoAudio $Directory
    $application = Join-Path $Directory 'rockbox.r1'
    $checksum = Get-Digest $application
    if (-not $script:Applications.ContainsKey($checksum)) { Stop-Diagnostics 'Nieznany oryginalny program' 'Unrecognized original application' }
    $runtime = Get-Runtime $Directory
    foreach ($name in @($script:OriginalName, $script:StateName, $script:StageName, $script:LogName)) {
        if (Test-Path -LiteralPath (Join-Path $Directory $name)) { Stop-Diagnostics "Istnieje plik: $name" "Existing file: $name" }
    }
    $state = [ordered]@{ schema = 1; application = $checksum; release = $script:Applications[$checksum]; launcher = $script:LauncherHash; runtime = $runtime }
    $statePath = Join-Path $Directory $script:StateName
    $stagePath = Join-Path $Directory $script:StageName
    $original = Join-Path $Directory $script:OriginalName
    $stateBytes = [Text.Encoding]::UTF8.GetBytes(($state | ConvertTo-Json -Depth 6))
    $stateHash = ''
    $createdState = $false
    $createdStage = $false
    try {
        Write-NewFile $stagePath ([IO.File]::ReadAllBytes((Join-Path $script:KitRoot 'launcher.sh')))
        $createdStage = $true
        if ((Get-Digest $stagePath) -ne $script:LauncherHash) { Stop-Diagnostics 'Błąd zapisu skryptu uruchamiającego' 'Launcher write failure' }
        Write-NewFile $statePath $stateBytes
        $createdState = $true
        $stateHash = Get-Digest $statePath
        Assert-Runtime $Directory ($state | ConvertTo-Json -Depth 6 | ConvertFrom-Json).runtime
        Move-CheckedItem $application $original $checksum
        Move-CheckedItem $stagePath $application $script:LauncherHash
        Assert-Runtime $Directory ($state | ConvertTo-Json -Depth 6 | ConvertFrom-Json).runtime
    } catch {
        $failure = $_
        if ((Test-Path -LiteralPath $original) -and (Test-Path -LiteralPath $application) -and
            (Get-Digest $application) -eq $script:LauncherHash -and -not (Test-Path -LiteralPath $stagePath)) {
            Move-CheckedItem $application $stagePath $script:LauncherHash
        }
        if ((Test-Path -LiteralPath $original) -and -not (Test-Path -LiteralPath $application)) {
            Move-CheckedItem $original $application $checksum
        }
        if ($createdState -and $stateHash -and (Get-Digest $statePath) -eq $stateHash) { Remove-Item -LiteralPath $statePath }
        if ($createdStage -and (Test-Path -LiteralPath $stagePath) -and (Get-Digest $stagePath) -eq $script:LauncherHash) { Remove-Item -LiteralPath $stagePath }
        throw $failure
    }
    Write-Host (Say 'Gotowe. Oryginał przeniesiono na tej samej karcie. Uruchom R1 raz, wyłącz go, potem Collect i Restore.' 'Ready. Original moved on the same card. Boot R1 once, shut it down, then Collect and Restore.')
}

function Restore-Card([string]$Directory) {
    Assert-NoAudio $Directory
    $statePath = Join-Path $Directory $script:StateName
    $state = Read-SmallText $statePath | ConvertFrom-Json
    if ($state.schema -ne 1 -or -not $script:Applications.ContainsKey([string]$state.application) -or
        $state.launcher -cne $script:LauncherHash -or $state.release -cne $script:Applications[[string]$state.application]) {
        Stop-Diagnostics 'Nieznany stan diagnostyki' 'Unrecognized diagnostic state'
    }
    Assert-Runtime $Directory $state.runtime
    $application = Join-Path $Directory 'rockbox.r1'
    $original = Join-Path $Directory $script:OriginalName
    $stage = Join-Path $Directory $script:StageName
    $hasOriginal = Test-Path -LiteralPath $original
    $hasApplication = Test-Path -LiteralPath $application
    $hasStage = Test-Path -LiteralPath $stage
    $moves = New-Object Collections.ArrayList
    if ($hasOriginal) {
        if ((Get-Digest $original) -cne $state.application -or ($hasApplication -and $hasStage)) {
            Stop-Diagnostics 'Niezgodny oryginał lub etap' 'Original or stage mismatch'
        }
        if ($hasApplication -and (Get-Digest $application) -cne $script:LauncherHash) { Stop-Diagnostics 'Nieznany aktualny program' 'Unknown current application' }
        if (-not $hasApplication -and -not $hasStage) { Stop-Diagnostics 'Brak skryptu uruchamiającego diagnostykę' 'Missing diagnostic launcher' }
    } elseif (-not $hasApplication -or (Get-Digest $application) -cne $state.application -or -not $hasStage) {
        Stop-Diagnostics 'Niekompletny stan przywracania' 'Incomplete restore state'
    }
    if ($hasStage -and (Get-Digest $stage) -cne $script:LauncherHash) { Stop-Diagnostics 'Nieznany etap' 'Unknown staged launcher' }
    $log = Join-Path $Directory $script:LogName
    $logHash = ''
    if (Test-Path -LiteralPath $log) { $logHash = Get-Digest $log 65536 }
    $stateHash = Get-Digest $statePath
    $destination = New-ReportDirectory
    try {
        if ($hasOriginal -and $hasApplication) {
            $saved = Join-Path $destination 'launcher.sh'
            Move-JournalItem $moves $application $saved $script:LauncherHash
        }
        if ($hasStage) {
            $saved = Join-Path $destination 'launcher.sh'
            Move-JournalItem $moves $stage $saved $script:LauncherHash
        }
        if ($hasOriginal) {
            Move-JournalItem $moves $original $application $state.application
        }
        if ($logHash) {
            $saved = Join-Path $destination $script:LogName
            Move-JournalItem $moves $log $saved $logHash
        }
        $saved = Join-Path $destination $script:StateName
        Move-JournalItem $moves $statePath $saved $stateHash
        Assert-Runtime $Directory $state.runtime
        if ((Get-Digest $application) -cne $state.application) { Stop-Diagnostics 'Błąd integralności przywrócenia' 'Restore integrity failure' }
        Save-Report $destination ([ordered]@{ schema = 1; mode = 'Restore'; application = $state.application; runtime = $state.runtime; log = $logHash })
    } catch {
        $failure = $_
        for ($index = $moves.Count - 1; $index -ge 0; $index--) {
            $move = $moves[$index]
            if ((Test-Path -LiteralPath $move[1]) -and -not (Test-Path -LiteralPath $move[0])) {
                Move-CheckedItem $move[1] $move[0] $move[2]
            } elseif (-not (Test-Path -LiteralPath $move[0]) -or (Test-Path -LiteralPath $move[1])) {
                Stop-Diagnostics 'Wycofanie wymaga analizy zachowanych plików' 'Rollback requires review of preserved files'
            }
        }
        throw $failure
    }
    Write-Host (Say 'Przywrócono oryginał. Diagnostyka przeniesiona do:' 'Original restored. Diagnostics moved to:')
    Write-Host $destination
}

function Invoke-ConnectivityDiagnostics {
    Initialize-Policy
    if ($Menu) {
        Write-Host (Say '1 Sprawdź (domyślnie); 2 Włącz; 3 Zbierz log; 4 Przywróć; 0 Wyjdź' '1 Check (default); 2 Enable; 3 Collect log; 4 Restore; 0 Exit')
        $choice = Read-Answer 'Numer i Enter; sam Enter = Sprawdź' 'Number and Enter; Enter alone = Check'
        switch ($choice) {
            '' { $script:Mode = 'Check' }
            '1' { $script:Mode = 'Check' }
            '2' { $script:Mode = 'Enable' }
            '3' { $script:Mode = 'Collect' }
            '4' { $script:Mode = 'Restore' }
            '0' { return }
            default { Stop-Diagnostics 'Nieznany wybór' 'Unknown selection' }
        }
    }
    $directory = Get-CardDirectory
    if ($Mode -in @('Enable', 'Restore')) {
        Write-Host (Say 'R1 musi być wyłączony, karta w czytniku. Ustawienia i profile pozostaną bez zmian.' 'R1 must be off and its card in the reader. Settings and profiles remain unchanged.')
        $answer = Read-Answer 'Wpisz dokładnie TAK, aby zatwierdzić' 'Type exactly YES to confirm'
        if (($Language -eq 'pl' -and $answer -cne 'TAK') -or ($Language -eq 'en' -and $answer -cne 'YES')) {
            Stop-Diagnostics 'Anulowano bez zmian' 'Cancelled without changes'
        }
    }
    switch ($Mode) {
        'Check' { Check-Card $directory $false }
        'Enable' { Enable-Card $directory }
        'Collect' { Check-Card $directory $true }
        'Restore' { Restore-Card $directory }
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    try { Invoke-ConnectivityDiagnostics } catch { [Console]::Error.WriteLine((Get-FailureText $_)); exit 1 }
}
