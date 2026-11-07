#!/usr/bin/env python3
"""Shared pieces of the rGV2 (SNES Ghost Valley 2) search tools.

Vocabulary used across the gv2_* tools:

- **row**: one line of a Kinoko replay dump (`kinoko_host replay --dump`), or one GPU step: the state after the race
  was stepped with the inputs of row r. The L1 fast block hit is at row 846 in the 27.818.
- **input frame**: index into the .rkg input stream (0 = first countdown frame) = row - 172. Row r is played with
  the decoded frame inputs[r] (`brute_force.decode_rkg` puts the 172 pre-countdown frames first).
- **race frame**: frames since the race timer started = input frame - 240 (sam's CSVs use this).
- **reference**: the run everything is compared against, by default slimpanda's 27.818 (9.418 / 9.209 / 9.191).
- **progress on the reference path**: project the kart's x/z onto the reference's path and express it as a row
  number. "Frames ahead" at row r = that projected row minus r (positive = further along than the reference was
  at the same row). The lateral offset is the distance from the reference path.
- **frame inputs**: a tuple (buttons, trick, stick_x, stick_y) with sticks in -1..1, as `brute_force.decode_rkg`
  returns them. In a genome sticks are stored as integers -7..+7 (the .rkg values), i.e. stick * 7.
"""
import csv
import math
import os
import sys

import numpy as np

TOOLS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(TOOLS_DIR)
sys.path.insert(0, TOOLS_DIR)
sys.path.insert(0, os.path.join(TOOLS_DIR, "gpu_spike"))

GV2_GHOSTS_DIR = os.path.join(REPO_ROOT, "samples", "tracks", "ghost-valley-2", "ghosts")
REFERENCE_GHOST = os.path.join(GV2_GHOSTS_DIR, "rGV2_27.818_slimpanda_best.rkg")
PENDING_GHOST = os.path.join(GV2_GHOSTS_DIR, "rGV2_22.000_slimpanda_L1_with_L3_movement_PENDING.rkg")
REFERENCE_DUMP = os.path.join(REPO_ROOT, "runs", "gv2", "gv2_27818.csv")

ROW_TO_INPUT_FRAME = 172          # input frame = row - 172 (brute_force.COUNTDOWN_START_FRAME)
INPUT_FRAME_TO_RACE_FRAME = 240   # race frame = input frame - 240
FRAMES_PER_SECOND = 59.94

BLOCK_CONTACT_FLAG = 0x400        # bit in the `flags` column set on the frame the kart touches the block
STICK_STEPS = 7                   # .rkg stick values are -7..+7
TRICK_NAMES = {0: "none", 1: "up", 2: "down", 3: "left", 4: "right"}
NO_INPUT = (0, 0, 0.0, 0.0)       # frame inputs used to pad a run past its last recorded frame


def input_frame_of_row(row):
    return row - ROW_TO_INPUT_FRAME


# ---------------------------------------------------------------------------------------------------------------
# CPU replay dumps (lists of dicts, one per row)
# ---------------------------------------------------------------------------------------------------------------

def load_dump(path):
    """A `kinoko_host replay --dump` CSV as a list of {column: string} rows."""
    return list(csv.DictReader(open(path)))


def position_xz(row):
    return float(row["px"]), float(row["pz"])


def yaw_degrees(row):
    """Facing yaw in degrees from the rotation quaternion. Higher (less negative) = turned further right here."""
    qx, qy, qz, qw = (float(row[k]) for k in ("qx", "qy", "qz", "qw"))
    return math.degrees(math.atan2(2 * (qx * qz + qw * qy), 1 - 2 * (qx * qx + qy * qy)))


def horizontal_ev(row):
    """Size of the external velocity in the x/z plane (what the block push gives)."""
    return math.hypot(float(row["evx"]), float(row["evz"]))


def first_contact_row(rows, first, last_exclusive):
    """First row in [first, last_exclusive) with the block-contact flag, or None."""
    for r in range(first, last_exclusive):
        if int(rows[r]["flags"]) & BLOCK_CONTACT_FLAG:
            return r
    return None


