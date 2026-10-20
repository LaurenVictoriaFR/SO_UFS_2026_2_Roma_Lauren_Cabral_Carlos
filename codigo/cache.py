import re
import threading
import unicodedata

from ingestao import embed

CACHE = "CACHE"

PALAVRAS_VAZIAS = {"o", "a", "os", "as", "um", "uma", "de", "do", "da", "dos", "das",
                   "que", "e", "em", "no", "na", "para", "por", "qual", "quais",
                   "como", "explique", "me", "fale", "sobre"}


class Chave:
    def __init__(self, pergunta):
        self.pergunta = pergunta
        self.palavras = _palavras_chave(pergunta)
        self._vetor = None

    @property
    def vetor(self):
        if self._vetor is None:
            self._vetor = embed(self.pergunta)
        return self._vetor

    def __hash__(self):
        return hash(self.palavras)

    def __eq__(self, outra):
        return isinstance(outra, Chave) and self.palavras == outra.palavras

    def __repr__(self):
        return f"Chave({sorted(self.palavras)})"


def _palavras_chave(pergunta):
    texto = unicodedata.normalize("NFD", pergunta.lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    palavras = set()
    for p in re.findall(r"\w+", texto):
        if p in PALAVRAS_VAZIAS:
            continue
        if len(p) > 3 and p.endswith("ns"):
            p = p[:-2] + "m"
        elif len(p) > 3 and p.endswith("s"):
            p = p[:-1]
        palavras.add(p)
    return frozenset(palavras)


def gerar_chave(pergunta):
    return Chave(pergunta)


class Cache:
    def __init__(self, capacidade, politica="LRU", logger=None, limiar=None):
        if capacidade <= 0:
            raise ValueError("capacidade deve ser maior que zero")
        if politica not in ("LRU", "FIFO"):
            raise ValueError("politica deve ser 'LRU' ou 'FIFO'")
        if limiar is not None and not 0 < limiar <= 1:
            raise ValueError("limiar deve estar entre 0 e 1")
        self.capacidade = capacidade
        self.politica = politica
        self.logger = logger
        self.limiar = limiar
        self.dados = {}
        self.lock = threading.Lock()
        self.acertos = 0
        self.acertos_semanticos = 0
        self.erros = 0
        self.substituicoes = 0
        self.tempo_economizado = 0.0

    def _localizar(self, chave):
        if chave in self.dados:
            return chave, 1.0
        if self.limiar is None:
            return None, 0.0
        melhor, melhor_score = None, -1.0
        for existente in self.dados:
            score = float(existente.vetor @ chave.vetor)
            if score > melhor_score:
                melhor, melhor_score = existente, score
        if melhor_score >= self.limiar:
            return melhor, melhor_score
        return None, melhor_score

    def get(self, chave):
        with self.lock:
            achada, score = self._localizar(chave)
            if achada is not None:
                if self.politica == "LRU":
                    self.dados[achada] = self.dados.pop(achada)
                resposta, custo = self.dados[achada]
                self.acertos += 1
                self.tempo_economizado += custo
                semantico = achada != chave
                if semantico:
                    self.acertos_semanticos += 1
                resultado = resposta
            else:
                self.erros += 1
                resultado = None
        if resultado is None:
            self._registrar(f"erro chave: {sorted(_palavras(chave))}")
        else:
            tipo = "acerto_semantico" if semantico else "acerto"
            self._registrar(f"{tipo} chave: {sorted(_palavras(chave))} similaridade: {score:.3f}")
        return resultado

    def put(self, chave, resposta, custo=0.0):
        removida = None
        with self.lock:
            if chave in self.dados:
                del self.dados[chave]
            elif len(self.dados) >= self.capacidade:
                removida = next(iter(self.dados))
                del self.dados[removida]
                self.substituicoes += 1
            self.dados[chave] = (resposta, custo)
        if removida is not None:
            self._registrar(f"substituicao removida: {sorted(_palavras(removida))}")

    def estatisticas(self):
        with self.lock:
            total = self.acertos + self.erros
            return {
                "politica": self.politica,
                "capacidade": self.capacidade,
                "limiar": self.limiar,
                "entradas": len(self.dados),
                "acertos": self.acertos,
                "acertos_semanticos": self.acertos_semanticos,
                "erros": self.erros,
                "taxa_acerto": self.acertos / total if total else 0.0,
                "substituicoes": self.substituicoes,
                "tempo_economizado": self.tempo_economizado,
            }

    def _registrar(self, mensagem):
        if self.logger is not None:
            self.logger.registrar(CACHE, mensagem)


def _palavras(chave):
    return getattr(chave, "palavras", chave)
