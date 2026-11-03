param([int]$Port = 5180)

# Vite 代理默认后端 127.0.0.1:8010；相机位置与定位计算仍由后端配置决定。
$projectRoot = Split-Path -Parent $PSScriptRoot
Push-Location -LiteralPath (Join-Path $projectRoot 'frontend')
try {
    & npm.cmd run dev -- --port $Port --strictPort
}
finally {
    Pop-Location
}
