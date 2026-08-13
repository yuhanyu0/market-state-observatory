param(
  [string]$Owner = "yuhanyu0",
  [string]$Repo = "market-state-observatory",
  [ValidateSet("public","private")][string]$Visibility = "public"
)
$ErrorActionPreference = "Stop"
if (-not (Get-Command git -ErrorAction SilentlyContinue)) { throw "git is required" }
if (-not (Get-Command gh -ErrorAction SilentlyContinue)) { throw "GitHub CLI (gh) is required" }

gh auth status
if (Test-Path .git) { throw "This directory is already a Git repository. Review it manually." }

git init -b main
git add .
git commit -m "initial: launch Market State Observatory"
gh repo create "$Owner/$Repo" --$Visibility --source . --remote origin --push
Write-Host "Created https://github.com/$Owner/$Repo"
Write-Host "Enable GitHub Pages with Source = GitHub Actions if the first Pages run requests it."
