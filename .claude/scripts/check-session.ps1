# check-session.ps1
# Claude Code Stop hook for VS Code project template.
# Blocks exit (exit 2) only when session close is actively in progress.
# Validates STATUS.md frontmatter: YAML line format, required fields, allowed values.

# 1. Parse stop_hook_active from stdin to avoid infinite loop (BOM-safe)
$inputJson = [Console]::In.ReadToEnd().TrimStart([char]0xFEFF)
$hookInput = $null
if (-not [string]::IsNullOrWhiteSpace($inputJson)) {
    try { $hookInput = $inputJson | ConvertFrom-Json } catch { $hookInput = $null }
}
if ($hookInput -and $hookInput.stop_hook_active -eq $true) { exit 0 }

# 2. Locate docs/STATUS.md via CLAUDE_PROJECT_DIR (fallback to cwd)
if (-not [string]::IsNullOrWhiteSpace($env:CLAUDE_PROJECT_DIR)) {
    $projectDir = $env:CLAUDE_PROJECT_DIR
} else {
    $projectDir = (Get-Location).Path
}
$statusFile = Join-Path $projectDir "docs/STATUS.md"
if (-not (Test-Path $statusFile)) { exit 0 }

$content = Get-Content $statusFile -Raw -ErrorAction SilentlyContinue

# 3. Extract ONLY the first frontmatter block (fail-closed if missing or malformed delimiters)
$frontmatterMatch = [regex]::Match(
    $content,
    '\A---\s*\r?\n(?<yaml>[\s\S]*?)\r?\n---(?:\r?\n|\z)'
)

if (-not $frontmatterMatch.Success) {
    [Console]::Error.WriteLine("")
    [Console]::Error.WriteLine("Cannot validate session state: docs/STATUS.md frontmatter is missing or malformed.")
    [Console]::Error.WriteLine("Please ensure STATUS.md starts with a valid YAML frontmatter block (--- ... ---).")
    [Console]::Error.WriteLine("")
    exit 2
}

$frontmatter = $frontmatterMatch.Groups['yaml'].Value

# 4. Validate YAML lines and extract required fields
#    Each non-empty, non-comment line must be key: value format.
#    Duplicate keys and invalid values are fail-closed.
$seenKeys = @{}
$sessionState = $null
$currentAction = $null
$validStateValues  = @('open', 'closed')
$validActionValues = @('idle', 'session-start', 'task-planning', 'executing', 'session-end', 'task-close')

foreach ($line in ($frontmatter -split '\r?\n')) {
    if ([string]::IsNullOrWhiteSpace($line)) { continue }
    if ($line -match '^\s*#') { continue }

    if ($line -notmatch '^([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(.*)$') {
        [Console]::Error.WriteLine("")
        [Console]::Error.WriteLine("Cannot validate session state: docs/STATUS.md frontmatter contains invalid YAML.")
        [Console]::Error.WriteLine("  Offending line: '$($line.Trim())'")
        [Console]::Error.WriteLine("  Please ensure every frontmatter line uses 'key: value' format.")
        [Console]::Error.WriteLine("")
        exit 2
    }

    $key   = $Matches[1]
    $value = $Matches[2].Trim()

    if ($seenKeys.ContainsKey($key)) {
        [Console]::Error.WriteLine("")
        [Console]::Error.WriteLine("Cannot validate session state: docs/STATUS.md frontmatter has duplicate key '$key'.")
        [Console]::Error.WriteLine("")
        exit 2
    }
    $seenKeys[$key] = $value

    if ($key -eq 'session_state')  { $sessionState  = $value }
    if ($key -eq 'current_action') { $currentAction = $value }
}

# 5. Required field: session_state
if ($null -eq $sessionState) {
    [Console]::Error.WriteLine("")
    [Console]::Error.WriteLine("Cannot validate session state: docs/STATUS.md frontmatter is missing 'session_state'.")
    [Console]::Error.WriteLine("")
    exit 2
}
if ($sessionState -notin $validStateValues) {
    [Console]::Error.WriteLine("")
    [Console]::Error.WriteLine("Cannot validate session state: docs/STATUS.md 'session_state' has invalid value '$sessionState'.")
    [Console]::Error.WriteLine("  Allowed values: open, closed")
    [Console]::Error.WriteLine("")
    exit 2
}

# 6. Required field: current_action
if ($null -eq $currentAction) {
    [Console]::Error.WriteLine("")
    [Console]::Error.WriteLine("Cannot validate session state: docs/STATUS.md frontmatter is missing 'current_action'.")
    [Console]::Error.WriteLine("")
    exit 2
}
if ($currentAction -notin $validActionValues) {
    [Console]::Error.WriteLine("")
    [Console]::Error.WriteLine("Cannot validate session state: docs/STATUS.md 'current_action' has invalid value '$currentAction'.")
    [Console]::Error.WriteLine("  Allowed values: idle, session-start, task-planning, executing, session-end, task-close")
    [Console]::Error.WriteLine("")
    exit 2
}

# 7. Only act when session_state is open
if ($sessionState -ne 'open') { exit 0 }

# 8. Block only during session-end or task-close; allow all other states
if ($currentAction -eq 'session-end' -or $currentAction -eq 'task-close') {
    [Console]::Error.WriteLine("")
    [Console]::Error.WriteLine("Cannot stop: session close in progress (current_action: $currentAction).")
    [Console]::Error.WriteLine("Please complete the action before exiting:")
    [Console]::Error.WriteLine("  session-end -> follow docs/PROJECT_RULES.md Section: Session End")
    [Console]::Error.WriteLine("  task-close  -> follow docs/PROJECT_RULES.md Section: Task Close")
    [Console]::Error.WriteLine("")
    exit 2
}

# 9. Other states (executing, task-planning, idle, etc.) - allow exit
exit 0
