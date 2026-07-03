# Seeds predefined local demo files into backend/demo-inbox in phases.
# Usage examples:
#   .\scripts\seed-local-demo-files.ps1 -Phase ccd
#   .\scripts\seed-local-demo-files.ps1 -Phase settlement
#   .\scripts\seed-local-demo-files.ps1 -Phase returns
#   .\scripts\seed-local-demo-files.ps1 -Phase all
#   .\scripts\seed-local-demo-files.ps1 -Phase clean
#   .\scripts\seed-local-demo-files.ps1 -Phase reset

[CmdletBinding()]
param(
    [ValidateSet("ccd", "settlement", "returns", "all", "clean", "reset")]
    [string]$Phase = "all",
    [string]$DemoInboxRoot,
    [string]$SampleRoot
)

$ErrorActionPreference = "Stop"

$repoRoot = Split-Path -Parent $PSScriptRoot

if ([string]::IsNullOrWhiteSpace($DemoInboxRoot)) {
    $DemoInboxRoot = Join-Path $repoRoot "backend/demo-inbox"
} elseif (-not [System.IO.Path]::IsPathRooted($DemoInboxRoot)) {
    $DemoInboxRoot = Join-Path $repoRoot $DemoInboxRoot
}

if ([string]::IsNullOrWhiteSpace($SampleRoot)) {
    $SampleRoot = Join-Path $repoRoot "demo-data/local-folder-demo/batch_1100"
} elseif (-not [System.IO.Path]::IsPathRooted($SampleRoot)) {
    $SampleRoot = Join-Path $repoRoot $SampleRoot
}

$targetDirs = @{
    ccd = Join-Path $DemoInboxRoot "ccd"
    settlement = Join-Path $DemoInboxRoot "settlement"
    schemeReject = Join-Path $DemoInboxRoot "scheme-reject"
    returns = Join-Path $DemoInboxRoot "returns"
    processed = Join-Path $DemoInboxRoot "processed"
}

foreach ($dir in $targetDirs.Values) {
    New-Item -ItemType Directory -Path $dir -Force | Out-Null
}

function Copy-SampleFile {
    param(
        [Parameter(Mandatory = $true)]
        [string]$SourcePath,
        [Parameter(Mandatory = $true)]
        [string]$TargetDir
    )

    if (-not (Test-Path $SourcePath)) {
        throw "Missing sample file: $SourcePath"
    }

    Copy-Item -Path $SourcePath -Destination $TargetDir -Force
    Write-Host "Copied $(Split-Path $SourcePath -Leaf) -> $TargetDir"
}

function Copy-CcdFixture {
    Copy-SampleFile -SourcePath (Join-Path $SampleRoot "ccd/batch_1100.ach") -TargetDir $targetDirs.ccd
}

function Copy-SettlementAndSchemeRejectFixtures {
    Copy-SampleFile -SourcePath (Join-Path $SampleRoot "settlement/batch_1100_settlement.dat") -TargetDir $targetDirs.settlement

    Copy-SampleFile -SourcePath (Join-Path $SampleRoot "scheme-reject/batch_1100_reject.json") -TargetDir $targetDirs.schemeReject
}

function Copy-ReturnFixture {
    Copy-SampleFile -SourcePath (Join-Path $SampleRoot "returns/batch_1100_return.ach") -TargetDir $targetDirs.returns
}

function Reset-DemoInbox {
    foreach ($dir in $targetDirs.Values) {
        if (Test-Path $dir) {
            Get-ChildItem -Path $dir -File -Force -ErrorAction SilentlyContinue | Remove-Item -Force
        }
    }
    Write-Host "Reset complete for $DemoInboxRoot"
}

Write-Host "Seeding phase: $Phase"
Write-Host "Sample root : $SampleRoot"
Write-Host "Target root : $DemoInboxRoot"

switch ($Phase) {
    "ccd" {
        Copy-CcdFixture
    }
    "settlement" {
        Copy-SettlementAndSchemeRejectFixtures
    }
    "returns" {
        Copy-ReturnFixture
    }
    "all" {
        Copy-CcdFixture
        Copy-SettlementAndSchemeRejectFixtures
        Copy-ReturnFixture
    }
    "clean" {
        Reset-DemoInbox
    }
    "reset" {
        Reset-DemoInbox
    }
}

Write-Host "Done."
