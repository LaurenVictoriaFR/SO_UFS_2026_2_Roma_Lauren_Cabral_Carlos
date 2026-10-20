import os
import time
import mmap
import resource
import csv
import gc


def obter_metricas_so():
    """Lê VmRSS e VmSize do /proc/self/status e as page faults."""
    vm_rss = 0.0
    vm_size = 0.0
    try:
        with open('/proc/self/status', 'r') as f:
            for linha in f:
                if linha.startswith('VmRSS:'):
                    vm_rss = int(linha.split()[1]) / 1024  # Em MB
                elif linha.startswith('VmSize:'):
                    vm_size = int(linha.split()[1]) / 1024  # Em MB
    except Exception:
        pass

    uso = resource.getrusage(resource.RUSAGE_SELF)
    return vm_rss, vm_size, uso.ru_majflt, uso.ru_minflt


def limpar_cache_so(fd):
    """Esfria o cache de páginas no Linux/WSL."""
    try:
        os.posix_fadvise(fd, 0, 0, os.POSIX_FADV_DONTNEED)
    except AttributeError:
        pass


def preparar_arquivo_teste(nome_arquivo, tamanho_mb):
    """Gera arquivos em bytes no tamanho especificado."""
    tamanho_bytes = tamanho_mb * 1024 * 1024
    if os.path.exists(nome_arquivo) and os.path.getsize(nome_arquivo) >= tamanho_bytes:
        return
    print(f"Gerando arquivo {nome_arquivo} ({tamanho_mb}MB)...")
    chunk = b"Sistemas Operacionais GenResearch IA " * 128
    with open(nome_arquivo, "wb") as f:
        escritos = 0
        while escritos < tamanho_bytes:
            f.write(chunk)
            escritos += len(chunk)


def executar_leitura(nome_arquivo, metodo, execucao_tipo):
    gc.collect()
    rss_antes, vsz_antes, maj_antes, min_antes = obter_metricas_so()

    if execucao_tipo == 'fria':
        fd_limpeza = os.open(nome_arquivo, os.O_RDONLY)
        limpar_cache_so(fd_limpeza)
        os.close(fd_limpeza)

    inicio_abertura = time.perf_counter()
    f = open(nome_arquivo, "rb")  # Ambos os metodos usam leitura binária
    fd = f.fileno()
    fim_abertura = time.perf_counter()
    tempo_abertura = fim_abertura - inicio_abertura

    inicio_leitura = time.perf_counter()

    if metodo == 'convencional':
        conteudo = f.read()
        _ = len(conteudo)
        # Obter métricas no momento de pico de consumo, antes de apagar a variável
        rss_depois, vsz_depois, maj_depois, min_depois = obter_metricas_so()
        del conteudo

    elif metodo == 'mmap':
        tamanho = os.path.getsize(nome_arquivo)
        mm = mmap.mmap(fd, 0, access=mmap.ACCESS_READ)
        # Toca numa página a cada 4KB sem copiar tudo para a RAM
        for i in range(0, tamanho, 4096):
            _ = mm[i:i + 1]
        # Obter métricas antes de fechar o mapeamento
        rss_depois, vsz_depois, maj_depois, min_depois = obter_metricas_so()
        mm.close()

    fim_leitura = time.perf_counter()
    tempo_leitura = fim_leitura - inicio_leitura
    f.close()

    return {
        "metodo": metodo,
        "cache": execucao_tipo,
        "tempo_abertura": f"{tempo_abertura:.6f}",
        "tempo_leitura": f"{tempo_leitura:.6f}",
        "rss_delta_mb": f"{(rss_depois - rss_antes):.2f}",
        "vsz_delta_mb": f"{(vsz_depois - vsz_antes):.2f}",
        "maj_faults": maj_depois - maj_antes,
        "min_faults": min_depois - min_antes
    }


def iniciar_experimentos():
    tamanhos_mb = [1, 100, 1000]
    repeticoes = 3
    resultados = []

    print("-" * 50)
    print("Iniciando Experimentos da Parte E (mmap vs read)")
    print("-" * 50)

    for tamanho in tamanhos_mb:
        nome_arquivo = f"corpus_simulado_{tamanho}MB.bin"
        preparar_arquivo_teste(nome_arquivo, tamanho)

        for rep in range(1, repeticoes + 1):
            print(f"-> Processando {tamanho}MB | Repeticao {rep}/3")

            res_conv_fria = executar_leitura(nome_arquivo, 'convencional', 'fria')
            res_conv_quente = executar_leitura(nome_arquivo, 'convencional', 'quente')

            res_mmap_fria = executar_leitura(nome_arquivo, 'mmap', 'fria')
            res_mmap_quente = executar_leitura(nome_arquivo, 'mmap', 'quente')

            for res in [res_conv_fria, res_conv_quente, res_mmap_fria, res_mmap_quente]:
                res['tamanho_mb'] = tamanho
                res['repeticao'] = rep
                resultados.append(res)

    # CSV dinâmico para evitar sobrescrever dados de múltiplas execuções
    timestamp_atual = int(time.time())
    csv_file = f"resultados_experimento_{timestamp_atual}.csv"
    with open(csv_file, "w", newline='', encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "tamanho_mb", "metodo", "cache", "repeticao",
            "tempo_abertura", "tempo_leitura", "rss_delta_mb",
            "vsz_delta_mb", "maj_faults", "min_faults"
        ])
        writer.writeheader()
        writer.writerows(resultados)

    print(f"\nExperimento concluido! Os dados brutos foram salvos em '{csv_file}'.")


if __name__ == "__main__":
    iniciar_experimentos()