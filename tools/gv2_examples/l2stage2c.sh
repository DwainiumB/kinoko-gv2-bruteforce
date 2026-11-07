cd "$(dirname "$0")/../.."  # repo root
SYNC="1130 1140 1150 1154 1158 1162 1166 1170 1174 1178 1182 1186 1190 1195 1200 1205 1210 1220 1240 1260 1280 1300"
echo "=== stage 2c, tail-shift 0 (line up with the ramp) ==="
python tools/gv2_tail_evolve.py --base runs/gv2/l2st1_0_0.rkg --from-row 1095 --to-row 1200 --tail-shift 0 --sim-to 1320 \
  --lat-rows 1140 1146 1150 1154 1158 1162 --w-lat 5 --lat-tol 20 --ev-row 1154 --w-ev 0 --w-sp 10 --w-cross 0 --sync-rows $SYNC --sync-y-from 1150 --comp-row 1300 \
  --pop 2048 --gens ${GENS:-5000} --time-limit 720 --seed runs/gv2/l2st2b_0_0.rkg --seed runs/gv2/l2st2_0_0.rkg --out runs/gv2/l2st2c_0 2>&1 | grep --line-buffered -vi warn
echo ALLDONE
