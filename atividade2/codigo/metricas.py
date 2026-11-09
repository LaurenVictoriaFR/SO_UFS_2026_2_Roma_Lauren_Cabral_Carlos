import argparse
import csv
import json
import math
import os
import re
import statistics
from collections import defaultdict
from datetime import datetime

# [2026-10-15 13:15:37.560] [NIVEL] [thread] mensagem [duracao: 0.0100s]
PADRAO_LINHA = re.compile(
    r"^\[(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d{3})?)\] "
    r"\[(?P<nivel>[^\]]+)\] \[(?P<thread>[^\]]+)\] "
    r"(?P<msg>.*?)(?: duracao: (?P<dur>[\d.]+)s)?$"
)


def ler_log(caminho):
    eventos = []
    invalidas = 0
    with open(caminho, "r", encoding="utf-8", errors="replace") as f:
        for numero, linha in enumerate(f, start=1):
            linha = linha.rstrip("\n")
            if not linha.strip():
                continue
            m = PADRAO_LINHA.match(linha)
            if not m:
                invalidas += 1
                continue
            formato = "%Y-%m-%d %H:%M:%S.%f" if "." in m["ts"] else "%Y-%m-%d %H:%M:%S"
            eventos.append({
                "arquivo": os.path.basename(caminho),
                "linha": numero,
                "ts": datetime.strptime(m["ts"], formato),
                "nivel": m["nivel"],
                "thread": m["thread"],
                "msg": m["msg"],
                "duracao": float(m["dur"]) if m["dur"] is not None else None,
            })
    return eventos, invalidas


