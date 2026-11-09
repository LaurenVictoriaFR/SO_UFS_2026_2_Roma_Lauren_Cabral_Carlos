import argparse
import json
import time
import urllib.request
import urllib.error

from ingestao import Indice
from cache import Cache, gerar_chave
from logger import LoggerConcorrente


class RecuperacaoResposta:
    """
    Integra recuperação de documentos, cache e geração
    de respostas utilizando um modelo local do Ollama.

    Categorias de log:
    - CONSULTA: tempo total da operação.
    - RECUPERACAO: tempo exclusivo da busca de documentos.
    - GERACAO: tempo exclusivo da chamada ao Ollama.
    - CACHE: acertos, falhas e tempo de acesso ao cache.
    - FALHA: erros ocorridos durante o processamento.
    - ENCERRAMENTO: conclusão da consulta.
    """

    def __init__(
        self,
        pasta_indice="dados/pequeno",
        modelo="llama3.2:3b",
        capacidade_cache=100,
        politica_cache="LRU",
        usar_mmap=False,
        arquivo_log="logs/papel4.log",
        url_ollama="http://localhost:11434/api/generate",
    ):
        self.modelo = modelo
        self.url_ollama = url_ollama

        self.logger = LoggerConcorrente(arquivo_log)

        self.indice = Indice(
            pasta_indice,
            usar_mmap=usar_mmap,
        )

        self.cache = Cache(
            capacidade=capacidade_cache,
            politica=politica_cache,
            logger=self.logger,
        )

    def _gerar_resposta(self, pergunta, documentos):
        """
        Gera uma resposta com o Ollama.

        Retorna:
            Tupla contendo a resposta e o tempo de geração.

        A categoria GERACAO registra apenas o tempo desta etapa.
        """

        contexto = "\n\n".join(
            f"Documento {documento['doc_id']}:\n"
            f"{documento['texto']}"
            for documento in documentos
        )

        if not contexto:
            contexto = (
                "Nenhum documento relevante foi encontrado "
                "no índice para esta consulta."
            )

        prompt = f"""
Você é um assistente que responde perguntas sobre Sistemas
Operacionais e Inteligência Artificial.

Responda em português brasileiro, com clareza e objetividade.

Utilize os documentos recuperados como referência.
Não invente informações que não estejam sustentadas pelo contexto.
Se o contexto não for suficiente, informe essa limitação.

CONTEXTO:
{contexto}

PERGUNTA:
{pergunta}

RESPOSTA:
"""

        dados = {
            "model": self.modelo,
            "prompt": prompt,
            "stream": False,
        }

        requisicao = urllib.request.Request(
            self.url_ollama,
            data=json.dumps(dados).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        inicio_geracao = time.perf_counter()

        try:
            with urllib.request.urlopen(
                requisicao,
                timeout=180,
            ) as resposta_http:
                conteudo = json.loads(
                    resposta_http.read().decode("utf-8")
                )

            resposta = conteudo.get("response", "").strip()

            if not resposta:
                raise RuntimeError(
                    "O Ollama retornou uma resposta vazia."
                )

            tempo_geracao = (
                time.perf_counter() - inicio_geracao
            )

            self.logger.registrar(
                "GERACAO",
                f"status: geracao_concluida caracteres_resposta={len(resposta)}",
                duracao=tempo_geracao,
            )

            return resposta, tempo_geracao

        except Exception as erro:
            tempo_geracao = (
                time.perf_counter() - inicio_geracao
            )

            # A falha é registrada aqui. O método responder()
            # evita registrar novamente a mesma falha.
            self.logger.registrar(
                "FALHA",
                (
                    f"etapa: geracao; "
                    f"erro: {type(erro).__name__}: {erro}"
                ),
                duracao=tempo_geracao,
            )

            if isinstance(erro, urllib.error.URLError):
                raise RuntimeError(
                    "Não foi possível conectar ao Ollama. "
                    "Verifique se ele está em execução e se o "
                    f"modelo '{self.modelo}' está disponível. "
                    f"Detalhes: {erro}"
                ) from erro

            raise

    def responder(self, pergunta):
        """
        Processa uma consulta e retorna a resposta e as métricas.

        CONSULTA mede a operação completa.
        RECUPERACAO mede apenas a busca no índice.
        GERACAO mede apenas a chamada ao Ollama.
        ENCERRAMENTO é registrado uma única vez por consulta.
        """

        # O cronômetro total começa antes de qualquer operação.
        inicio_total = time.perf_counter()

        tempo_cache = 0.0
        tempo_recuperacao = None
        tempo_geracao = None

        documentos = []
        cache_hit = False
        origem = None
        resposta = None
        etapa_atual = "consulta"
        falha_registrada = False

        self.logger.registrar(
            "CONSULTA",
            "status: consulta_iniciada",
        )

        try:
            # Etapa 1: consulta ao cache.
            etapa_atual = "validacao"

            chave = gerar_chave(pergunta)

            if not chave.palavras:
                raise ValueError("A pergunta não pode estar vazia.")

            etapa_atual = "cache"

            inicio_cache = time.perf_counter()

            resposta_cache = self.cache.get(chave)

            tempo_cache = (
                time.perf_counter() - inicio_cache
            )

            if resposta_cache is not None:
                cache_hit = True
                origem = "cache"
                resposta = resposta_cache

                self.logger.registrar(
                    "CACHE",
                    "status: cache_hit",
                    duracao=tempo_cache,
                )

            else:
                self.logger.registrar(
                    "CACHE",
                    "status: cache_miss",
                    duracao=tempo_cache,
                )

                # Etapa 2: recuperação de documentos.
                etapa_atual = "recuperacao"

                inicio_recuperacao = time.perf_counter()

                try:
                    documentos = self.indice.buscar(
                        pergunta,
                        k=3,
                    )

                finally:
                    # O tempo inclui somente a busca no índice.
                    tempo_recuperacao = (
                        time.perf_counter()
                        - inicio_recuperacao
                    )

                    self.logger.registrar(
                        "RECUPERACAO",
                        f"status: busca_concluida documentos_encontrados={len(documentos)}",
                        duracao=tempo_recuperacao,
                    )

                # Etapa 3: geração pelo Ollama.
                etapa_atual = "geracao"

                resposta, tempo_geracao = (
                    self._gerar_resposta(
                        pergunta,
                        documentos,
                    )
                )

                origem = "ollama"

                # Etapa 4: armazenamento no cache.
                etapa_atual = "cache"

                self.cache.put(
                    chave,
                    resposta,
                    custo=tempo_geracao,
                )

            # As operações anteriores são contabilizadas no
            # tempo total da consulta, inclusive o cache.
            tempo_total = (
                time.perf_counter() - inicio_total
            )

            metricas = {
                "cache_hit": cache_hit,
                "tempo_cache_s": tempo_cache,
                "tempo_recuperacao_s": tempo_recuperacao,
                "tempo_geracao_s": tempo_geracao,
                "tempo_total_s": tempo_total,
            }

            self.logger.registrar(
                "CONSULTA",
                (
                    f"status: consulta_concluida; "
                    f"origem: {origem}; "
                    f"cache_hit: {cache_hit}; "
                    f"tempo_cache_s: {tempo_cache:.4f}; "
                    f"tempo_recuperacao_s: "
                    f"{tempo_recuperacao}; "
                    f"tempo_geracao_s: {tempo_geracao}"
                ),
                duracao=tempo_total,
            )

            return {
                "pergunta": pergunta,
                "resposta": resposta,
                "origem": origem,
                "documentos": documentos,
                "metricas": metricas,
            }

        except Exception as erro:
            # Falhas de geração já são registradas por
            # _gerar_resposta(). As demais são registradas aqui.
            if etapa_atual != "geracao":
                self.logger.registrar(
                    "FALHA",
                    (
                        f"etapa: {etapa_atual}; "
                        f"erro: {type(erro).__name__}: {erro}"
                    ),
                )
            else:
                # Se a falha ocorreu depois do retorno de
                # _gerar_resposta(), ela ainda pode não ter sido
                # registrada, por exemplo durante cache.put().
                #
                # Nesse caso, registra a falha de armazenamento.
                if origem == "ollama":
                    self.logger.registrar(
                        "FALHA",
                        (
                            f"etapa: cache; "
                            f"erro: {type(erro).__name__}: {erro}"
                        ),
                    )

            raise

        finally:
            # O tempo final é calculado também quando há erro.
            tempo_total_final = (
                time.perf_counter() - inicio_total
            )

            self.logger.registrar(
                "ENCERRAMENTO",
                "status: consulta_encerrada",
                duracao=tempo_total_final,
            )

    def estatisticas_cache(self):
        """Retorna as estatísticas atuais do cache."""
        return self.cache.estatisticas()

    def reiniciar_cache(self):
        antigo = self.cache
        self.cache = Cache(
            capacidade=antigo.capacidade,
            politica=antigo.politica,
            logger=self.logger,
            limiar=antigo.limiar,
        )


def criar_sistema():
    """
    Cria uma única instância do sistema.
    O índice, o logger e o cache serão compartilhados
    pelas requisições processadas pelas threads.
    """
    return RecuperacaoResposta()


# Instância única, criada quando o módulo é importado.
sistema = criar_sistema()


def processar(req):
    """
    Processa a requisição utilizando a instância compartilhada.
    """
    return sistema.responder(req.pergunta)


def reiniciar_cache():
    sistema.reiniciar_cache()


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Sistema de recuperação de documentos, cache "
            "e geração de respostas com Ollama."
        )
    )

    parser.add_argument(
        "pergunta",
        nargs="+",
        help="Pergunta que será respondida pelo sistema.",
    )

    argumentos = parser.parse_args()
    pergunta = " ".join(argumentos.pergunta)

    try:
        resultado = sistema.responder(pergunta)

        print("\n=== RESULTADO ===")
        print(f"Pergunta: {resultado['pergunta']}")
        print(f"Origem: {resultado['origem']}")
        print(f"\nResposta:\n{resultado['resposta']}")

        print("\n=== MÉTRICAS ===")
        for nome, valor in resultado["metricas"].items():
            print(f"{nome}: {valor}")

        print("\n=== ESTATÍSTICAS DO CACHE ===")
        print(
            json.dumps(
                sistema.estatisticas_cache(),
                ensure_ascii=False,
                indent=2,
            )
        )

    except Exception as erro:
        print(
            f"Erro ao processar a pergunta: "
            f"{type(erro).__name__}: {erro}"
        )


if __name__ == "__main__":
    main()