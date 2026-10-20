import argparse
import csv
import importlib
import os
import random
import statistics
import threading
import time
import sys

from dataclasses import dataclass, field

from logger import (
    LoggerConcorrente,
    CONSULTA,
    GERACAO,
    FALHA,
    ENCERRAMENTO,
)

FILA = "FILA"
_FIM = object()


# =====================================================================
# ESTRUTURAS
# =====================================================================

@dataclass
class Requisicao:
    id: int
    pergunta: str
    produtor: str
    t_entrada: float = 0.0
    t_saida: float = 0.0


# =====================================================================
# FILA LIMITADA
# =====================================================================

class FilaLimitada:
    """
    Buffer circular limitado com semaforos e mutex.

    segura=True:
        protege a leitura e a escrita dos indices.

    segura=False:
        permite condicoes de corrida para fins experimentais.
    """

    def __init__(
        self,
        capacidade,
        segura=True,
        logger=None,
        janela_corrida=0.0005,
    ):
        if capacidade <= 0:
            raise ValueError("capacidade deve ser > 0")

        self.capacidade = capacidade
        self.segura = segura
        self.logger = logger
        self.janela = janela_corrida

        self.buffer = [None] * capacidade

        self.entrada = 0
        self.saida = 0
        self.tamanho = 0

        self.vagas = threading.Semaphore(capacidade)
        self.itens = threading.Semaphore(0)
        self.mutex = threading.Lock()

        self._lock_metricas = threading.Lock()

        self.amostras_tamanho = []
        self.tamanho_max = 0

        self.inseridos = 0
        self.retirados = 0
        self.rejeitados = 0

        self.bloqueios_produtor = 0
        self.esperas_consumidor = 0

    def _amostrar(self, tam):
        with self._lock_metricas:
            self.amostras_tamanho.append(tam)

            if tam > self.tamanho_max:
                self.tamanho_max = tam

    def _inserir(self, item, segura):
        if segura:
            with self.mutex:
                self.buffer[self.entrada] = item

                self.entrada = (
                    self.entrada + 1
                ) % self.capacidade

                self.tamanho += 1
                tam = self.tamanho

        else:
            # Secao desprotegida para demonstracao de corrida.
            pos = self.entrada

            time.sleep(self.janela)

            self.buffer[pos] = item

            self.entrada = (
                pos + 1
            ) % self.capacidade

            tam = self.tamanho

            time.sleep(self.janela)

            self.tamanho = tam + 1
            tam = self.tamanho

        self._amostrar(tam)

    def _remover(self, segura):
        if segura:
            with self.mutex:
                item = self.buffer[self.saida]
                self.buffer[self.saida] = None

                self.saida = (
                    self.saida + 1
                ) % self.capacidade

                self.tamanho -= 1
                tam = self.tamanho

        else:
            pos = self.saida

            time.sleep(self.janela)

            item = self.buffer[pos]
            self.buffer[pos] = None

            self.saida = (
                pos + 1
            ) % self.capacidade

            tam = self.tamanho

            time.sleep(self.janela)

            self.tamanho = tam - 1
            tam = self.tamanho

        self._amostrar(tam)

        return item

    def put(self, item, timeout=None, _forcar_segura=False):
        """
        Insere um item na fila.

        Retorna False se nao houver vaga dentro do timeout.
        Com timeout=None, aguarda indefinidamente por uma vaga.
        """

        if not self.vagas.acquire(blocking=False):
            with self._lock_metricas:
                self.bloqueios_produtor += 1

            if not self.vagas.acquire(timeout=timeout):
                with self._lock_metricas:
                    self.rejeitados += 1

                return False

        self._inserir(
            item,
            self.segura or _forcar_segura,
        )

        with self._lock_metricas:
            self.inseridos += 1

        self.itens.release()

        return True

    def get(self, timeout=None):
        """
        Retira um item da fila.

        Levanta TimeoutError se nenhum item ficar disponivel
        dentro do periodo de espera.
        """

        if not self.itens.acquire(blocking=False):
            with self._lock_metricas:
                self.esperas_consumidor += 1

            if not self.itens.acquire(timeout=timeout):
                raise TimeoutError

        item = self._remover(self.segura)

        with self._lock_metricas:
            self.retirados += 1

        self.vagas.release()

        return item


