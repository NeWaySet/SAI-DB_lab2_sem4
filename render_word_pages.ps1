param(
    [Parameter(Mandatory = $true)][string]$DocPath,
    [Parameter(Mandatory = $true)][string]$OutputDir
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Force -Path $OutputDir | Out-Null
Get-ChildItem -Path $OutputDir -Filter "page-*.*" -File -ErrorAction SilentlyContinue | Remove-Item -Force

Add-Type -AssemblyName System.Drawing

$word = $null
$doc = $null
try {
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $doc = $word.Documents.Open($DocPath)
    $word.ActiveWindow.View.Type = 3
    $doc.Repaginate()

    $pages = $word.ActiveWindow.Panes.Item(1).Pages
    $count = $pages.Count
    for ($i = 1; $i -le $count; $i++) {
        $page = $pages.Item($i)
        $bits = $page.EnhMetaFileBits
        $emfPath = Join-Path $OutputDir ("page-{0}.emf" -f $i)
        $pngPath = Join-Path $OutputDir ("page-{0}.png" -f $i)
        [System.IO.File]::WriteAllBytes($emfPath, [byte[]]$bits)
        $image = [System.Drawing.Image]::FromFile($emfPath)
        try {
            $bitmap = New-Object System.Drawing.Bitmap($image.Width, $image.Height)
            $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
            try {
                $graphics.Clear([System.Drawing.Color]::White)
                $graphics.DrawImage($image, 0, 0, $image.Width, $image.Height)
                $bitmap.Save($pngPath, [System.Drawing.Imaging.ImageFormat]::Png)
            }
            finally {
                $graphics.Dispose()
                $bitmap.Dispose()
            }
        }
        finally {
            $image.Dispose()
        }
        Write-Output $pngPath
    }
    Write-Output ("pages {0}" -f $count)
}
finally {
    if ($doc -ne $null) {
        $doc.Close($false)
    }
    if ($word -ne $null) {
        $word.Quit()
    }
}