def ler_csv(caminho):
    with open(caminho, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def percentil(valores, p):
    s = sorted(valores)
    k = (len(s) - 1) * p / 100
    baixo = math.floor(k)
    alto = min(baixo + 1, len(s) - 1)
    return s[baixo] + (s[alto] - s[baixo]) * (k - baixo)


def resumo_estatistico(valores):
    return {
        "n": len(valores),
        "media": statistics.mean(valores),
        "mediana": statistics.median(valores),
        "p95": percentil(valores, 95),
        "max": max(valores),
        "total": sum(valores),
    }


def resumo_log(eventos, invalidas):
    por_nivel = defaultdict(int)
    for e in eventos:
        por_nivel[e["nivel"]] += 1
    total = len(eventos) + invalidas
    linhas = [{"metrica": "linhas_total", "valor": total},
              {"metrica": "linhas_validas", "valor": len(eventos)},
              {"metrica": "linhas_corrompidas", "valor": invalidas},
              {"metrica": "threads_distintas", "valor": len({e["thread"] for e in eventos})}]
    for nivel in sorted(por_nivel):
        linhas.append({"metrica": f"eventos_{nivel}", "valor": por_nivel[nivel]})
    return linhas


def tempos_por_nivel(eventos):
    grupos = defaultdict(list)
    for e in eventos:
        if e["duracao"] is not None:
            grupos[e["nivel"]].append(e["duracao"])
    linhas = []
    for nivel in sorted(grupos):
        r = resumo_estatistico(grupos[nivel])
        linhas.append({"evento": nivel, "n": r["n"],
                       "media_s": round(r["media"], 6), "mediana_s": round(r["mediana"], 6),
                       "p95_s": round(r["p95"], 6), "max_s": round(r["max"], 6)})
    return linhas


def metricas_cache(eventos):
    acertos = semanticos = erros = substituicoes = 0
    for e in eventos:
        if e["nivel"] != "CACHE":
            continue
        if e["msg"].startswith("acerto"):
            acertos += 1
            if e["msg"].startswith("acerto_semantico"):
                semanticos += 1
        elif e["msg"].startswith("erro"):
            erros += 1
        elif e["msg"].startswith("substituicao"):
            substituicoes += 1
    consultas = acertos + erros
    return [{
        "consultas": consultas, "acertos": acertos, "acertos_semanticos": semanticos, "erros": erros,
        "taxa_acerto": round(acertos / consultas, 4) if consultas else 0.0,
        "taxa_erro": round(erros / consultas, 4) if consultas else 0.0,
        "substituicoes": substituicoes,
    }]


def utilizacao_threads(eventos):
    if not eventos:
        return []
    janela = (max(e["ts"] for e in eventos) - min(e["ts"] for e in eventos)).total_seconds()
    por_thread = defaultdict(lambda: {"eventos": 0, "ocupado": 0.0})
    for e in eventos:
        t = por_thread[e["thread"]]
        t["eventos"] += 1
        if e["nivel"] not in ("CONSULTA", "ENCERRAMENTO"):
            t["ocupado"] += e["duracao"] or 0.0
    linhas = []
    for nome in sorted(por_thread):
        t = por_thread[nome]
        linhas.append({"thread": nome, "eventos": t["eventos"],
                       "tempo_ocupado_s": round(t["ocupado"], 4),
                       "janela_s": round(janela, 4),
                       "utilizacao": round(t["ocupado"] / janela, 4) if janela > 0 else 0.0})
    return linhas


def resumo_mmap(linhas_csv):
    colunas = ["tempo_abertura", "tempo_leitura", "rss_delta_mb", "vsz_delta_mb", "maj_faults", "min_faults"]
    grupos = defaultdict(list)
    for r in linhas_csv:
        grupos[(int(r["tamanho_mb"]), r["metodo"], r["cache"])].append(r)
    saida = []
    for (tamanho, metodo, cache) in sorted(grupos):
        rs = grupos[(tamanho, metodo, cache)]
        linha = {"tamanho_mb": tamanho, "metodo": metodo, "cache": cache, "repeticoes": len(rs)}
        for c in colunas:
            valores = [float(r[c]) for r in rs]
            linha[f"{c}_media"] = round(statistics.mean(valores), 6)
            linha[f"{c}_desvio"] = round(statistics.pstdev(valores), 6)
        saida.append(linha)
    return saida


CAMPO_NUMERICO = re.compile(r"(\w+): (-?[\d.]+)")
TIPOS_FALHA = ("fila_saturada", "item_invalido", "erro_processamento", "encerramento_forcado")


def metricas_fila(eventos):
    esperas, processos, tamanhos = [], [], []
    falhas = {t: 0 for t in TIPOS_FALHA}
    for e in eventos:
        if e["nivel"] in ("FILA", "CONSULTA") and ("evento: processada" in e["msg"] or "evento: enfileirada" in e["msg"]):
            campos = {k: float(v) for k, v in CAMPO_NUMERICO.findall(e["msg"])}
            if "fila" in campos:
                tamanhos.append(campos["fila"])
            if "evento: processada" in e["msg"]:
                esperas.append(campos["espera_s"])
                processos.append(campos["proc_s"])
        elif e["nivel"] == "FALHA":
            for tipo in TIPOS_FALHA:
                if f"evento: {tipo}" in e["msg"]:
                    falhas[tipo] += 1
    if not esperas:
        return []
    r = resumo_estatistico(esperas)
    return [{
        "processadas": len(esperas),
        "espera_media_s": round(r["media"], 4), "espera_mediana_s": round(r["mediana"], 4),
        "espera_p95_s": round(r["p95"], 4), "espera_max_s": round(r["max"], 4),
        "processamento_medio_s": round(statistics.mean(processos), 4),
        "fila_media": round(statistics.mean(tamanhos), 2) if tamanhos else 0.0,
        "fila_max": max(tamanhos) if tamanhos else 0.0,
        **{f"falha_{t}": n for t, n in falhas.items()},
    }]


def resumo_c3(linhas_csv):
    colunas = ["vazao_req_s_media", "espera_p95_s_media", "fila_max_media", "utilizacao_media_media",
               "rejeitadas_media", "perdidas_media", "duplicadas_media", "invalidas_media",
               "falhas_processamento_media"]
    return [{"configuracao": r["configuracao"], "carga": r["carga"], "modo": r["modo"],
             "trabalhadores": r["trabalhadores"], "repeticoes": r["repeticoes"],
             **{c.replace("_media", ""): r.get(c, "") for c in colunas}} for r in linhas_csv]


def resumo_ingestao(caminhos):
    linhas = []
    for caminho in caminhos:
        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)
        linhas.append({"origem": os.path.basename(os.path.dirname(os.path.abspath(caminho))), **dados,
                       "bytes_indice_total": dados["bytes_db"] + dados["bytes_vetores"]})
    return linhas