# =====================================================================
# CARGAS SIMULADAS
# =====================================================================

_calibracao = {}


def _iteracoes_cpu(custo):
    """Estima o numero de iteracoes para a carga CPU."""

    if "por_s" not in _calibracao:
        n = 2_000_000
        t0 = time.perf_counter()

        x = 0

        for _ in range(n):
            x += 1

        duracao = time.perf_counter() - t0

        _calibracao["por_s"] = (
            n / duracao if duracao > 0 else n
        )

    return int(_calibracao["por_s"] * custo)


def processar_simulado(
    req,
    custo=0.05,
    carga="io",
    logger=None,
):
    """Simula o processamento de uma requisicao."""

    t0 = time.perf_counter()

    if carga == "io":
        time.sleep(custo)

    else:
        x = 0

        for _ in range(_iteracoes_cpu(custo)):
            x += 1

    duracao = time.perf_counter() - t0

    if logger:
        logger.registrar(
            GERACAO,
            f"id: {req.id} simulado: {carga}",
            duracao=duracao,
        )

    return f"resposta simulada {req.id}"


def carregar_processador(spec):
    """Carrega uma funcao no formato modulo:funcao."""

    modulo, funcao = spec.split(":", 1)

    return getattr(
        importlib.import_module(modulo),
        funcao,
    )


def perguntas_sinteticas(n, seed=42):
    """Gera perguntas sinteticas para os experimentos."""

    termos = [
        "paginacao",
        "swap",
        "memoria virtual",
        "cache de paginas",
        "mutex",
        "semaforo",
        "deadlock",
        "starvation",
        "escalonador",
        "troca de contexto",
        "inode",
        "fsync",
        "embedding",
        "RAG",
        "janela de contexto",
        "indice vetorial",
        "mmap",
        "thrashing",
    ]

    modelos = [
        "o que e {t}",
        "explique {t}",
        "como funciona {t}",
        "qual a relacao entre {t} e {u}",
    ]

    rng = random.Random(seed)
    saida = []

    for _ in range(n):
        t, u = rng.sample(termos, 2)

        saida.append(
            rng.choice(modelos).format(t=t, u=u)
        )

    return saida


# =====================================================================
# CONFIGURACAO
# =====================================================================

@dataclass
class Config:
    trabalhadores: int = 2
    produtores: int = 2
    capacidade: int = 8
    requisicoes: int = 100

    modo: str = "seguro"
    carga: str = "io"

    custo: float = 0.05
    intervalo: float = 0.0

    timeout_put: float = None
    timeout_encerrar: float = 10.0

    perguntas: list = field(default=None)


def percentil(valores, p):
    """Calcula um percentil por interpolacao linear."""

    if not valores:
        return 0.0

    valores_ordenados = sorted(valores)

    k = (len(valores_ordenados) - 1) * p / 100

    base = int(k)

    seguinte = min(
        base + 1,
        len(valores_ordenados) - 1,
    )

    return (
        valores_ordenados[base]
        + (
            valores_ordenados[seguinte]
            - valores_ordenados[base]
        ) * (k - base)
    )


# =====================================================================
# EXECUCAO DO SERVIDOR
# =====================================================================

