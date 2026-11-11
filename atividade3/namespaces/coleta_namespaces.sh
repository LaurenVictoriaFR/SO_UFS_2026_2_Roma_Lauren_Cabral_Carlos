#!/usr/bin/env bash
# =============================================================================
# coleta_namespaces.sh — Atividade 3 / Parte B (Evidências de namespaces)
# Sistemas Operacionais — UFS 2026.2
#
# O que faz:
#   1. Registra o contexto do daemon Docker (nativo x Docker Desktop/remoto).
#   2. Sobe DOIS contêineres independentes da MESMA imagem (fixada por digest).
#   3. Coleta, de cada um: PID no host (inspect), comando do PID 1 interno e
#      handles dos namespaces pid, mnt, net (+ uts, ipc, cgroup, user como extra).
#   4. Verificação cruzada pelo lado do host (NSpid em /proc/<pid>/status).
#   5. Gera tabela_namespaces.md e namespaces.csv a partir dos dados coletados.
#   6. Remove SOMENTE os dois contêineres que criou.
#
# Uso:
#   export IMAGEM_LAB="python@sha256:..."   # opcional; se vazio, o script resolve
#   bash coleta_namespaces.sh
#   (opcional: rodar "sudo -v" antes para a verificação cruzada dos handles)
#
# Saída: evidencias/namespaces/<data_hora>/
# =============================================================================
set -euo pipefail

A="ns_lab_a"
B="ns_lab_b"
ROTULO="so2026.atividade3=namespaces"
TS="$(date +%Y%m%d_%H%M%S)"
OUT="${OUT:-evidencias/namespaces/$TS}"
mkdir -p "$OUT"
REG="$OUT/registro_completo.txt"
NS_PRINCIPAIS="pid mnt net"
NS_EXTRAS="uts ipc cgroup user"

# Tudo o que aparece na tela também vai para o registro bruto.
exec > >(tee -a "$REG") 2>&1

limpar() {
  echo
  echo "# Limpeza: removendo apenas $A e $B"
  docker rm -f "$A" "$B" >/dev/null 2>&1 || true
}
trap limpar EXIT

secao() { printf '\n========== %s ==========\n' "$1"; }
val()   { grep "^$2=" "$OUT/$1.env" 2>/dev/null | head -n1 | cut -d= -f2- || true; }

# ---------------------------------------------------------------- 0. Imagem
secao "0. Imagem fixada por digest"
if [ -z "${IMAGEM_LAB:-}" ]; then
  docker image inspect python:3.12-slim >/dev/null 2>&1 || docker pull python:3.12-slim
  IMAGEM_LAB="$(docker image inspect --format '{{index .RepoDigests 0}}' python:3.12-slim)"
fi
echo "IMAGEM_LAB=$IMAGEM_LAB"

# ------------------------------------------------------- 1. Contexto daemon
secao "1. Contexto do daemon"
echo "data=$(date -Iseconds)"
echo "kernel_terminal=$(uname -srm)"
echo "docker_context=$(docker context show 2>/dev/null || echo desconhecido)"
docker info --format 'daemon_OS={{.OperatingSystem}} | kernel_daemon={{.KernelVersion}} | cgroup=v{{.CgroupVersion}} driver={{.CgroupDriver}}'

# ------------------------------------------------------ 2. Subir contêineres
secao "2. Subindo dois contêineres independentes"
docker rm -f "$A" "$B" >/dev/null 2>&1 || true   # restos de execução anterior (só esses nomes)
for c in "$A" "$B"; do
  docker run -d --name "$c" --label "$ROTULO" \
    --network none \
    --cap-drop ALL --security-opt no-new-privileges \
    --memory 64m --pids-limit 16 \
    "$IMAGEM_LAB" sleep 600 >/dev/null
  echo "$c iniciado: id=$(docker inspect --format '{{.Id}}' "$c" | cut -c1-12)"
done
echo "Flags: --network none, --cap-drop ALL, no-new-privileges, 64 MiB, pids-limit 16, sleep 600 (encerra sozinho)"

# ------------------------------------------------- 3. Coleta dentro de cada
coletar() {
  local c="$1" env="$OUT/$1.env"
  : > "$env"
  echo "PID_host=$(docker inspect --format '{{.State.Pid}}' "$c")" | tee -a "$env"
  echo "comm_PID1=$(docker exec "$c" sh -c 'cat /proc/1/comm')"   | tee -a "$env"
  for ns in $NS_PRINCIPAIS $NS_EXTRAS; do
    echo "ns_$ns=$(docker exec "$c" readlink "/proc/1/ns/$ns")"   | tee -a "$env"
  done
  echo "--- Processos visíveis em /proc dentro de $c  [PID(comando)]:"
  docker exec "$c" sh -c 'for p in /proc/[0-9]*; do printf "%s(%s) " "${p#/proc/}" "$(cat "$p/comm" 2>/dev/null)"; done; echo'
  echo "--- Shell aberto pelo docker exec (entra nos mesmos namespaces):"
  docker exec "$c" sh -c 'echo "PID_interno_do_sh=$$ ns_pid_do_sh=$(readlink /proc/self/ns/pid)"'
  echo "--- Interfaces de rede vistas em $c: $(docker exec "$c" sh -c 'ls /sys/class/net | tr "\n" " "')"
  echo "--- hostname (UTS) em $c: $(docker exec "$c" cat /etc/hostname)"
}

for c in "$A" "$B"; do
  secao "3. Coleta dentro de $c"
  coletar "$c"
done

