param(
    [ValidateSet("up", "down", "status")]
    [string]$Action = "up"
)

$ErrorActionPreference = "Stop"
docker info *> $null
if ($LASTEXITCODE -ne 0) {
    throw "Docker is installed, but its daemon is not running. Start Docker Desktop and retry."
}
$composeFiles = @(
    "-f", "compose.yaml",
    "-f", "compose.runtime.yaml",
    "-f", "compose.demo.yaml"
)

switch ($Action) {
    "up" {
        docker compose @composeFiles up --detach --build
        Write-Host ""
        Write-Host "Incident Investigator is starting."
        Write-Host "1. Open http://127.0.0.1:8501"
        Write-Host "2. Wait for the runtime-demo incident to appear."
        Write-Host "3. Review the evidence and click 'Разрешить действие'."
        Write-Host "4. Watch the agent verify service recovery automatically."
    }
    "down" {
        docker compose @composeFiles down
    }
    "status" {
        docker compose @composeFiles ps
    }
}
