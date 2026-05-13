# Encuentra el primer puerto TCP libre en loopback (prueba enlace real).
# Uso: powershell -File find-free-api-port.ps1
# Salida: número de puerto por stdout; código 1 si el rango está ocupado.

$start = 8000
$end = 8020

foreach ($p in $start..$end) {
    try {
        $listener = New-Object System.Net.Sockets.TcpListener ([System.Net.IPAddress]::Loopback, $p)
        $listener.Start()
        $listener.Stop()
        Write-Output $p
        exit 0
    } catch {
        continue
    }
}

[Console]::Error.WriteLine("OATI: no hay puerto libre entre $start y $end en 127.0.0.1.")
exit 1
