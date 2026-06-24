# ─────────────────────────────────────────────────────────────────────────────
# Reset a forgotten PostgreSQL 'postgres' password AND create the app's database.
#
#   RUN THIS IN AN ELEVATED POWERSHELL  (right-click PowerShell → Run as administrator)
#       cd "d:\Doctor_project\Doctor project\gastro_poc2"
#       powershell -ExecutionPolicy Bypass -File .\reset_pg_password.ps1
#
# It temporarily switches local auth to "trust", makes the changes, then restores
# your original pg_hba.conf — even if something fails midway.
# ─────────────────────────────────────────────────────────────────────────────

$ErrorActionPreference = 'Stop'

# Log everything to a file so the outcome can be reviewed afterwards.
try { Start-Transcript -Path (Join-Path $PSScriptRoot 'reset_log.txt') -Force | Out-Null } catch {}

# --- Edit these if you like ---------------------------------------------------
$PgBin              = 'C:\Program Files\PostgreSQL\17\bin'
$PgData             = 'C:\Program Files\PostgreSQL\17\data'
$ServiceName        = 'postgresql-x64-17'
$NewPostgresPassword = 'postgres'   # the new superuser password you'll remember
$AppRole            = 'gastro'       # must match POSTGRES_USER in .env
$AppRolePassword    = 'gastro'       # must match POSTGRES_PASSWORD in .env
$AppDb              = 'gastro'       # must match POSTGRES_DB in .env
# -----------------------------------------------------------------------------

$hba    = Join-Path $PgData 'pg_hba.conf'
$backup = Join-Path $PgData 'pg_hba.conf.bak'
$psql   = Join-Path $PgBin  'psql.exe'

# Require elevation
$id = [Security.Principal.WindowsIdentity]::GetCurrent()
if (-not (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole(
        [Security.Principal.WindowsBuiltinRole]::Administrator)) {
    Write-Error "Not elevated. Re-open PowerShell as Administrator and run this again."
    exit 1
}

Write-Host "1) Backing up pg_hba.conf -> pg_hba.conf.bak" -ForegroundColor Cyan
Copy-Item $hba $backup -Force

try {
    Write-Host "2) Switching local auth to 'trust' (temporary)" -ForegroundColor Cyan
    (Get-Content $hba) `
        -replace '^(local\s+all\s+all\s+)scram-sha-256', '$1trust' `
        -replace '^(host\s+all\s+all\s+(127\.0\.0\.1/32|::1/128)\s+)scram-sha-256', '$1trust' |
        Set-Content $hba -Encoding ascii

    Write-Host "3) Restarting PostgreSQL service" -ForegroundColor Cyan
    Restart-Service $ServiceName
    Start-Sleep -Seconds 3

    Write-Host "4) Applying changes (set postgres password, create app role + db)" -ForegroundColor Cyan
    $env:PGPASSWORD = ''   # trust mode: no password needed
    & $psql -U postgres -h 127.0.0.1 -d postgres -v ON_ERROR_STOP=1 -c "ALTER USER postgres WITH PASSWORD '$NewPostgresPassword';"

    # Create role only if missing
    & $psql -U postgres -h 127.0.0.1 -d postgres -v ON_ERROR_STOP=1 -c @"
DO `$`$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = '$AppRole') THEN
    CREATE ROLE $AppRole WITH LOGIN PASSWORD '$AppRolePassword';
  END IF;
END `$`$;
"@
    # Create database only if missing (CREATE DATABASE can't run inside DO/transaction)
    $exists = & $psql -U postgres -h 127.0.0.1 -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname = '$AppDb';"
    if ($exists -ne '1') {
        & $psql -U postgres -h 127.0.0.1 -d postgres -v ON_ERROR_STOP=1 -c "CREATE DATABASE $AppDb OWNER $AppRole;"
    }
    & $psql -U postgres -h 127.0.0.1 -d postgres -v ON_ERROR_STOP=1 -c "GRANT ALL PRIVILEGES ON DATABASE $AppDb TO $AppRole;"
}
finally {
    Write-Host "5) Restoring original pg_hba.conf and restarting" -ForegroundColor Cyan
    Copy-Item $backup $hba -Force
    Restart-Service $ServiceName
    Start-Sleep -Seconds 3
}

Write-Host ""
Write-Host "DONE." -ForegroundColor Green
Write-Host "  postgres password is now: $NewPostgresPassword"
Write-Host "  database '$AppDb' owned by role '$AppRole' is ready (matches your .env)."
Write-Host "  Next:  python manage.py migrate ; python manage.py seed_doctor ; python manage.py runserver"

try { Stop-Transcript | Out-Null } catch {}
exit 0
