#!/usr/bin/env python3
"""Search for the lap 1 fast block hit on GV2 (population search on the GPU, sam's / fable5mkw's settings).

What is searched: one stick X and one stick Y value (-7..+7) per row of the edit window, rows --from-row up to
--freeze-from (default 771..846, input frames 599..674: the run-up to the block contact at row ~846). Buttons and
tricks always come from the base run (or from --btn-from), and every row from --freeze-from on keeps the base run's
inputs. The population starts at the base run and mostly changes stick Y (--p-y), with a small edit budget.

How a candidate is scored (lower cost = better). Everything is compared with the reference run at the same row:
    - w_fwd  * frames ahead on the reference path at contact +20 / +30  (--fwd-after)
    - w_ev   * min(horizontal EV at --ev-row, --ev-cap)                 (the push out of the hit; 27.818: ~44)
    - w_yaw  * (yaw 2 rows before contact - reference yaw)              (higher yaw = facing right = better)
    + w_pace * sum over rows before contact of max(|frames ahead| - pace_tol, 0)   (sam's pace attractor: stay on
                                                                         the reference's pace until the hit)
    + 20 per row before contact that is more than --max-lat off the reference path
    + w_postlat * mean over the --fwd-after rows of max(lateral offset - postlat_tol, 0)
    + w_yaw_contact * max(|yaw at contact - target| - tol, 0)           (only with --yaw-contact-target)
    + w_edit * edits beyond --budget  + w_each * edits                  (edits = stick values changed vs the base)
    + 1000 if the contact row is outside [--contact-lo, --contact-hi]
    + 1000 if the drift ends before contact (only with --need-drift)

Writes the 6 best distinct candidates as <out>_0.rkg .. <out>_5.rkg (0 = best).

    python tools/gv2_hit_evolve.py --out runs/gv2/evoA --gens 150
"""
import argparse
import time

import numpy as np

import gv2_common as gv2
import brute_force as bf  # noqa: E402  (gv2_common puts tools/ on sys.path)

cp, Engine, make_inputs, COLUMN = gv2.gpu_modules()

CONTACT_NOT_YET = 9999   # contact row of a race that has not touched the block (yet)
LATERAL_LIMIT_COST = 20.0
PENALTY = 1000.0


