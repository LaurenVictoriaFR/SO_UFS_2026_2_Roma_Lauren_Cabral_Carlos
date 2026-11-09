#!/usr/bin/env bash
# Atividade 3 — Parte D (Mount e menor privilégio) — Papel 5.
# Cinco execuções (D0..D4), da mais permissiva (root, caps padrão, rw) até a exigida
# no enunciado (não-root, --cap-drop=ALL, no-new-privileges, /dados:ro).
#
# Uso, a partir de atividade3/, com a imagem da Parte A já baixada:
#   export IMAGEM_LAB="$(docker image inspect --format '{{index .RepoDigests 0}}' python:3.12-slim)"
#   ./parte_d_readonly.sh
#
# Toca só em ./dados_demo (montado :ro) e numa cópia descartável em /tmp (montada rw).
# Sem --privileged, sem alterar AppArmor/SELinux, sem montar /, home ou docker.sock.
# Se o SELinux (enforcing) negar a leitura, registre o contexto e peça orientação.
set -u

IMAGEM_LAB="${IMAGEM_LAB:?defina IMAGEM_LAB (imagem fixada por digest, Parte A)}"
SRC="dados_demo"
OUT="evidencias/D/$(date +%Y%m%d-%H%M%S)"
WORK="$(mktemp -d)"
U="$(id -u)"; G="$(id -g)"
if [ "$U" = 0 ]; then U=1000; G=1000; fi   # a identidade "não-root" do teste nunca é uid 0

docker image inspect "$IMAGEM_LAB" >/dev/null 2>&1 \
  || { echo "imagem $IMAGEM_LAB ausente no daemon (docker pull)" >&2; exit 1; }
mkdir -p "$OUT"

# 1. Registro do ambiente (sem dump integral de inspect/info: só campos selecionados).
{
  date -Is
  echo "terminal: $(uname -sr)"
  docker version --format 'docker: cliente {{.Client.Version}} | servidor {{.Server.Version}}'
  docker info --format 'daemon: {{.OperatingSystem}} | kernel {{.KernelVersion}} | cgroup v{{.CgroupVersion}} | {{.SecurityOptions}}'
  echo "imagem: $IMAGEM_LAB"
  echo "identidade não-root do teste: $U:$G"
} > "$OUT/ambiente.txt" 2>&1

# 2. Sondas, executadas dentro do contêiner via stdin (heredoc literal).
#    O mountinfo é filtrado para não publicar o caminho do host.
cat > "$OUT/sondas.sh" <<'EOF'
t() { r=$1; shift; s=$("$@" 2>&1 </dev/null); c=$?; printf '%-28s rc=%-3s %s\n' "$r" "$c" "$(printf '%s' "$s" | head -n 1)"; }
echo "--- estado efetivo"
id
readlink /proc/self/ns/mnt
grep -E '^(CapBnd|CapEff|NoNewPrivs)' /proc/self/status
grep ' /dados ' /proc/self/mountinfo | sed -E 's/^([0-9]+ [0-9]+ [0-9]+:[0-9]+) [^ ]+ /\1 <oculto> /'
echo "--- operações em /dados"
t "L  ler texto.txt"        cat /dados/texto.txt
t "E1 criar novo.txt"       touch /dados/novo.txt
t "E2 anexar em texto.txt"  sh -c 'echo x >> /dados/texto.txt'
t "E3 remover texto.txt"    rm /dados/texto.txt
echo "--- outras camadas (fora de /dados)"
t "C1 chown em /tmp"        sh -c 'touch /tmp/f && chown 1234 /tmp/f'
t "C2 escrever em /etc"     sh -c 'echo x > /etc/lab-x'
EOF

# 3. Fixture sintética, recriada antes de cada execução.
#    Diretório real (usado em :ro) com modo 755/644; cópia descartável (usada em rw)
#    com 777/666, para que as permissões UNIX nunca expliquem sozinhas uma negação.
prep() {
  mkdir -p "$SRC" || exit 1
  rm -f "$SRC/novo.txt"
  printf '%s\n' 'Documento sintetico' > "$SRC/texto.txt" || exit 1
  chmod 755 "$SRC"; chmod 644 "$SRC/texto.txt"
  rm -rf "$WORK/dados_rw"
  mkdir "$WORK/dados_rw" || exit 1
  printf '%s\n' 'Documento sintetico' > "$WORK/dados_rw/texto.txt" || exit 1
  chmod 777 "$WORK/dados_rw"; chmod 666 "$WORK/dados_rw/texto.txt"
}

# 4. Execuções. A D4 é a configuração exigida no enunciado.
NAMES=(D0_rw_root_padrao D1_ro_root_padrao D2_ro_root_sem_caps D3_rw_endurecido D4_ro_endurecido)
FLAGS=(
  "--user 0"
  "--user 0"
  "--user 0 --cap-drop=ALL"
  "--user $U:$G --cap-drop=ALL --security-opt no-new-privileges"
  "--user $U:$G --cap-drop=ALL --security-opt no-new-privileges"
)
MODOS=(rw ro ro rw ro)

for i in "${!NAMES[@]}"; do
  n=${NAMES[$i]}; f=${FLAGS[$i]}; m=${MODOS[$i]}
  prep
  if [ "$m" = ro ]; then
    HDIR="$SRC"; V="$PWD/$SRC:/dados:ro"; SHOW="./$SRC:/dados:ro"
  else
    HDIR="$WORK/dados_rw"; V="$WORK/dados_rw:/dados"; SHOW="<copia-descartavel>:/dados"
  fi
  {
    echo "### $n"
    echo "# docker run --rm -i --network none $f -v $SHOW $IMAGEM_LAB sh -s"
    echo "# host antes"
    ls -ln "$HDIR"; sha256sum "$HDIR/texto.txt"
    # $f sem aspas de propósito: precisa ser dividido em palavras.
    # shellcheck disable=SC2086
    docker run --rm -i --network none $f -v "$V" "$IMAGEM_LAB" sh -s < "$OUT/sondas.sh"
    echo "# host depois"
    ls -ln "$HDIR"; sha256sum "$HDIR/texto.txt" 2>&1
  } 2>&1 | tee "$OUT/$n.txt"
done

# 5. Resumo, verificação do controle rw e limpeza.
grep -hE '^(###|uid=|CapEff|NoNewPrivs|L |E[0-9]|C[0-9])' "$OUT"/D?_*.txt > "$OUT/resumo.txt"
if ! grep -q '^E1.*rc=0' "$OUT"/D3_*.txt; then
  echo "AVISO: o controle rw (D3) não criou o arquivo; a negação em D4 não é atribuível a :ro." \
       "Verifique permissões/FS do ambiente." | tee -a "$OUT/resumo.txt"
fi
rm -rf "$WORK"
echo "evidências em: $OUT (resumo: $OUT/resumo.txt)"