def progress_on_path(x, z, row, path_xz, look_back, look_ahead):
    """Frames ahead of the reference path and signed lateral offset, for a kart at (x, z) on `row`.

    path_xz: numpy (N, 2) float64 array of the reference's x/z per row. The nearest path point is searched among
    rows max(0, row - look_back) .. min(N - 2, row + look_ahead), and (x, z) is projected onto the segment from that
    point to the next one. Returns (projected row - row, lateral offset; positive = to the right of travel)."""
    first = max(0, row - look_back)
    last = min(len(path_xz) - 2, row + look_ahead)
    window = path_xz[first:last + 1]
    nearest = int(np.argmin((window[:, 0] - x) ** 2 + (window[:, 1] - z) ** 2)) + first
    dx, dz = path_xz[nearest + 1] - path_xz[nearest]
    segment_length_sq = max(dx * dx + dz * dz, 1e-6)
    along = ((x - path_xz[nearest, 0]) * dx + (z - path_xz[nearest, 1]) * dz) / segment_length_sq
    lateral = ((x - path_xz[nearest, 0]) * dz - (z - path_xz[nearest, 1]) * dx) / segment_length_sq ** 0.5
    return nearest + along - row, lateral


def ahead_of_reference_row(candidate_row, reference_row, reference_next_row):
    """A quicker, local version of progress_on_path: the candidate's offset from the reference at one row, measured
    along the reference's motion in that row and divided by the distance it covered (so in frames), plus the signed
    lateral offset. Only meaningful while the two runs are close."""
    (x, z), (x0, z0), (x1, z1) = position_xz(candidate_row), position_xz(reference_row), position_xz(reference_next_row)
    dx, dz = x1 - x0, z1 - z0
    step = math.hypot(dx, dz)
    along = ((x - x0) * dx + (z - z0) * dz) / step
    lateral = ((x - x0) * dz - (z - z0) * dx) / step
    return along / step, lateral


def path_of_dump(rows, count=None):
    """numpy (N, 2) float64 x/z path of a dump's first `count` rows (all rows if None)."""
    rows = rows if count is None else rows[:count]
    return np.array([position_xz(r) for r in rows])


def line_crossing(completion, target, first_row, require_rise=False, max_jump=None):
    """Sub-frame row where race completion first reaches `target` (2.0 = L1 line, 4.0 = finish), searching from
    `first_row`. Linear interpolation between the two rows around the crossing. With require_rise the row before must
    be below the target, and with max_jump the step between the two rows must be smaller (skips respawn jumps).
    Returns nan if it never crosses."""
    for r in range(first_row, len(completion)):
        if completion[r] < target:
            continue
        if require_rise and completion[r - 1] >= target:
            continue
        if max_jump is not None and completion[r] - completion[r - 1] >= max_jump:
            continue
        return (r - 1) + (target - completion[r - 1]) / (completion[r] - completion[r - 1])
    return float("nan")


# ---------------------------------------------------------------------------------------------------------------
# GPU engine helpers
# ---------------------------------------------------------------------------------------------------------------

def gpu_modules():
    """(cupy, Engine, make_inputs, ROW_COLUMN): imported lazily so the CPU-only tools run without CUDA."""
    import cupy as cp
    from gpu_engine import ROW_COLUMN, Engine, make_inputs
    return cp, Engine, make_inputs, ROW_COLUMN


def step_single_race(engine, slot, frame_inputs):
    """Advance the one race in `slot` by one frame with frame_inputs = (buttons, trick, stick_x, stick_y)."""
    cp, _, make_inputs, _ = gpu_modules()
    buttons, trick, stick_x, stick_y = frame_inputs
    engine.step(slot, 1, make_inputs(cp.asarray([buttons], cp.int32), cp.asarray([trick], cp.int32),
                                     cp.asarray([stick_x], cp.float32), cp.asarray([stick_y], cp.float32)))


def same_inputs_for_all(count, frame_inputs):
    """GPU inputs giving every one of `count` races the same frame inputs."""
    cp, _, make_inputs, _ = gpu_modules()
    buttons, trick, stick_x, stick_y = frame_inputs
    return make_inputs(cp.full(count, buttons, cp.int32), cp.full(count, trick, cp.int32),
                       cp.full(count, stick_x, cp.float32), cp.full(count, stick_y, cp.float32))


