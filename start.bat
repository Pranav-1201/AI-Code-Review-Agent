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

REM ---- ports must be free ----------------------------------------
REM  A server left over from a previous run is the single most common way this
REM  script half-works. Closing THIS window never stopped the servers - only
REM  closing the two server windows does - so leftovers accumulate easily.
REM
REM  It used to fail silently and confusingly: vite would quietly move to 8081,
REM  the page still loaded, but its Origin was no longer in the backend's CORS
REM  allowlist, so every API call died at the preflight with nothing in the
REM  uvicorn log but "OPTIONS /scan 400". Meanwhile this script kept polling
REM  8080 and never opened the browser. vite.config.ts now sets strictPort so
REM  the drift cannot happen - which means a busy port stops us here instead,
REM  and the operator gets told which PID to kill.
set "PORTCLASH="
for %%p in (8000 8080) do (
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr /r /c:":%%p .*LISTENING"') do (
        echo  [X] Port %%p is already in use by PID %%a
        set "PORTCLASH=1"
    )
)
if defined PORTCLASH (
    echo.
    echo      Close the old "ETP Backend" / "ETP Frontend" windows, or run:
    echo          taskkill /F /PID ^<pid^>
    echo      then re-run start.bat.
    echo.
    pause
    exit /b 1
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

REM  THE WORST CASE IS THE ONE THE OPERATOR SEES.
REM
REM  A backend can sit with its port bound and accepting while never answering
REM  HTTP at all - measured on this machine 2026-08-26, connect in 0.02s and no
REM  response in 60s, from a backend this script had launched. The probe below
REM  correctly refuses to call that ready. The problem was what happened next:
REM  at 60 iterations of two one-second probes plus a sleep, the browser was
REM  held back for roughly three minutes behind one unchanging "Waiting..."
REM  line. That reads as "the launcher did nothing", so the page gets opened by
REM  hand - exactly what this step exists to prevent.
REM
REM  So: 12 iterations, about 35 seconds worst case, a dot per iteration so it
REM  is visibly alive, and the browser opens either way. A backend that is
REM  genuinely down is reported below rather than waited on in silence.
REM
REM  Probe 127.0.0.1, not localhost: uvicorn binds IPv4 loopback only, while
REM  "localhost" can resolve to ::1 first and make a healthy backend look dead.
REM  /health rather than / because it is the route that reports real readiness,
REM  and -f so an error status is not mistaken for an answer.
set "BACK="
set "FRONT="
for /l %%i in (1,1,12) do (
    if not defined BACK (
        curl.exe -sf -o NUL --max-time 1 http://127.0.0.1:8000/health >NUL 2>&1
        if not errorlevel 1 (
            set "BACK=1"
            echo.
            echo      backend  ready
        )
    )
    if not defined FRONT (
        curl.exe -sf -o NUL --max-time 1 http://127.0.0.1:8080/ >NUL 2>&1
        if not errorlevel 1 (
            set "FRONT=1"
            echo.
            echo      frontend ready
        )
    )

    REM  Leave the moment both answer. A batch FOR cannot break, so this is a
    REM  GOTO out of the loop - and without it the loop ran every iteration
    REM  no matter what, which is why the browser used to appear minutes after
    REM  the servers were already up and the script looked like it did nothing.
    if defined BACK if defined FRONT goto :ready

    <nul set /p "=."
    ping -n 2 127.0.0.1 >NUL
)
echo.

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