def executar(cfg, logger, processar=None):
    """
    Executa produtores e trabalhadores.

    O encerramento normal ocorre depois que todos os produtores
    terminam e os sinais de encerramento sao inseridos na fila.

    O timeout de encerramento e usado para registrar trabalhadores
    que demoram a finalizar. Ele nao cancela operacoes em andamento.
    """

    if cfg.trabalhadores <= 0:
        raise ValueError("trabalhadores deve ser > 0")

    if cfg.produtores <= 0:
        raise ValueError("produtores deve ser > 0")

    if cfg.capacidade <= 0:
        raise ValueError("capacidade deve ser > 0")

    if cfg.timeout_encerrar <= 0:
        raise ValueError("timeout_encerrar deve ser > 0")

    if processar is None:

        def processar(req):
            return processar_simulado(
                req,
                cfg.custo,
                cfg.carga,
                logger,
            )

    perguntas = (
        cfg.perguntas
        if cfg.perguntas is not None
        else perguntas_sinteticas(cfg.requisicoes)
    )

    fila = FilaLimitada(
        cfg.capacidade,
        segura=(cfg.modo == "seguro"),
        logger=logger,
    )

    lock_res = threading.Lock()

    aceitos = []
    processados = []
    esperas = []

    invalidos = [0]
    falhas = [0]

    ocupado = {}

    parar = threading.Event()

    logger.registrar(
        FILA,
        f"evento: inicio modo: {cfg.modo} "
        f"trabalhadores: {cfg.trabalhadores} "
        f"produtores: {cfg.produtores} "
        f"capacidade: {cfg.capacidade} "
        f"requisicoes: {len(perguntas)} "
        f"carga: {cfg.carga}",
    )

    # ----------------------------------------------------------
    # PRODUTORES
    # ----------------------------------------------------------

    def produtor(indice):
        nome = threading.current_thread().name

        for i in range(
            indice,
            len(perguntas),
            cfg.produtores,
        ):
            if parar.is_set():
                break

            req = Requisicao(
                id=i,
                pergunta=perguntas[i],
                produtor=nome,
                t_entrada=time.perf_counter(),
            )

            inserida = fila.put(
                req,
                timeout=cfg.timeout_put,
            )

            if inserida:
                with lock_res:
                    aceitos.append(i)

                logger.registrar(
                    CONSULTA,
                    f"evento: enfileirada id: {i} "
                    f"fila: {fila.tamanho}",
                )

            else:
                logger.registrar(
                    FALHA,
                    f"evento: fila_saturada id: {i} "
                    f"acao: rejeitada "
                    f"timeout_s: {cfg.timeout_put}",
                )

            if cfg.intervalo:
                time.sleep(cfg.intervalo)

    # ----------------------------------------------------------
    # TRABALHADORES
    # ----------------------------------------------------------

    def trabalhador():
        nome = threading.current_thread().name

        ocupado[nome] = 0.0

        while True:
            try:
                req = fila.get(timeout=0.5)

            except TimeoutError:
                if parar.is_set():
                    break

                continue

            if req is _FIM:
                break

            if not isinstance(req, Requisicao):
                with lock_res:
                    invalidos[0] += 1

                logger.registrar(
                    FALHA,
                    "evento: item_invalido conteudo: vazio",
                )

                continue

            req.t_saida = time.perf_counter()

            espera = req.t_saida - req.t_entrada

            t0 = time.perf_counter()

            try:
                processar(req)

            except Exception as e:
                with lock_res:
                    falhas[0] += 1

                logger.registrar(
                    FALHA,
                    f"evento: erro_processamento "
                    f"id: {req.id} "
                    f"erro: {type(e).__name__}",
                )

            finally:
                proc = time.perf_counter() - t0

                ocupado[nome] += proc

                with lock_res:
                    processados.append(req.id)
                    esperas.append(espera)

                logger.registrar(
                    FILA,
                    f"evento: processada id: {req.id} "
                    f"espera_s: {espera:.4f} "
                    f"proc_s: {proc:.4f} "
                    f"fila: {fila.tamanho}",
                )

        logger.registrar(
            ENCERRAMENTO,
            "evento: trabalhador_encerrado",
        )

    # ----------------------------------------------------------
    # INICIALIZACAO
    # ----------------------------------------------------------

    t_inicio = time.perf_counter()

    trab = [
        threading.Thread(
            target=trabalhador,
            name=f"Trabalhador-{i}",
        )
        for i in range(cfg.trabalhadores)
    ]

    prod = [
        threading.Thread(
            target=produtor,
            args=(i,),
            name=f"Produtor-{i}",
        )
        for i in range(cfg.produtores)
    ]

    for t in trab + prod:
        t.start()

    # Espera todos os produtores terminarem.
    for t in prod:
        t.join()

    # ----------------------------------------------------------
    # ENCERRAMENTO COORDENADO
    # ----------------------------------------------------------

    prazo = time.perf_counter() + cfg.timeout_encerrar

    sinais_inseridos = 0

    for _ in trab:
        restante = prazo - time.perf_counter()

        if restante <= 0:
            break

        if fila.put(
            _FIM,
            timeout=restante,
            _forcar_segura=True,
        ):
            sinais_inseridos += 1
        else:
            break

    for t in trab:
        restante = prazo - time.perf_counter()

        if restante <= 0:
            break

        t.join(timeout=restante)

    presos = [
        t.name
        for t in trab
        if t.is_alive()
    ]

    if presos:
        logger.registrar(
            FALHA,
            f"evento: encerramento_pendente "
            f"trabalhadores: {','.join(presos)}",
        )

        # Threads Python nao podem ser canceladas com seguranca
        # enquanto executam uma funcao de processamento.
        for t in trab:
            t.join()

    t_total = time.perf_counter() - t_inicio

    conjunto_aceitos = set(aceitos)

    contagem = {}

    for i in processados:
        contagem[i] = contagem.get(i, 0) + 1

    perdidos = len(
        conjunto_aceitos - set(contagem)
    )

    duplicados = sum(
        c - 1
        for c in contagem.values()
        if c > 1
    )

    amostras = fila.amostras_tamanho

    util = [
        v / t_total
        for v in ocupado.values()
    ] if t_total > 0 else [0.0]

    res = {
        "modo": cfg.modo,
        "carga": cfg.carga,
        "trabalhadores": cfg.trabalhadores,
        "produtores": cfg.produtores,
        "capacidade": cfg.capacidade,
        "requisicoes": len(perguntas),
        "custo_s": cfg.custo,

        "timeout_put_s": (
            cfg.timeout_put
            if cfg.timeout_put is not None
            else ""
        ),

        "aceitas": len(aceitos),
        "rejeitadas": fila.rejeitados,

        "processadas_unicas": len(contagem),
        "perdidas": perdidos,
        "duplicadas": duplicados,

        "invalidas": invalidos[0],
        "falhas_processamento": falhas[0],

        "tempo_total_s": round(t_total, 4),

        "vazao_req_s": (
            round(len(contagem) / t_total, 3)
            if t_total > 0
            else 0.0
        ),

        "espera_media_s": (
            round(statistics.mean(esperas), 4)
            if esperas
            else 0.0
        ),

        "espera_mediana_s": (
            round(statistics.median(esperas), 4)
            if esperas
            else 0.0
        ),

        "espera_p95_s": round(
            percentil(esperas, 95),
            4,
        ),

        "espera_max_s": (
            round(max(esperas), 4)
            if esperas
            else 0.0
        ),

        "fila_media": (
            round(statistics.mean(amostras), 2)
            if amostras
            else 0.0
        ),

        "fila_max": fila.tamanho_max,

        "bloqueios_produtor": fila.bloqueios_produtor,
        "esperas_consumidor": fila.esperas_consumidor,

        "utilizacao_media": round(
            statistics.mean(util),
            3,
        ),

        "contador_final": fila.tamanho,

        "sinais_encerramento": sinais_inseridos,

        "encerramento_forcado": bool(presos),
    }

    logger.registrar(
        FILA,
        "evento: resumo "
        + " ".join(
            f"{k}: {v}"
            for k, v in res.items()
        ),
    )

    return res


