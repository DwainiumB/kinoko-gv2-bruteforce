cd "$(dirname "$0")/../.."  # repo root
for X in D F A; do
  echo "=== $X ===" 
  python tools/gv2_tail_evolve.py --base runs/gv2/gv2_L1hit_$X.rkg --pop 2048 --gens 300 --time-limit 600 --to-row 1000 --tail-shift 1 --sim-to 1040 --lat-rows 976 990 1010 1030 --seed runs/gv2/graft${X}_T1.rkg --seed runs/gv2/splice${X}_0.rkg --out runs/gv2/tail$X 2>&1 | grep --line-buffered -vi warn
done
echo ALLDONE
