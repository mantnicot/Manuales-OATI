param(
    [Parameter(Mandatory = $true)][int]$Port,
    [Parameter(Mandatory = $true)][string]$OutPath
)

# Angular CLI rechaza UTF-8 con BOM (error InvalidSymbol en [1,1]).
$lines = @(
    '{',
    '  "/api": {',
    "    `"target`": `"http://127.0.0.1:$Port`",",
    '    "secure": false,',
    '    "changeOrigin": true',
    '  }',
    '}'
)
$text = ($lines -join "`n") + "`n"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($OutPath, $text, $utf8NoBom)
