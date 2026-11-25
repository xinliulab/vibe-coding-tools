# queue.ps1 - queue helper for the session-manager skill (Windows; also runs in PowerShell 7 on macOS/Linux).
# Reads Claude Code's own session records (~/.claude/sessions/*.json) and, when present,
# the switchboard plugin's status reports (~/.claude/switchboard/reports/*.json). Prints JSON.
#   Queue:   queue.ps1 -Self <local_id of the manager session>
#   Handled: queue.ps1 -Mark <local_id>      (run BEFORE relaying, or on skip: leaves the queue until it finishes new work)
#            queue.ps1 -Unmark <local_id>    (undo a mark, e.g. when the relay failed)
#   Ignore:  queue.ps1 -Ignore <local_id>    (never queue it again)   / -Unignore <local_id>
#   Watch:   queue.ps1 -Self <id> -Watch     (print "READY: title | kind | id" whenever a session newly enters the queue)
#   Testing: -Only <local_id>,<local_id>  and  -StateFile <path>
param(
  [string]$Self = '',
  [string]$Mark = '',
  [string]$Ignore = '',
  [string]$Unignore = '',
  [string]$Unmark = '',
  [string[]]$Only = @(),
  [string]$StateFile = '',
  [switch]$Watch,
  [int]$Interval = 20
)
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$claudeDir = Join-Path $HOME '.claude'
if (-not $StateFile) { $StateFile = Join-Path (Join-Path $claudeDir 'session-manager') 'state.json' }
$sessionsDir = Join-Path $claudeDir 'sessions'
$reportsDir = Join-Path (Join-Path $claudeDir 'switchboard') 'reports'

function Read-State {
  $s = @{ handled = @{}; ignored = @() }
  if (Test-Path -LiteralPath $StateFile) {
    try {
      $j = Get-Content -LiteralPath $StateFile -Raw -Encoding UTF8 | ConvertFrom-Json
      if ($null -ne $j.handled) { foreach ($p in $j.handled.PSObject.Properties) { $s.handled[$p.Name] = [int64]$p.Value } }
      if ($null -ne $j.ignored) { $s.ignored = @($j.ignored | Where-Object { $_ }) }
    } catch { }
  }
  return $s
}

function Save-State($s) {
  $dir = Split-Path -Parent $StateFile
  if (-not (Test-Path -LiteralPath $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
  $obj = [pscustomobject]@{ handled = [pscustomobject]$s.handled; ignored = @($s.ignored) }
  [System.IO.File]::WriteAllText($StateFile, ($obj | ConvertTo-Json -Depth 4), (New-Object System.Text.UTF8Encoding($false)))
}

function To-Ms([double]$v) { if ($v -gt 0 -and $v -lt 1e12) { return [int64]($v * 1000) } return [int64]$v }

function Local-Id([string]$h) { if ($h.StartsWith('local_')) { return $h } return 'local_' + $h }

function Get-Queue {
  $state = Read-State
  $nowMs = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
  $alive = @{}
  Get-Process | ForEach-Object { $alive[$_.Id] = $true }

  $queue = @(); $working = @(); $handledQuiet = 0
  foreach ($f in @(Get-ChildItem -Path $sessionsDir -Filter '*.json' -ErrorAction SilentlyContinue)) {
    try { $r = Get-Content -LiteralPath $f.FullName -Raw -Encoding UTF8 | ConvertFrom-Json } catch { continue }
    if ($null -eq $r -or -not $r.hostSessionId -or "$($r.entrypoint)" -notmatch 'desktop') { continue }
    if (-not $alive.ContainsKey([int]$r.pid)) { continue }
    $id = Local-Id "$($r.hostSessionId)"
    if ($id -eq $Self) { continue }
    if ($Only.Count -gt 0 -and $Only -notcontains $id) { continue }
    if ($state.ignored -contains $id) { continue }

    $title = "$($r.name)"
    if (-not $title) { $title = Split-Path -Leaf "$($r.cwd)" }
    $updated = To-Ms ([double]("0" + "$($r.statusUpdatedAt)"))

    $rep = $null
    if ($r.sessionId) {
      $repPath = Join-Path $reportsDir ("$($r.sessionId)" + '.json')
      if (Test-Path -LiteralPath $repPath) {
        try { $rep = Get-Content -LiteralPath $repPath -Raw -Encoding UTF8 | ConvertFrom-Json } catch { $rep = $null }
      }
    }

    $status = "$($r.status)"
    if ($status -eq 'busy' -or $status -eq 'shell') { $working += $title; continue }
    if ($status -ne 'idle' -and $status -ne 'waiting') { continue }

    if ($state.handled.ContainsKey($id) -and $updated -le $state.handled[$id]) { $handledQuiet++; continue }

    $kind = 'done'
    if ($status -eq 'waiting') { $kind = 'approval' }
    elseif ($null -ne $rep -and $rep.turnError) { $kind = 'error' }
    elseif ($null -ne $rep -and $rep.question) { $kind = 'question' }

    $waited = 0
    if ($updated -gt 0) { $waited = [math]::Round(($nowMs - $updated) / 60000) }

    $queue += [pscustomobject]@{
      id        = $id
      title     = $title
      kind      = $kind
      waitedMin = $waited
      since     = $updated
      cwd       = "$($r.cwd)"
      question  = $(if ($null -ne $rep) { $rep.question } else { $null })
      approval  = $(if ($null -ne $rep) { $rep.approval } else { $null })
      error     = $(if ($null -ne $rep) { $rep.turnError } else { $null })
    }
  }
  return [pscustomobject]@{
    queue        = @($queue | Sort-Object -Property since)
    working      = @($working)
    handledQuiet = $handledQuiet
  }
}

# With -File, "a,b" arrives as one string: split it.
$Only = @($Only | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })

if ($Mark -or $Unmark -or $Ignore -or $Unignore) {
  $state = Read-State
  $nowMs = [DateTimeOffset]::UtcNow.ToUnixTimeMilliseconds()
  if ($Mark) { $state.handled[$Mark] = $nowMs; Save-State $state; '{"ok":true,"marked":"' + $Mark + '"}'; exit 0 }
  if ($Unmark) { $state.handled.Remove($Unmark); Save-State $state; '{"ok":true,"unmarked":"' + $Unmark + '"}'; exit 0 }
  if ($Ignore) {
    if ($state.ignored -notcontains $Ignore) { $state.ignored = @($state.ignored) + $Ignore }
    Save-State $state; '{"ok":true,"ignored":"' + $Ignore + '"}'; exit 0
  }
  if ($Unignore) {
    $state.ignored = @($state.ignored | Where-Object { $_ -ne $Unignore }); Save-State $state
    '{"ok":true,"unignored":"' + $Unignore + '"}'; exit 0
  }
}

if ($Watch) {
  # Sessions already waiting when the watch starts are not reported again.
  $seen = @{}
  try { foreach ($it in @((Get-Queue).queue)) { if ($it) { $seen[$it.id] = $true } } } catch { }
  while ($true) {
    Start-Sleep -Seconds $Interval
    try {
      $now = @{}
      foreach ($it in @((Get-Queue).queue)) {
        if (-not $it) { continue }
        $now[$it.id] = $true
        if (-not $seen.ContainsKey($it.id)) {
          [Console]::Out.WriteLine("READY: $($it.title) | $($it.kind) | $($it.id)")
          [Console]::Out.Flush()
        }
      }
      $seen = $now
    } catch {
      [Console]::Out.WriteLine("WATCH-ERROR: $($_.Exception.Message)")
      [Console]::Out.Flush()
    }
  }
}

Get-Queue | ConvertTo-Json -Depth 6
