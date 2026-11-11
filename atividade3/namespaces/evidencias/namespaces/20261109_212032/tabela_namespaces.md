# Evidências de namespaces — coleta de 20261109_212032

Imagem: `python@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b`  
Contêineres: `ns_lab_a` (A) e `ns_lab_b` (B)  
Daemon nativo neste terminal: sim

## Tabela principal (PID, mount, network)

| Recurso | Handle em A | Handle em B | A × B | Handle do host | Interpretação |
|---|---|---|---|---|---|
| pid | `pid:[4026533284]` | `pid:[4026533521]` | Diferentes | `pid:[4026531836]` | Árvores de processos separadas: cada contêiner tem seu próprio PID 1 e não enxerga os processos do outro |
| mnt | `mnt:[4026533280]` | `mnt:[4026533459]` | Diferentes | `mnt:[4026531832]` | Tabelas de montagem separadas: cada um vê seu próprio / (rootfs da imagem) e seus próprios mounts |
| net | `net:[4026533286]` | `net:[4026533523]` | Diferentes | `net:[4026531833]` | Pilhas de rede separadas: interfaces, rotas e portas próprias (aqui só lo, por causa de --network none) |

## Namespaces adicionais (contexto)

| Recurso | Handle em A | Handle em B | A × B | Handle do host | Interpretação |
|---|---|---|---|---|---|
| uts | `uts:[4026533282]` | `uts:[4026533460]` | Diferentes | `uts:[4026531838]` | Hostname próprio em cada contêiner |
| ipc | `ipc:[4026533283]` | `ipc:[4026533461]` | Diferentes | `ipc:[4026531839]` | Recursos IPC (System V / POSIX mqueue) separados |
| cgroup | `cgroup:[4026533285]` | `cgroup:[4026533522]` | Diferentes | `cgroup:[4026531835]` | Visão própria da hierarquia de cgroups (a raiz aparente é o cgroup do contêiner) |
| user | `user:[4026531837]` | `user:[4026531837]` | Iguais | `user:[4026531837]` | Compartilhado: sem userns-remap/rootless, ambos usam o user namespace do host (UID 0 interno é UID 0 no host) |

## PID 1 de cada contêiner

| Contêiner | PID no host (inspect) | Comando do PID 1 interno | NSpid (host → interno) |
|---|---|---|---|
| ns_lab_a | 350794 | sleep | 350794 1 |
| ns_lab_b | 350867 | sleep | 350867 1 |
