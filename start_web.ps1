# VIP Health Vault - Baslatma Scripti
Write-Host "VIP Health Vault baslatiliyor..." -ForegroundColor Cyan

$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$backend = Join-Path $root "backend"

Write-Host "Gereksinimler yukleniyor..." -ForegroundColor Yellow
pip install fastapi uvicorn[standard] pyjwt cryptography lmdb keyring wmi pyotp qrcode pillow --quiet

Write-Host "Sunucu baslatiliyor..." -ForegroundColor Green
Write-Host "   URL: http://localhost:8000" -ForegroundColor White
Write-Host "   API: http://localhost:8000/docs" -ForegroundColor White
Write-Host ""
Write-Host 'Demo Hesaplar:' -ForegroundColor Yellow
Write-Host '  Admin  : admin / Admin@2026Secure!'
Write-Host '  Doktor : dr.smith / Doctor@2026Secure!'
Write-Host '  VIP    : vip001 / VIPPatient@2026!'
Write-Host ""

$env:ENVIRONMENT="development"
$env:VHV_DEMO_MODE="true"
Set-Location $backend
python -m uvicorn main:app --host 0.0.0.0 --port 8000 --reload