# =====================================================================
# CSV E EXIBICAO
# =====================================================================

def salvar_csv(caminho, linhas):
    if not linhas:
        return

    novo = not os.path.exists(caminho)

    os.makedirs(
        os.path.dirname(caminho) or ".",
        exist_ok=True,
    )

    with open(
        caminho,
        "a",
        newline="",
        encoding="utf-8",
    ) as arquivo:
        escritor = csv.DictWriter(
            arquivo,
            fieldnames=list(linhas[0].keys()),
        )

        if novo:
            escritor.writeheader()

        escritor.writerows(linhas)


def imprimir(res):
    print(
        f"\n=== modo={res['modo']} "
        f"carga={res['carga']} "
        f"trabalhadores={res['trabalhadores']} "
        f"produtores={res['produtores']} "
        f"capacidade={res['capacidade']} ==="
    )

    print(
        f"aceitas={res['aceitas']} "
        f"rejeitadas={res['rejeitadas']} "
        f"processadas={res['processadas_unicas']} "
        f"perdidas={res['perdidas']} "
        f"duplicadas={res['duplicadas']} "
        f"invalidas={res['invalidas']}"
    )

    print(
        f"falhas_processamento={res['falhas_processamento']} "
        f"tempo={res['tempo_total_s']}s "
        f"vazao={res['vazao_req_s']} req/s"
    )

    print(
        f"espera_media={res['espera_media_s']}s "
        f"p95={res['espera_p95_s']}s "
        f"espera_max={res['espera_max_s']}s"
    )

    print(
        f"fila_media={res['fila_media']} "
        f"fila_max={res['fila_max']} "
        f"bloqueios_produtor={res['bloqueios_produtor']} "
        f"utilizacao={res['utilizacao_media']}"
    )

    print(
        f"contador_final={res['contador_final']} "
        f"sinais_encerramento={res['sinais_encerramento']} "
        f"encerramento_forcado={res['encerramento_forcado']}"
    )

    if res["contador_final"] != 0:
        print(
            "ATENCAO: o contador da fila terminou diferente de zero."
        )

    if res["perdidas"] or res["duplicadas"] or res["invalidas"]:
        print(
            "FALHA DE CONSISTENCIA: "
            "verifique o buffer e as secoes criticas."
        )

    if res["rejeitadas"]:
        print(
            "FILA SATURADA: requisicoes rejeitadas "
            "por timeout de insercao."
        )

    if res["falhas_processamento"]:
        print(
            "ATENCAO: houve falhas durante o processamento."
        )


