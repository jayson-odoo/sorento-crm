# Lookup meaning floors, gemini-embedding-001 (cached vectors, zero API spend)

mo = meaning-only pairs (spelling < spell floor and partial < partial floor, `list_resolver.FLOORS`). Precision counts wrong rows and phrases that name nothing in the list as false positives. Best floor = highest mo recall with mo precision >= 0.95 over the 0.55..0.85 sweep.

| list | positives (meaning-only) | negatives | current floor | P / R all pairs at current | P / R meaning-only at current | best floor with mo P >= 0.95 / recall | decision |
|---|---|---|---|---|---|---|---|
| category | 66 (42 mo) | 315 | 0.70 | 0.39 / 0.95 | mo 0.34 / 0.93 (tp 39, fp 77); fixture mo 0.46 / 0.93 (tp 38, fp 44) | 0.85 / 0.10 | strict bound only; decided on the fixture decisions below |
| file_type | 26 (3 mo) | 255 | 0.65 | 0.80 / 0.92 | mo 0.25 / 0.33 (tp 1, fp 3); fixture mo 0.33 / 0.50 (tp 1, fp 2) | 0.70 / 0.33 | strict bound only; decided on the fixture decisions below |
| brand | 15 (0 mo) | 225 | 0.60 | 0.79 / 1.00 | mo 0.00 / n/a (tp 0, fp 4); fixture mo 0.00 / n/a (tp 0, fp 2) | none / n/a | strict bound only; decided on the fixture decisions below |
| sales_channel | 4 (0 mo) | 124 | 0.65 | 1.00 / 1.00 | mo n/a / n/a (tp 0, fp 0); fixture mo n/a / n/a (tp 0, fp 0) | none / n/a | strict bound only; decided on the fixture decisions below |

## Fixture decisions (the pinned metric)

One decision per meaning-only phrase (no row reaches it by spelling or partial; the nearest row by meaning is at or above the floor). Correct = a positive phrase whose nearest row is one of its gold rows; a negative phrase that gets a row, or a wrong row, is a false positive.

| list | meaning-only positives | decisions at current | right | precision | recall | best floor with precision >= 0.95 | decision | wrong decisions at current |
|---|---|---|---|---|---|---|---|---|
| category | 35 | 34 | 32 | 0.94 | 0.91 | 0.71: 30 of 31 right, recall 0.86 | precision 0.94 at 0.70 is under 0.95; 0.71 reaches it: owner decides | flush tank -> Flush valve (0.83); jet spray -> Hand shower (0.7) |
| file_type | 2 | 2 | 1 | 0.50 | 0.50 | 0.70: 1 of 1 right, recall 0.50 | 2 decisions: too few to move a floor, KEEP 0.65 | cwc -> Certification (0.67) |
| brand | 0 | 1 | 0 | 0.00 | n/a | none | 1 decisions: too few to move a floor, KEEP 0.60 | single piece -> OTHERS (OTHERS) (0.6) |
| sales_channel | 0 | 0 | 0 | n/a | n/a | none | 0 decisions: too few to move a floor, KEEP 0.65 | none |

## Pair metric (gold messages + fixture)

(wrong rows of a positive phrase count as false positives, so this is the strict bound)

Pair counts (list, source, kind): brand/fixture/neg 15; brand/fixture/ool 180; brand/fixture/pos 5; brand/gold/neg 30; brand/gold/pos 10; category/fixture/neg 126; category/fixture/ool 117; category/fixture/pos 42; category/gold/neg 72; category/gold/pos 24; file_type/fixture/neg 33; file_type/fixture/ool 168; file_type/fixture/pos 11; file_type/gold/neg 45; file_type/gold/ool 9; file_type/gold/pos 15; sales_channel/fixture/neg 1; sales_channel/fixture/ool 120; sales_channel/fixture/pos 1; sales_channel/gold/neg 3; sales_channel/gold/pos 3

Skipped for missing vectors: category/no vector: 5; file_type/no vector: 3

