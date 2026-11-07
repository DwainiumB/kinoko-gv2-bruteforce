#!/usr/bin/env python3
"""Search the inputs after the fast block hit on GV2: the superhops to the L1 line, or the lap 2 entry (GPU).

What is searched: stick X, stick Y (-7..+7), face buttons and trick for every row from --from-row to --to-row.
Rows before --from-row are the base run (usually a run with the hit already found, e.g. gv2_L1hit_E). Rows after
--to-row are the reference's inputs taken --tail-shift rows later (tail shift 1 = play the reference's inputs one
frame early, i.e. try to stay one frame ahead of it). Simulation runs to --sim-to.

Mutations: stick edits, moving a hop-timing boundary by one frame (the start or end of a run of equal buttons),
single-frame button toggles (11 <-> 1, i.e. drift held or not), trick copies from the reference (+-1 row), and block
copies from another good genome (crossover).

How a candidate is scored (lower cost = better):
      w_cross * (sub-frame row where it crosses the --line-comp line - the reference's crossing)   (frames; not
                crossed by --sim-to: 1000 + 1000 * completion still missing)
    + w_lat   * mean over --lat-rows of max(lateral offset from the reference path - lat_tol, 0)
    - w_ev    * min(horizontal EV at --ev-row, ev_cap)
    + w_sp    * |speed - reference speed| at --ev-row
    + w_each  * changed values vs the base
    - w_ev2   * mean over --ev2-rows of min(EV, ev2_cap)                      (the 2nd block bounce)
    - w_ahead * frames ahead on the reference path at --ahead-row (clipped to -60..+5; -60 if > 300 off the path)
    + w_sync  * mean over --sync-rows of the distance to the reference at row + tail_shift (capped at sync_cap;
                includes height from --sync-y-from on)
    + w_comp  * race completion short of the reference's at --comp-row      (did the ultra shortcut happen)

Writes the 6 best distinct candidates as <out>_0.rkg .. <out>_5.rkg; after --sim-to each carries the reference's
remaining inputs (shifted), so the files hold a full race.

    python tools/gv2_tail_evolve.py --base runs/gv2/gv2_L1hit_E.rkg --seed runs/gv2/spliceE_0.rkg --out runs/gv2/tailA
"""
import argparse
import os
import time

import numpy as np

import gv2_common as gv2
import brute_force as bf  # noqa: E402  (gv2_common puts tools/ on sys.path)

cp, Engine, make_inputs, COLUMN = gv2.gpu_modules()

# genome columns
STICK_X, STICK_Y, BUTTONS, TRICK = 0, 1, 2, 3
DRIFT_HELD, DRIFT_RELEASED = 11, 1        # button values toggled by the single-frame button mutation


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=os.path.join(gv2.REPO_ROOT, "runs/gv2/gv2_L1hit_E.rkg"), help="run whose inputs are used before --from-row")
    ap.add_argument("--ref", default=gv2.REFERENCE_GHOST, help="reference run (default: the 27.818)")
    ap.add_argument("--ref-dump", default=gv2.REFERENCE_DUMP, help="CPU replay dump of the reference")
    ap.add_argument("--seed", action="append", default=[], help="extra runs whose rows seed part of the population")
    ap.add_argument("--from-row", type=int, default=849, help="first searched row")
    ap.add_argument("--to-row", type=int, default=990, help="last searched row")
    ap.add_argument("--tail-shift", type=int, default=0, help="after --to-row, play the reference's inputs from this many rows later")
    ap.add_argument("--sim-to", type=int, default=1000, help="last simulated row")
    ap.add_argument("--lat-rows", type=int, nargs="+", default=[976, 990], help="rows where distance from the reference path is scored")
    ap.add_argument("--ev-row", type=int, default=976, help="row where EV and speed are scored")
    ap.add_argument("--ev2-rows", type=int, nargs="*", default=[], help="rows where EV is rewarded too (the 2nd block bounce, ~1032/1044)")
    ap.add_argument("--w-ev2", type=float, default=2.0)
    ap.add_argument("--ev2-cap", type=float, default=50.0)
    ap.add_argument("--ahead-row", type=int, default=None, help="reward along-track progress on the ref path at this row (w-ahead per frame)")
    ap.add_argument("--w-ahead", type=float, default=100.0)
    ap.add_argument("--sync-rows", type=int, nargs="*", default=[], help="rows where the distance to the reference position at row + tail_shift costs --w-sync per unit (mean)")
    ap.add_argument("--w-sync", type=float, default=1.0)
    ap.add_argument("--sync-cap", type=float, default=3000.0)
    ap.add_argument("--sync-y-from", type=int, default=None, help="from this row on, the sync distance includes height (py): did the kart take the same jump")
    ap.add_argument("--comp-row", type=int, default=None, help="cost w-comp per unit of race completion short of the reference's (at row + tail_shift) at this row: did the ultra shortcut happen")
    ap.add_argument("--w-comp", type=float, default=2000.0)
    ap.add_argument("--pop", type=int, default=2048, help="population size (races simulated per generation)")
    ap.add_argument("--gens", type=int, default=300)
    ap.add_argument("--elite", type=float, default=0.08, help="share of the best kept unchanged each generation")
    ap.add_argument("--w-cross", type=float, default=100.0, help="weight of the line crossing (per frame)")
    ap.add_argument("--line-comp", type=float, default=2.0, help="completion value of the line scored by w-cross (2.0 = L1 line, 4.0 = finish)")
    ap.add_argument("--cross-after", type=int, default=900, help="only count line crossings after this row")
    ap.add_argument("--w-lat", type=float, default=0.5)
    ap.add_argument("--lat-tol", type=float, default=40.0)
    ap.add_argument("--w-ev", type=float, default=2.0)
    ap.add_argument("--ev-cap", type=float, default=45.0)
    ap.add_argument("--w-sp", type=float, default=1.0)
    ap.add_argument("--w-each", type=float, default=0.3, help="cost per changed value (tie-break toward fewer edits)")
    ap.add_argument("--p-btn", type=float, default=0.35, help="share of mutations that move hop timing / toggle a button")
    ap.add_argument("--p-trick", type=float, default=0.05, help="share of mutations that copy a trick from the reference")
    ap.add_argument("--seed-rng", type=int, default=1, help="random seed (same seed + same inputs = same result)")
    ap.add_argument("--time-limit", type=float, default=1500.0, help="stop after this many seconds and write the candidates")
    ap.add_argument("--out", required=True, help="output prefix for the candidate .rkg files")
    return ap.parse_args()


