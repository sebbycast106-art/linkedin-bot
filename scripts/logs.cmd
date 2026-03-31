@echo off
setlocal

:: Stream live Railway logs for the linkedin-bot service
:: Run this from anywhere - it uses the linked project config

set "RAILWAY=%~dp0..\..\railway-cli\railway.exe"
if not exist "%RAILWAY%" set "RAILWAY=railway"

"%RAILWAY%" logs --service 5e669659-0256-48da-af00-73aa7aa63f9d --environment e50cf998-9ca9-4676-938c-b9bd7413c16b
