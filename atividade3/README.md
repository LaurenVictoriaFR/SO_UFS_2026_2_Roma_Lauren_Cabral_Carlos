# Atividade 3 — Virtualização, contêineres, namespaces e cgroups

Atividade 3 de Sistemas Operacionais (UFS, 2026.2). Experimentos com contêineres Docker: ambiente, namespaces, limites de CPU por cgroup e montagem somente leitura com menor privilégio. A análise está no relatório.

**Vídeo:** https://drive.google.com/drive/folders/1fizUgOrEJEJvSLtU7qDfkwxsj9nkDGcp

## Estrutura

| Pasta | Parte | Conteúdo |
|---|---|---|
| `testes_/` | A (ambiente) | Diagnóstico de host e kernel, diagrama e foto |
| `namespaces/` | B (namespaces) | `coleta_namespaces.sh` e evidências em `evidencias/namespaces/` |
| `experimento_cgroups/` | C (cgroups) | `carga_cpu.py`, `run_experimentos.sh`, `resumo.py`, `resultados/` e `resultados_piloto/` |
| `testesD/` | D (mount e menor privilégio) | `parte_d_readonly.sh` e evidências em `evidencias/D/` |

## Como reproduzir

Todos os experimentos usam a mesma imagem, fixada por digest. Defina antes de rodar:

```bash
docker pull python:3.12-slim
export IMAGEM_LAB="$(docker image inspect --format '{{index .RepoDigests 0}}' python:3.12-slim)"
```

No PowerShell: `$env:IMAGEM_LAB = docker image inspect --format '{{index .RepoDigests 0}}' python:3.12-slim`.

| Parte | Pasta de execução | Comando |
|---|---|---|
| B | `atividade3/namespaces/` | `bash coleta_namespaces.sh` |
| C | `atividade3/experimento_cgroups/` | `ITERACOES=50000000 bash run_experimentos.sh` e depois `python3 resumo.py` (requer `pandas` e `matplotlib`) |
| D | `atividade3/testesD/` | `./parte_d_readonly.sh` |

## Parte C em resumo

Carga fixa de 50 milhões de iterações, três repetições alternadas por condição: C1 com `--cpus 0.5` e C2 com `--cpus 1.0`.

| Mediana | C1 (0,5 CPU) | C2 (1,0 CPU) |
|---|---|---|
| Wall time (s) | 14,13 | 7,19 |
| Tempo de CPU (s) | 7,08 | 7,18 |
| `nr_throttled` | 142 | 0 |

A razão entre os wall times é 1,97, com o mesmo checksum nas seis execuções.

## Ambiente

Partes A, C e D: Docker Desktop (backend WSL2), kernel `6.18.33.2-microsoft-standard-WSL2`, cgroup v2. Parte B: Docker Engine nativo em Kubuntu, kernel `7.0.0-42-generic`, cgroup v2.

## Equipe

| Integrante | Papel |
|---|---|
| Wanessa Silva Santos | 1 - Ambiente (A) |
| Roseane Resende Couto | 2 - Namespaces (B) |
| Lauren Victoria Ferreira Roma | 3 - Execução (C) |
| Carlos Henrico Fontes Cabral | 4 - Análise (C) |
| Daniel de Andrade Lima | 5 - Mount e Segurança (D) |
| Marcos Vinícios Assunção Nery Santos | 6 - Integração |

## Segurança e IA

Os scripts não usam `--privileged`, não montam `/` nem `docker.sock`, e não executam fork bomb, estouro deliberado de memória ou escrita manual em `/sys`. Não há credenciais nem dados pessoais no repositório. Parte dos scripts foi escrita com auxílio de IA generativa; a declaração está no relatório.
