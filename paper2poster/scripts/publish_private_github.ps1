param(
    [string]$RepoName = "paper2poster",
    [string]$Description = "Paper-to-poster generation workflow prototype"
)

$ErrorActionPreference = "Stop"

if (-not $env:GITHUB_TOKEN) {
    throw "Set GITHUB_TOKEN to a GitHub personal access token with repo scope."
}

$headers = @{
    Authorization = "Bearer $env:GITHUB_TOKEN"
    Accept = "application/vnd.github+json"
    "X-GitHub-Api-Version" = "2022-11-28"
}

$user = Invoke-RestMethod -Method Get -Uri "https://api.github.com/user" -Headers $headers
$owner = if ($env:GITHUB_OWNER) { $env:GITHUB_OWNER } else { $user.login }

$repoUri = "https://api.github.com/repos/$owner/$RepoName"
$createUri = if ($env:GITHUB_OWNER) {
    "https://api.github.com/orgs/$owner/repos"
} else {
    "https://api.github.com/user/repos"
}

try {
    $repo = Invoke-RestMethod -Method Get -Uri $repoUri -Headers $headers
    Write-Host "Repository already exists: $($repo.html_url)"
} catch {
    $body = @{
        name = $RepoName
        description = $Description
        private = $true
        auto_init = $false
    } | ConvertTo-Json
    $repo = Invoke-RestMethod -Method Post -Uri $createUri -Headers $headers -Body $body -ContentType "application/json"
    Write-Host "Created private repository: $($repo.html_url)"
}

$remoteUrl = "https://github.com/$owner/$RepoName.git"
$existingRemote = $null
$remotes = @(git remote)
if ($remotes -contains "origin") {
    git remote set-url origin $remoteUrl
} else {
    git remote add origin $remoteUrl
}

git -c http.extraHeader="Authorization: Bearer $env:GITHUB_TOKEN" push -u origin main
Write-Host "Pushed main to $remoteUrl"
