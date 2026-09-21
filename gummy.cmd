@echo off
REM ==========================================================================
REM  GUMMY OS - one command, cold machine to running assistant.
REM
REM    gummy            start everything and open the app
REM    gummy stop       stop the backend and frontend
REM    gummy rebuild    rebuild the frontend, then start
REM    gummy dev        start with the frontend dev server (for UI work)
REM
REM  A .cmd wrapper so it runs from Command Prompt with no PowerShell
REM  execution-policy setup: -ExecutionPolicy Bypass applies to this one
REM  call and changes nothing machine-wide.
REM
REM  This file must stay pure ASCII with CRLF line endings. cmd.exe
REM  mis-parses a batch file with LF-only endings or non-ASCII bytes, and
REM  the symptom is an unrelated-looking "'X' is not recognized" error.
REM ==========================================================================

setlocal
set "SCRIPT=%~dp0ops\windows\start-gummy.ps1"

if /i "%~1"=="stop"    goto stop
if /i "%~1"=="rebuild" goto rebuild
if /i "%~1"=="dev"     goto dev

powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%"
goto done

:stop
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -Stop
goto done

:rebuild
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -Rebuild
goto done

:dev
powershell -NoProfile -ExecutionPolicy Bypass -File "%SCRIPT%" -Dev
goto done

:done
endlocal
