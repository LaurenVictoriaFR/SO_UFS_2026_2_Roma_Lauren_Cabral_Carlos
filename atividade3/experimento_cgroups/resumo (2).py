#!/usr/bin/env python3
"""Atividade 3, Parte C: resumo e grafico das 6 execucoes.

Le  resultados/resultados.csv  (gerado por run_experimentos.sh) e escreve em analise/:
  - resumo_por_condicao.csv : consolidado por condicao (Tabela 2 do relatorio)
  - grafico_cpu_wall.png    : tempo de CPU x wall time (mediana, barras = min-max)

Uso (a partir da raiz do repositorio):
    python3 atividade3/experimento_cgroups/resumo.py
Dependencias: pandas, matplotlib.
"""
import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

AQUI = Path(__file__).resolve().parent
ENTRADA = Path(sys.argv[1]) if len(sys.argv) > 1 else AQUI / "resultados" / "resultados.csv"
SAIDA = AQUI / "analise"
SAIDA.mkdir(exist_ok=True)

df = pd.read_csv(ENTRADA)

# ---- verificacoes de validade (mesmo trabalho, nenhuma falha) ----
assert (df["status"] == "OK").all(), "ha execucao com status diferente de OK"
assert df["checksum"].nunique() == 1, "checksum difere entre execucoes: trabalho nao foi o mesmo"
assert df["iteracoes"].nunique() == 1, "N diferente entre execucoes"

# ---- colunas derivadas ----
df["throttled_s"] = df["throttled_usec_delta"] / 1e6
df["trabalho_mit_s"] = df["iteracoes"] / df["wall_s"] / 1e6
df["peak_mib"] = df["memory_peak"] / 2**20

# rotulo legivel a partir do cpu.max lido no contêiner (ex.: "C1 (0,5 CPU)")
def rotulo(cond: str) -> str:
    quota, periodo = df.loc[df["condicao"] == cond, "cpu_max"].iloc[0].split()
    return f"{cond} ({int(quota) / int(periodo):.1f} CPU)".replace(".", ",")

ordem = sorted(df["condicao"].unique())
nomes = {c: rotulo(c) for c in ordem}
g = df.groupby("condicao")

# ---- Tabela 2 ----
wall_med = g["wall_s"].median()
tab = pd.DataFrame({
    "wall_mediana_s": wall_med,
    "wall_min_s": g["wall_s"].min(),
    "wall_max_s": g["wall_s"].max(),
    "variacao_amplitude_mediana_pct": (g["wall_s"].max() - g["wall_s"].min()) / wall_med * 100,
    "wall_desvio_padrao_s": g["wall_s"].std(),
    "cpu_mediana_s": g["cpu_s"].median(),
    "trabalho_mediana_mit_s": g["trabalho_mit_s"].median(),
    "nr_throttled_mediana": g["nr_throttled_delta"].median(),
    "throttled_mediana_s": g["throttled_s"].median(),
}).loc[ordem]
tab.index = [nomes[c] for c in tab.index]
tab.index.name = "condicao"
tab.round(4).to_csv(SAIDA / "resumo_por_condicao.csv")

print(tab.round(3).T.to_string())
razao = wall_med[ordem[0]] / wall_med[ordem[1]]
print(f"\nRazao das medianas de wall ({ordem[0]}/{ordem[1]}): {razao:.2f}")

# ---- Grafico ----
def mediana_e_faixa(col):
    med = g[col].median().loc[ordem]
    return med, [(med - g[col].min().loc[ordem]).values, (g[col].max().loc[ordem] - med).values]

cpu, cpu_err = mediana_e_faixa("cpu_s")
wall, wall_err = mediana_e_faixa("wall_s")
thr = g["throttled_s"].median().loc[ordem]
nthr = g["nr_throttled_delta"].median().loc[ordem]

fig, ax = plt.subplots(figsize=(8, 5.2))
w = 0.36
pos = range(len(ordem))
b1 = ax.bar([i - w/2 for i in pos], cpu.values, w, yerr=cpu_err, capsize=5,
            color="#3b6fb6", label="Tempo de CPU")
b2 = ax.bar([i + w/2 for i in pos], wall.values, w, yerr=wall_err, capsize=5,
            color="#e07b39", label="Wall time")
for barras in (b1, b2):
    for b in barras:
        ax.text(b.get_x() + b.get_width()/2, b.get_height()/2,
                f"{b.get_height() + 1e-9:.2f} s".replace(".", ","),
                ha="center", va="center", color="white", fontweight="bold")
for i, c in enumerate(ordem):
    ax.text(i, wall[c] + wall_err[1][i] + 0.4,
            f"throttled ≈ {thr[c]:.2f} s\nnr_throttled = {nthr[c]:.0f}".replace(".", ","),
            ha="center", va="bottom", fontsize=9)

ax.set_xticks(list(pos))
ax.set_xticklabels([nomes[c] for c in ordem])
ax.set_ylabel("Tempo (s)")
ax.set_ylim(0, wall.max() * 1.3)
ax.set_title(f"Tempo de CPU × wall time por condição (N = {int(df['iteracoes'].iloc[0]):,})".replace(",", "."))
ax.grid(axis="y", linestyle="--", alpha=0.6)
ax.set_axisbelow(True)
ax.legend(loc="upper right")
fig.text(0.5, 0.005, "Barras = mediana de 3 repetições; barras de erro = mínimo–máximo.",
         ha="center", fontsize=8, style="italic")
plt.tight_layout(rect=(0, 0.03, 1, 1))
plt.savefig(SAIDA / "grafico_cpu_wall.png", dpi=200)
print(f"\nSalvo em {SAIDA}/")
