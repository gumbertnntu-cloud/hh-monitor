@echo off
setlocal
set SCRIPT_DIR=%~dp0
powershell -ExecutionPolicy Bypass -File "%SCRIPT_DIR%build_windows_exe.ps1" -PythonExe python -Clean
endlocal
