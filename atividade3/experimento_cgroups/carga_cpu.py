#!/usr/bin/env python3

import resource
import sys
import time

LIMITE_S = 60
LOTE = 1_000_000          
MASC32 = 0xFFFFFFFF
MASC64 = 0xFFFFFFFFFFFFFFFF


def main():
    n = int(sys.argv[1])
    x = 12345            
    soma = 0
    feitas = 0
    status = "OK"

    t0 = time.perf_counter()
    c0 = time.process_time()
    while feitas < n:
        for _ in range(min(LOTE, n - feitas)):
            x = (x * 1103515245 + 12345) & MASC32
            soma = (soma + x) & MASC64
        feitas += min(LOTE, n - feitas)
        if time.perf_counter() - t0 > LIMITE_S:
            status = "TIMEOUT"
            break
    wall = time.perf_counter() - t0
    cpu = time.process_time() - c0

    rss_kb = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss  
    print(f"n={n}")
    print(f"feitas={feitas}")
    print(f"checksum={soma}")
    print(f"status={status}")
    print(f"wall_s={wall:.3f}")
    print(f"cpu_s={cpu:.3f}")
    print(f"rss_kb={rss_kb}")
    sys.exit(0 if status == "OK" else 2)


if __name__ == "__main__":
    main()
