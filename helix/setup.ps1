param([string]$JdkHome = "")
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$info = Get-Content (Join-Path $PSScriptRoot 'provenance.json') -Raw | ConvertFrom-Json
if (-not $JdkHome -and $env:JAVA_HOME -and (Test-Path (Join-Path $env:JAVA_HOME 'bin\javac.exe'))) { $JdkHome = $env:JAVA_HOME }
if (-not $JdkHome) {
    $cache = Join-Path $root '.tools\java17'
    New-Item -ItemType Directory -Path $cache -Force | Out-Null
    $archive = Join-Path $cache 'jdk.zip'
    if (-not (Test-Path $archive)) { Invoke-WebRequest -Uri $info.java.download_url -OutFile $archive }
    if ((Get-FileHash -LiteralPath $archive -Algorithm SHA256).Hash.ToLowerInvariant() -ne $info.java.archive_sha256) { throw 'JDK archive checksum mismatch.' }
    $JdkHome = Join-Path $cache 'jdk-17.0.20.1+1'
    if (-not (Test-Path (Join-Path $JdkHome 'bin\javac.exe'))) { Expand-Archive -LiteralPath $archive -DestinationPath $cache -Force }
}
$javac = Join-Path $JdkHome 'bin\javac.exe'
if (-not (Test-Path $javac)) { throw 'A Windows JDK with javac is required to build the helper.' }
$classes = Join-Path $PSScriptRoot 'build'
New-Item -ItemType Directory -Path $classes -Force | Out-Null
& $javac --release 17 -d $classes -sourcepath (Join-Path $PSScriptRoot 'LibLaserCut-source\src\main\java') (Join-Path $PSScriptRoot 'src\PCBHelixJob.java')
if ($LASTEXITCODE -ne 0) { throw 'Laser helper compilation failed.' }
$runtime = Join-Path $PSScriptRoot 'java'
if (-not (Test-Path (Join-Path $runtime 'bin\java.exe'))) {
    & (Join-Path $JdkHome 'bin\jlink.exe') --add-modules ($info.java.runtime_modules -join ',') --strip-debug --no-header-files --no-man-pages --output $runtime
    if ($LASTEXITCODE -ne 0) { throw 'Java runtime creation failed.' }
}
Write-Output 'Offline laser helper and private Java runtime are ready. No machine connection was made.'
