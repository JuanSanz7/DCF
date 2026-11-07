@echo off
REM One-command local start on Windows: builds the UI once, installs the backend, opens the browser.
cd /d %~dp0
if not exist frontend\dist (pushd frontend & call npm install & call npm run build & popd)
python -m pip install -q -e .\backend
set DCF_STATIC_DIR=%cd%\frontend\dist
python -m dcfmc serve --open %*
