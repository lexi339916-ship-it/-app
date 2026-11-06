$ErrorActionPreference = "Stop"
$w = New-Object -ComObject Word.Application
$w.Visible = $false
$w.DisplayAlerts = 0
$p = (Resolve-Path "课程设计报告_最新版.docx").Path
$doc = $w.Documents.Open($p)
$doc.Fields.Update() | Out-Null
if ($doc.TablesOfContents.Count -gt 0) { $doc.TablesOfContents.Item(1).Update() }
$doc.Repaginate()
$pages = $doc.ComputeStatistics(2)
Write-Output ("PAGES " + $pages)
$doc.Save()
$pdf = (Join-Path (Get-Location) "课程设计报告_最新版.pdf")
$doc.ExportAsFixedFormat($pdf, 17)
$doc.Close($false)
$w.Quit()
Write-Output ("PDF " + $pdf)
