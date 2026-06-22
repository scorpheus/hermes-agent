# See scripts/update-galadriel-windows.md for the operational protocol.
param(
    [switch]$Check,
    [switch]$NoPush,
    [switch]$NoInstall,
    [switch]$NoNpm,
    # Open the Windows TUI if the update fails after the Desktop/app has handed off.
    [switch]$FallbackToTui,
    # Relaunch the full Companion stack after a successful Desktop-initiated update.
    [switch]$RelaunchDesktop
)

$ErrorActionPreference = 'Stop'

$Repository = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$HermesCore = Split-Path -Parent $Repository
$ProjectRoot = Split-Path -Parent $HermesCore
$HomeDir = Join-Path $HermesCore 'home'
$DataDir = Join-Path $HermesCore 'data'
$LogDir = Join-Path $DataDir 'logs'
$BackupDir = Join-Path $DataDir 'backups'
$FallbackLog = Join-Path $LogDir 'galadriel-update-fallback.log'
$TuiLauncher = Join-Path $HermesCore 'Start-Hermes-Windows.bat'
$DesktopLauncher = Join-Path $ProjectRoot 'Start-GaladrielCompanion.bat'
$OriginUrl = 'https://github.com/scorpheus/hermes-agent.git'
$UpstreamUrl = 'https://github.com/NousResearch/hermes-agent.git'
$DisabledPushUrl = 'DISABLED'
$RecoveryBundle = $null

function Invoke-Step([string]$Label, [scriptblock]$Body) {
    Write-Host ''
    Write-Host "== $Label ==" -ForegroundColor Cyan
    & $Body
}

function Invoke-Git([Parameter(ValueFromRemainingArguments = $true)][string[]]$GitArgs) {
    & git @GitArgs
    if ($LASTEXITCODE -ne 0) {
        throw "git $($GitArgs -join ' ') failed with exit code $LASTEXITCODE"
    }
}

function Test-GitAncestor([string]$Ancestor, [string]$Descendant) {
    & git merge-base --is-ancestor $Ancestor $Descendant *> $null
    return $LASTEXITCODE -eq 0
}

function Get-GitOutput([Parameter(ValueFromRemainingArguments = $true)][string[]]$GitArgs) {
    $output = & git @GitArgs
    if ($LASTEXITCODE -ne 0) {
        throw "git $($GitArgs -join ' ') failed with exit code $LASTEXITCODE"
    }
    return ($output -join "`n").Trim()
}

function Resolve-PythonExe() {
    $candidates = @(
        (Join-Path $Repository '.venv\Scripts\python.exe'),
        (Join-Path $Repository 'venv\Scripts\python.exe')
    )
    foreach ($candidate in $candidates) {
        if (Test-Path $candidate) { return $candidate }
    }
    throw "Python venv introuvable dans $Repository (.venv ou venv)."
}

function Write-RecoveryLog([string]$Message) {
    try {
        New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
        $line = "{0} {1}" -f (Get-Date -Format 'yyyy-MM-dd HH:mm:ss'), $Message
        Add-Content -Path $FallbackLog -Value $line -Encoding UTF8
    } catch { }
}

function Start-TuiFallback([string]$Reason) {
    if (!$FallbackToTui) { return }
    if (!(Test-Path $TuiLauncher)) {
        Write-Host "ATTENTION: fallback TUI demande mais launcher introuvable: $TuiLauncher" -ForegroundColor Yellow
        Write-RecoveryLog "fallback-tui-missing reason=$Reason launcher=$TuiLauncher"
        return
    }

    Write-Host "ATTENTION: update Galadriel interrompu; ouverture du TUI de secours." -ForegroundColor Yellow
    Write-Host "          Raison: $Reason" -ForegroundColor Yellow
    if ($RecoveryBundle) {
        Write-Host "          Bundle recovery: $RecoveryBundle" -ForegroundColor DarkYellow
    }
    Write-RecoveryLog "fallback-tui reason=$Reason recovery=$RecoveryBundle"

    $command = "& '$TuiLauncher' --continue"
    Start-Process -FilePath 'powershell.exe' -ArgumentList @(
        '-NoExit',
        '-NoProfile',
        '-ExecutionPolicy', 'Bypass',
        '-Command', $command
    ) -WorkingDirectory $HermesCore | Out-Null
}

