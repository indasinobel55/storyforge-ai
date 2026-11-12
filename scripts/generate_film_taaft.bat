@echo off
REM ============================================================
REM  AUTONOMOUS TAAFT FILM GENERATOR (no AI assistant involved)
REM
REM  Usage:  scripts\generate_film_taaft.bat [prompt.md] [tier]
REM
REM  Defaults: prompts\obsidian_spire.md, tier=quality (slow mode)
REM
REM  What it does:
REM    - Drives the real TAAFT website from your logged-in Chrome
REM      profile (.taaft_chrome_profile), scene by scene
REM    - Adds narration + ambient sound, assembles, validates
REM    - Auto-resumes: if a run crashes or is interrupted, it
REM      restarts and continues where it left off
REM    - Final MP4 lands in outputs\<film-name>_taaft\_
REM
REM  Stop it by closing this window or pressing Ctrl+C.
REM ============================================================
setlocal
chcp 65001 >nul
cd /d "%~dp0.."

set PROMPT_FILE=%~1
if "%PROMPT_FILE%"=="" set PROMPT_FILE=prompts\obsidian_spire.md
set TIER=%~2
if "%TIER%"=="" set TIER=quality

if not exist "%PROMPT_FILE%" (
    echo ERROR: master prompt file not found: %PROMPT_FILE%
    pause
    exit /b 2
)

echo ============================================================
echo  Film prompt : %PROMPT_FILE%
echo  TAAFT tier  : %TIER% (quality = the site's slow mode)
echo  Output      : outputs\<film-name>_taaft\
echo  Progress    : one line per scene; each scene takes minutes
echo ============================================================

:autoresume
python -m agent.autonomous "%PROMPT_FILE%" --provider taaft --enable-taaft --tier %TIER%
if %ERRORLEVEL% EQU 0 goto complete
echo.
echo Run interrupted or failed - resuming automatically in 30 seconds...
echo (Completed scenes are kept and reused; nothing is regenerated.)
timeout /t 30 /nobreak >nul
goto autoresume

:complete
echo.
echo ============================================================
echo  FILM COMPLETE. Final MP4, thumbnail, plan.json and
echo  report.json are in outputs\<film-name>_taaft\
echo ============================================================
pause
