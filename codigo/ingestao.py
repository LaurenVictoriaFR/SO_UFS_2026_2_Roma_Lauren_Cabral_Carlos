import argparse
import json
import os
import random
import re
import sqlite3
import threading
import time
import unicodedata
import zlib

import numpy as np

DIM = 1024            # 128 gerava muita colisao (top-3 sem o termo em 8 de 48 buscas); 1024 reduz para 4
TAM_FRAGMENTO = 80    # palavras por fragmento
SOBREPOSICAO = 16     # palavras repetidas entre fragmentos vizinhos
SEED = 42

PALAVRAS_VAZIAS = {"o", "a", "os", "as", "um", "uma", "de", "do", "da", "dos", "das",
                   "que", "e", "em", "no", "na", "para", "por", "qual", "quais",
                   "como", "explique", "me", "fale", "sobre", "se", "com", "ao", "ou"}

# ---------------------------------------------------------------- corpus sintetico
TOPICOS = {
    "memoria_virtual": ["paginacao", "tabela de paginas", "TLB", "swap", "falta de pagina",
                        "memoria virtual", "quadro de pagina", "thrashing"],
    "cache_paginas": ["cache de paginas", "MemAvailable", "readahead", "writeback",
                      "dirty pages", "page cache", "posix_fadvise", "mmap"],
    "sincronizacao": ["mutex", "semaforo", "deadlock", "starvation", "condicao de corrida",
                      "monitor", "secao critica", "variavel de condicao"],
    "escalonamento": ["escalonador", "quantum", "round robin", "prioridade",
                      "troca de contexto", "preempcao", "fila de prontos", "CFS"],
    "armazenamento": ["sistema de arquivos", "inode", "journal", "ext4", "bloco de disco",
                      "fsync", "buffer de E/S", "SSD"],
    "ia_generativa": ["embedding", "RAG", "checkpoint", "janela de contexto", "token",
                      "indice vetorial", "lote", "inferencia"],
}
FRASES = [
    "O mecanismo de {a} influencia diretamente o comportamento de {b} em cargas reais.",
    "Quando {a} e saturado, o sistema operacional recorre a {b} para manter a estabilidade.",
    "Um servidor de IA depende de {a} e de {b} para sustentar a vazao esperada.",
    "A relacao entre {a} e {b} costuma ser a causa de gargalos dificeis de diagnosticar.",
    "Medir {a} sem observar {b} leva a conclusoes incompletas sobre o desempenho.",
    "Em sistemas concorrentes, {a} precisa ser coordenado com {b} para evitar inconsistencias.",
    "O custo de {a} aumenta de forma perceptivel quando {b} nao esta bem dimensionado.",
]


def gerar_corpus(n_docs, saida, palavras_por_doc=400, seed=SEED):
    """Gera n_docs arquivos .txt sinteticos e deterministicos (mesma seed => mesmo corpus)."""
    rng = random.Random(seed)
    pasta = os.path.join(saida, "docs")
    os.makedirs(pasta, exist_ok=True)
    for antigo in os.listdir(pasta):          # limpa docs/ de execucoes anteriores
        if antigo.startswith("doc_") and antigo.endswith(".txt"):
            os.remove(os.path.join(pasta, antigo))
    nomes = list(TOPICOS)
    total_bytes = 0
    for i in range(n_docs):
        topico = nomes[i % len(nomes)]
        termos = TOPICOS[topico]
        outros = [t for k, v in TOPICOS.items() if k != topico for t in v]
        palavras, paragrafos = 0, []
        while palavras < palavras_por_doc:
            frases = []
            for _ in range(rng.randint(3, 5)):
                a = rng.choice(termos)
                b = rng.choice(termos if rng.random() < 0.8 else outros)
                f = rng.choice(FRASES).format(a=a, b=b)
                frases.append(f)
                palavras += len(f.split())
            paragrafos.append(" ".join(frases))
        texto = f"Documento {i:05d} - Topico: {topico}\n\n" + "\n\n".join(paragrafos) + "\n"
        caminho = os.path.join(pasta, f"doc_{i:05d}.txt")
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(texto)
        total_bytes += len(texto.encode("utf-8"))
    return {"n_docs": n_docs, "bytes": total_bytes, "pasta": pasta}


