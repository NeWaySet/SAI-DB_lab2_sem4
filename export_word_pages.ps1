param(
  [Parameter(Mandatory=$true)][string]$DocxPath,
  [Parameter(Mandatory=$true)][string]$OutputDir
)

New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
Add-Type -AssemblyName System.Drawing

$word = New-Object -ComObject Word.Application
$word.Visible = $false
$word.DisplayAlerts = 0
$doc = $null

try {
  $doc = $word.Documents.Open($DocxPath, $false, $true)
  $doc.Repaginate()
  $pageCount = $doc.ComputeStatistics(2)
  Write-Output "pages $pageCount"

  $pane = $word.ActiveWindow.ActivePane
  for ($i = 1; $i -le $pageCount; $i++) {
    $page = $pane.Pages.Item($i)
    $bits = [byte[]]$page.EnhMetaFileBits
    $emfPath = Join-Path $OutputDir ("page-{0:D2}.emf" -f $i)
    $pngPath = Join-Path $OutputDir ("page-{0:D2}.png" -f $i)
    [System.IO.File]::WriteAllBytes($emfPath, $bits)

    $image = [System.Drawing.Image]::FromFile($emfPath)
    try {
      $scale = 2
      $bitmapWidth = [int]($image.Width * $scale)
      $bitmapHeight = [int]($image.Height * $scale)
      $bitmap = New-Object System.Drawing.Bitmap -ArgumentList $bitmapWidth, $bitmapHeight
      $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
      $graphics.Clear([System.Drawing.Color]::White)
      $graphics.InterpolationMode = [System.Drawing.Drawing2D.InterpolationMode]::HighQualityBicubic
      $graphics.SmoothingMode = [System.Drawing.Drawing2D.SmoothingMode]::HighQuality
      $graphics.DrawImage($image, 0, 0, $bitmap.Width, $bitmap.Height)
      $bitmap.Save($pngPath, [System.Drawing.Imaging.ImageFormat]::Png)
      $graphics.Dispose()
      $bitmap.Dispose()
    }
    finally {
      $image.Dispose()
    }
    Write-Output $pngPath
  }
}
finally {
  if ($doc -ne $null) { $doc.Close($false) | Out-Null }
  $word.Quit() | Out-Null
}
