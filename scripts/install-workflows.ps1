[CmdletBinding(SupportsShouldProcess)]
param(
    [string]$Destination = (Join-Path ([Environment]::GetFolderPath('UserProfile')) '.agents/skills'),
    [switch]$Uninstall
)

$ErrorActionPreference = 'Stop'

$repositoryRoot = Split-Path -Parent $PSScriptRoot
$workflowRoot = Join-Path $repositoryRoot 'skills/workflows'
$workflows = @(Get-ChildItem -LiteralPath $workflowRoot -Directory | Where-Object {
    Test-Path -LiteralPath (Join-Path $_.FullName 'SKILL.md') -PathType Leaf
})

if ($workflows.Count -eq 0) {
    throw "No Workflow Skills found under $workflowRoot"
}

$destinationRoot = [System.IO.Path]::GetFullPath($Destination)
$plannedLinks = foreach ($workflow in $workflows) {
    [pscustomobject]@{
        Name = $workflow.Name
        Source = [System.IO.Path]::GetFullPath($workflow.FullName)
        Link = Join-Path $destinationRoot $workflow.Name
    }
}

foreach ($plannedLink in $plannedLinks) {
    if (-not (Test-Path -LiteralPath $plannedLink.Link)) {
        continue
    }

    $existing = Get-Item -LiteralPath $plannedLink.Link -Force
    $existingTarget = @($existing.Target)[0]
    if (-not $existing.LinkType -or -not $existingTarget) {
        throw "Cannot install $($plannedLink.Name): $($plannedLink.Link) already exists and is not a link."
    }

    if (-not [System.IO.Path]::IsPathRooted($existingTarget)) {
        $existingTarget = Join-Path (Split-Path -Parent $plannedLink.Link) $existingTarget
    }
    $existingTarget = [System.IO.Path]::GetFullPath($existingTarget)

    if ($existingTarget -ne $plannedLink.Source) {
        throw "Cannot install $($plannedLink.Name): $($plannedLink.Link) points to $existingTarget."
    }
}

if ($Uninstall) {
    if ($PSCmdlet.ShouldProcess($destinationRoot, 'Remove Workflow Skill links')) {
        foreach ($plannedLink in $plannedLinks) {
            if (-not (Test-Path -LiteralPath $plannedLink.Link)) {
                Write-Output "Not installed: $($plannedLink.Name)"
                continue
            }

            [System.IO.Directory]::Delete($plannedLink.Link, $false)
            Write-Output "Uninstalled: $($plannedLink.Name)"
        }

        if ($PSBoundParameters.ContainsKey('Destination') -and
            (Test-Path -LiteralPath $destinationRoot) -and
            -not (Get-ChildItem -LiteralPath $destinationRoot -Force | Select-Object -First 1)) {
            [System.IO.Directory]::Delete($destinationRoot, $false)
        }
    }
    return
}

if ($PSCmdlet.ShouldProcess($destinationRoot, 'Create Workflow Skill links')) {
    New-Item -ItemType Directory -Path $destinationRoot -Force | Out-Null

    foreach ($plannedLink in $plannedLinks) {
        if (Test-Path -LiteralPath $plannedLink.Link) {
            Write-Output "Already installed: $($plannedLink.Name)"
            continue
        }

        $linkType = if ([System.IO.Path]::DirectorySeparatorChar -eq '\') { 'Junction' } else { 'SymbolicLink' }
        New-Item -ItemType $linkType -Path $plannedLink.Link -Target $plannedLink.Source | Out-Null
        Write-Output "Installed: $($plannedLink.Name) -> $($plannedLink.Source)"
    }
}