# ---------------------------------------------------------------- texto e embeddings
def tokenizar(texto):
    """Normaliza (sem acento, minusculo), remove stopwords e aplica stemming leve."""
    t = unicodedata.normalize("NFD", texto.lower())
    t = "".join(c for c in t if unicodedata.category(c) != "Mn")
    saida = []
    for p in re.findall(r"\w+", t):
        if p in PALAVRAS_VAZIAS:
            continue
        if len(p) > 3 and p.endswith("ns"):
            p = p[:-2] + "m"
        elif len(p) > 3 and p.endswith("s"):
            p = p[:-1]
        saida.append(p)
    return saida


def embed(texto, dim=None):
    """Vetor simulado: hashing trick com sinal, normalizado (norma 1). Deterministico."""
    dim = dim or DIM
    v = np.zeros(dim, dtype=np.float32)
    for tok in tokenizar(texto):
        b = tok.encode("utf-8")
        h = zlib.crc32(b)
        sinal = 1.0 if zlib.crc32(b + b"#") & 1 else -1.0
        v[h % dim] += sinal
    n = np.linalg.norm(v)
    return v / n if n > 0 else v


def fragmentar(texto, tam=TAM_FRAGMENTO, sobreposicao=SOBREPOSICAO):
    """Divide em janelas de `tam` palavras com sobreposicao. Retorna (trecho, char_ini, char_fim)."""
    spans = [m.span() for m in re.finditer(r"\S+", texto)]
    passo = tam - sobreposicao
    saida = []
    for ini in range(0, len(spans), passo):
        janela = spans[ini:ini + tam]
        if not janela:
            break
        c0, c1 = janela[0][0], janela[-1][1]
        saida.append((texto[c0:c1], c0, c1))
        if ini + tam >= len(spans):
            break
    return saida


# ---------------------------------------------------------------- ingestao
ESQUEMA = """
CREATE TABLE IF NOT EXISTS documentos (
    doc_id INTEGER PRIMARY KEY, caminho TEXT, topico TEXT, n_bytes INTEGER, n_fragmentos INTEGER);
CREATE TABLE IF NOT EXISTS fragmentos (
    chunk_id INTEGER PRIMARY KEY, doc_id INTEGER, idx INTEGER, texto TEXT,
    n_palavras INTEGER, n_bytes INTEGER, char_ini INTEGER, char_fim INTEGER, linha_vetor INTEGER);
CREATE INDEX IF NOT EXISTS ix_frag_doc ON fragmentos(doc_id);
CREATE TABLE IF NOT EXISTS meta (chave TEXT PRIMARY KEY, valor TEXT);
"""


def ingerir(pasta_docs, saida, logger=None, dim=None):
    """Le .txt, fragmenta, gera vetores e persiste. Escrita unica e serializada (um escritor)."""
    dim = dim or DIM
    t0 = time.perf_counter()
    os.makedirs(saida, exist_ok=True)
    db_path = os.path.join(saida, "genresearch.db")
    vet_path = os.path.join(saida, "vetores.npy")
    if os.path.exists(db_path):
        os.remove(db_path)

    arquivos = sorted(f for f in os.listdir(pasta_docs) if f.endswith(".txt"))
    con = sqlite3.connect(db_path)
    con.executescript(ESQUEMA)
    vetores, bytes_corpus, chunk_id = [], 0, 0
    soma_bytes_frag = 0
    tempos_doc = []

    for doc_id, nome in enumerate(arquivos):
        t_doc = time.perf_counter()
        caminho = os.path.join(pasta_docs, nome)
        with open(caminho, "r", encoding="utf-8") as f:
            texto = f.read()
        n_bytes = len(texto.encode("utf-8"))
        bytes_corpus += n_bytes
        m = re.match(r"Documento \d+ - Topico: (\w+)", texto)
        topico = m.group(1) if m else "desconhecido"
        frags = fragmentar(texto)
        linhas = []
        for idx, (trecho, c0, c1) in enumerate(frags):
            nb = len(trecho.encode("utf-8"))
            soma_bytes_frag += nb
            linhas.append((chunk_id, doc_id, idx, trecho, len(trecho.split()), nb, c0, c1, len(vetores)))
            vetores.append(embed(trecho, dim))
            chunk_id += 1
        con.executemany("INSERT INTO fragmentos VALUES (?,?,?,?,?,?,?,?,?)", linhas)
        con.execute("INSERT INTO documentos VALUES (?,?,?,?,?)", (doc_id, nome, topico, n_bytes, len(frags)))
        dur_doc = time.perf_counter() - t_doc
        tempos_doc.append((nome, len(frags), n_bytes, dur_doc))
        if logger:
            logger.registrar("INGESTAO", f"doc: {nome} fragmentos: {len(frags)} bytes: {n_bytes}",
                             duracao=dur_doc)

    matriz = np.vstack(vetores).astype(np.float32) if vetores else np.zeros((0, dim), np.float32)
    np.save(vet_path, matriz)
    meta = {"dim": dim, "tam_fragmento": TAM_FRAGMENTO, "sobreposicao": SOBREPOSICAO,
            "tipo_embedding": "simulado_hashing_trick", "seed": SEED}
    con.executemany("INSERT INTO meta VALUES (?,?)", [(k, str(v)) for k, v in meta.items()])
    con.commit()
    con.close()

    with open(os.path.join(saida, "tempos_ingestao_por_doc.csv"), "w", encoding="utf-8") as f:
        f.write("documento,fragmentos,bytes,duracao_s\n")
        for nome, nf, nb, d in tempos_doc:
            f.write(f"{nome},{nf},{nb},{d:.6f}\n")

    dur = time.perf_counter() - t0
    est = {
        "n_documentos": len(arquivos), "bytes_corpus": bytes_corpus,
        "n_fragmentos": chunk_id,
        "tam_medio_fragmento_bytes": round(soma_bytes_frag / chunk_id, 1) if chunk_id else 0,
        "dim": dim, "bytes_db": os.path.getsize(db_path), "bytes_vetores": os.path.getsize(vet_path),
        "tempo_ingestao_s": round(dur, 4),
        "tempo_medio_por_doc_s": round(sum(t[3] for t in tempos_doc) / len(tempos_doc), 6) if tempos_doc else 0,
    }
    with open(os.path.join(saida, "estatisticas_ingestao.json"), "w", encoding="utf-8") as f:
        json.dump(est, f, indent=2)
    if logger:
        logger.registrar("INGESTAO", f"status: concluida fragmentos: {chunk_id}", duracao=dur)
    return est


