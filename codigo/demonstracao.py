import threading
import time
import os
import re
from logger import LoggerConcorrente, CONSULTA, GERACAO


def trabalhador_simulado(id_trabalhador, logger, usar_mutex=True):
    nome_thread = threading.current_thread().name

    for i in range(5):
        if usar_mutex:
            logger.registrar(CONSULTA, f"tarefa: {i} status: iniciada")
        else:
            # Falha controlada: Usar escrita binária sem buffer para garantir a colisão
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            prefixo = f"[{timestamp}] [{CONSULTA}] [{nome_thread}] "
            mensagem = f"tarefa: {i} status: iniciada\n"

            with open(logger.caminho_arquivo, "ab", buffering=0) as f:
                f.write(prefixo.encode('utf-8'))
                time.sleep(0.001)
                f.write(mensagem.encode('utf-8'))

        time.sleep(0.01)

        if usar_mutex:
            logger.registrar(GERACAO, f"tarefa: {i} status: concluida", duracao=0.01)
        else:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            prefixo = f"[{timestamp}] [{GERACAO}] [{nome_thread}] "
            mensagem = f"tarefa: {i} status: concluida duracao: 0.01s\n"

            with open(logger.caminho_arquivo, "ab", buffering=0) as f:
                f.write(prefixo.encode('utf-8'))
                time.sleep(0.001)
                f.write(mensagem.encode('utf-8'))


def testar_concorrencia(nome_arquivo, usar_mutex):
    if os.path.exists(nome_arquivo):
        os.remove(nome_arquivo)

    meu_logger = LoggerConcorrente(nome_arquivo)
    threads = []

    for i in range(10):
        t = threading.Thread(target=trabalhador_simulado, args=(i, meu_logger, usar_mutex), name=f"Worker-{i}")
        threads.append(t)
        t.start()

    for t in threads:
        t.join()

    meu_logger.encerrar()

    # Checagem do resultado usando Regex
    # Valida formato: [YYYY-MM-DD HH:MM:SS.mmm] [NIVEL] [Thread] mensagem
    padrao_linha = re.compile(r"^\[\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?\] \[[A-Z]+\] \[[^\]]+\] .+$")
    linhas_validas = 0
    total_linhas = 0

    with open(nome_arquivo, "r", encoding="utf-8") as f:
        for linha in f:
            total_linhas += 1
            if padrao_linha.match(linha.strip()):
                linhas_validas += 1

    print(f"\n--- Resultados do Teste (usar_mutex={usar_mutex}) ---")
    esperado = 102  # 1 cabecalho + (10 workers * 5 iterações * 2 logs) + 1 encerramento
    print(f"Linhas lidas: {total_linhas} / Formato correto: {linhas_validas} / Esperadas: {esperado}")

    if linhas_validas == esperado and total_linhas == esperado:
        print("SUCESSO: Nenhuma linha foi sobreposta e todas mantiveram o formato.")
    else:
        print("FALHA: Ocorreu uma condicao de corrida (Race Condition). Linhas foram corrompidas ou perdidas.")


if __name__ == "__main__":
    print("Iniciando demonstracao...")

    print("\n[Cenario 1] Demonstrando Falha Controlada (SEM PROTECAO):")
    testar_concorrencia("logs/teste_sem_mutex.log", usar_mutex=False)

    print("\n[Cenario 2] Demonstrando Execucao Segura (COM MUTEX):")
    testar_concorrencia("logs/teste_com_mutex.log", usar_mutex=True)