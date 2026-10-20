import threading
import datetime
import os

# Eventos exigidos pelo enunciado
INGESTAO = "INGESTAO"
CONSULTA = "CONSULTA"
RECUPERACAO = "RECUPERACAO"
CACHE = "CACHE"
GERACAO = "GERACAO"
FALHA = "FALHA"
ENCERRAMENTO = "ENCERRAMENTO"


class LoggerConcorrente:
    def __init__(self, caminho_arquivo="logs/genresearch_execucao.log"):
        self.caminho_arquivo = caminho_arquivo

        # O Mutex protege a escrita (Nota: protege apenas threads no mesmo processo)
        self.mutex = threading.Lock()

        os.makedirs(os.path.dirname(self.caminho_arquivo) or '.', exist_ok=True)

        # Usar "a" (append) para não apagar o arquivo a cada nova instância
        with self.mutex:
            with open(self.caminho_arquivo, "a", encoding="utf-8") as f:
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                f.write(f"[{timestamp}] [SISTEMA] [MainThread] status: inicio_execucao\n")

    def registrar(self, nivel, mensagem, duracao=None):
        """Registra uma mensagem no log de forma estruturada: [timestamp] [nivel] [thread] chave valor"""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        nome_thread = threading.current_thread().name

        linha_log = f"[{timestamp}] [{nivel}] [{nome_thread}] {mensagem}"
        if duracao is not None:
            linha_log += f" duracao: {duracao:.4f}s"
        linha_log += "\n"

        with self.mutex:
            with open(self.caminho_arquivo, "a", encoding="utf-8") as f:
                f.write(linha_log)
                # O fechamento automático do 'with' envia os dados ao sistema operacional

    def encerrar(self):
        """Método explícito de encerramento."""
        self.registrar(ENCERRAMENTO, "status: sistema_encerrado")