# ---------------------------------------------------------------- interface p/ Wanessa
class Indice:
    """Somente leitura, seguro para varias threads (uma conexao SQLite por thread)."""

    def __init__(self, pasta, usar_mmap=False):
        self.pasta = pasta
        self.db_path = os.path.join(pasta, "genresearch.db")
        self.vetores = np.load(os.path.join(pasta, "vetores.npy"),
                               mmap_mode="r" if usar_mmap else None)
        self._local = threading.local()

    def _con(self):
        if not hasattr(self._local, "con"):
            self._local.con = sqlite3.connect(f"file:{self.db_path}?mode=ro", uri=True)
        return self._local.con

    def buscar(self, consulta, k=3):
        """Retorna ate k fragmentos: [{chunk_id, doc_id, texto, n_bytes, n_palavras, score}]"""
        if len(self.vetores) == 0:
            return []
        q = embed(consulta, self.vetores.shape[1])
        scores = np.asarray(self.vetores) @ q
        k = min(k, len(scores))
        top = np.argpartition(-scores, k - 1)[:k]
        top = top[np.argsort(-scores[top])]
        con = self._con()
        out = []
        for linha in top:
            r = con.execute("SELECT chunk_id, doc_id, texto, n_bytes, n_palavras "
                            "FROM fragmentos WHERE linha_vetor=?", (int(linha),)).fetchone()
            out.append({"chunk_id": r[0], "doc_id": r[1], "texto": r[2],
                        "n_bytes": r[3], "n_palavras": r[4], "score": float(scores[linha])})
        return out


# ---------------------------------------------------------------- CLI
if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    sub = ap.add_subparsers(dest="cmd", required=True)
    g = sub.add_parser("gerar"); g.add_argument("--docs", type=int, default=200); g.add_argument("--saida", required=True)
    i = sub.add_parser("ingerir"); i.add_argument("--corpus", required=True); i.add_argument("--saida", required=True)
    i.add_argument("--dim", type=int, default=DIM)
    b = sub.add_parser("buscar"); b.add_argument("--indice", required=True)
    b.add_argument("--consulta", required=True); b.add_argument("-k", type=int, default=3)
    a = ap.parse_args()

    if a.cmd == "gerar":
        print(json.dumps(gerar_corpus(a.docs, a.saida), indent=2))
    elif a.cmd == "ingerir":
        from logger import LoggerConcorrente
        logger = LoggerConcorrente("logs/ingestao.log")
        try:
            print(json.dumps(ingerir(a.corpus, a.saida, logger=logger, dim=a.dim), indent=2))
        finally:
            logger.encerrar()
    else:
        for r in Indice(a.indice).buscar(a.consulta, a.k):
            print(f"[{r['score']:.3f}] doc {r['doc_id']} chunk {r['chunk_id']}: {r['texto'][:110]}...")
