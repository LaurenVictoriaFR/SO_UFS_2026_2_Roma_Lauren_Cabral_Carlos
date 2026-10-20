import argparse
import csv
import json
import os
import random
import subprocess
import sys
import time

try:
    import resource
except ImportError:
    resource = None

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingestao import Indice, TOPICOS


def ler_kb(caminho, chaves):
    valores = {}
    try:
        with open(caminho) as f:
            for linha in f:
                partes = linha.replace(":", " ").split()
                if partes and partes[0] in chaves:
                    valores[partes[0]] = int(partes[1])
    except OSError:
        pass
    return valores


def estado():
    st = ler_kb("/proc/self/status", ["VmRSS", "VmSize"])
    mem = ler_kb("/proc/meminfo", ["MemAvailable", "SwapTotal", "SwapFree"])
    if resource:
        uso = resource.getrusage(resource.RUSAGE_SELF)
        maj, minr = uso.ru_majflt, uso.ru_minflt
    else:
        maj = minr = 0
    return {"rss": st.get("VmRSS", 0), "vsz": st.get("VmSize", 0), "disp": mem.get("MemAvailable", 0),
            "swap": mem.get("SwapTotal", 0) - mem.get("SwapFree", 0), "maj": maj, "min": minr}


def consultas(n, semente):
    rng = random.Random(semente)
    termos = [t for lista in TOPICOS.values() for t in lista]
    return [f"o que e {rng.choice(termos)} e {rng.choice(termos)}" for _ in range(n)]


def trabalhador(pasta, usar_mmap, n_consultas):
    antes = estado()
    t0 = time.perf_counter()
    indice = Indice(pasta, usar_mmap=usar_mmap)
    carga = time.perf_counter() - t0

    latencias = []
    for consulta in consultas(n_consultas, 42):
        t = time.perf_counter()
        indice.buscar(consulta, k=3)
        latencias.append(time.perf_counter() - t)
    depois = estado()

    latencias.sort()
    p95 = latencias[min(len(latencias) - 1, int(0.95 * len(latencias)))]
    print(json.dumps({
        "tamanho_vetores_mb": round(os.path.getsize(os.path.join(pasta, "vetores.npy")) / 2**20, 2),
        "tempo_carga_s": round(carga, 4),
        "lat_media_s": round(sum(latencias) / len(latencias), 5),
        "lat_p95_s": round(p95, 5),
        "rss_delta_mb": round((depois["rss"] - antes["rss"]) / 1024, 2),
        "vsz_delta_mb": round((depois["vsz"] - antes["vsz"]) / 1024, 2),
        "maj_faults": depois["maj"] - antes["maj"],
        "min_faults": depois["min"] - antes["min"],
        "memavailable_mb": round(depois["disp"] / 1024, 1),
        "swap_usado_mb": round(depois["swap"] / 1024, 1),
    }))


def main():
    ap = argparse.ArgumentParser(description="Experimento C5: pressão de memória")
    ap.add_argument("--indices", nargs="+", default=["dados/pequeno", "dados/medio", "dados/grande"])
    ap.add_argument("--consultas", type=int, default=200)
    ap.add_argument("--repeticoes", type=int, default=3)
    ap.add_argument("--saida", default="resultados/c5.csv")
    ap.add_argument("--trabalhador", nargs=2, metavar=("PASTA", "MMAP"), help=argparse.SUPPRESS)
    args = ap.parse_args()

    if args.trabalhador:
        trabalhador(args.trabalhador[0], args.trabalhador[1] == "1", args.consultas)
        return

    linhas = []
    for pasta in args.indices:
        if not os.path.exists(os.path.join(pasta, "vetores.npy")):
            print(f"[aviso] índice não encontrado, pulando: {pasta}")
            continue
        for usar_mmap in (0, 1):
            for rep in range(1, args.repeticoes + 1):
                print(f"{pasta} | mmap={usar_mmap} | repetição {rep}/{args.repeticoes}", flush=True)
                saida = subprocess.run(
                    [sys.executable, os.path.abspath(__file__), "--trabalhador", pasta, str(usar_mmap),
                     "--consultas", str(args.consultas)],
                    capture_output=True, text=True, check=True).stdout
                linhas.append({"indice": pasta, "mmap": usar_mmap, "repeticao": rep, **json.loads(saida)})

    if not linhas:
        sys.exit("nenhum índice encontrado")
    os.makedirs(os.path.dirname(args.saida) or ".", exist_ok=True)
    with open(args.saida, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0]))
        w.writeheader()
        w.writerows(linhas)
    print(f"{len(linhas)} execuções gravadas em {args.saida}")


if __name__ == "__main__":
    main()