def gpu_yaw_degrees(rows):
    """yaw_degrees() for a cupy (races, columns) block of GPU rows."""
    cp, _, _, column = gpu_modules()
    qx, qy, qz, qw = (rows[:, column[k]] for k in ("qx", "qy", "qz", "qw"))
    return cp.degrees(cp.arctan2(2 * (qx * qz + qw * qy), 1 - 2 * (qx * qx + qy * qy)))


def gpu_horizontal_ev(rows):
    cp, _, _, column = gpu_modules()
    return cp.hypot(rows[:, column["evx"]], rows[:, column["evz"]])


class GpuReferencePath:
    """The reference's x/z path on the GPU, for scoring many races at once.

    progress(rows, row) gives each race's frames ahead of the reference at `row` (the same measure as
    progress_on_path, nearest point searched among rows row-25 .. row+24) and its unsigned lateral offset."""

    LOOK_AROUND = 25

    def __init__(self, path_xz):
        cp, _, _, _ = gpu_modules()
        self.path = cp.asarray(path_xz)

    def progress(self, rows, row):
        cp, _, _, column = gpu_modules()
        first = max(0, row - self.LOOK_AROUND)
        end = min(len(self.path) - 1, row + self.LOOK_AROUND)
        x, z = rows[:, column["px"]], rows[:, column["pz"]]
        window = self.path[first:end]
        dist_sq = (x[:, None] - window[None, :, 0]) ** 2 + (z[:, None] - window[None, :, 1]) ** 2
        nearest = cp.minimum(dist_sq.argmin(axis=1), end - first - 2)
        x0, z0 = window[nearest, 0], window[nearest, 1]
        x1, z1 = self.path[first + nearest + 1, 0], self.path[first + nearest + 1, 1]
        dx, dz = x1 - x0, z1 - z0
        segment_length_sq = cp.maximum(dx * dx + dz * dz, 1e-6)
        along = ((x - x0) * dx + (z - z0) * dz) / segment_length_sq
        lateral = cp.abs((x - x0) * dz - (z - z0) * dx) / cp.sqrt(segment_length_sq)
        return (first + nearest).astype(cp.float32) + along - row, lateral


# ---------------------------------------------------------------------------------------------------------------
# Population search (shared by gv2_hit_evolve and gv2_tail_evolve)
# ---------------------------------------------------------------------------------------------------------------

def initial_population(seeds, size, mutate_new):
    """size genomes: the seeds in turn, and from the first repeat on, a mutated copy of a seed."""
    population = np.zeros((size,) + seeds[0].shape, seeds[0].dtype)
    for i in range(size):
        genome = seeds[i % len(seeds)].copy()
        if i >= len(seeds):
            genome = mutate_new(genome)
        population[i] = genome
    return population


def next_generation(population, cost, rng, elite_share, mutate_child, crossover_chance=0.3):
    """(mu + lambda) step: keep the best `elite_share` unchanged; every other child is a tournament pick from the best
    third (best of two random picks), sometimes given a contiguous block of rows from a second pick, then mutated."""
    size, rows = population.shape[0], population.shape[1]
    order = np.argsort(cost)
    elite_count = max(2, int(elite_share * size))
    parents_pool = max(elite_count + 1, size // 3)
    children = np.empty_like(population)
    children[:elite_count] = population[order[:elite_count]]
    for i in range(elite_count, size):
        child = population[order[rng.integers(0, parents_pool, 2)].min()].copy()
        if rng.random() < crossover_chance:
            donor = population[order[rng.integers(0, parents_pool, 2)].min()]
            block_start, block_end = sorted(rng.integers(0, rows, 2))
            child[block_start:block_end + 1] = donor[block_start:block_end + 1]
        children[i] = mutate_child(child)
    return children


def write_best_candidates(population, cost, frames_of, encode, describe, out_prefix, count=6):
    """Write the `count` best distinct genomes as <out_prefix>_<k>.rkg (k = 0 is the best) and print each."""
    os.makedirs(os.path.dirname(out_prefix) or ".", exist_ok=True)
    seen, written = set(), 0
    for i in np.argsort(cost):
        key = population[i].tobytes()
        if key in seen:
            continue
        seen.add(key)
        path = f"{out_prefix}_{written}.rkg"
        open(path, "wb").write(encode(frames_of(population[i])))
        print(f"candidate {written}: {describe(i)} -> {path}", flush=True)
        written += 1
        if written >= count:
            break