function Start-DesktopRelaunch {
    if (!$RelaunchDesktop) { return }
    if (!(Test-Path $DesktopLauncher)) {
        Write-Host "ATTENTION: relance Desktop demandee mais launcher introuvable: $DesktopLauncher" -ForegroundColor Yellow
        Write-RecoveryLog "desktop-relaunch-missing launcher=$DesktopLauncher"
        return
    }

    Write-Host ''
    Write-Host "Relance du corps Desktop Galadriel..." -ForegroundColor Cyan
    Write-RecoveryLog "desktop-relaunch launcher=$DesktopLauncher"
    Start-Process -FilePath $DesktopLauncher -WorkingDirectory $ProjectRoot | Out-Null
}

function Save-RecoveryBundle {
    New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $bundle = Join-Path $BackupDir "galadriel-update-$stamp"
    New-Item -ItemType Directory -Force -Path $bundle | Out-Null

    try { (& git rev-parse HEAD 2>&1) | Set-Content -Path (Join-Path $bundle 'HEAD.txt') -Encoding UTF8 } catch { }
    try { (& git status --short --branch 2>&1) | Set-Content -Path (Join-Path $bundle 'status-before.txt') -Encoding UTF8 } catch { }
    try { (& git remote -v 2>&1) | Set-Content -Path (Join-Path $bundle 'remotes-before.txt') -Encoding UTF8 } catch { }
    try { (& git diff --binary --submodule=diff 2>&1) | Set-Content -Path (Join-Path $bundle 'worktree-before.patch') -Encoding UTF8 } catch { }
    try { (& git diff --cached --binary --submodule=diff 2>&1) | Set-Content -Path (Join-Path $bundle 'index-before.patch') -Encoding UTF8 } catch { }
    try { (& git stash list -n 10 2>&1) | Set-Content -Path (Join-Path $bundle 'stash-list-before.txt') -Encoding UTF8 } catch { }

    $script:RecoveryBundle = $bundle
    Write-Host "Recovery bundle: $bundle" -ForegroundColor DarkGray
    return $bundle
}

trap {
    $reason = $_.Exception.Message
    Write-Host ''
    Write-Host "ERREUR update Galadriel: $reason" -ForegroundColor Red
    if ($RecoveryBundle) {
        Write-Host "Recovery bundle: $RecoveryBundle" -ForegroundColor Yellow
    }
    Start-TuiFallback -Reason $reason
    exit 1
}

Set-Location $Repository
if (Test-Path $HomeDir) { $env:HERMES_HOME = $HomeDir }
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'

Invoke-Step 'Verification remotes Galadriel' {
    $origin = (& git remote get-url origin 2>$null) -join ''
    if ($LASTEXITCODE -ne 0) {
        Invoke-Git remote add origin $OriginUrl
    } elseif ($origin -ne $OriginUrl) {
        Invoke-Git remote set-url origin $OriginUrl
    }

    $upstream = (& git remote get-url upstream 2>$null) -join ''
    if ($LASTEXITCODE -ne 0) {
        Invoke-Git remote add upstream $UpstreamUrl
    } elseif ($upstream -ne $UpstreamUrl) {
        Invoke-Git remote set-url upstream $UpstreamUrl
    }

    $upstreamPush = (& git remote get-url --push upstream 2>$null) -join ''
    if ($upstreamPush -ne $DisabledPushUrl) {
        Invoke-Git remote set-url --push upstream $DisabledPushUrl
    }

    git remote -v
}

Invoke-Step 'Fetch origin/upstream main' {
    Invoke-Git fetch upstream main --prune
    Invoke-Git fetch origin main --prune
}

Invoke-Step 'Etat avant update' {
    git status --short --branch
    Write-Host 'HEAD vs upstream/main:' (Get-GitOutput rev-list --left-right --count HEAD...upstream/main)
    Write-Host 'HEAD vs origin/main:  ' (Get-GitOutput rev-list --left-right --count HEAD...origin/main)
}

if ($Check) { exit 0 }

$unmerged = Get-GitOutput diff --name-only --diff-filter=U
if ($unmerged) {
    throw "Merge Git deja en conflit. Resolvez d'abord:`n$unmerged"
}

Save-RecoveryBundle | Out-Null

