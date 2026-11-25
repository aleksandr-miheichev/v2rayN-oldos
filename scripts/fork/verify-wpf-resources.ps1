param(
    [Parameter(Mandatory)]
    [string]$AssemblyPath,
    [Parameter(Mandatory)]
    [string]$ResourceDesignerPath
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Reflection.Metadata

$designer = [IO.File]::ReadAllText((Resolve-Path -LiteralPath $ResourceDesignerPath).Path)
$lookups = [regex]::Matches($designer, '\bnew\s+(?:global::)?System\.Resources\.ResourceManager\s*\(\s*"(?<base>[^"\\]+)"\s*,')
if ($lookups.Count -ne 1) {
    throw "Expected one generated ResourceManager lookup in '$ResourceDesignerPath'."
}
$trayResources = $lookups[0].Groups['base'].Value + '.resources'

$assemblyFile = (Resolve-Path -LiteralPath $AssemblyPath).Path
$stream = [IO.File]::OpenRead($assemblyFile)
try {
    $pe = [System.Reflection.PortableExecutable.PEReader]::new($stream)
    try {
        $metadata = [System.Reflection.Metadata.PEReaderExtensions]::GetMetadataReader($pe)
        $names = foreach ($handle in $metadata.ManifestResources) {
            $metadata.GetString($metadata.GetManifestResource($handle).Name)
        }
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