def comparar_configuracoes(rotulos_logs):
    linhas = []
    for rotulo, caminho in rotulos_logs:
        eventos, invalidas = ler_log(caminho)
        c = metricas_cache(eventos)[0]
        geracao = next((t for t in tempos_por_nivel(eventos) if t["evento"] == "GERACAO"), None)
        janela = (max(e["ts"] for e in eventos) - min(e["ts"] for e in eventos)).total_seconds() if eventos else 0.0
        linhas.append({
            "configuracao": rotulo, "consultas_cache": c["consultas"], "taxa_acerto": c["taxa_acerto"],
            "acertos_semanticos": c["acertos_semanticos"], "substituicoes": c["substituicoes"],
            "geracao_media_s": geracao["media_s"] if geracao else "", "geracao_p95_s": geracao["p95_s"] if geracao else "",
            "threads": len({e["thread"] for e in eventos}), "janela_s": round(janela, 4), "linhas_corrompidas": invalidas,
        })
    return linhas


def resumo_c4(linhas_csv):
    grupos = defaultdict(list)
    for r in linhas_csv:
        grupos[(r["carga"], r["politica"], int(r["capacidade"]), float(r["limiar"]))].append(r)
    saida = []
    for (carga, politica, capacidade, limiar) in sorted(grupos):
        rs = grupos[(carga, politica, capacidade, limiar)]
        taxas = [float(r["taxa_acerto"]) for r in rs]
        saida.append({
            "carga": carga, "politica": politica, "capacidade": capacidade, "limiar": limiar, "repeticoes": len(rs),
            "taxa_acerto_media": round(statistics.mean(taxas), 4), "taxa_acerto_desvio": round(statistics.pstdev(taxas), 4),
            "acertos_semanticos_media": round(statistics.mean(float(r["acertos_semanticos"]) for r in rs), 1),
            "respostas_erradas_media": round(statistics.mean(float(r["respostas_erradas"]) for r in rs), 1),
            "substituicoes_media": round(statistics.mean(float(r["substituicoes"]) for r in rs), 1),
            "tempo_economizado_s_media": round(statistics.mean(float(r["tempo_economizado_s"]) for r in rs), 4),
        })
    return saida


def escrever_csv(caminho, linhas):
    if not linhas:
        return
    with open(caminho, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(linhas[0].keys()))
        w.writeheader()
        w.writerows(linhas)


def tabela_markdown(titulo, linhas):
    if not linhas:
        return f"## {titulo}\n\n(sem dados)\n\n"
    cab = list(linhas[0].keys())
    out = [f"## {titulo}", "", "| " + " | ".join(cab) + " |", "|" + "---|" * len(cab)]
    for l in linhas:
        out.append("| " + " | ".join(str(l[c]) for c in cab) + " |")
    return "\n".join(out) + "\n\n"


