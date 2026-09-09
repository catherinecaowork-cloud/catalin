#!/usr/bin/env pwsh
# 跑全部自测（等价于 pytest tests/）
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Error "请先创建 .venv 并 pip install -e .[dev]"
}
& .\.venv\Scripts\python.exe -m pytest tests/ @args
exit $LASTEXITCODE
