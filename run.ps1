[CmdletBinding()]
param(
    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateNotNullOrEmpty()]
    [string]$Url,

    [Parameter()]
    [ValidateSet("video", "audio")]
    [string]$Mode,

    [Parameter()]
    [string]$Config
)

$ErrorActionPreference = "Stop"
$projectRoot = $PSScriptRoot
$venvPython = Join-Path $projectRoot ".venv\Scripts\python.exe"
$mainScript = Join-Path $projectRoot "main.py"

$pythonPrefix = @()
if (Test-Path -LiteralPath $venvPython -PathType Leaf) {
    $python = $venvPython
}
elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $python = (Get-Command py).Source
    $pythonPrefix = @("-3.13")
}
elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $python = (Get-Command python).Source
}
else {
    throw "Python 3.13が見つかりません。.venvを作成するかPython 3.13をインストールしてください。"
}

$pythonArgs = @($mainScript, $Url)
if ($PSBoundParameters.ContainsKey("Mode")) {
    $pythonArgs += @("--mode", $Mode)
}
if ($PSBoundParameters.ContainsKey("Config")) {
    $pythonArgs += @("--config", $Config)
}

& $python @pythonPrefix @pythonArgs
exit $LASTEXITCODE
