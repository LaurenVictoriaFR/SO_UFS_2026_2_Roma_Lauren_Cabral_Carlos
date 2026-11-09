import argparse
import csv
import itertools
import random
import time

from ingestao import Indice, TOPICOS
from cache import Cache, gerar_chave

TERMOS = sorted({t for lista in TOPICOS.values() for t in lista})
VARIANTES = ["O que é {t}?", "Explique {t}", "Fale sobre {t}", "O que é {t} no Linux?", "Explique {t} em detalhes"]


def carga_repetidas(rng, n=200, n_base=20):
    base = rng.sample(TERMOS, n_base)
    return [(f"O que é {t}?", t) for t in (rng.choice(base) for _ in range(n))]


def carga_reformuladas(rng, n=200, n_base=20):
    base = rng.sample(TERMOS, n_base)
    consultas = []
    for _ in range(n):
        t = rng.choice(base)
        consultas.append((rng.choice(VARIANTES).format(t=t), t))
    return consultas


def carga_distintas(rng, n=150):
    pares = list(itertools.combinations(TERMOS, 2))
    rng.shuffle(pares)
    return [(f"Qual a relação entre {a} e {b}?", f"{a}|{b}") for a, b in pares[:n]]


def carga_localidade(rng, n=200, n_quentes=8, p_quente=0.8):
    quentes = rng.sample(TERMOS, n_quentes)
    pares = list(itertools.combinations(TERMOS, 2))
    rng.shuffle(pares)
    frias = iter(pares)
    consultas = []
    for _ in range(n):
        if rng.random() < p_quente:
            t = rng.choice(quentes)
            consultas.append((f"O que é {t}?", t))
        else:
            a, b = next(frias)
            consultas.append((f"Qual a relação entre {a} e {b}?", f"{a}|{b}"))
    return consultas


CARGAS = {"repetidas": carga_repetidas, "reformuladas": carga_reformuladas, "distintas": carga_distintas,
          "localidade": carga_localidade}


def gerar_resposta(intencao, trechos, custo_geracao):
    time.sleep(custo_geracao)
    return f"resposta:{intencao}"


def executar(indice, consultas, capacidade, politica, limiar, custo_geracao):
    cache = Cache(capacidade, politica, limiar=limiar)
    respostas_erradas = 0
    inicio = time.perf_counter()
    for consulta, intencao in consultas:
        chave = gerar_chave(consulta)
        resposta = cache.get(chave)
        if resposta is None:
            trechos = indice.buscar(consulta, k=3)
            t0 = time.perf_counter()
            resposta = gerar_resposta(intencao, trechos, custo_geracao)
            cache.put(chave, resposta, custo=time.perf_counter() - t0)
        elif resposta != f"resposta:{intencao}":
            respostas_erradas += 1
    total = time.perf_counter() - inicio
    est = cache.estatisticas()
    return {
        "consultas": len(consultas),
        "acertos": est["acertos"],
        "acertos_semanticos": est["acertos_semanticos"],
        "respostas_erradas": respostas_erradas,
        "erros": est["erros"],
        "taxa_acerto": round(est["taxa_acerto"], 4),
        "substituicoes": est["substituicoes"],
        "tempo_total_s": round(total, 4),
        "tempo_economizado_s": round(est["tempo_economizado"], 4),
    }


def main():
    ap = argparse.ArgumentParser(description="Experimento C4: cache compartilhado")
    ap.add_argument("--indice", required=True, help="pasta do índice (genresearch.db + vetores.npy)")
    ap.add_argument("--saida", default="resultados_c4.csv")
    ap.add_argument("--repeticoes", type=int, default=3)
    ap.add_argument("--capacidades", type=int, nargs="+", default=[10, 50, 100])
    ap.add_argument("--politicas", nargs="+", default=["FIFO", "LRU"])
    ap.add_argument("--limiares", type=float, nargs="+", default=[0.0, 0.6, 0.8],
                    help="0 = chave exata (sem semelhança)")
    ap.add_argument("--custo-geracao", type=float, default=0.005, help="segundos simulados por geração")
    args = ap.parse_args()

    indice = Indice(args.indice)
    linhas = []
    for nome_carga, montar in CARGAS.items():
        for rep in range(1, args.repeticoes + 1):
            consultas = montar(random.Random(f"{nome_carga}-{rep}"))
            for capacidade, politica, limiar in itertools.product(args.capacidades, args.politicas, args.limiares):
                print(f"{nome_carga} rep {rep} | cap {capacidade} {politica} limiar {limiar}")
                resultado = executar(indice, consultas, capacidade, politica, limiar or None, args.custo_geracao)
                linhas.append({"carga": nome_carga, "repeticao": rep, "capacidade": capacidade,
                               "politica": politica, "limiar": limiar, **resultado})

    with open(args.saida, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
        w.writeheader()
        w.writerows(linhas)
    print(f"{len(linhas)} execuções gravadas em {args.saida}")


if __name__ == "__main__":
    main()