def graficos(saida, tempos, cache, mmap_resumo, c4_resumo=None, comparacao=None, c3_resumo=None):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print("matplotlib não instalado: gráficos não gerados (pip install matplotlib).")
        return

    if tempos:
        eventos = [t["evento"] for t in tempos]
        x = range(len(eventos))
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.bar([i - 0.2 for i in x], [t["media_s"] for t in tempos], 0.4, label="média")
        ax.bar([i + 0.2 for i in x], [t["p95_s"] for t in tempos], 0.4, label="p95")
        ax.set_xticks(list(x))
        ax.set_xticklabels(eventos)
        ax.set_ylabel("segundos")
        ax.set_title("Latência por tipo de evento")
        ax.legend()
        fig.tight_layout()
        fig.savefig(os.path.join(saida, "grafico_latencia.png"), dpi=150)
        plt.close(fig)

    if cache and cache[0]["consultas"]:
        c = cache[0]
        fig, ax = plt.subplots(figsize=(4, 4))
        ax.bar(["acertos", "erros"], [c["acertos"], c["erros"]], color=["#2e7d32", "#c62828"])
        ax.set_title(f"Cache: taxa de acerto {c['taxa_acerto']:.0%}")
        fig.tight_layout()
        fig.savefig(os.path.join(saida, "grafico_cache.png"), dpi=150)
        plt.close(fig)

    if mmap_resumo:
        tamanhos = sorted({r["tamanho_mb"] for r in mmap_resumo})
        combos = sorted({(r["metodo"], r["cache"]) for r in mmap_resumo})
        fig, ax = plt.subplots(figsize=(8, 4.5))
        largura = 0.8 / len(combos)
        for j, (metodo, cache_tipo) in enumerate(combos):
            ys = []
            for t in tamanhos:
                linha = next((r for r in mmap_resumo
                              if r["tamanho_mb"] == t and r["metodo"] == metodo and r["cache"] == cache_tipo), None)
                ys.append(linha["tempo_leitura_media"] if linha else 0)
            ax.bar([i + j * largura for i in range(len(tamanhos))], ys, largura, label=f"{metodo} ({cache_tipo})")
        ax.set_xticks([i + 0.4 - largura / 2 for i in range(len(tamanhos))])
        ax.set_xticklabels([f"{t} MB" for t in tamanhos])
        ax.set_yscale("log")
        ax.set_ylabel("tempo de leitura (s, escala log)")
        ax.set_title("Leitura convencional vs mmap")
        ax.legend()
        fig.tight_layout()
        fig.savefig(os.path.join(saida, "grafico_mmap.png"), dpi=150)
        plt.close(fig)

    if c4_resumo:
        cargas = sorted({r["carga"] for r in c4_resumo})
        fig, eixos = plt.subplots(1, len(cargas), figsize=(5 * len(cargas), 4), sharey=True, squeeze=False)
        for ax, carga in zip(eixos[0], cargas):
            series = sorted({(r["politica"], r["limiar"]) for r in c4_resumo if r["carga"] == carga})
            for politica, limiar in series:
                pts = sorted((r["capacidade"], r["taxa_acerto_media"]) for r in c4_resumo
                             if r["carga"] == carga and r["politica"] == politica and r["limiar"] == limiar)
                rotulo = f"{politica}, " + ("chave exata" if limiar == 0 else f"limiar {limiar}")
                ax.plot([p[0] for p in pts], [p[1] for p in pts], marker="o", label=rotulo)
            ax.set_title(carga)
            ax.set_xlabel("capacidade (entradas)")
        eixos[0][0].set_ylabel("taxa de acerto")
        eixos[0][-1].legend(fontsize=7)
        fig.tight_layout()
        fig.savefig(os.path.join(saida, "grafico_c4.png"), dpi=150)
        plt.close(fig)

    if c3_resumo:
        c3 = [r for r in c3_resumo if r["configuracao"].startswith("C3_")]
        if c3:
            fig, ax = plt.subplots(figsize=(6, 4))
            for carga in sorted({r["carga"] for r in c3}):
                pts = sorted((int(r["trabalhadores"]), float(r["vazao_req_s"])) for r in c3 if r["carga"] == carga)
                ax.plot([p[0] for p in pts], [p[1] for p in pts], marker="o", label=f"carga {carga}")
            ax.set_xlabel("trabalhadores")
            ax.set_ylabel("vazão (req/s)")
            ax.set_title("C3: vazão por número de trabalhadores")
            ax.legend()
            fig.tight_layout()
            fig.savefig(os.path.join(saida, "grafico_c3.png"), dpi=150)
            plt.close(fig)

    if comparacao:
        fig, ax = plt.subplots(figsize=(7, 4))
        ax.bar([c["configuracao"] for c in comparacao], [c["taxa_acerto"] for c in comparacao])
        ax.set_ylabel("taxa de acerto do cache")
        ax.set_title("Cache por configuração")
        plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
        fig.tight_layout()
        fig.savefig(os.path.join(saida, "grafico_comparacao.png"), dpi=150)
        plt.close(fig)


