
import argparse
import csv
import time
from datetime import datetime

MEMINFO = ["MemTotal", "MemFree", "MemAvailable", "Cached", "SwapTotal", "SwapFree"]
VMSTAT = ["pgfault", "pgmajfault", "pswpin", "pswpout"]


def ler_chaves(caminho, chaves, separador=None):
    valores = {}
    with open(caminho, "r") as f:
        for linha in f:
            partes = linha.replace(":", " ").split(separador)
            if partes and partes[0] in chaves:
                valores[partes[0]] = int(partes[1])
    return valores


def amostrar(pid):
    linha = {"timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]}
    mem = ler_chaves("/proc/meminfo", MEMINFO)
    for c in MEMINFO:
        linha[c + "_kB"] = mem.get(c, 0)
    vm = ler_chaves("/proc/vmstat", VMSTAT)
    for c in VMSTAT:
        linha[c] = vm.get(c, 0)
    if pid is not None:
        try:
            st = ler_chaves(f"/proc/{pid}/status", ["VmRSS", "VmSize"])
            io = ler_chaves(f"/proc/{pid}/io", ["read_bytes", "write_bytes"])
            linha.update({"proc_VmRSS_kB": st.get("VmRSS", 0), "proc_VmSize_kB": st.get("VmSize", 0),
                          "proc_read_bytes": io.get("read_bytes", 0), "proc_write_bytes": io.get("write_bytes", 0)})
        except (FileNotFoundError, ProcessLookupError, PermissionError):
            return linha, False
    return linha, True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--pid", type=int, help="processo a acompanhar (opcional)")
    ap.add_argument("--intervalo", type=float, default=1.0, help="segundos entre amostras")
    ap.add_argument("--duracao", type=float, help="parar depois de N segundos (opcional)")
    ap.add_argument("--saida", default="amostras.csv")
    args = ap.parse_args()

    inicio = time.time()
    with open(args.saida, "w", newline="", encoding="utf-8") as f:
        escritor = None
        try:
            while True:
                linha, vivo = amostrar(args.pid)
                if escritor is None:
                    escritor = csv.DictWriter(f, fieldnames=list(linha.keys()))
                    escritor.writeheader()
                escritor.writerow(linha)
                f.flush()
                if not vivo or (args.duracao and time.time() - inicio >= args.duracao):
                    break
                time.sleep(args.intervalo)
        except KeyboardInterrupt:
            pass
    print(f"Amostras gravadas em {args.saida}")


if __name__ == "__main__":
    main()
