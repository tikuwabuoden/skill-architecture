[CmdletBinding()]
param(
    [string]$Project = (Get-Location).Path,
    [switch]$Uninstall,
    [switch]$ClaudeHook
)

$ErrorActionPreference = 'Stop'
$repositoryRoot = Split-Path -Parent $PSScriptRoot
$installer = Join-Path $repositoryRoot 'scripts/policy/install.py'
$pythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($pythonCommand) {
    $pythonArguments = @('-B', $installer, '--project', $Project)
} else {
    $pythonCommand = Get-Command py -ErrorAction SilentlyContinue
    if (-not $pythonCommand) {
        throw 'Policy installer requires Python 3.10 or newer (`python` or `py -3`) on PATH.'
    }
    $pythonArguments = @('-3', '-B', $installer, '--project', $Project)
}
if ($Uninstall) {
    $pythonArguments += '--uninstall'
}
if ($ClaudeHook) {
    $pythonArguments += @('--agent-hook', 'claude')
}
& $pythonCommand.Source @pythonArguments
exit $LASTEXITCODE
