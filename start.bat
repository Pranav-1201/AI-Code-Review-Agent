@echo off
REM ==========================================================
REM  start.bat - one-click local dev launcher
REM
REM  Backend : uvicorn main:app  -> http://localhost:8000
REM  Frontend: vite (npm run dev) -> http://localhost:8080
REM            (8080, not Vite's default 5173 - set in
REM             frontend/vite.config.ts)
REM
REM  Each server gets its own window so you can read its logs
REM  and Ctrl+C it independently. Closing this window does not
REM  stop them; close the two server windows to shut down.
REM ==========================================================

cd /d "%~dp0"

echo.
echo  ET Code Review Agent - starting local dev environment
echo  =====================================================
echo.

REM ---- preflight -------------------------------------------------
if not exist "venv\Scripts\python.exe" (
    echo  [X] Python venv not found at venv\Scripts\python.exe
    echo      Create it with:  python -m venv venv
    echo      then:            venv\Scripts\pip install -r requirements.txt
    echo.
    pause
    exit /b 1
)

if not exist "frontend\package.json" (
    echo  [X] frontend\package.json not found. Wrong directory?
    echo.
    pause
    exit /b 1
)

if not exist "frontend\node_modules" (
    echo  [!] frontend\node_modules missing - running npm install once...
    pushd frontend
    call npm install
    popd
    if not exist "frontend\node_modules" (
        echo  [X] npm install failed. Fix that, then re-run start.bat
        echo.
        pause
        exit /b 1
    )
)

REM ---- launch ----------------------------------------------------
echo  [1/3] Starting backend on http://localhost:8000 ...
start "ETP Backend  (port 8000)" cmd /k "cd /d "%~dp0" && venv\Scripts\python.exe -m uvicorn main:app --reload --port 8000"

echo  [2/3] Starting frontend on http://localhost:8080 ...
start "ETP Frontend (port 8080)" cmd /k "cd /d "%~dp0frontend" && npm run dev"

REM ---- wait for BOTH services to actually answer -----------------
REM  Gating only on the frontend is a race: Vite serves the page in
REM  about a second, while the backend has to import the whole
REM  analysis stack (torch included). On a COLD start the backend
REM  loses that race, so the browser opens onto a working page whose
REM  every API call fails with "Failed to fetch" - which reads to the
REM  user as "the app is broken" rather than "still starting".
REM  So poll both ports, and open the browser only when the API that
REM  the page depends on is genuinely answering.
echo  [3/3] Waiting for backend (8000) and frontend (8080) ...

set "BACK="
set "FRONT="
for /l %%i in (1,1,60) do (
    if not defined BACK (
        curl.exe -s -o NUL --max-time 1 http://localhost:8000/ >NUL 2>&1
        if not errorlevel 1 (
            set "BACK=1"
            echo      backend  ready
        )
    )
    if not defined FRONT (
        curl.exe -s -o NUL --max-time 1 http://localhost:8080/ >NUL 2>&1
        if not errorlevel 1 (
            set "FRONT=1"
            echo      frontend ready
        )
    )

    REM  Leave the moment both answer. A batch FOR cannot break, so this is a
    REM  GOTO out of the loop - and without it the loop ran all 60 iterations
    REM  no matter what, which is why the browser used to appear minutes after
    REM  the servers were already up and the script looked like it did nothing.
    if defined BACK if defined FRONT goto :ready

    ping -n 2 127.0.0.1 >NUL
)

:ready
if not defined BACK (
    echo.
    echo  [!] Backend never answered on port 8000.
    echo      Read the "ETP Backend" window - the traceback is in there.
    echo      The page will still load, but every scan will fail with
    echo      "Cannot reach backend".
    echo.
)
if not defined FRONT (
    echo.
    echo  [!] Frontend never answered on port 8080.
    echo      Read the "ETP Frontend" window for the real error.
    echo      Opening the browser anyway so you can see its error page.
    echo.
)

REM  Open the app. The URL is echoed as well, so that if the default browser
REM  fails to launch there is still something to click rather than a script
REM  that appears to have done nothing.
echo  Opening http://localhost:8080 ...
start "" "http://localhost:8080"

echo.
echo  Done. Two server windows are running:
echo      ETP Backend  (port 8000)
echo      ETP Frontend (port 8080)
echo  Close those windows to stop the servers.
echo.
timeout /t 5 >NUL
