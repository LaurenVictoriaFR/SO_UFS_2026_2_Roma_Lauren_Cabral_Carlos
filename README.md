# GenResearch-Servidor

Serviço simplificado de recuperação e geração de respostas (RAG) com experimentos de sistemas operacionais: leitura convencional vs. mmap, fila e concorrência, cache compartilhado e logs. Atividade 2 de Sistemas Operacionais (UFS, 2026.2).

## Estrutura

| Pasta/arquivo | Conteúdo |
|---|---|
| `codigo/` | Todos os scripts Python (um único diretório, para os `import` funcionarem) |
| `dados/pequeno/` | Índice do corpus sintético (200 documentos, 1422 fragmentos, vetores de 1024 dimensões) |
| `logs/`, `resultados/` | Saída das execuções (vazias no repositório) |
| `requirements.txt` | Dependências (`numpy`, `matplotlib`); o restante usa a biblioteca padrão |

## Módulos

| Arquivo | Autor(a) | Função |
|---|---|---|
| `logger.py` | Marcos | `LoggerConcorrente`: log compartilhado com mutex (eventos INGESTAO, CONSULTA, RECUPERACAO, CACHE, GERACAO, FALHA, ENCERRAMENTO) |
| `mmap_experimento.py` | Marcos | Parte E: leitura convencional vs. mmap |
| `demonstracao.py`, `teste_concorrencia.py` | Marcos | Escrita concorrente no log com e sem mutex |
| `ingestao.py` | Henrico | Geração do corpus, fragmentação, embeddings simulados, `Indice.buscar()` |
| `dados/pequeno/` | Henrico | Índice do corpus sintético gerado por `ingestao.py`: `genresearch.db` (SQLite), `vetores.npy`, `estatisticas_ingestao.json` e `tempos_ingestao_por_doc.csv` |
| `fila.py`, `experimento_c3.py` | Rose | Fila limitada produtor/consumidor, C3 e falhas controladas |
| `recuperacao_resposta.py` | Wanessa | `RecuperacaoResposta`: cache, recuperação e geração com o Ollama; `processar(req)` para a fila |
| `cache.py`, `experimento_c4.py`, `experimento_c5.py` | Lauren | `Cache` (FIFO/LRU, semelhança por limiar); experimentos C4 (cache) e C5 (pressão de memória) |
| `metricas.py`, `amostrador.py` | Lauren | Tabelas e gráficos a partir dos logs/CSVs; amostragem de /proc |

## Como rodar

Todos os comandos partem da **raiz do repositório**, no Linux ou WSL2 (dentro de `~/`, não em `/mnt/c`). O Ollama precisa estar ativo com o modelo `llama3.2:3b` para as consultas reais.

```bash
pip install -r requirements.txt
python3 codigo/ingestao.py buscar --indice dados/pequeno --consulta "o que e paginacao" -k 3
python3 codigo/recuperacao_resposta.py "O que é paginação?"
python3 codigo/metricas.py --log logs/papel4.log --saida resultados/analise
```

## Experimentos

**Execute todos os comandos abaixo**, para receber os dados brutos. A análise dos resultados está no relatório. Cada experimento foi repetido ao menos 3 vezes. Os resultados brutos ficam em `resultados/` e os logs em `logs/`.

| Experimento | Comando | Saída |
|---|---|---|
| Parte A (ambiente) | `uname -a; cat /etc/os-release; lscpu; free -h; lsblk; df -h; swapon --show` | texto em `resultados/ambiente/` |
| C1 e C2 / Parte E (read vs. mmap) | `cd resultados && python3 ../codigo/mmap_experimento.py` | `resultados_experimento_<ts>.csv` |
| C3 (fila e concorrência) | `python3 codigo/experimento_c3.py` (carga simulada) ou `... --processador recuperacao_resposta:processar --requisicoes 8 --sem-falhas` (modelo real) | `resultados/c3_*.csv`, `logs/c3_<ts>/` |
| Parte D e C6 (corrida sem/com mutex, fila saturada) | incluídos no `experimento_c3.py` (sem `--sem-falhas`) | linhas `D_corrida_*` e `C6_fila_saturada` no resumo |
| C4 (cache) | `python3 codigo/experimento_c4.py --indice dados/pequeno --saida resultados/c4.csv` | `resultados/c4.csv` |
| C5 (pressão de memória) | `python3 codigo/experimento_c5.py --indices dados/pequeno dados/medio dados/grande --saida resultados/c5.csv` | `resultados/c5.csv` |
| Ingestão em outras escalas | `python3 codigo/ingestao.py gerar --docs 5000 --saida dados/medio` e `ingerir --corpus dados/medio/docs --saida dados/medio` (idem 50000 em `dados/grande`) | `dados/<escala>/estatisticas_ingestao.json`, `logs/ingestao.log` |
| Memória do processo (amostragem) | `python3 codigo/amostrador.py --pid <PID> --saida resultados/amostras.csv` | CSV de /proc |
| Tabelas e gráficos | `python3 codigo/metricas.py --log logs/papel4.log --mmap <csv> --c3 <csv> --c4 resultados/c4.csv --saida resultados/analise` | `resumo.md`, CSVs e PNGs |

O C6 também pode ser provocado desligando o Ollama e fazendo uma consulta: o log registra o evento `FALHA`.

## Vídeo

https://drive.google.com/drive/folders/1gvZHCQy1qjLPcn4lPBkRquRQMsyRp2v3

## Equipe e atribuição

Equipe: Carlos Henrico Fontes Cabral, Daniel de Andrade Lima, Lauren Victoria Ferreira Roma, Marcos Vinícios Assunção Nery Santos, Roseane Resende Couto e Wanessa Silva Santos. A autoria de cada módulo está na tabela de módulos (coluna Autor(a)); a tabela de contribuição individual está no relatório.

Modelo de linguagem: `llama3.2:3b`, executado localmente pelo [Ollama](https://ollama.com). Nenhum peso de modelo, chave ou dado pessoal está neste repositório; o corpus é sintético e gerado por `codigo/ingestao.py`.
