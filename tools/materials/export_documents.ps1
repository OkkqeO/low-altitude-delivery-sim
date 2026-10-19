param([switch]$OnlyForms)
$ErrorActionPreference = 'Stop'
$materialRoot = $PSScriptRoot
while (-not (Test-Path -LiteralPath (Join-Path $materialRoot 'engine.py'))) { $materialRoot = Split-Path -Parent $materialRoot }
$materialDocx = @()
if (-not $OnlyForms) { $materialDocx += Join-Path $materialRoot '参赛材料/主报告/主报告_面向园区末端配送的低空风险仿真与起降场选址系统.docx' }
$materialDocx += Join-Path $materialRoot '参赛材料/独立表单/作品信息表.docx'
$materialDocx += Join-Path $materialRoot '参赛材料/独立表单/诚信承诺书.docx'
$materialWord = $null
try {
  $materialWord = New-Object -ComObject Word.Application
  $materialWord.Visible = $false
  $materialWord.DisplayAlerts = 0
  foreach ($materialPath in $materialDocx) {
    $materialDocument = $null
    try {
      $materialDocument = $materialWord.Documents.Open($materialPath, $false, $true)
      [void]$materialDocument.Fields.Update()
      $materialDocument.Repaginate()
      $materialDocument.ExportAsFixedFormat([IO.Path]::ChangeExtension($materialPath,'.pdf'),17)
      $materialPages = $materialDocument.ComputeStatistics(2)
      Write-Output ($materialPath + ': ' + $materialPages + ' pages')
      if ($materialPath -match '主报告') {
        $materialRecords = @()
        for ($materialN=1; $materialN -le $materialPages; $materialN++) {
          $materialBegin=$materialDocument.GoTo(1,1,$materialN).Start
          if ($materialN -lt $materialPages) { $materialEnd=$materialDocument.GoTo(1,1,($materialN+1)).Start } else { $materialEnd=$materialDocument.Content.End }
          $materialRecords += [PSCustomObject]@{page=$materialN;text=$materialDocument.Range($materialBegin,$materialEnd).Text}
        }
        $materialRecords | ConvertTo-Json -Depth 4 | Set-Content -LiteralPath (Join-Path $PSScriptRoot 'word-pages.json') -Encoding utf8
      }
    } finally { if ($null -ne $materialDocument) { $materialDocument.Close(0); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($materialDocument) } }
  }
} finally { if ($null -ne $materialWord) { $materialWord.Quit(); [void][Runtime.InteropServices.Marshal]::FinalReleaseComObject($materialWord) } }