class TailSearch:
    """The base run, the searched rows and the scoring. A genome is an int8 array (rows, 4): stick X, stick Y,
    buttons, trick."""

    def __init__(self, args, rng):
        self.args, self.rng = args, rng
        self.course, self.character, self.vehicle, base_frames = bf.decode_rkg(args.base)
        self.reference_frames = list(bf.decode_rkg(args.ref)[3])
        self.first_row, self.last_searched_row, self.last_row = args.from_row, args.to_row, args.sim_to
        self.searched_rows = self.last_searched_row - self.first_row + 1
        self.size = args.pop

        base_frames = list(base_frames)
        base_frames += [gv2.NO_INPUT] * max(0, self.last_searched_row + 1 - len(base_frames))
        self.frames = self.with_reference_tail(base_frames)
        self.base_genome = self.genome_of(self.frames)
        self.reference_genome = self.genome_of(self.reference_frames)
        self.seeds = [self.base_genome] + [self.genome_of(list(bf.decode_rkg(p)[3])) for p in args.seed]

        # the reference from its CPU dump: path, height, completion, line crossing, speed at --ev-row
        dump = gv2.load_dump(args.ref_dump)
        self.reference_xz = cp.asarray(np.array([[float(r["px"]), float(r["pz"])] for r in dump[:self.last_row + 60]], np.float32))
        self.reference_height = cp.asarray(np.array([float(r["py"]) for r in dump[:self.last_row + 60]], np.float32))
        self.reference_path = gv2.GpuReferencePath(self.reference_xz)
        self.reference_completion = [float(r["completion"]) for r in dump]
        self.reference_crossing = gv2.line_crossing(self.reference_completion, args.line_comp, args.cross_after)
        self.reference_speed = float(dump[args.ev_row]["speed"])

        # slot 0 holds the race just before the searched rows; slots 1..size are the population
        self.engine = Engine(self.size + 2, course=self.course, character=self.character, vehicle=self.vehicle)
        self.engine.clone_template(0, 1)
        for row in range(self.first_row):
            gv2.step_single_race(self.engine, 0, self.frames[row])
        self.fixed_tail = self.frames[self.last_searched_row + 1:self.last_row + 1]

    def with_reference_tail(self, frames):
        """frames up to the last searched row, then the reference's (shifted) inputs up to the last simulated row."""
        shift = self.args.tail_shift
        out = list(frames[:self.last_searched_row + 1])
        out += [self.reference_frames[r + shift] for r in range(self.last_searched_row + 1, self.last_row + 1)]
        while len(out) < self.last_row + 1:
            out.append(gv2.NO_INPUT)
        return out

    def genome_of(self, frames):
        return np.array([[round(frames[r][2] * 7), round(frames[r][3] * 7), frames[r][0], frames[r][1]]
                         for r in range(self.first_row, self.last_searched_row + 1)], np.int8)

    def frames_of(self, genome):
        """A full race: base inputs, the genome's rows, the reference tail, then the rest of the reference (shifted)."""
        frames = list(self.frames)
        for k in range(self.searched_rows):
            stick_x, stick_y, buttons, trick = (int(x) for x in genome[k])
            frames[self.first_row + k] = (buttons, trick, stick_x / 7.0, stick_y / 7.0)
        shift = self.args.tail_shift
        frames += [self.reference_frames[r + shift] for r in range(self.last_row + 1, len(self.reference_frames) - max(shift, 0))]
        return frames

    def mutate(self, genome):
        """1-3 random changes (see the module docstring for the kinds)."""
        a, rng = self.args, self.rng
        for _ in range(int(rng.integers(1, 4))):
            row = int(rng.integers(0, self.searched_rows))
            kind = rng.random()
            if kind < a.p_btn:
                if rng.random() < 0.6:          # move a hop-timing boundary by one frame
                    boundaries = np.nonzero(genome[1:, BUTTONS] != genome[:-1, BUTTONS])[0] + 1
                    if len(boundaries):
                        edge = int(rng.choice(boundaries))
                        if rng.random() < 0.5:
                            genome[edge, BUTTONS] = genome[edge - 1, BUTTONS]
                        else:
                            genome[edge - 1, BUTTONS] = genome[edge, BUTTONS]
                else:                           # toggle a single frame between drift held and released
                    genome[row, BUTTONS] = DRIFT_RELEASED if genome[row, BUTTONS] == DRIFT_HELD else DRIFT_HELD
            elif kind < a.p_btn + a.p_trick:    # copy the reference's trick from this row or a neighbour
                source = int(np.clip(row + rng.integers(-1, 2), 0, self.searched_rows - 1))
                genome[row, TRICK] = self.reference_genome[source, TRICK] if rng.random() < 0.7 else 0
            else:                               # stick edit
                axis = int(rng.integers(0, 2))
                how = rng.random()
                if how < 0.5:
                    genome[row, axis] = np.clip(genome[row, axis] + rng.choice([-2, -1, 1, 2]), -7, 7)
                elif how < 0.8:
                    genome[row, axis] = rng.choice([-7, 0, 7]) if rng.random() < 0.6 else rng.integers(-7, 8)
                else:
                    genome[row, axis] = self.base_genome[row, axis]
        return genome

    def evaluate(self, population):
        """Simulate every genome from --from-row to --sim-to and score it (see the module docstring)."""
        a, n = self.args, self.size
        self.engine.copy([0] * n, list(range(1, n + 1)))
        genomes = cp.asarray(population.astype(np.float32))
        previous_completion = cp.zeros(n, cp.float32)
        crossing = cp.full(n, cp.nan, cp.float32)      # sub-frame row of the line crossing
        lateral_excess = cp.zeros(n, cp.float32)
        ev = cp.zeros(n, cp.float32)
        speed = cp.zeros(n, cp.float32)
        last_completion = cp.zeros(n, cp.float32)
        ev_second_bounce = cp.zeros(n, cp.float32)
        ahead = cp.zeros(n, cp.float32)
        sync_distance = cp.zeros(n, cp.float32)
        completion_short = cp.zeros(n, cp.float32)

        for row in range(self.first_row, self.last_row + 1):
            if row <= self.last_searched_row:
                k = row - self.first_row
                inputs = make_inputs(genomes[:, k, BUTTONS].astype(cp.int32), genomes[:, k, TRICK].astype(cp.int32),
                                     genomes[:, k, STICK_X] / 7.0, genomes[:, k, STICK_Y] / 7.0)
            else:
                inputs = gv2.same_inputs_for_all(n, self.fixed_tail[row - self.last_searched_row - 1])
            self.engine.step(1, n, inputs)
            state = self.engine.rows(1, n, row + 1)

            completion = state[:, COLUMN["completion"]].astype(cp.float32)
            crosses = ((completion >= a.line_comp) & (previous_completion < a.line_comp) & cp.isnan(crossing)
                       & (row > a.cross_after))
            crossing = cp.where(crosses, (row - 1) + (a.line_comp - previous_completion)
                                / cp.maximum(completion - previous_completion, 1e-6), crossing)
            previous_completion = completion
            last_completion = completion

            if row in a.lat_rows:
                lateral = self.reference_path.progress(state, row)[1]
                lateral_excess += cp.maximum(lateral - a.lat_tol, 0.0) / len(a.lat_rows)
            if a.comp_row is not None and row == a.comp_row:
                completion_short = cp.maximum(self.reference_completion[row + a.tail_shift] - completion, 0.0).astype(cp.float32)
            if row in a.sync_rows:
                target = row + a.tail_shift
                dist_sq = ((state[:, COLUMN["px"]] - self.reference_xz[target, 0]) ** 2
                           + (state[:, COLUMN["pz"]] - self.reference_xz[target, 1]) ** 2)
                if a.sync_y_from is not None and row >= a.sync_y_from:
                    dist_sq = dist_sq + (state[:, COLUMN["py"]] - self.reference_height[target]) ** 2
                sync_distance += cp.minimum(cp.sqrt(dist_sq), a.sync_cap).astype(cp.float32) / len(a.sync_rows)
            if row in a.ev2_rows:
                ev_second_bounce += cp.minimum(gv2.gpu_horizontal_ev(state), a.ev2_cap).astype(cp.float32) / len(a.ev2_rows)
            if a.ahead_row is not None and row == a.ahead_row:
                frames_ahead, lateral = self.reference_path.progress(state, row)
                ahead = cp.clip(frames_ahead, -60.0, 5.0).astype(cp.float32)
                ahead = cp.where(lateral > 300.0, -60.0, ahead).astype(cp.float32)
            if row == a.ev_row:
                ev = gv2.gpu_horizontal_ev(state).astype(cp.float32)
                speed = state[:, COLUMN["speed"]].astype(cp.float32)

        crossing_vs_reference = cp.where(cp.isnan(crossing), 1000.0 + 1000.0 * cp.maximum(a.line_comp - last_completion, 0),
                                         crossing - self.reference_crossing)
        edits = cp.asarray((population != self.base_genome[None]).sum(axis=(1, 2)).astype(np.float32))
        # the order of the terms is kept as it was when the published results were found (float sums depend on it)
        cost = (a.w_cross * crossing_vs_reference
                + a.w_lat * lateral_excess
                - a.w_ev * cp.minimum(ev, a.ev_cap)
                + a.w_sp * cp.abs(speed - self.reference_speed)
                + a.w_each * edits
                - a.w_ev2 * ev_second_bounce
                - a.w_ahead * ahead
                + a.w_sync * sync_distance
                + a.w_comp * completion_short)
        metrics = dict(cost=cost, dcross=crossing_vs_reference, lat=lateral_excess, ev=ev, sp=speed, edits=edits,
                       ev2=ev_second_bounce, ahd=ahead, sync=sync_distance, cshort=completion_short)
        return {name: cp.asnumpy(values) for name, values in metrics.items()}

    def describe(self, metrics, i):
        a, m = self.args, metrics
        return (f"cost {m['cost'][i]:8.1f} | L1 line {m['dcross'][i]:+.3f}f vs 27.818 | off-line excess {m['lat'][i]:6.1f} | "
                f"sync {m['sync'][i]:6.1f} | comp short {m['cshort'][i]:.3f} | EV2 {m['ev2'][i]:4.1f} | ahead@{a.ahead_row} {m['ahd'][i]:+.2f}f | "
                f"EV@{a.ev_row} {m['ev'][i]:4.1f} sp {m['sp'][i]:5.1f} (ref {self.reference_speed:.1f}) | edits {int(m['edits'][i])}")


