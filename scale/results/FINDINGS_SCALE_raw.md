# Scale benchmark results

_source: `results/results.csv` ; cold-session priced at Sonnet list $3/M in, $15/M out_

## Verdict — cheapest arm at each N (realistic per-task cost, passing only)

| N | ranking (cheapest → priciest) |
|---|---|
| 1 | B1 preload ($0.102)  <  B3 blind grep ($0.103)  <  B2 index+grep ($0.111)  <  C archcore ($0.147)  |  ✗fail: A cold |
| 20 | B2 index+grep ($0.113)  <  B3 blind grep ($0.120)  <  B1 preload ($0.134)  <  C archcore ($0.147)  |  ✗fail: A cold |
| 80 | B2 index+grep ($0.119)  <  B3 blind grep ($0.123)  <  C archcore ($0.147)  <  B1 preload ($0.238)  |  ✗fail: A cold |
| 160 | B3 blind grep ($0.124)  <  B2 index+grep ($0.130)  <  C archcore ($0.141)  <  B1 preload ($0.386)  |  ✗fail: A cold |
| 320 | B3 blind grep ($0.112)  <  C archcore ($0.147)  <  B2 index+grep ($0.152)  <  B1 preload ($0.681)  |  ✗fail: A cold |

### Crossover points — N where **C (archcore)** overtakes a baseline

| vs baseline | realistic N* | (no-cache N*) |
|---|---|---|
| C vs B1 preload | ≈ 27 docs | ≈ 207 docs |
| C vs B2 index+grep | ≈ 272 docs | never (in range) |
| C vs B3 blind grep | never (in range) | never (in range) |

_N* = KB size where archcore's cost drops to/below the baseline. "never" = baseline stays cheaper across the whole tested range._

## Crossover — fixed task, KB size N sweep

Cost = **realistic per-task** USD (fresh session, intra-task turns cached; order-independent). pass = fraction correct over trials.

| N | A cold $ | B1 preload $ | B2 index+grep $ | B3 blind grep $ | C archcore $ | A pass | B1 pass | B2 pass | B3 pass | C pass |
|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 0.2040 | 0.1015 | 0.1114 | 0.1032 | 0.1472 | 0% | 100% | 100% | 100% | 100% |
| 20 | 0.1829 | 0.1340 | 0.1129 | 0.1205 | 0.1466 | 20% | 100% | 100% | 100% | 100% |
| 80 | 0.1878 | 0.2376 | 0.1186 | 0.1232 | 0.1466 | 0% | 100% | 100% | 100% | 100% |
| 160 | 0.1953 | 0.3857 | 0.1296 | 0.1242 | 0.1407 | 0% | 100% | 100% | 100% | 100% |
| 320 | 0.2277 | 0.6811 | 0.1517 | 0.1115 | 0.1469 | 0% | 100% | 100% | 100% | 100% |

### Context tokens processed (input+cache_create+cache_read+output), median

| N | A cold | B1 preload | B2 index+grep | B3 blind grep | C archcore |
|---|---|---|---|---|---|
| 1 | 304,952 | 27,025 | 53,935 | 80,393 | 142,336 |
| 20 | 285,772 | 35,688 | 54,684 | 80,845 | 141,998 |
| 80 | 294,894 | 63,314 | 57,462 | 82,833 | 141,990 |
| 160 | 260,781 | 102,793 | 62,892 | 83,495 | 116,714 |
| 320 | 352,088 | 181,586 | 73,659 | 83,515 | 142,020 |

### Turns (median)

| N | A cold | B1 preload | B2 index+grep | B3 blind grep | C archcore |
|---|---|---|---|---|---|
| 1 | 13 | 1 | 2 | 3 | 5 |
| 20 | 11 | 1 | 2 | 3 | 5 |
| 80 | 13 | 1 | 2 | 3 | 5 |
| 160 | 12 | 1 | 2 | 3 | 4 |
| 320 | 13 | 1 | 2 | 3 | 5 |

## Realistic per-task cost vs N (each █ ≈ $0.017)

```
A cold          
  N=1    ████████████                              $0.204
  N=20   ███████████                               $0.183
  N=80   ███████████                               $0.188
  N=160  ███████████                               $0.195
  N=320  █████████████                             $0.228
B1 preload      
  N=1    ██████                                    $0.102
  N=20   ████████                                  $0.134
  N=80   ██████████████                            $0.238
  N=160  ███████████████████████                   $0.386
  N=320  ████████████████████████████████████████  $0.681
B2 index+grep   
  N=1    ███████                                   $0.111
  N=20   ███████                                   $0.113
  N=80   ███████                                   $0.119
  N=160  ████████                                  $0.130
  N=320  █████████                                 $0.152
B3 blind grep   
  N=1    ██████                                    $0.103
  N=20   ███████                                   $0.120
  N=80   ███████                                   $0.123
  N=160  ███████                                   $0.124
  N=320  ███████                                   $0.112
C archcore      
  N=1    █████████                                 $0.147
  N=20   █████████                                 $0.147
  N=80   █████████                                 $0.147
  N=160  ████████                                  $0.141
  N=320  █████████                                 $0.147
```

### Cost-model spread (per task) — real is the headline; cold/warm bound it

| arm @ N=max | realistic | no-cache (cold) | measured warm |
|---|---|---|---|
| A cold @ N=320 | $0.228 | $1.078 | $0.193 |
| B1 preload @ N=320 | $0.681 | $0.545 | $0.055 |
| B2 index+grep @ N=320 | $0.152 | $0.224 | $0.027 |
| B3 blind grep @ N=320 | $0.112 | $0.254 | $0.038 |
| C archcore @ N=320 | $0.147 | $0.432 | $0.083 |

## Workload — fixed KB (N=80), 20-task suite

Per-arm **suite total** = sum over tasks of the median per-task cost (cost to run the whole suite once).

| Arm | suite realistic $ | (cold) | (warm) | pass | med turns/task | med ctx/task |
|---|---|---|---|---|---|---|
| B2 index+grep | 2.3746 | 3.4952 | 0.4746 | 100% | 2 | 57,460 |
| B3 blind grep | 2.2939 | 5.0397 | 0.8494 | 100% | 3 | 82,847 |
| C archcore | 2.7157 | 7.3702 | 1.1286 | 100% | 5 | 141,955 |