$stashMade = $false
$stashRef = $null
$stashName = 'galadriel-update-' + (Get-Date -Format 'yyyyMMdd-HHmmss')
$dirty = Get-GitOutput status --porcelain=v1
if ($dirty) {
    Invoke-Step 'Sauvegarde temporaire du working tree' {
        Invoke-Git stash push --include-untracked -m $stashName
        $script:stashMade = $true
        $script:stashRef = Get-GitOutput rev-parse --verify refs/stash
    }
}

Invoke-Step 'Checkout main local' {
    $currentBranch = Get-GitOutput branch --show-current
    if ($currentBranch -ne 'main') {
        Invoke-Git checkout main
    }
}

Invoke-Step 'Synchronisation depuis le fork Scorpheus' {
    if (Test-GitAncestor HEAD origin/main) {
        Invoke-Git merge --ff-only origin/main
    } elseif (-not (Test-GitAncestor origin/main HEAD)) {
        throw 'main local et origin/main ont diverge. Refus de rebaser/reset automatiquement; inspectez git log --graph HEAD origin/main.'
    } else {
        Write-Host 'main local contient deja origin/main.' -ForegroundColor DarkGray
    }
}

$mergedUpstream = $false
Invoke-Step 'Fusion upstream/main dans Galadriel main' {
    if (Test-GitAncestor upstream/main HEAD) {
        Write-Host 'upstream/main deja inclus.' -ForegroundColor DarkGray
        return
    }

    $stamp = Get-Date -Format 'yyyyMMdd-HHmmss'
    $backupBranch = "galadriel/backup-before-upstream-$stamp"
    Invoke-Git branch $backupBranch HEAD
    Write-Host "Backup branch: $backupBranch" -ForegroundColor DarkGray

    & git merge --no-edit upstream/main
    if ($LASTEXITCODE -ne 0) {
        Write-Host ''
        Write-Host 'Conflits de merge upstream:' -ForegroundColor Yellow
        git diff --name-only --diff-filter=U
        throw 'Fusion upstream/main interrompue; resoudre les conflits puis git commit.'
    }
    $script:mergedUpstream = $true
}

if ($stashMade) {
    Invoke-Step 'Restauration du working tree sauvegarde' {
        & git stash pop $stashRef
        if ($LASTEXITCODE -ne 0) {
            Write-Host 'La stash est conservee; resolvez les conflits puis supprimez-la manuellement.' -ForegroundColor Yellow
            throw "git stash pop $stashRef failed"
        }
    }
}

if (-not $NoNpm) {
    Invoke-Step 'Refresh npm workspace' {
        if (Test-Path (Join-Path $Repository 'package-lock.json')) {
            npm ci --no-fund --no-audit --progress=false
        } elseif (Test-Path (Join-Path $Repository 'package.json')) {
            npm install --no-fund --no-audit --progress=false
        }
    }
}

if (-not $NoInstall) {
    Invoke-Step 'Refresh editable Python package' {
        $PythonExe = Resolve-PythonExe
        & $PythonExe -m pip install -e '.[all]'
        if ($LASTEXITCODE -ne 0) { throw 'pip install editable failed' }
    }
}

Invoke-Step 'Verification runtime' {
    $PythonExe = Resolve-PythonExe
    & $PythonExe -m hermes_cli.main --version
    if ($LASTEXITCODE -ne 0) { throw 'hermes --version failed' }
    & $PythonExe -c "import hermes_cli, run_agent; print('imports ok')"
    if ($LASTEXITCODE -ne 0) { throw 'Hermes imports failed' }
}

Invoke-Step 'Etat final Git' {
    git status --short --branch
    Write-Host 'HEAD vs upstream/main:' (Get-GitOutput rev-list --left-right --count HEAD...upstream/main)
    Write-Host 'HEAD vs origin/main:  ' (Get-GitOutput rev-list --left-right --count HEAD...origin/main)
}

if (-not $NoPush) {
    Invoke-Step 'Push vers le fork Scorpheus' {
        if (-not (Test-GitAncestor origin/main HEAD)) {
            throw 'origin/main contient des commits absents du HEAD local; refus de push. Refaites un fetch/merge.'
        }
        Invoke-Git push -u origin main
    }
}

Write-Host ''
if ($mergedUpstream) {
    Write-Host 'Galadriel update complete: upstream/main fusionne et fork Scorpheus a jour.' -ForegroundColor Green
} else {
    Write-Host 'Galadriel update complete: aucun merge upstream necessaire.' -ForegroundColor Green
}
Start-DesktopRelaunch