def main():
    args = parse_args()
    rng = np.random.default_rng(args.seed_rng)
    search = TailSearch(args, rng)
    population = gv2.initial_population(search.seeds, search.size, search.mutate)

    start = time.time()
    metrics = search.evaluate(population)
    print(f"reference L1 crossing {search.reference_crossing:.3f}", flush=True)
    print(f"base : {search.describe(metrics, 0)}", flush=True)
    for j in range(1, len(search.seeds)):
        print(f"seed{j}: {search.describe(metrics, j)}", flush=True)
    for generation in range(1, args.gens + 1):
        population = gv2.next_generation(population, metrics["cost"], rng, args.elite, search.mutate)
        metrics = search.evaluate(population)
        if generation % 5 == 0 or generation == args.gens:
            best = int(np.argmin(metrics["cost"]))
            print(f"gen {generation:3d}: {search.describe(metrics, best)} [{time.time() - start:.0f}s]", flush=True)
        if time.time() - start > args.time_limit:
            print(f"time limit reached at gen {generation}", flush=True)
            break

    gv2.write_best_candidates(population, metrics["cost"], search.frames_of,
                              lambda frames: bf.encode_rkg(search.course, search.character, search.vehicle, frames, 0),
                              lambda i: search.describe(metrics, i), args.out)
    print("done", flush=True)


if __name__ == "__main__":
    main()
