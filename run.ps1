param(
    [string]$Url,
    [string]$Mode,
    [string]$Config
)

if ([string]::IsNullOrWhiteSpace($Url)) {
    throw 'YouTube URLを指定してください。'
}

$ProjectRoot = $PSScriptRoot
$EntryScript = Join-Path $ProjectRoot 'run.py'
$VenvPython = Join-Path $ProjectRoot '.venv\Scripts\python.exe'

if (Test-Path -LiteralPath $VenvPython -PathType Leaf) {
    $Python = $VenvPython
}
else {
    $PythonCommand = Get-Command 'python' -ErrorAction SilentlyContinue
    if ($null -eq $PythonCommand) {
        throw 'Pythonが見つかりません。.venvを作成するかPythonをインストールしてください。'
    }
    $Python = $PythonCommand.Source
}

if ($Mode -and $Config) {
    & $Python $EntryScript $Url --mode $Mode --config $Config
}
elseif ($Mode) {
    & $Python $EntryScript $Url --mode $Mode
}
elseif ($Config) {
    & $Python $EntryScript $Url --config $Config
}
else {
    & $Python $EntryScript $Url
}

exit $LASTEXITCODE
