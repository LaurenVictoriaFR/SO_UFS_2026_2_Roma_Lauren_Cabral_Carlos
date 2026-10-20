import argparse
import os
import platform
import statistics
import sys
import time

from fila import Config, executar, salvar_csv, carregar_processador, _iteracoes_cpu
from logger import LoggerConcorrente


METRICAS = [
    "tempo_total_s",
    "vazao_req_s",
    "espera_media_s",
    "espera_p95_s",
    "fila_media",
    "fila_max",
    "utilizacao_media",
    "rejeitadas",
    "perdidas",
    "duplicadas",
    "invalidas",
    "falhas_processamento",
    "contador_final",
]


def main():
    ap = argparse.ArgumentParser(
        description="Experimento de concorrência, capacidade de fila e falhas controladas."
    )

    ap.add_argument(
        "--repeticoes",
        type=int,
        default=3,
        help="Quantidade de repetições por configuração."
    )

    ap.add_argument(
        "--trabalhadores",
        type=int,
        nargs="+",
        default=[1, 2, 4],
        help="Quantidades de trabalhadores."
    )

    ap.add_argument(
        "--capacidades",
        type=int,
        nargs="+",
        default=[4, 8, 16],
        help="Capacidades da fila."
    )

    ap.add_argument(
        "--produtores",
        type=int,
        nargs="+",
        default=[1, 2, 4],
        help="Quantidades de produtores."
    )

    ap.add_argument(
        "--requisicoes",
        type=int,
        default=80,
        help="Quantidade de requisições por configuração."
    )

    ap.add_argument(
        "--custo",
        type=float,
        default=0.05,
        help="Custo de processamento utilizado na simulação."
    )

    ap.add_argument(
        "--processador",
        help="Processador real no formato modulo:funcao; sem isso usa carga simulada."
    )

    ap.add_argument(
        "--sem-falhas",
        action="store_true",
        help="Não executa os cenários de falha controlada."
    )

    a = ap.parse_args()

    if a.repeticoes < 1:
        ap.error("--repeticoes deve ser maior ou igual a 1.")

    if a.requisicoes < 1:
        ap.error("--requisicoes deve ser maior ou igual a 1.")

    if any(valor < 1 for valor in a.trabalhadores):
        ap.error("Todos os valores de --trabalhadores devem ser positivos.")

    if any(valor < 1 for valor in a.produtores):
        ap.error("Todos os valores de --produtores devem ser positivos.")

    if any(valor < 1 for valor in a.capacidades):
        ap.error("Todas as capacidades devem ser positivas.")

    if a.custo < 0:
        ap.error("--custo não pode ser negativo.")

    ts = time.strftime("%Y%m%d_%H%M%S")
    pasta_logs = f"logs/c3_{ts}"

    os.makedirs("resultados", exist_ok=True)
    os.makedirs(pasta_logs, exist_ok=True)

    processar = carregar_processador(a.processador) if a.processador else None

    reiniciar_cache = (
        getattr(sys.modules.get(processar.__module__), "reiniciar_cache", None)
        if processar
        else None
    )

    cargas = ["real"] if processar else ["io", "cpu"]

    if "cpu" in cargas:
        _iteracoes_cpu(a.custo)

    # Cenários principais:
    # combinações de carga, capacidade, trabalhadores e produtores.
    cenarios = []

    for carga in cargas:
        for capacidade in a.capacidades:
            for trabalhadores in a.trabalhadores:
                for produtores in a.produtores:

                    rotulo = (
                        f"C3_{carga}"
                        f"_w{trabalhadores}"
                        f"_p{produtores}"
                        f"_cap{capacidade}"
                    )

                    configuracao = Config(
                        trabalhadores=trabalhadores,
                        produtores=produtores,
                        capacidade=capacidade,
                        requisicoes=a.requisicoes,
                        carga=carga if carga != "real" else "io",
                        custo=a.custo,
                        timeout_encerrar=3600.0 if carga == "real" else 10.0,
                    )

                    cenarios.append((rotulo, configuracao))

    # Cenários de falhas controladas.
    # Mantêm suas configurações específicas para garantir
    # que as condições de concorrência e saturação sejam testadas.
    if not a.sem_falhas:

        cenarios.append(
            (
                "D_corrida_sem_mutex",
                Config(
                    trabalhadores=4,
                    produtores=4,
                    capacidade=8,
                    requisicoes=200,
                    modo="inseguro",
                    custo=0.005,
                ),
            )
        )

        cenarios.append(
            (
                "D_corrida_com_mutex",
                Config(
                    trabalhadores=4,
                    produtores=4,
                    capacidade=8,
                    requisicoes=200,
                    modo="seguro",
                    custo=0.005,
                ),
            )
        )

        cenarios.append(
            (
                "C6_fila_saturada",
                Config(
                    trabalhadores=1,
                    produtores=4,
                    capacidade=4,
                    requisicoes=60,
                    custo=0.1,
                    timeout_put=0.2,
                ),
            )
        )

    # Executa todas as configurações e suas repetições.
    bruto = []

    for rotulo, configuracao in cenarios:

        usa_real = processar is not None and rotulo.startswith("C3_")

        for repeticao in range(1, a.repeticoes + 1):

            print(
                f"-> {rotulo} | repetição {repeticao}/{a.repeticoes}",
                flush=True,
            )

            caminho_log = os.path.join(
                pasta_logs,
                f"{rotulo}_r{repeticao}.log",
            )

            if usa_real and reiniciar_cache:
                reiniciar_cache()

            logger = LoggerConcorrente(caminho_log)

            try:
                resultado = executar(
                    configuracao,
                    logger,
                    processar if usa_real else None,
                )
            finally:
                logger.encerrar()

            bruto.append(
                {
                    "configuracao": rotulo,
                    "repeticao": repeticao,
                    "horario": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "python": platform.python_version(),
                    "kernel": platform.release(),
                    **resultado,
                }
            )

    # Salva os dados brutos.
    arquivo_bruto = f"resultados/c3_bruto_{ts}.csv"
    salvar_csv(arquivo_bruto, bruto)

    # Calcula média e desvio padrão para cada configuração.
    resumo = []

    for rotulo, configuracao in cenarios:

        resultados_configuracao = [
            resultado
            for resultado in bruto
            if resultado["configuracao"] == rotulo
        ]

        if not resultados_configuracao:
            continue

        primeira_linha = resultados_configuracao[0]

        linha = {
            "configuracao": rotulo,
            "trabalhadores": getattr(
                configuracao, "trabalhadores", primeira_linha.get("trabalhadores")
            ),
            "produtores": getattr(
                configuracao, "produtores", primeira_linha.get("produtores")
            ),
            "capacidade": getattr(
                configuracao, "capacidade", primeira_linha.get("capacidade")
            ),
            "carga": primeira_linha.get("carga"),
            "modo": primeira_linha.get("modo"),
            "repeticoes": len(resultados_configuracao),
        }

        for metrica in METRICAS:

            valores = [
                float(resultado[metrica])
                for resultado in resultados_configuracao
                if resultado.get(metrica) is not None
            ]

            if valores:
                linha[f"{metrica}_media"] = round(
                    statistics.mean(valores), 4
                )

                linha[f"{metrica}_desvio"] = round(
                    statistics.pstdev(valores), 4
                )
            else:
                linha[f"{metrica}_media"] = None
                linha[f"{metrica}_desvio"] = None

        resumo.append(linha)

    # Salva o resumo.
    arquivo_resumo = f"resultados/c3_resumo_{ts}.csv"
    salvar_csv(arquivo_resumo, resumo)

    # Exibe um resumo no terminal.
    print(
        f"\n{'configuracao':<38}"
        f"{'vazao req/s':>12}"
        f"{'espera p95':>12}"
        f"{'perdidas':>10}"
        f"{'rejeitadas':>12}"
    )

    for linha in resumo:
        print(
            f"{linha['configuracao']:<38}"
            f"{linha.get('vazao_req_s_media', 0) or 0:>12}"
            f"{linha.get('espera_p95_s_media', 0) or 0:>12}"
            f"{linha.get('perdidas_media', 0) or 0:>10}"
            f"{linha.get('rejeitadas_media', 0) or 0:>12}"
        )

    print(f"\nBruto: {arquivo_bruto}")
    print(f"Resumo: {arquivo_resumo}")
    print(f"Logs: {pasta_logs}/")


if __name__ == "__main__":
    main()