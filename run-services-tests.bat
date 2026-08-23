@echo off
setlocal

rem -- PLM-IQ service-layer tests (root wrapper) ----------------------------
rem   Delegates to backend\run-services-tests.bat, which runs one
rem   positive+negative suite per service with green tick / red cross output.
rem   Requires the dev Postgres running with schema+seed deployed:
rem     database\deploy-schema.bat -schema -seed
rem ------------------------------------------------------------------------

call "%~dp0backend\run-services-tests.bat"
endlocal & exit /b %ERRORLEVEL%
