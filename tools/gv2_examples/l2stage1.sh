cd "$(dirname "$0")/../.."  # repo root
SYNC="1028 1030 1032 1035 1040 1045 1050 1055 1060 1065 1070 1075 1080 1085 1090 1095 1100 1105 1110"
for D in ${SHIFTS:-1 0}; do
  echo "=== stage 1, tail-shift $D ==="
  python tools/gv2_tail_evolve.py --base runs/gv2/_l2probe_d$D.rkg --from-row 976 --to-row 1040 --tail-shift $D --sim-to 1110 \
    --lat-rows 1000 1010 1020 --ev2-rows 1032 1044 --sync-rows $SYNC --sync-y-from 1028 --pop 2048 --gens ${GENS:-5000} --time-limit 600 \
    --seed runs/gv2/l2s1_0.rkg --seed runs/gv2/_l2seed_d${D}_T2.rkg --seed runs/gv2/_l2seed_d${D}_S990.rkg --out runs/gv2/l2st1_$D 2>&1 | grep --line-buffered -vi warn
done
echo ALLDONE
