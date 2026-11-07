cd "$(dirname "$0")/../.."  # repo root
gpu_busy() { powershell -NoProfile -Command "@(Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { \$_.CommandLine -match 'gv2_tail_evolve|gv2_hit_evolve|gv2_splice|evolve.py|gpu_' }).Count" | tr -d '\r'; }
echo "waiting for the GPU ($(date +%T))"
until grep -q ALLDONE runs/gv2/l2stage2b.log 2>/dev/null; do sleep 15; done
while true; do
  b1=$(gpu_busy); sleep 30; b2=$(gpu_busy)
  [ "$b1" = "0" ] && [ "$b2" = "0" ] && break
done
echo "GPU free, starting ($(date +%T))"; python tools/mem.py | tail -1
COMMON="--base samples/tracks/ghost-valley-2/ghosts/rGV2_20.444_sircorvid.rkg --pop 2048 --gens 200 --time-limit 300 --w-pace 0 --p-y 0.85"
run() { echo "=== $1 ==="; python tools/gv2_hit_evolve.py $COMMON "${@:2}" --out runs/gv2/sirc$1 2>&1 | grep --line-buffered -vi warn; }
run S1 --budget 10 --seed-rng 1
run S2 --budget 10 --seed-rng 2
run S3 --budget 10 --seed-rng 3 --from-row 740
run S4 --budget 6 --seed-rng 4
echo ALLDONE
