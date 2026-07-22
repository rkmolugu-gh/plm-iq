@echo off
REM Run the two-stage indexing pipeline: stage (build JSONL) then publish (push to search backend).
cd /d "%~dp0.."

python -m db.indexing.build_all --stage-only --force
python -m db.indexing.publish --force
