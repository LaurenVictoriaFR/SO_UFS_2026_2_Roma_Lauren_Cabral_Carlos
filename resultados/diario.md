  479  2026-10-19 22:36:51 sudo apt update
  480  2026-10-19 22:37:37 sudo apt install python3-pip python3-numpy python3-matplotlib sysstat strace
  487  2026-10-19 22:41:17 ollama pull llama3.2:3b
  488  2026-10-19 22:41:44 git clone https://github.com/LaurenVictoriaFR/SO_UFS_2026_2_Roma_Lauren_Cabral_Carlos.git ~/genresearch
  490  2026-10-19 22:41:53 cd genresearch/
  492  2026-10-19 22:42:31 mkdir -p resultados/ambiente && rm -f logs/*.log
  493  2026-10-19 22:42:47 { uname -a; cat /etc/os-release; lscpu; free -h; lsblk; df -h ~; swapon --show; python3 --version; ollama list; git log -1 --format=%h; date; nvidia-smi | head -4; } > resultados/ambiente/ambiente.txt 2>&1
  495  2026-10-19 22:42:47 vmstat 1 10 > resultados/ambiente/vmstat.txt
  496  2026-10-19 22:42:56 iostat -xz 1 10 > resultados/ambiente/iostat.txt
  503  2026-10-19 22:44:19 python3 codigo/teste_concorrencia.py
  504  2026-10-19 22:44:28 python3 codigo/demonstracao.py
  505  2026-10-19 22:46:02 for i in 1 2 3; do python3 codigo/ingestao.py gerar --docs 200 --saida dados/pequeno; python3 codigo/ingestao.py ingerir --corpus dados/pequeno/docs --saida dados/pequeno; cp dados/pequeno/estatisticas_ingestao.json resultados/ingestao_pequeno_$i.json; done
  506  2026-10-19 22:48:28 for i in 1 2 3; do python3 codigo/ingestao.py gerar --docs 5000 --saida dados/medio; python3 codigo/ingestao.py ingerir --corpus dados/medio/docs --saida dados/medio; cp dados/medio/estatisticas_ingestao.json resultados/ingestao_medio_$i.json; done
  507  2026-10-19 22:51:15 for i in 1 2 3; do python3 codigo/ingestao.py gerar --docs 50000 --saida dados/grande; python3 codigo/ingestao.py ingerir --corpus dados/grande/docs --saida dados/grande; cp dados/grande/estatisticas_ingestao.json resultados/ingestao_grande_$i.json; done
  508  2026-10-19 22:56:12 cd resultados && python3 ../codigo/mmap_experimento.py && rm -f corpus_simulado_*.bin ; cd ..
  509  2026-10-19 22:57:40 vmstat 1 > resultados/vmstat_c5.txt &
  510  2026-10-19 22:57:40 python3 codigo/experimento_c5.py --indices dados/pequeno dados/medio dados/grande --saida resultados/c5.csv
  511  2026-10-19 23:08:03 kill %1
  512  2026-10-19 23:10:47 python3 codigo/experimento_c3.py
  513  2026-10-19 23:20:03 mkdir -p resultados/c3_sim && mv resultados/c3_*.csv logs/c3_* resultados/c3_sim/
  514  2026-10-19 23:20:49 rm -f logs/papel4.log
  515  2026-10-19 23:21:02 ollama serve
  516  2026-10-19 23:22:16 python3 codigo/experimento_c3.py --processador recuperacao_resposta:processar --requisicoes 8 --trabalhadores 1 2 4 --capacidades 8 --produtores 2 --repeticoes 3 --sem-falhas &
  517  2026-10-19 23:22:16 python3 codigo/amostrador.py --pid $! --saida resultados/amostras_c3_real.csv
  518  2026-10-19 23:26:25 wait
  519  2026-10-19 23:26:25 mkdir -p resultados/c3_real
  520  2026-10-19 23:26:25 mv resultados/c3_*.csv logs/c3_* resultados/c3_real/
  521  2026-10-19 23:26:25 cp logs/papel4.log resultados/c3_real/
  536  2026-10-19 23:39:07 sudo systemctl stop ollama
  537  2026-10-19 23:39:11 python3 codigo/recuperacao_resposta.py "O que é paginação?" 2>&1 | tee resultados/c6_ollama_fora.txt
  538  2026-10-19 23:40:09 cat resultados/c6_ollama_fora.txt 
  539  2026-10-19 23:41:38 grep -E 'FALHA|ENCERRAMENTO' logs/papel4.log | tail -3 | tee -a resultados/c6_ollama_fora.txt
  540  2026-10-19 23:42:34 ollama serve > /dev/null 2>&1 &
  541  2026-10-19 23:42:34 mv dados/pequeno dados/pequeno_off
  542  2026-10-19 23:42:57 python3 codigo/recuperacao_resposta.py "teste" 2>&1 | tail -5 | tee resultados/c6_indice_ausente.txt
  543  2026-10-19 23:43:20 mv dados/pequeno_off dados/pequeno
  544  2026-10-19 23:44:25 python3 codigo/experimento_c4.py --indice dados/pequeno --saida resultados/c4_pequeno.csv &
  545  2026-10-19 23:44:25 python3 codigo/amostrador.py --pid $! --saida resultados/amostras_c4.csv ; wait
  546  2026-10-19 23:53:21 python3 codigo/experimento_c4.py --indice dados/medio --saida resultados/c4_medio.csv
  553  2026-10-20 00:35:10 ollama run llama3.2:3b
  554  2026-10-20 00:41:47 python3 -c "import sys; sys.path.insert(0,'codigo'); \
from recuperacao_resposta import sistema as s; \
print(s.responder('O que é paginação?')['metricas']); \
print(s.responder('Explique paginação')['metricas']); \
print(s.estatisticas_cache())" | tee resultados/cache_real.txt
  555  2026-10-20 00:42:44 python3 codigo/metricas.py --log logs/papel4.log resultados/c3_real/c3_*/*.log --mmap $(ls resultados/resultados_experimento_*.csv | tail -1) --ingestao resultados/ingestao_*.json --c3 $(ls resultados/c3_sim/c3_resumo_*.csv | tail -1) --c4 resultados/c4_pequeno.csv --saida resultados/analise
  556  2026-10-20 00:42:46 tar czf resultados_$(date +%Y%m%d).tgz resultados logs dados/*/estatisticas_ingestao.json
  557  2026-10-20 00:45:53 HISTTIMEFORMAT="%F %T " history | tee resultados/diario.md