# --------------------------------------------- 4. Verificação pelo host
secao "4. Verificação cruzada pelo host"
NATIVO=sim
for c in "$A" "$B"; do
  pidh="$(val "$c" PID_host)"
  echo "--- $c (PID_host=$pidh)"
  if [ -r "/proc/$pidh/status" ] && [ "$(cat "/proc/$pidh/comm" 2>/dev/null)" = "sleep" ]; then
    echo "comm visto pelo host: $(cat "/proc/$pidh/comm")"
    nspid="$(grep '^NSpid:' "/proc/$pidh/status" | cut -f2- | tr '\t' ' ')"
    echo "NSpid (host -> interno): $nspid"
    echo "NSpid=$nspid" >> "$OUT/$c.env"
    for ns in $NS_PRINCIPAIS; do
      v="$(readlink "/proc/$pidh/ns/$ns" 2>/dev/null \
           || sudo -n readlink "/proc/$pidh/ns/$ns" 2>/dev/null \
           || echo 'sem_permissao(rode "sudo -v" antes do script)')"
      echo "host_ve_ns_$ns=$v"
    done
  else
    NATIVO=nao
    echo "AVISO: /proc/$pidh deste terminal NÃO corresponde ao contêiner."
    echo "Provável Docker Desktop/daemon remoto: o PID_host pertence ao Linux da VM do daemon."
  fi
done

: > "$OUT/host.env"
if [ "$NATIVO" = sim ]; then
  echo "--- Namespaces do próprio host (processo do terminal):"
  for ns in $NS_PRINCIPAIS $NS_EXTRAS; do
    echo "ns_$ns=$(readlink "/proc/self/ns/$ns")" | tee -a "$OUT/host.env"
  done
fi

# ------------------------------------------------------------ 5. Tabelas
interpretar() {
  local ns="$1" igual="$2"
  if [ "$igual" = sim ]; then
    case "$ns" in
      user) echo "Compartilhado: sem userns-remap/rootless, ambos usam o user namespace do host (UID 0 interno é UID 0 no host)" ;;
      *)    echo "Compartilhado entre A e B: verificar configuração (ex.: --pid, --network ou --ipc container:/host)" ;;
    esac
  else
    case "$ns" in
      pid)    echo "Árvores de processos separadas: cada contêiner tem seu próprio PID 1 e não enxerga os processos do outro" ;;
      mnt)    echo "Tabelas de montagem separadas: cada um vê seu próprio / (rootfs da imagem) e seus próprios mounts" ;;
      net)    echo "Pilhas de rede separadas: interfaces, rotas e portas próprias (aqui só lo, por causa de --network none)" ;;
      uts)    echo "Hostname próprio em cada contêiner" ;;
      ipc)    echo "Recursos IPC (System V / POSIX mqueue) separados" ;;
      cgroup) echo "Visão própria da hierarquia de cgroups (a raiz aparente é o cgroup do contêiner)" ;;
      user)   echo "User namespaces distintos (userns-remap ou rootless ativo)" ;;
    esac
  fi
}

MD="$OUT/tabela_namespaces.md"
CSV="$OUT/namespaces.csv"
echo 'recurso,handle_A,handle_B,iguais,handle_host,interpretacao' > "$CSV"

linha() {
  local ns="$1" ha hb hh igual txt
  ha="$(val "$A" "ns_$ns")"; hb="$(val "$B" "ns_$ns")"
  hh="$(val host "ns_$ns")"; [ -z "$hh" ] && hh="n/d"
  if [ "$ha" = "$hb" ]; then igual=sim; else igual=nao; fi
  txt="$(interpretar "$ns" "$igual")"
  local rotulo; [ "$igual" = sim ] && rotulo="Iguais" || rotulo="Diferentes"
  printf '| %s | `%s` | `%s` | %s | `%s` | %s |\n' "$ns" "$ha" "$hb" "$rotulo" "$hh" "$txt" >> "$MD"
  printf '%s,%s,%s,%s,%s,"%s"\n' "$ns" "$ha" "$hb" "$igual" "$hh" "$txt" >> "$CSV"
}

{
  echo "# Evidências de namespaces — coleta de $TS"
  echo
  echo "Imagem: \`$IMAGEM_LAB\`  "
  echo "Contêineres: \`$A\` (A) e \`$B\` (B)  "
  echo "Daemon nativo neste terminal: $NATIVO"
  echo
  echo "## Tabela principal (PID, mount, network)"
  echo
  echo "| Recurso | Handle em A | Handle em B | A × B | Handle do host | Interpretação |"
  echo "|---|---|---|---|---|---|"
} > "$MD"
for ns in $NS_PRINCIPAIS; do linha "$ns"; done
{
  echo
  echo "## Namespaces adicionais (contexto)"
  echo
  echo "| Recurso | Handle em A | Handle em B | A × B | Handle do host | Interpretação |"
  echo "|---|---|---|---|---|---|"
} >> "$MD"
for ns in $NS_EXTRAS; do linha "$ns"; done
{
  echo
  echo "## PID 1 de cada contêiner"
  echo
  echo "| Contêiner | PID no host (inspect) | Comando do PID 1 interno | NSpid (host → interno) |"
  echo "|---|---|---|---|"
  for c in "$A" "$B"; do
    n="$(val "$c" NSpid)"; [ -z "$n" ] && n="n/d"
    echo "| $c | $(val "$c" PID_host) | $(val "$c" comm_PID1) | $n |"
  done
} >> "$MD"

secao "5. Arquivos gerados"
ls -1 "$OUT"
echo
cat "$MD"
