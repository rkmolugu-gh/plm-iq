@echo off
echo Setting up database...
echo.

REM Run schema.sql
echo Running schema.sql...
sqlite3 plm-iq.db < schema.sql

REM Run seed.sql
echo Running seed.sql...
sqlite3 plm-iq.db < seed.sql

echo.
echo Database setup complete.
pause
