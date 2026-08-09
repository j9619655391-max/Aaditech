@echo off
REM ============================================================================
REM  Aaditech Agent - ONE-CLICK endpoint installer (standalone systems, §7.2)
REM
REM  This is the ONLY file you double-click on a Windows endpoint. It does all
REM  the manual work automatically:
REM    1. Self-elevates to Administrator (UAC prompt once).
REM    2. Reads AgentConfig.json in the SAME folder (downloaded from the portal,
REM       or exported by the wizard).
REM    3. Installs the portal's mkcert root CA into the Windows Root store
REM       (fetched from the portal over HTTPS), so the endpoint trusts the
REM       portal cert and MeshCentral/HTTPS endpoints work.
REM    4. Downloads Aaditech-Agent-Setup.exe from the portal if it is not
REM       already next to this file.
REM    5. Runs the installer silently, injecting the server values
REM       (ManagerIp / ZabbixServerIp / MeshCentralUrl / WazuhEnrollKey) from
REM       AgentConfig.json - no typing, no separate steps.
REM    6. Writes a .env-style answer file (%ProgramData%\Aaditech\AADITECH_ENV.txt)
REM       so self-healing/agent-command-poller.ps1 can be scheduled with no
REM       manual flag passing.
REM
REM  Usage:  install-agent.bat            (AgentConfig.json must be beside it)
REM
REM  Nothing is hardcoded here - every value comes from AgentConfig.json,
REM  which the portal generates per deployment. The .bat contains no secrets.
REM ============================================================================
setlocal EnableExtensions

REM --- 1. Self-elevate -------------------------------------------------------
net session >nul 2>&1
if %errorlevel% neq 0 (
  echo Requesting Administrator privileges...
  powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
  exit /b
)

cd /d "%~dp0"

if not exist "AgentConfig.json" (
  echo ERROR: AgentConfig.json not found next to install-agent.bat.
  echo Download it from the portal:  Portal ^> Create Agent ^> Download config
  echo (or copy AgentConfig.json into this folder), then re-run.
  pause
  exit /b 1
)

REM --- 2. Read config into env vars ------------------------------------------
REM Dump key=value lines via PowerShell, then load them into the batch env.
set "CC=%TEMP%\aaditech-cc.txt"
powershell -NoProfile -Command "$c = Get-Content -Raw 'AgentConfig.json' | ConvertFrom-Json; @('MANAGER_IP=' + $c.managerIp, 'ENROLL_KEY=' + $c.wazuhEnrollKey, 'ZABBIX_IP=' + $c.zabbixServerIp, 'MESH_URL=' + $c.meshCentralUrl, 'MESH_ID=' + $c.meshId) | Set-Content -Path '%CC%'"
for /f "usebackq tokens=1,* delims==" %%a in ("%CC%") do set "%%a=%%b"
del "%CC%" >nul 2>&1

if not defined MANAGER_IP (
  echo ERROR: could not parse AgentConfig.json. Check it is valid JSON.
  pause
  exit /b 1
)

REM --- 3. Portal base URL -----------------------------------------------------
REM Mesh URL carries the portal host:port (https://<ip>:4433); strip the port
REM to derive the portal base used for the CA + installer download.
for /f "tokens=1-2 delims=:" %%a in ("%MESH_URL%") do set "PORTAL_BASE=%%a:%%b"
set "CA_URL=%PORTAL_BASE%/api/agent-installer/root-ca"
set "EXE_URL=%PORTAL_BASE%/api/agent-installer/download"

echo.
echo ============================================
echo  Aaditech Agent - one-click install
echo  Manager IP : %MANAGER_IP%
echo  Portal     : %PORTAL_BASE%
echo ============================================
echo.

REM --- 4. Install root CA ----------------------------------------------------
echo [1/5] Installing portal root CA...
del "rootCA.pem" >nul 2>&1
powershell -NoProfile -Command "try { Invoke-WebRequest -Uri '%CA_URL%' -OutFile 'rootCA.pem' -UseBasicParsing -TimeoutSec 30 | Out-Null; 'ok' } catch { 'fail' }" >nul 2>&1
if not exist "rootCA.pem" (
  echo        WARNING: could not download the portal root CA from %CA_URL%.
  echo        HTTPS endpoints on this machine may show cert warnings.
) else (
  certutil -addstore Root rootCA.pem >nul 2>&1
  if %errorlevel% equ 0 (
    echo        CA installed into the Windows Root store.
  ) else (
    echo        WARNING: CA downloaded but addstore failed - check permissions.
  )
  del "rootCA.pem" >nul 2>&1
)

REM --- 5. Ensure the installer is present ------------------------------------
echo [2/5] Ensuring Aaditech-Agent-Setup.exe is available...
if not exist "Aaditech-Agent-Setup.exe" (
  echo        Downloading from portal...
  powershell -NoProfile -Command "try { Invoke-WebRequest -Uri '%EXE_URL%' -OutFile 'Aaditech-Agent-Setup.exe' -UseBasicParsing -TimeoutSec 300 | Out-Null; 'ok' } catch { 'fail' }" >nul 2>&1
)
if not exist "Aaditech-Agent-Setup.exe" (
  echo ERROR: installer not found locally and download from the portal failed.
  echo        Build/publish it first (Portal ^> Create Agent ^> Build), then re-run.
  pause
  exit /b 1
)
echo        Installer ready.

REM --- 6. Run the silent install ----------------------------------------------
echo [3/5] Installing the Aaditech Agent (silent)...
"Aaditech-Agent-Setup.exe" ManagerIp=%MANAGER_IP% ZabbixServerIp=%ZABBIX_IP% MeshCentralUrl=%MESH_URL% WazuhEnrollKey=%ENROLL_KEY%
if %errorlevel% neq 0 (
  echo ERROR: installer exited with code %errorlevel%.
  pause
  exit /b %errorlevel%
)
echo        Install complete.

REM --- 7. Write the poller answer file -----------------------------------------
echo [4/5] Writing poller answer file (AADITECH_ENV.txt)...
if not exist "%ProgramData%\Aaditech" mkdir "%ProgramData%\Aaditech" >nul 2>&1
(
  echo PORTAL_BASE_URL=%PORTAL_BASE%
  echo ENDPOINT_ID=%COMPUTERNAME%
  echo SERVICE_TOKEN=
  echo MESH_ID=%MESH_ID%
  echo AGENT_INSTALLED=%date% %time%
) > "%ProgramData%\Aaditech\AADITECH_ENV.txt"
echo        Answer file written to %ProgramData%\Aaditech\AADITECH_ENV.txt

REM --- 8. Done ----------------------------------------------------------------
echo.
echo [5/5] Done.
echo.
echo Next steps (automated for the fleet via GPO/Intune):
echo   - Schedule the command poller every 5 minutes:
echo       schtasks /create /tn "Aaditech Agent Poller" /sc minute /mo 5 ^
echo         /tr "powershell -ExecutionPolicy Bypass -File \"self-healing\agent-command-poller.ps1\" ^
echo               -PortalBaseUrl %PORTAL_BASE% -EndpointId %COMPUTERNAME% -ServiceToken ^<token^>"
echo   - The endpoint Host ID is %COMPUTERNAME% (matches what the portal shows).
echo   - Verify in the portal:  Security Alerts ^> Agent Health.
echo.
pause
exit /b 0