def main():
    ap = argparse.ArgumentParser(description="Métricas do GenResearch-Servidor")
    ap.add_argument("--log", nargs="*", default=[], help="um ou mais arquivos de log")
    ap.add_argument("--mmap", help="CSV gerado pelo mmap_experimento.py")
    ap.add_argument("--ingestao", nargs="*", default=[], help="estatisticas_ingestao.json (um ou mais)")
    ap.add_argument("--comparar", nargs="*", default=[], help="rotulo=arquivo.log, um por configuração")
    ap.add_argument("--c4", help="CSV gerado pelo experimento_c4.py")
    ap.add_argument("--c3", help="c3_resumo_*.csv gerado pelo experimento_c3.py")
    ap.add_argument("--saida", default="resultados_analise", help="pasta de saída")
    args = ap.parse_args()

    os.makedirs(args.saida, exist_ok=True)
    md = "# Métricas do GenResearch-Servidor\n\n"

    eventos, invalidas = [], 0
    for caminho in args.log:
        ev, inv = ler_log(caminho)
        eventos += ev
        invalidas += inv

    tempos = cache = []
    if args.log:
        resumo = resumo_log(eventos, invalidas)
        tempos = tempos_por_nivel(eventos)
        cache = metricas_cache(eventos)
        threads = utilizacao_threads(eventos)
        fila = metricas_fila(eventos)
        for nome, linhas, titulo in [
            ("log_resumo", resumo, "Integridade do log"),
            ("tempos_por_evento", tempos, "Tempo por tipo de evento"),
            ("cache", cache, "Cache"),
            ("fila", fila, "Fila de requisições"),
            ("threads", threads, "Utilização por thread"),
        ]:
            escrever_csv(os.path.join(args.saida, nome + ".csv"), linhas)
            md += tabela_markdown(titulo, linhas)

    mmap_resumo = []
    if args.mmap:
        mmap_resumo = resumo_mmap(ler_csv(args.mmap))
        escrever_csv(os.path.join(args.saida, "mmap_resumo.csv"), mmap_resumo)
        md += tabela_markdown("mmap vs leitura convencional", mmap_resumo)

    if args.ingestao:
        ingestao = resumo_ingestao(args.ingestao)
        escrever_csv(os.path.join(args.saida, "ingestao.csv"), ingestao)
        md += tabela_markdown("Ingestão e armazenamento", ingestao)

    comparacao = []
    if args.comparar:
        pares = [item.split("=", 1) for item in args.comparar]
        comparacao = comparar_configuracoes(pares)
        escrever_csv(os.path.join(args.saida, "comparacao_configuracoes.csv"), comparacao)
        md += tabela_markdown("Comparação entre configurações", comparacao)

    c4_resumo = []
    if args.c4:
        c4_resumo = resumo_c4(ler_csv(args.c4))
        escrever_csv(os.path.join(args.saida, "c4_resumo.csv"), c4_resumo)
        md += tabela_markdown("C4: cache compartilhado", c4_resumo)

    c3_resumo = []
    if args.c3:
        c3_resumo = resumo_c3(ler_csv(args.c3))
        escrever_csv(os.path.join(args.saida, "c3_resumo.csv"), c3_resumo)
        md += tabela_markdown("C3: concorrência e fila", c3_resumo)

    with open(os.path.join(args.saida, "resumo.md"), "w", encoding="utf-8") as f:
        f.write(md)
    graficos(args.saida, tempos, cache, mmap_resumo, c4_resumo, comparacao, c3_resumo)
    print(f"Resultados em '{args.saida}/' (resumo.md, CSVs e gráficos).")


if __name__ == "__main__":
    main()