# =====================================================================
# FUNCAO PRINCIPAL
# =====================================================================

def main():
    ap = argparse.ArgumentParser(
        description=(
            "Fila de requisicoes do GenResearch-Servidor (Rose)"
        )
    )

    ap.add_argument("--trabalhadores", type=int, default=2)
    ap.add_argument("--produtores", type=int, default=2)
    ap.add_argument("--capacidade", type=int, default=8)
    ap.add_argument("--requisicoes", type=int, default=100)

    ap.add_argument(
        "--modo",
        choices=["seguro", "inseguro"],
        default="seguro",
    )

    ap.add_argument(
        "--carga",
        choices=["io", "cpu"],
        default="io",
    )

    ap.add_argument(
        "--custo",
        type=float,
        default=0.05,
        help="segundos por requisicao simulada",
    )

    ap.add_argument("--intervalo", type=float, default=0.0)
    ap.add_argument("--timeout-put", type=float, default=None)

    ap.add_argument(
        "--cenario",
        choices=["saturacao"],
        help="preset de falha controlada",
    )

    ap.add_argument(
        "--processador",
        help="modulo:funcao da Wanessa",
    )

    ap.add_argument(
        "--perguntas",
        help="arquivo .txt com uma pergunta por linha",
    )

    ap.add_argument("--log", default="logs/fila.log")

    ap.add_argument(
        "--csv",
        default="resultados/fila_execucoes.csv",
    )

    a = ap.parse_args()

    cfg = Config(
        trabalhadores=a.trabalhadores,
        produtores=a.produtores,
        capacidade=a.capacidade,
        requisicoes=a.requisicoes,
        modo=a.modo,
        carga=a.carga,
        custo=a.custo,
        intervalo=a.intervalo,
        timeout_put=a.timeout_put,
    )

    if a.cenario == "saturacao":
        cfg.trabalhadores = 1
        cfg.produtores = 4
        cfg.capacidade = 4

        cfg.custo = 0.1
        cfg.timeout_put = 0.2

        cfg.requisicoes = min(
            cfg.requisicoes,
            60,
        )

    if cfg.carga == "cpu":
        _iteracoes_cpu(cfg.custo)

    if a.perguntas:
        with open(
            a.perguntas,
            encoding="utf-8",
        ) as arquivo:
            cfg.perguntas = [
                linha.strip()
                for linha in arquivo
                if linha.strip()
            ]

    logger = LoggerConcorrente(a.log)

    try:
        processar = (
            carregar_processador(a.processador)
            if a.processador
            else None
        )

        res = executar(
            cfg,
            logger,
            processar,
        )

    finally:
        logger.encerrar()

    salvar_csv(a.csv, [res])

    imprimir(res)

    print(
        f"\nlog: {a.log} | csv: {a.csv}"
    )


if __name__ == "__main__":
    sys.exit(main())