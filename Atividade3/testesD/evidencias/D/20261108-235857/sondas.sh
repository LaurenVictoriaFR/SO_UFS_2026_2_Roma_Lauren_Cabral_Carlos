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
