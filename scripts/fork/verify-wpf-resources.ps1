param(
    [Parameter(Mandatory)]
    [string]$AssemblyPath
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Reflection.Metadata

$assemblyFile = (Resolve-Path -LiteralPath $AssemblyPath).Path
$stream = [IO.File]::OpenRead($assemblyFile)
try {
    $pe = [System.Reflection.PortableExecutable.PEReader]::new($stream)
    try {
        $metadata = [System.Reflection.Metadata.PEReaderExtensions]::GetMetadataReader($pe)
        $names = foreach ($handle in $metadata.ManifestResources) {
            $metadata.GetString($metadata.GetManifestResource($handle).Name)
        }
        $trayResources = 'v2rayN.Properties.Resources.resources'
        if ($trayResources -cnotin $names) {
            throw "WPF tray icon resource set '$trayResources' is missing from '$assemblyFile'. Found: $($names -join ', ')"
        }
        Write-Host "Verified WPF tray icon resource set in $assemblyFile"
    } finally {
        $pe.Dispose()
    }
} finally {
    $stream.Dispose()
}
