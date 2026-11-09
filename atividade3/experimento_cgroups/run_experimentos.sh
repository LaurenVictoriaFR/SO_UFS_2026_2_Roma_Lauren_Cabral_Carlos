#!/usr/bin/env bash
# Atividade 3, Parte C: 2 condicoes x 3 repeticoes, alternadas (C1,C2,C1,C2,C1,C2).
# Requer Docker com cgroup v2. Tentativas com erro sao preservadas (nao apague).
set -u
cd "$(dirname "$0")"

: "${ITERACOES:?defina ITERACOES (valor congelado no piloto)}"
IMAGEM="${IMAGEM_LAB:-python:3.12-slim}"   
SAIDA=resultados
mkdir -p "$SAIDA"
CSV="$SAIDA/resultados.csv"
[ -f "$CSV" ] || echo "condicao,repeticao,iteracoes,checksum,status,wall_s,cpu_s,rss_kb,cpu_max,memory_max,pids_max,usage_usec_delta,nr_throttled_delta,throttled_usec_delta,memory_current,memory_peak" > "$CSV"

TIMEOUT=""; command -v timeout >/dev/null && TIMEOUT="timeout 90"

INTERNO='
lim() { [ -r "/sys/fs/cgroup/$1" ] && cat "/sys/fs/cgroup/$1" || echo NA; }
st()  { awk -v k="$1" "\$1==k{print \$2}" /sys/fs/cgroup/cpu.stat; }
echo "cpu_max=\"$(lim cpu.max)\""
echo "memory_max=\"$(lim memory.max)\""
echo "pids_max=\"$(lim pids.max)\""
echo "ini_usage=$(st usage_usec)"
echo "ini_nrthr=$(st nr_throttled)"
echo "ini_thrus=$(st throttled_usec)"
python /carga_cpu.py "$1"
echo "rc=$?"
echo "fim_usage=$(st usage_usec)"
echo "fim_nrthr=$(st nr_throttled)"
echo "fim_thrus=$(st throttled_usec)"
echo "memory_current=$(lim memory.current)"
echo "memory_peak=$(lim memory.peak)"
'

rodar() {  # $1=condicao  $2=cpus  $3=repeticao
  local cond="$1" cpus="$2" rep="$3"
  local nome="lab3_${cond}_r${rep}_$$"
  local log="$SAIDA/${cond}_r${rep}.log"

  docker create --name "$nome" --network none \
      --cpus "$cpus" --memory 256m --memory-swap 256m --pids-limit 64 \
      --user 65534:65534 --cap-drop ALL --security-opt no-new-privileges \
      "$IMAGEM" sh -c "$INTERNO" sh "$ITERACOES" > /dev/null
  docker cp carga_cpu.py "$nome":/carga_cpu.py
  $TIMEOUT docker start -a "$nome" > "$log" 2>&1
  local rc_host=$?
  docker inspect --format 'OOMKilled={{.State.OOMKilled}} ExitCode={{.State.ExitCode}}' "$nome" >> "$log"
  docker rm -f "$nome" > /dev/null

  (
    cpu_max=NA memory_max=NA pids_max=NA memory_current=NA memory_peak=NA
    status=ERRO checksum=NA wall_s=NA cpu_s=NA rss_kb=NA
    ini_usage=0 ini_nrthr=0 ini_thrus=0 fim_usage=0 fim_nrthr=0 fim_thrus=0
    eval "$(grep -E '^[a-z_]+=' "$log" | grep -vE '^(OOMKilled|ExitCode)=')"
    [ "$rc_host" -ne 0 ] && [ "$status" = OK ] && status="ERRO_rc$rc_host"
    echo "$cond,$rep,$ITERACOES,$checksum,$status,$wall_s,$cpu_s,$rss_kb,$cpu_max,$memory_max,$pids_max,$((fim_usage-ini_usage)),$((fim_nrthr-ini_nrthr)),$((fim_thrus-ini_thrus)),$memory_current,$memory_peak" >> "$CSV"
  )
  echo "[$cond r$rep] concluido (rc=$rc_host) -> $log"
}

for rep in 1 2 3; do
  rodar C1 0.5 "$rep"
  rodar C2 1.0 "$rep"
done

echo; echo "Pronto: $CSV"
