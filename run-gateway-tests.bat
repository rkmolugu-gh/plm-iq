@echo off
setlocal

rem -- PLM-IQ gateway tests (root wrapper) -----------------------------------

call "%~dp0backend\run-gateway-tests.bat"
endlocal & exit /b %ERRORLEVEL%
