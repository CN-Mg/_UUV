param([int]$Port = 8010)

# 使用用户指定的 UUV 环境，从任意目录启动同一套后端。
$projectRoot = Split-Path -Parent $PSScriptRoot
$uuvPython = 'D:\_DownloadDeepLearning\Anaconda\envs\UUV\python.exe'
if (-not (Test-Path -LiteralPath $uuvPython)) {
    throw "找不到指定的 UUV Python：$uuvPython"
}
Push-Location -LiteralPath $projectRoot
try {
    & $uuvPython -m uvicorn app.main:app --app-dir (Join-Path $projectRoot 'backend') --host 127.0.0.1 --port $Port
}
finally {
    Pop-Location
}
