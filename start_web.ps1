# VIP Health Vault — Başlatma Scripti
Write-Host "🏥 VIP Health Vault baslatiliyor..." -ForegroundColor Cyan

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"

Write-Host "📦 Gereksinimler yukleniyor..." -ForegroundColor Yellow
pip install fastapi uvicorn[standard] pyjwt cryptography lmdb --quiet

Write-Host "🚀 Sunucu baslatiliyor..." -ForegroundColor Green
Write-Host "   URL: http://localhost:8000" -ForegroundColor White
Write-Host "   API: http://localhost:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host "Demo Hesaplar:" -ForegroundColor Yellow
Write-Host "  Admin  : admin / Admin@2026"
Write-Host "  Doktor : dr.smith / Doctor@2026"
Write-Host "  VIP    : vip001 / VIP@2026"
Write-Host ""

Set-Location $backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
