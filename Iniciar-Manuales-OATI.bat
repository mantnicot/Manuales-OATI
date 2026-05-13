@echo off
setlocal EnableExtensions
chcp 65001 >nul

set "ROOT=%~dp0"
set "USE_PROXY_OATI=0"
cd /d "%ROOT%"

title OATI Manuales — Lanzador

echo.
echo ============================================================
echo   OATI — Manuales institucionales
echo   Inicio del proyecto ^(un clic^)
echo ============================================================
echo.

set "BACKEND_LOCAL=1"

where docker >nul 2>&1
if errorlevel 1 goto NO_DOCKER

echo [Paso 1/3] Docker detectado: levantando servicios ^(API, PostgreSQL, Redis, MinIO^)...
docker compose -f "%ROOT%docker-compose.yml" up -d --build
if errorlevel 1 (
  echo.
  echo    Advertencia: docker compose fallo. Se usara backend local con Python.
  echo.
  goto USE_LOCAL_BACKEND
)

set "BACKEND_LOCAL=0"
set "USE_PROXY_OATI=0"
echo    OK. Esperando a que la API este disponible en puerto 8000...
timeout /t 10 /nobreak >nul
goto START_FRONTEND

:NO_DOCKER
echo [Paso 1/3] Docker no encontrado en PATH. Se usara backend local con Python.

:USE_LOCAL_BACKEND
if not exist "%ROOT%backend\app\main.py" (
  echo ERROR: No existe backend\app\main.py. Revise la carpeta del proyecto.
  pause
  exit /b 1
)
echo    Liberando puerto: si Docker dejo el servicio api en marcha, se detiene...
where docker >nul 2>&1
if not errorlevel 1 (
  docker compose -f "%ROOT%docker-compose.yml" stop api 2>nul
)
echo    Buscando puerto libre para FastAPI ^(8000-8020^)...
set "API_PORT="
for /f "usebackq delims=" %%p in (`powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\find-free-api-port.ps1"`) do set "API_PORT=%%p"
if not defined API_PORT (
  echo.
  echo    ERROR: No hay puerto libre entre 8000 y 8020, o PowerShell fallo.
  echo    Cierre otras instancias de la API / Docker o libere un puerto manualmente.
  pause
  exit /b 1
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%ROOT%scripts\write-api-proxy.ps1" -Port %API_PORT% -OutPath "%ROOT%frontend\proxy.oati.json"
if errorlevel 1 (
  echo ERROR: No se pudo escribir frontend\proxy.oati.json
  pause
  exit /b 1
)
echo    FastAPI en http://127.0.0.1:%API_PORT% ^(Angular usara proxy hacia este puerto^)
if not "%API_PORT%"=="8000" echo    Nota: el puerto 8000 estaba ocupado; el proxy se ajusto automaticamente.
start "OATI Backend (FastAPI)" cmd /k "cd /d ""%ROOT%backend"" && set PYTHONPATH=. && python -m uvicorn app.main:app --host 127.0.0.1 --port %API_PORT%"
timeout /t 5 /nobreak >nul
set "USE_PROXY_OATI=1"

:START_FRONTEND
echo.
echo [Paso 2/3] Iniciando Angular en http://localhost:4200 ...

if not exist "%ROOT%frontend\node_modules\" (
  echo    Primera ejecucion: instalando dependencias npm ^(puede tardar varios minutos^)...
  pushd "%ROOT%frontend"
  call npm install
  if errorlevel 1 (
    echo ERROR: npm install fallo. Verifique Node.js y npm.
    popd
    pause
    exit /b 1
  )
  popd
)

if "%USE_PROXY_OATI%"=="1" (
  start "OATI Frontend (Angular)" cmd /k "cd /d ""%ROOT%frontend"" && npm start -- --proxy-config proxy.oati.json"
) else (
  start "OATI Frontend (Angular)" cmd /k "cd /d ""%ROOT%frontend"" && npm start"
)

echo.
echo [Paso 3/3] Abriendo el navegador en ~18 segundos ^(primera compilacion puede demorar mas^)...
timeout /t 18 /nobreak >nul
start "" "http://localhost:4200/"

echo.
echo ------------------------------------------------------------
echo Listo.
if "%BACKEND_LOCAL%"=="0" (
  echo  - API y servicios: Docker ^(docker compose^)
  echo  - Para detener contenedores, en esta carpeta ejecute:
  echo      docker compose -f "%ROOT%docker-compose.yml" down
  echo  - Cierre la ventana del Frontend para detener Angular.
) else (
  echo  - API: ventana "OATI Backend (FastAPI)"
  echo  - Web: ventana "OATI Frontend (Angular)"
  echo  - Cierre ambas ventanas para detener API y Angular.
  goto END_MSG
)
echo  - Web: ventana "OATI Frontend (Angular)"

:END_MSG
echo ------------------------------------------------------------
pause
endlocal
