#!/usr/bin/env bash
# Regression check for the GV2 tools: short, fixed-seed runs of every tool. The text output (timings stripped)
# and every file the tools write go to runs/regression/<name>/. Run it before and after a change and compare:
#     tools/gv2_examples/regression_check.sh before
#     tools/gv2_examples/regression_check.sh after
#     diff -r runs/regression/before runs/regression/after && echo IDENTICAL
# Needs the reference dump runs/gv2/gv2_27818.csv (see README) and the GPU engine. Takes ~5 minutes.
set -u
cd "$(dirname "$0")/../.."  # repo root
NAME=${1:?usage: regression_check.sh <name>}
OUT=runs/regression/$NAME
rm -rf "$OUT"; mkdir -p "$OUT"
GH=samples/tracks/ghost-valley-2/ghosts
RES=samples/tracks/ghost-valley-2/results
strip() { sed -E 's/ \[[0-9]+s\]//; s/time limit reached.*//'; }
run() { local tag=$1; shift; echo "== $tag"; python "$@" 2>&1 | grep -v -i warn | strip > "$OUT/$tag.txt"; tail -1 "$OUT/$tag.txt"; }

run hit_default    tools/gv2_hit_evolve.py --pop 256 --gens 10 --seed-rng 3 --out "$OUT/hit_default"
run hit_options    tools/gv2_hit_evolve.py --pop 256 --gens 10 --seed-rng 4 --need-drift --btn-from $GH/rGV2_27.818_slimpanda_best.rkg \
                   --yaw-contact-target -114.7 --w-yaw-contact 20 --w-postlat 2 --seed $RES/gv2_L1hit_A.rkg --out "$OUT/hit_options"
run tail_line      tools/gv2_tail_evolve.py --base $RES/gv2_L1hit_A.rkg --ref-dump runs/gv2/gv2_27818.csv --pop 256 --gens 10 --seed-rng 5 \
                   --seed $RES/gv2_L1_A_superhops.rkg --out "$OUT/tail_line"
run tail_lap2      tools/gv2_tail_evolve.py --base $RES/gv2_L1_A_superhops.rkg --ref-dump runs/gv2/gv2_27818.csv --from-row 976 --to-row 1040 \
                   --tail-shift 1 --sim-to 1110 --lat-rows 1000 1010 --ev2-rows 1032 1044 --ahead-row 1030 --sync-rows 1030 1060 1090 1110 \
                   --sync-y-from 1060 --comp-row 1100 --pop 256 --gens 10 --seed-rng 6 --out "$OUT/tail_lap2"
run splice_line    tools/gv2_splice.py --cand $RES/gv2_L1hit_E.rkg --s 960 966 --d -1 1 --top 4 --out "$OUT/splice_line"
run splice_comp    tools/gv2_splice.py --cand $RES/gv2_L1_A_superhops.rkg --s 990 994 --d 0 1 --to-row 1110 --at-rows 976 1050 1110 --rank-comp --top 3 --out "$OUT/splice_comp"
cp $RES/gv2_L1hit_E.rkg $RES/gv2_L1_A_superhops.rkg "$OUT/"
run verify         tools/gv2_verify.py --ref-dump runs/gv2/gv2_27818.csv "$OUT/gv2_L1hit_E.rkg" "$OUT/gv2_L1_A_superhops.rkg"
run laps           tools/gv2_laps.py runs/gv2/gv2_27818.csv "$OUT/gv2_L1hit_E_cpu.csv" "$OUT/gv2_L1_A_superhops_cpu.csv"
run hitcmp         tools/gv2_hitcmp.py runs/gv2/gv2_27818.csv "$OUT/gv2_L1hit_E_cpu.csv"
run metrics        tools/gv2_metrics.py runs/gv2/gv2_27818.csv "$OUT/gv2_L1hit_E_cpu.csv" "$OUT/gv2_L1_A_superhops_cpu.csv@0"
run parity         tools/gv2_gpu_parity.py $GH/rGV2_27.818_slimpanda_best.rkg runs/gv2/gv2_27818.csv 900
echo "done: $OUT"
