<#
.SYNOPSIS
    Renders every Markdown file under docs/deliverables/ to PDF for
    Leho submission.

.DESCRIPTION
    Walks docs/deliverables/ recursively and converts each *.md to
    a side-by-side *.pdf using pandoc + xelatex. Honours per-file
    YAML front-matter (geometry, mainfont, fontsize) so A4 +
    A3 + standard pages render correctly without per-file flags.

    Surfaces clear, actionable errors when pandoc or a LaTeX
    engine is missing, and prints a tidy summary at the end.

.PARAMETER Source
    Root folder to scan. Defaults to docs/deliverables/ relative
    to the repo root (resolved from the script's location).

.PARAMETER Engine
    PDF engine for pandoc. Default: xelatex. Override with lualatex
    if you have Unicode-heavy content.

.PARAMETER WarnOnTeamPlaceholders
    If set, the script greps each .md for `<!-- TEAM:` markers and
    prints a warning so you don't ship a deliverable with blanks.
    On by default.

.EXAMPLE
    pwsh scripts/build-deliverables.ps1
    Render every deliverable to PDF.

.EXAMPLE
    pwsh scripts/build-deliverables.ps1 -Source docs/deliverables/meeting-reports
    Only render the meeting reports.

.NOTES
    Prerequisites:
      - pandoc on PATH (https://pandoc.org/installing.html)
      - A LaTeX engine on PATH. On Windows: MiKTeX or TeX Live.
        MiKTeX installs xelatex by default and auto-installs missing
        packages on first run.

    On a clean Windows machine you can install both via winget:
      winget install JohnMacFarlane.Pandoc
      winget install MiKTeX.MiKTeX
#>

[CmdletBinding()]
param (
    [string]$Source,
    [string]$Engine = 'xelatex',
    [switch]$WarnOnTeamPlaceholders = $true,
    # Scan for unfilled markers only — no pandoc/LaTeX needed. For CI / pre-submit.
    [switch]$CheckOnly,
    # Exit non-zero if any unfilled marker is found. Pair with -CheckOnly in CI so a
    # deliverable with blank <!-- TEAM -->, [TODO] or TBD markers can't be shipped
    # (audit IMP-DOC-12).
    [switch]$Strict
)

$ErrorActionPreference = 'Stop'

# Every unfilled-marker form, not just `TEAM:` with a colon. The old check matched
# only `TEAM:` and missed bare `<!-- TEAM -->` (the majority), `[TODO]` cells, and
# `TBD` — under-reporting blanks ~10x (audit IMP-DOC-12).
$MarkerPattern = '<!--\s*TEAM|\[TODO\]|\bTBD\b'
$totalPlaceholders = 0

# Resolve the deliverables source relative to the script location
# so the script works regardless of the caller's cwd.
$repoRoot = Split-Path -Parent (Split-Path -Parent $PSCommandPath)
if (-not $Source) {
    $Source = Join-Path $repoRoot 'docs\deliverables'
}

if (-not (Test-Path $Source)) {
    Write-Error "Source folder not found: $Source"
    exit 1
}

# --- Marker-only mode (CI / pre-submit) -----------------------------------
# Lightweight scan with no pandoc/LaTeX dependency so a CI job can gate on
# unfilled markers without installing a TeX toolchain (audit IMP-DOC-12 / IMP-INF-2).
if ($CheckOnly) {
    $mdFiles = Get-ChildItem -Path $Source -Filter '*.md' -Recurse |
        Where-Object { $_.Name -notmatch '^_' }
    foreach ($md in $mdFiles) {
        $markers = Select-String -Path $md.FullName -Pattern $MarkerPattern
        if ($markers) {
            $totalPlaceholders += $markers.Count
            $rel = Resolve-Path -Relative -Path $md.FullName
            Write-Warning "$rel : $($markers.Count) unfilled marker(s)"
        }
    }
    Write-Host ""
    Write-Host "$totalPlaceholders unfilled marker(s) across $($mdFiles.Count) deliverable(s)."
    if ($Strict -and $totalPlaceholders -gt 0) { exit 1 }
    exit 0
}

# --- Sanity checks --------------------------------------------------------

$pandoc = Get-Command pandoc -ErrorAction SilentlyContinue
if (-not $pandoc) {
    Write-Error @'
pandoc not found on PATH.
Install it with:   winget install JohnMacFarlane.Pandoc
or download from:  https://pandoc.org/installing.html
'@
    exit 1
}

$enginePath = Get-Command $Engine -ErrorAction SilentlyContinue
if (-not $enginePath) {
    Write-Error @"
PDF engine '$Engine' not found on PATH.
Install MiKTeX (xelatex) with: winget install MiKTeX.MiKTeX
or TeX Live with:              winget install TeXLive.TeXLive
"@
    exit 1
}

Write-Host "Source        : $Source"
Write-Host "PDF engine    : $($enginePath.Source)"
Write-Host "Pandoc version: $((& $pandoc.Source --version | Select-Object -First 1))"
Write-Host ""

# --- Build ----------------------------------------------------------------

$markdownFiles = Get-ChildItem -Path $Source -Filter '*.md' -Recurse |
    Where-Object { $_.Name -notmatch '^_' }

if ($markdownFiles.Count -eq 0) {
    Write-Warning "No .md files found under $Source"
    exit 0
}

$results = [System.Collections.Generic.List[object]]::new()

foreach ($md in $markdownFiles) {
    $rel = Resolve-Path -Relative -Path $md.FullName
    $pdf = [System.IO.Path]::ChangeExtension($md.FullName, '.pdf')
    $pdfRel = Resolve-Path -Relative -Path (Split-Path -Parent $pdf) |
        Join-Path -ChildPath (Split-Path -Leaf $pdf)

    Write-Host "Rendering $rel" -ForegroundColor Cyan

    # Detect un-filled team placeholders early so the team doesn't
    # accidentally upload a PDF with `<!-- TEAM -->` left in it.
    if ($WarnOnTeamPlaceholders) {
        $placeholders = Select-String -Path $md.FullName -Pattern $MarkerPattern
        if ($placeholders) {
            $totalPlaceholders += $placeholders.Count
            Write-Warning "  $($placeholders.Count) unfilled marker(s) (TEAM / TODO / TBD) still present. Fill them before submission."
        }
    }

    # Build the pandoc command. Honour per-file YAML front-matter for
    # geometry, fonts, etc. We force the engine here so callers don't
    # need to know the default.
    $pandocArgs = @(
        $md.FullName,
        '--from=markdown+yaml_metadata_block',
        '--to=pdf',
        "--pdf-engine=$Engine",
        '--standalone',
        '--toc-depth=2',
        "--output=$pdf"
    )

    $startedAt = Get-Date
    try {
        & $pandoc.Source @pandocArgs 2>&1 | ForEach-Object { Write-Host "    $_" }
        $ok = ($LASTEXITCODE -eq 0)
    } catch {
        $ok = $false
        Write-Host "    $_" -ForegroundColor Red
    }
    $elapsed = (New-TimeSpan -Start $startedAt -End (Get-Date)).TotalSeconds

    $results.Add([pscustomobject]@{
        Source  = $rel
        Target  = $pdfRel
        Ok      = $ok
        Seconds = [math]::Round($elapsed, 1)
    })

    if ($ok) {
        Write-Host "  ✓ $pdfRel  ($([math]::Round($elapsed, 1))s)" -ForegroundColor Green
    } else {
        Write-Host "  ✗ failed  ($([math]::Round($elapsed, 1))s)" -ForegroundColor Red
    }
}

# --- Summary --------------------------------------------------------------

Write-Host ""
Write-Host "Summary"
Write-Host "-------"
$results | Format-Table -AutoSize Source, Target, Ok, Seconds

$failed = $results | Where-Object { -not $_.Ok }
if ($failed) {
    Write-Host ""
    Write-Host "$($failed.Count) file(s) failed to render." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "All $($results.Count) deliverable(s) rendered successfully." -ForegroundColor Green

if ($totalPlaceholders -gt 0) {
    Write-Host "$totalPlaceholders unfilled marker(s) (TEAM / TODO / TBD) across the deliverables." -ForegroundColor Yellow
    if ($Strict) {
        Write-Host "Failing because -Strict is set." -ForegroundColor Red
        exit 1
    }
}

exit 0
