# Parte B — Evidências de namespaces

> Texto-base para a seção "Namespaces" do relatório. Os valores entre ⟨ ⟩ devem ser
> substituídos pelos números REAIS gerados em `evidencias/namespaces/<data>/`.
> Nenhum handle aqui é exemplo para copiar.

## 1. Objetivo

Mostrar, com evidências coletadas do kernel, que dois contêineres criados a partir da
mesma imagem possuem visões isoladas de processos (namespace PID), de pontos de
montagem (namespace mount) e de rede (namespace network), embora rodem sobre o
mesmo kernel Linux.

## 2. Fundamento

Um *namespace* é um recurso do kernel Linux que envolve um recurso global do sistema
em uma abstração, de modo que os processos dentro dele enxergam uma instância
própria desse recurso [NS]. Cada processo pertence a exatamente um namespace de cada
tipo, e isso aparece em `/proc/<pid>/ns/`: cada entrada é um link simbólico no formato
`tipo:[inode]`. Dois processos estão no **mesmo** namespace se, e somente se, os links
apontam para o mesmo inode (no mesmo dispositivo `nsfs`). Por isso o número entre
colchetes é chamado de *handle*: ele identifica a instância do namespace.

O Docker cria os namespaces com as chamadas `clone()`/`unshare()` ao iniciar o
contêiner; o `docker exec` usa `setns()` para colocar um novo processo dentro dos
namespaces já existentes.

## 3. Procedimento

```bash
docker pull python:3.12-slim
export IMAGEM_LAB="$(docker image inspect --format '{{index .RepoDigests 0}}' python:3.12-slim)"
sudo -v                      # opcional: permite ler /proc/<pid>/ns pelo host
bash coleta_namespaces.sh
```

O script sobe `ns_lab_a` e `ns_lab_b` com `sleep 600` como processo principal,
`--network none`, `--cap-drop ALL`, `no-new-privileges`, 64 MiB e `pids-limit 16`.
Para cada um, coleta:

| Comando | O que evidencia |
|---|---|
| `docker inspect --format '{{.State.Pid}}'` | PID do processo principal **no host do daemon** |
| `docker exec NOME cat /proc/1/comm` | Qual programa é o PID 1 **dentro** do contêiner |
| `docker exec NOME readlink /proc/1/ns/{pid,mnt,net}` | Handle de cada namespace |
| `grep NSpid /proc/<PID_host>/status` (no host) | O mesmo processo visto nos dois níveis de PID |

Ao final, os dois contêineres (e só eles) são removidos.

## 4. Ambiente

Docker Engine nativo em Kubuntu ⟨versão⟩, kernel ⟨uname -r⟩, cgroup v⟨2⟩. Como o
daemon roda no próprio host, o PID informado pelo `inspect` existe no `/proc` do
terminal, permitindo a verificação cruzada. (Em Docker Desktop isso não valeria:
o PID pertenceria ao Linux da VM do daemon.)

## 5. Resultados

⟨colar aqui `tabela_namespaces.md` gerada pelo script⟩

Registros brutos: `evidencias/namespaces/<data>/registro_completo.txt`,
`ns_lab_a.env`, `ns_lab_b.env`, `namespaces.csv`.

## 6. Interpretação

**PID.** Os handles `pid:[…]` de A e B são diferentes, e ambos diferem do host.
Cada contêiner tem sua própria árvore de PIDs: listando `/proc` dentro de A,
aparecem apenas o `sleep` (PID 1) e os processos abertos pelo próprio `docker exec`;
os processos de B e do host não aparecem.

**Mount.** Handles `mnt:[…]` diferentes: cada contêiner tem sua tabela de montagens,
com o sistema de arquivos da imagem (overlay) como `/`. Uma montagem feita em um
não aparece no outro.

**Network.** Handles `net:[…]` diferentes: cada contêiner tem sua pilha de rede
(interfaces, rotas, tabela de portas). Com `--network none`, cada um vê apenas `lo`,
e o `lo` de A não é o mesmo de B.

**User (contexto).** O handle `user:[…]` é igual em A, B e no host: sem
userns-remap/rootless, o UID 0 dentro do contêiner é o UID 0 do host. O isolamento
de privilégio vem de capabilities removidas, `no-new-privileges`, seccomp/AppArmor,
e não de um user namespace.

## 7. Por que os dois contêineres têm PID 1 e não são o mesmo processo

O namespace PID é hierárquico. Quando um processo é criado em um namespace PID novo,
ele recebe **um número em cada nível**: um PID no namespace pai (o host) e um PID no
namespace filho, onde é o primeiro processo e, portanto, recebe o número 1.

A linha `NSpid` de `/proc/<PID_host>/status` mostra isso diretamente:

- `ns_lab_a`: `NSpid: ⟨PID_host_A⟩ 1`
- `ns_lab_b`: `NSpid: ⟨PID_host_B⟩ 1`

São dois processos diferentes no kernel (PIDs ⟨A⟩ e ⟨B⟩ no host, duas `task_struct`
distintas). O "1" é apenas o número que cada um recebe **dentro do seu próprio**
namespace PID, que são instâncias diferentes (handles diferentes). É como dois
apartamentos "101" em prédios diferentes: o número se repete porque o espaço de
numeração é outro.

Ser PID 1 tem consequências: o processo vira o "init" daquele namespace. Ele adota
órfãos, o kernel não entrega a ele sinais para os quais não instalou tratador
(por isso `sleep` como PID 1 ignora `SIGTERM` e o `docker rm -f` precisa de `SIGKILL`),
e se ele termina, o kernel encerra todos os processos do namespace, ou seja, o
contêiner para.

## 8. O que essas evidências NÃO demonstram

- **Não há kernel separado.** Namespaces mudam a *visão*; todos os processos de A,
  B e do host são escalonados pelo mesmo kernel ⟨uname -r⟩. Contêiner não é VM.
- **Não limitam recursos.** Namespace não impede um contêiner de usar toda a CPU ou
  memória; isso é papel dos cgroups (Parte C).
- **Não provam isolamento absoluto.** Uma falha no kernel ou no runtime atinge
  todos ao mesmo tempo; o user namespace é compartilhado com o host.
- **Não cobrem tudo.** Relógio do sistema, keyring do kernel, módulos e parte de
  `/proc`/`/sys` não são isolados por esses três namespaces.
- **Não dizem nada sobre permissões de arquivo** (isso é identidade/DAC e montagem
  read-only, Parte D).

## 9. Relação com um servidor de inferência

Em um servidor que hospeda vários serviços de inferência em contêineres, o namespace
PID impede que um serviço veja ou sinalize processos de outro; o namespace network
permite que cada um escute na mesma porta interna sem conflito e que serviços sem
necessidade de rede rodem com `--network none`; o namespace mount restringe quais
diretórios (modelos, corpus) cada um enxerga. Porém, como o kernel é compartilhado,
uma vulnerabilidade de kernel ainda afeta todos, e sem cgroups um serviço pode
esgotar os recursos dos demais.

## Referências

[NS] Linux man-pages. namespaces(7), pid_namespaces(7). https://man7.org/linux/man-pages/man7/namespaces.7.html