Sweep (list,floor,P_all,R_all,P_mo,R_mo,tp_mo,fp_mo):
```
list,floor,P_all,R_all,P_mo,R_mo,tp_mo,fp_mo
category,0.55,0.18,1.00,0.13,1.00,42,283
category,0.56,0.18,1.00,0.13,1.00,42,283
category,0.57,0.18,1.00,0.13,1.00,42,274
category,0.58,0.19,1.00,0.14,1.00,42,256
category,0.59,0.20,1.00,0.15,1.00,42,235
category,0.6,0.22,1.00,0.17,1.00,42,209
category,0.61,0.24,1.00,0.19,1.00,42,184
category,0.62,0.25,1.00,0.20,1.00,42,167
category,0.63,0.27,1.00,0.22,1.00,42,153
category,0.64,0.29,1.00,0.23,1.00,42,140
category,0.65,0.30,0.98,0.24,0.98,41,127
category,0.66,0.31,0.98,0.25,0.98,41,121
category,0.67,0.33,0.98,0.27,0.98,41,109
category,0.68,0.34,0.98,0.28,0.98,41,103
category,0.69,0.36,0.95,0.31,0.93,39,88
category,0.7,0.39,0.95,0.34,0.93,39,77
category,0.71,0.40,0.91,0.35,0.88,37,68
category,0.72,0.45,0.89,0.41,0.86,36,51
category,0.73,0.46,0.86,0.42,0.81,34,46
category,0.74,0.46,0.83,0.42,0.76,32,45
category,0.75,0.53,0.76,0.52,0.67,28,26
category,0.76,0.59,0.76,0.58,0.67,28,20
category,0.77,0.63,0.68,0.55,0.55,23,19
category,0.78,0.71,0.67,0.67,0.52,22,11
category,0.79,0.73,0.65,0.68,0.50,21,10
category,0.8,0.74,0.59,0.64,0.43,18,10
category,0.81,0.76,0.56,0.64,0.38,16,9
category,0.82,0.74,0.47,0.56,0.24,10,8
category,0.83,0.78,0.42,0.50,0.17,7,7
category,0.84,0.93,0.41,0.86,0.14,6,1
category,0.85,1.00,0.36,1.00,0.10,4,0
file_type,0.55,0.16,1.00,0.02,1.00,3,136
file_type,0.56,0.19,1.00,0.03,1.00,3,106
file_type,0.57,0.22,1.00,0.03,1.00,3,88
file_type,0.58,0.30,1.00,0.05,1.00,3,57
file_type,0.59,0.40,1.00,0.08,1.00,3,35
file_type,0.6,0.46,1.00,0.10,1.00,3,26
file_type,0.61,0.57,1.00,0.16,1.00,3,16
file_type,0.62,0.62,1.00,0.20,1.00,3,12
file_type,0.63,0.70,1.00,0.30,1.00,3,7
file_type,0.64,0.71,0.92,0.14,0.33,1,6
file_type,0.65,0.80,0.92,0.25,0.33,1,3
file_type,0.66,0.84,0.81,0.50,0.33,1,1
file_type,0.67,0.86,0.73,0.50,0.33,1,1
file_type,0.68,0.90,0.73,1.00,0.33,1,0
file_type,0.69,0.90,0.73,1.00,0.33,1,0
file_type,0.7,0.90,0.69,1.00,0.33,1,0
file_type,0.71,1.00,0.65,n/a,0.00,0,0
file_type,0.72,1.00,0.65,n/a,0.00,0,0
file_type,0.73,1.00,0.50,n/a,0.00,0,0
file_type,0.74,1.00,0.50,n/a,0.00,0,0
file_type,0.75,1.00,0.50,n/a,0.00,0,0
file_type,0.76,1.00,0.46,n/a,0.00,0,0
file_type,0.77,1.00,0.46,n/a,0.00,0,0
file_type,0.78,1.00,0.46,n/a,0.00,0,0
file_type,0.79,1.00,0.46,n/a,0.00,0,0
file_type,0.8,1.00,0.46,n/a,0.00,0,0
file_type,0.81,1.00,0.46,n/a,0.00,0,0
file_type,0.82,1.00,0.46,n/a,0.00,0,0
file_type,0.83,1.00,0.46,n/a,0.00,0,0
file_type,0.84,1.00,0.46,n/a,0.00,0,0
file_type,0.85,1.00,0.46,n/a,0.00,0,0
brand,0.55,0.12,1.00,0.00,n/a,0,105
brand,0.56,0.16,1.00,0.00,n/a,0,77
brand,0.57,0.22,1.00,0.00,n/a,0,53
brand,0.58,0.38,1.00,0.00,n/a,0,24
brand,0.59,0.65,1.00,0.00,n/a,0,8
brand,0.6,0.79,1.00,0.00,n/a,0,4
brand,0.61,1.00,1.00,n/a,n/a,0,0
brand,0.62,1.00,1.00,n/a,n/a,0,0
brand,0.63,1.00,1.00,n/a,n/a,0,0
brand,0.64,1.00,1.00,n/a,n/a,0,0
brand,0.65,1.00,1.00,n/a,n/a,0,0
brand,0.66,1.00,1.00,n/a,n/a,0,0
brand,0.67,1.00,1.00,n/a,n/a,0,0
brand,0.68,1.00,1.00,n/a,n/a,0,0
brand,0.69,1.00,1.00,n/a,n/a,0,0
brand,0.7,1.00,1.00,n/a,n/a,0,0
brand,0.71,1.00,1.00,n/a,n/a,0,0
brand,0.72,1.00,1.00,n/a,n/a,0,0
brand,0.73,1.00,1.00,n/a,n/a,0,0
brand,0.74,1.00,1.00,n/a,n/a,0,0
brand,0.75,1.00,1.00,n/a,n/a,0,0
brand,0.76,1.00,1.00,n/a,n/a,0,0
brand,0.77,1.00,1.00,n/a,n/a,0,0
brand,0.78,1.00,1.00,n/a,n/a,0,0
brand,0.79,1.00,1.00,n/a,n/a,0,0
brand,0.8,1.00,1.00,n/a,n/a,0,0
brand,0.81,1.00,1.00,n/a,n/a,0,0
brand,0.82,1.00,1.00,n/a,n/a,0,0
brand,0.83,1.00,1.00,n/a,n/a,0,0
brand,0.84,1.00,1.00,n/a,n/a,0,0
brand,0.85,1.00,1.00,n/a,n/a,0,0
sales_channel,0.55,0.11,1.00,0.00,n/a,0,34
sales_channel,0.56,0.14,1.00,0.00,n/a,0,25
sales_channel,0.57,0.17,1.00,0.00,n/a,0,19
sales_channel,0.58,0.27,1.00,0.00,n/a,0,11
sales_channel,0.59,0.33,1.00,0.00,n/a,0,8
sales_channel,0.6,0.36,1.00,0.00,n/a,0,7
sales_channel,0.61,0.57,1.00,0.00,n/a,0,3
sales_channel,0.62,0.57,1.00,0.00,n/a,0,3
sales_channel,0.63,0.80,1.00,0.00,n/a,0,1
sales_channel,0.64,1.00,1.00,n/a,n/a,0,0
sales_channel,0.65,1.00,1.00,n/a,n/a,0,0
sales_channel,0.66,1.00,1.00,n/a,n/a,0,0
sales_channel,0.67,1.00,1.00,n/a,n/a,0,0
sales_channel,0.68,1.00,1.00,n/a,n/a,0,0
sales_channel,0.69,1.00,1.00,n/a,n/a,0,0
sales_channel,0.7,1.00,1.00,n/a,n/a,0,0
sales_channel,0.71,1.00,1.00,n/a,n/a,0,0
sales_channel,0.72,1.00,1.00,n/a,n/a,0,0
sales_channel,0.73,1.00,1.00,n/a,n/a,0,0
sales_channel,0.74,1.00,1.00,n/a,n/a,0,0
sales_channel,0.75,1.00,1.00,n/a,n/a,0,0
sales_channel,0.76,1.00,1.00,n/a,n/a,0,0
sales_channel,0.77,1.00,1.00,n/a,n/a,0,0
sales_channel,0.78,1.00,1.00,n/a,n/a,0,0
sales_channel,0.79,1.00,1.00,n/a,n/a,0,0
sales_channel,0.8,1.00,1.00,n/a,n/a,0,0
sales_channel,0.81,1.00,1.00,n/a,n/a,0,0
sales_channel,0.82,1.00,1.00,n/a,n/a,0,0
sales_channel,0.83,1.00,1.00,n/a,n/a,0,0
sales_channel,0.84,1.00,1.00,n/a,n/a,0,0
sales_channel,0.85,1.00,1.00,n/a,n/a,0,0
```
