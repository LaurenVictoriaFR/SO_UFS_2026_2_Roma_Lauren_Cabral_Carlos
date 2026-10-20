import threading
from logger import LoggerConcorrente, CONSULTA

logger = LoggerConcorrente("logs/teste_concorrencia.log")

def registrar_eventos(numero_thread):
    for numero_evento in range(5):
        logger.registrar(
            CONSULTA,
            f"thread={numero_thread} evento={numero_evento}"
        )

threads = [
    threading.Thread(target=registrar_eventos, args=(i,))
    for i in range(10)
]

for thread in threads:
    thread.start()

for thread in threads:
    thread.join()

logger.encerrar()

with open("logs/teste_concorrencia.log", encoding="utf-8") as arquivo:
    linhas = arquivo.readlines()

print(f"Linhas encontradas: {len(linhas)}")
print(f"Linhas esperadas: 52")
print(f"Teste aprovado: {len(linhas) == 52}")