def parse_args():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--base", default=gv2.PENDING_GHOST, help="run to start from (default: slimpanda's PENDING lap 1)")
    ap.add_argument("--ref", default=gv2.REFERENCE_GHOST, help="reference run (default: the 27.818)")
    ap.add_argument("--seed", action="append", default=[], help="extra runs whose window sticks seed part of the population")
    ap.add_argument("--from-row", type=int, default=771, help="first edited row (input frame = row - 172)")
    ap.add_argument("--freeze-from", type=int, default=847, help="rows from here on keep the base inputs (B release / hit)")
    ap.add_argument("--contact-lo", type=int, default=840, help="earliest allowed contact row")
    ap.add_argument("--contact-hi", type=int, default=852, help="latest allowed contact row")
    ap.add_argument("--ref-contact", type=int, default=846, help="the reference's contact row")
    ap.add_argument("--fwd-after", type=int, nargs="+", default=[20, 30], help="score ahead at ref-contact + these rows")
    ap.add_argument("--ev-row", type=int, default=850, help="row where the EV out of the hit is scored")
    ap.add_argument("--pop", type=int, default=2048, help="population size (races simulated per generation)")
    ap.add_argument("--gens", type=int, default=150)
    ap.add_argument("--elite", type=float, default=0.08, help="share of the best kept unchanged each generation")
    ap.add_argument("--budget", type=int, default=10, help="edits (changed stick values vs base) allowed without penalty")
    ap.add_argument("--p-y", type=float, default=0.8, help="probability a mutation touches stick Y (else stick X)")
    ap.add_argument("--w-fwd", type=float, default=100.0, help="weight of frames ahead after the hit")
    ap.add_argument("--w-ev", type=float, default=3.0, help="weight of EV at --ev-row")
    ap.add_argument("--ev-cap", type=float, default=50.0, help="EV above this earns nothing more")
    ap.add_argument("--w-yaw", type=float, default=5.0, help="weight of yaw vs the reference before contact")
    ap.add_argument("--w-pace", type=float, default=200.0, help="weight of the pace attractor")
    ap.add_argument("--pace-tol", type=float, default=0.25, help="frames ahead/behind before contact that cost nothing")
    ap.add_argument("--w-edit", type=float, default=40.0, help="cost per edit beyond --budget")
    ap.add_argument("--w-each", type=float, default=0.5, help="cost per edit (tie-break toward fewer edits)")
    ap.add_argument("--max-lat", type=float, default=60.0, help="pre-contact lateral offset from the ref path above this costs 20/row")
    ap.add_argument("--need-drift", action="store_true", help="1000 if driftState < 1 on any pre-contact row (off: no drift in this window)")
    ap.add_argument("--btn-from", default=None, help="take the window buttons from this run instead of the base (e.g. the 27.818: 11 vs 3)")
    ap.add_argument("--w-postlat", type=float, default=0.0, help="cost per unit of lateral offset from the ref path beyond --postlat-tol at the --fwd-after rows (keeps the line for the superhops)")
    ap.add_argument("--postlat-tol", type=float, default=30.0)
    ap.add_argument("--yaw-contact-target", type=float, default=None, help="target yaw (deg) at the contact row, e.g. A's -114.7")
    ap.add_argument("--w-yaw-contact", type=float, default=0.0, help="cost per degree of |yaw at contact - target| beyond --yaw-contact-tol")
    ap.add_argument("--yaw-contact-tol", type=float, default=1.0)
    ap.add_argument("--seed-rng", type=int, default=1, help="random seed (same seed + same inputs = same result)")
    ap.add_argument("--time-limit", type=float, default=1700.0, help="stop after this many seconds and write the candidates")
    ap.add_argument("--out", required=True, help="output prefix for the candidate .rkg files")
    return ap.parse_args()


def simulate_reference(ref_ghost, row_count):
    """Replay the reference on the GPU: numpy (row_count, 4) float32 of x, z, yaw, completion per row."""
    course, character, vehicle, frames = bf.decode_rkg(ref_ghost)
    frames = list(frames)
    reference = np.zeros((row_count, 4), np.float32)
    engine = Engine(2, course=course, character=character, vehicle=vehicle)
    engine.clone_template(0, 1)
    for row in range(row_count):
        gv2.step_single_race(engine, 0, frames[row])
        state = engine.rows(0, 1, row + 1)
        reference[row] = [float(state[0, COLUMN["px"]]), float(state[0, COLUMN["pz"]]),
                          float(gv2.gpu_yaw_degrees(state)[0]), float(state[0, COLUMN["completion"]])]
    return reference


class HitSearch:
    """The base run, the edit window and the scoring. A genome is an int8 array (window rows, 2) of stick X, stick Y."""

    def __init__(self, args, rng):
        self.args, self.rng = args, rng
        self.course, self.character, self.vehicle, frames = bf.decode_rkg(args.base)
        self.frames = list(frames)
        self.first_row = args.from_row                                    # first edited row
        self.freeze_row = args.freeze_from                                # first row that keeps the base inputs
        self.window_rows = self.freeze_row - self.first_row
        self.last_row = args.ref_contact + max(args.fwd_after) + 2        # last simulated row
        self.size = args.pop
        self.score_rows = [args.ref_contact + d for d in args.fwd_after]

        self.reference = simulate_reference(args.ref, self.last_row + 40)
        self.reference_path = gv2.GpuReferencePath(self.reference[:, :2])

        # slot 0 holds the race just before the window; slots 1..size are the population
        self.engine = Engine(self.size + 2, course=self.course, character=self.character, vehicle=self.vehicle)
        self.engine.clone_template(0, 1)
        for row in range(self.first_row):
            gv2.step_single_race(self.engine, 0, self.frames[row])

        if args.btn_from:
            button_frames = list(bf.decode_rkg(args.btn_from)[3])
            for row in range(self.first_row, self.freeze_row):
                self.frames[row] = (button_frames[row][0],) + tuple(self.frames[row][1:])
        rows = range(self.first_row, self.last_row + 1)
        self.buttons = np.array([self.frames[r][0] for r in rows], np.int32)
        self.tricks = np.array([self.frames[r][1] for r in rows], np.int32)
        frozen = range(self.freeze_row, self.last_row + 1)
        self.frozen_stick_x = np.array([self.frames[r][2] for r in frozen], np.float32)
        self.frozen_stick_y = np.array([self.frames[r][3] for r in frozen], np.float32)

        self.base_genome = self.genome_of(self.frames)
        self.seeds = [self.base_genome] + [self.genome_of(list(bf.decode_rkg(p)[3])) for p in args.seed]

    def genome_of(self, frames):
        return np.array([[int(round(frames[r][2] * gv2.STICK_STEPS)), int(round(frames[r][3] * gv2.STICK_STEPS))]
                         for r in range(self.first_row, self.freeze_row)], np.int8)

    def frames_of(self, genome):
        """The base run's inputs with the window sticks replaced by the genome's."""
        frames = list(self.frames)
        for k in range(self.window_rows):
            buttons, trick, _, _ = frames[self.first_row + k]
            frames[self.first_row + k] = (buttons, trick, genome[k, 0] / 7.0, genome[k, 1] / 7.0)
        return frames

    def mutate(self, genome, edit_count):
        """edit_count random edits: nudge a stick value by 1-2, set it to a random value, or put back the base value."""
        rng = self.rng
        for _ in range(edit_count):
            row = rng.integers(0, self.window_rows)
            axis = 1 if rng.random() < self.args.p_y else 0
            kind = rng.random()
            if kind < 0.45:
                genome[row, axis] = np.clip(genome[row, axis] + rng.choice([-2, -1, 1, 2]), -7, 7)
            elif kind < 0.75:
                genome[row, axis] = rng.integers(-7, 8)
            else:                                   # revert toward the base (keeps the edit count small)
                genome[row, axis] = self.base_genome[row, axis]
        return genome

    def evaluate(self, population):
        """Simulate every genome from the window start to self.last_row and score it (see the module docstring)."""
        a, n = self.args, self.size
        self.engine.copy([0] * n, list(range(1, n + 1)))
        stick_x = cp.asarray(population[:, :, 0].astype(np.float32) / 7.0)
        stick_y = cp.asarray(population[:, :, 1].astype(np.float32) / 7.0)
        pace = cp.zeros(n, cp.float32)                  # sum of |frames ahead| beyond pace_tol before contact
        rows_off_line = cp.zeros(n, cp.float32)         # rows before contact more than max_lat off the path
        contact_row = cp.full(n, CONTACT_NOT_YET, cp.int32)
        rows_without_drift = cp.zeros(n, cp.int32)
        ahead_after = cp.zeros(n, cp.float32)           # mean frames ahead at the --fwd-after rows
        ev = cp.zeros(n, cp.float32)
        yaw_vs_reference = cp.zeros(n, cp.float32)
        lateral_after = cp.zeros(n, cp.float32)         # mean lateral excess at the --fwd-after rows
        yaw_at_contact = cp.zeros(n, cp.float32)
        ahead_before_contact = ahead_at_first_score_row = None

        for row in range(self.first_row, self.last_row + 1):
            k = row - self.first_row
            if row < self.freeze_row:
                sx, sy = stick_x[:, k], stick_y[:, k]
            else:
                sx = cp.full(n, float(self.frozen_stick_x[row - self.freeze_row]), cp.float32)
                sy = cp.full(n, float(self.frozen_stick_y[row - self.freeze_row]), cp.float32)
            self.engine.step(1, n, make_inputs(cp.full(n, int(self.buttons[k]), cp.int32),
                                               cp.full(n, int(self.tricks[k]), cp.int32), sx, sy))
            state = self.engine.rows(1, n, row + 1)

            flags = state[:, COLUMN["flags"]].astype(cp.int64)
            touches = ((flags & gv2.BLOCK_CONTACT_FLAG) != 0) & (contact_row == CONTACT_NOT_YET) & (row >= a.contact_lo - 6)
            contact_row = cp.where(touches, row, contact_row)
            yaw_at_contact = cp.where(touches, gv2.gpu_yaw_degrees(state).astype(cp.float32), yaw_at_contact)

            if row < a.ref_contact - 1:
                ahead, lateral = self.reference_path.progress(state, row)
                pace += cp.maximum(cp.abs(ahead) - a.pace_tol, 0.0)
                rows_off_line += (lateral > a.max_lat).astype(cp.float32)
                rows_without_drift += (state[:, COLUMN["driftState"]] < 1).astype(cp.int32)
            if row == a.ref_contact - 2:
                yaw_vs_reference = gv2.gpu_yaw_degrees(state) - float(self.reference[row, 2])
                ahead_before_contact = self.reference_path.progress(state, row)[0]
            if row == a.ev_row:
                ev = gv2.gpu_horizontal_ev(state)
            if row in self.score_rows:
                ahead, lateral = self.reference_path.progress(state, row)
                ahead_after += ahead / len(self.score_rows)
                lateral_after += cp.maximum(lateral - a.postlat_tol, 0.0) / len(self.score_rows)
                if row == self.score_rows[0]:
                    ahead_at_first_score_row = ahead

        edits = cp.asarray((population != self.base_genome[None]).sum(axis=(1, 2)).astype(np.float32))
        contact_out_of_range = (contact_row < a.contact_lo) | (contact_row > a.contact_hi)
        if a.yaw_contact_target is not None:
            yaw_contact_miss = cp.maximum(cp.abs(yaw_at_contact - a.yaw_contact_target) - a.yaw_contact_tol, 0.0)
        else:
            yaw_contact_miss = cp.zeros(n, cp.float32)
        drift_penalty = PENALTY * (rows_without_drift > 0) if a.need_drift else 0.0
        # the order of the terms is kept as it was when the published results were found (float sums depend on it)
        cost = (a.w_yaw_contact * yaw_contact_miss
                - a.w_fwd * ahead_after
                - a.w_ev * cp.minimum(ev, a.ev_cap)
                - a.w_yaw * yaw_vs_reference
                + a.w_pace * pace
                + LATERAL_LIMIT_COST * rows_off_line
                + a.w_postlat * lateral_after
                + a.w_edit * cp.maximum(edits - a.budget, 0)
                + a.w_each * edits
                + PENALTY * contact_out_of_range
                + drift_penalty)
        metrics = dict(cost=cost, fwd=ahead_after, fwd20=ahead_at_first_score_row, ev=ev, yaw=yaw_vs_reference, pace=pace,
                       contact=contact_row, edits=edits, ah_pre=ahead_before_contact, drift=rows_without_drift,
                       postlat=lateral_after, yawc=yaw_at_contact)
        return {name: cp.asnumpy(values) for name, values in metrics.items()}

    def describe(self, metrics, i):
        a, m = self.args, metrics
        return (f"cost {m['cost'][i]:8.1f} | fwd@+20 {m['fwd20'][i]:+.3f}f mean {m['fwd'][i]:+.3f}f | EV@{a.ev_row} {m['ev'][i]:5.1f} | "
                f"yaw-ref@{a.ref_contact - 2} {m['yaw'][i]:+.2f} | ahead@{a.ref_contact - 2} {m['ah_pre'][i]:+.3f}f | pace {m['pace'][i]:.2f} | "
                f"postlat {m['postlat'][i]:.0f} | yaw@contact {m['yawc'][i]:.1f} | contact row {m['contact'][i]} | edits {int(m['edits'][i])}")


def main():
    args = parse_args()
    rng = np.random.default_rng(args.seed_rng)
    search = HitSearch(args, rng)
    population = gv2.initial_population(search.seeds, search.size,
                                        lambda genome: search.mutate(genome, int(rng.integers(1, 4))))

    start = time.time()
    metrics = search.evaluate(population)
    print(f"base: {search.describe(metrics, 0)}", flush=True)
    print(f"gen   0: {search.describe(metrics, int(np.argmin(metrics['cost'])))} [{time.time() - start:.0f}s]", flush=True)
    for generation in range(1, args.gens + 1):
        population = gv2.next_generation(population, metrics["cost"], rng, args.elite,
                                         lambda genome: search.mutate(genome, int(rng.integers(1, 3))))
        metrics = search.evaluate(population)
        if generation % 5 == 0 or generation == args.gens:
            best = int(np.argmin(metrics["cost"]))
            valid = metrics["cost"] < 500
            best_valid = metrics["fwd20"][valid].max() if valid.any() else float("nan")
            print(f"gen {generation:3d}: {search.describe(metrics, best)} | valid {int(valid.sum())}/{search.size} | "
                  f"best fwd@+20 among valid {best_valid:+.3f}f [{time.time() - start:.0f}s]", flush=True)
        if time.time() - start > args.time_limit:
            print(f"time limit reached at gen {generation}", flush=True)
            break

    gv2.write_best_candidates(population, metrics["cost"], search.frames_of,
                              lambda frames: bf.encode_rkg(search.course, search.character, search.vehicle, frames, 0),
                              lambda i: search.describe(metrics, i), args.out)
    print("done", flush=True)


if __name__ == "__main__":
    main()
