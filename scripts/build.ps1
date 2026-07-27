param(
    [switch]$OneFile
)

$projectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$python = Join-Path $projectRoot ".venv\Scripts\python.exe"
$icon = Join-Path $projectRoot "assets\icons\app.ico"

if (-not (Test-Path -LiteralPath $python)) {
    throw "未找到项目虚拟环境，请先创建 .venv 并安装依赖。"
}
$arguments = @(
    "--noconfirm",
    "--clean",
    "--name", "数据库导出工具",
    "--windowed",
    "--paths", "src",
    "--hidden-import", "pymysql",
    "--hidden-import", "psycopg",
    "--hidden-import", "pymssql",
    "--collect-submodules", "pymongo",
    "scripts\pyinstaller_entry.py"
)
if (Test-Path -LiteralPath $icon) {
    $arguments += @("--icon", $icon, "--add-data", "$icon;assets\icons")
}
else {
    Write-Warning "未提供自定义图标，将使用默认应用图标。"
}
if ($OneFile) {
    $arguments += "--onefile"
}
Push-Location $projectRoot
try {
    & $python -m PyInstaller @arguments
}
finally {
    Pop-Location
}
