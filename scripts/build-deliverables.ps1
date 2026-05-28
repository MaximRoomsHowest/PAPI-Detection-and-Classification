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
    [switch]$WarnOnTeamPlaceholders = $true
)

$ErrorActionPreference = 'Stop'

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
        $placeholders = Select-String -Path $md.FullName -Pattern 'TEAM:' -SimpleMatch
        if ($placeholders) {
            Write-Warning "  $($placeholders.Count) <!-- TEAM: ... --> marker(s) still present. Fill them before submission."
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
} else {
    Write-Host ""
    Write-Host "All $($results.Count) deliverable(s) rendered successfully." -ForegroundColor Green
    exit 0
}
