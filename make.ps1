# HAYABUSA — PowerShell parity wrapper for the Makefile.
#
# `make` is not installed by default on Windows, so this script exposes the same
# targets. See DECISIONS.md D-005.
#
#   ./make.ps1 secrets
#   ./make.ps1 up
#   ./make.ps1 logs api

[CmdletBinding()]
param(
    [Parameter(Position = 0)] [string] $Target = 'help',
    [Parameter(Position = 1, ValueFromRemainingArguments = $true)] [string[]] $Rest
)

$ErrorActionPreference = 'Stop'
Set-Location -Path $PSScriptRoot

function Invoke-Step {
    param([string] $Command, [string[]] $Arguments)
    & $Command @Arguments
    if ($LASTEXITCODE -ne 0) {
        throw "'$Command $($Arguments -join ' ')' failed with exit code $LASTEXITCODE"
    }
}

function Invoke-InBackend {
    param([string[]] $Arguments)
    Push-Location backend
    try { Invoke-Step 'uv' $Arguments } finally { Pop-Location }
}

function Invoke-InFrontend {
    param([string[]] $Arguments)
    Push-Location frontend
    try { Invoke-Step 'npm' $Arguments } finally { Pop-Location }
}

$webPort = if ($env:WEB_HOST_PORT) { $env:WEB_HOST_PORT } else { '3000' }
$apiPort = if ($env:API_HOST_PORT) { $env:API_HOST_PORT } else { '8000' }
$pgUser  = if ($env:POSTGRES_USER) { $env:POSTGRES_USER } else { 'postgres' }
$pgDb    = if ($env:POSTGRES_DB)   { $env:POSTGRES_DB }   else { 'hayabusa' }

switch ($Target) {
    'help' {
        Write-Host ''
        Write-Host '  HAYABUSA targets' -ForegroundColor Cyan
        Write-Host ''
        @(
            @('secrets',   'Create .env from .env.example with generated secrets'),
            @('up',        'Build and start the full stack in the background'),
            @('down',      'Stop the stack (volumes preserved)'),
            @('restart',   'Restart application services, leaving datastores up'),
            @('build',     'Rebuild images without starting'),
            @('logs [svc]','Tail logs from all services, or one'),
            @('ps',        'Show service status'),
            @('migrate',   'Apply all migrations'),
            @('revision',  'Autogenerate a migration: ./make.ps1 revision "message"'),
            @('downgrade', 'Roll back one migration'),
            @('seed',      'Load curated sources, vendors and demo components'),
            @('psql',      'Open a psql shell on the application database'),
            @('redis-cli', 'Open a redis-cli shell'),
            @('test',      'Run the backend test suite'),
            @('lint',      'Lint backend (ruff + mypy) and frontend (eslint + tsc)'),
            @('fmt',       'Format backend and frontend sources'),
            @('check',     'Lint everything, then test'),
            @('types',     'Regenerate frontend API types from the OpenAPI schema'),
            @('shell',     'Open a shell in the api container'),
            @('clean',     'Stop the stack and delete its volumes (DESTROYS DATA)')
        ) | ForEach-Object { Write-Host ('    {0,-14} {1}' -f $_[0], $_[1]) }
        Write-Host ''
    }

    'secrets' { Invoke-Step 'python' @('scripts/gen_secrets.py') }

    'up' {
        Invoke-Step 'docker' @('compose', 'up', '-d', '--build')
        Write-Host ''
        Write-Host "  web   -> http://localhost:$webPort"
        Write-Host "  api   -> http://localhost:$apiPort/api/docs"
    }
    'down'    { Invoke-Step 'docker' @('compose', 'down') }
    'restart' { Invoke-Step 'docker' @('compose', 'restart', 'api', 'worker', 'beat', 'web') }
    'build'   { Invoke-Step 'docker' @('compose', 'build') }
    'ps'      { Invoke-Step 'docker' @('compose', 'ps') }
    'logs'    { Invoke-Step 'docker' (@('compose', 'logs', '-f', '--tail=100') + $Rest) }

    'migrate'   { Invoke-Step 'docker' @('compose', 'run', '--rm', 'api', 'alembic', 'upgrade', 'head') }
    'downgrade' { Invoke-Step 'docker' @('compose', 'run', '--rm', 'api', 'alembic', 'downgrade', '-1') }
    'revision'  {
        if (-not $Rest) { throw 'Usage: ./make.ps1 revision "describe the change"' }
        Invoke-Step 'docker' @('compose', 'run', '--rm', 'api', 'alembic', 'revision', '--autogenerate', '-m', ($Rest -join ' '))
    }
    'seed'      { Invoke-Step 'docker' @('compose', 'run', '--rm', 'api', 'python', '-m', 'app.seed') }
    'psql'      { Invoke-Step 'docker' @('compose', 'exec', 'postgres', 'psql', '-U', $pgUser, '-d', $pgDb) }
    'redis-cli' { Invoke-Step 'docker' @('compose', 'exec', 'redis', 'redis-cli') }

    'test' { Invoke-InBackend @('run', 'pytest', '-q') }
    'lint' {
        Invoke-InBackend @('run', 'ruff', 'check', '.')
        Invoke-InBackend @('run', 'mypy', 'app')
        Invoke-InFrontend @('run', 'lint')
        Invoke-InFrontend @('run', 'typecheck')
    }
    'fmt' {
        Invoke-InBackend @('run', 'ruff', 'format', '.')
        Invoke-InBackend @('run', 'ruff', 'check', '--fix', '.')
        Invoke-InFrontend @('run', 'format')
    }
    'check' {
        & $PSCommandPath 'lint'
        & $PSCommandPath 'test'
    }
    'types' { Invoke-InFrontend @('run', 'types') }

    'shell' { Invoke-Step 'docker' @('compose', 'exec', 'api', 'bash') }
    'clean' { Invoke-Step 'docker' @('compose', 'down', '-v') }

    default { throw "Unknown target '$Target'. Run ./make.ps1 help" }
}
