"""Many Kinoko races in GPU memory: a template race plus `capacity` slots, each a full snapshot-able race.

A slot is R private heap bytes followed by the statics block. Races in a contiguous range of slots are stepped
together (one thread per race). Snapshots are just slot copies (k_copy_slots relocates the pointers).

    eng = Engine(capacity=3000)
    eng.clone_template(0, 4)                # slots 0..3 = the race at frame 0
    eng.copy([0, 0], [10, 11])              # slot 0 -> slots 10 and 11
    rows = eng.rows(10, 2, frame)           # cupy (2, ROW_DOUBLES): see runtime.cu k_rows
    eng.step(10, 2, inputs)                 # inputs: cupy structured array (2,) of INPUT_DTYPE
"""

import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.dirname(HERE))

import cupy as cp  # noqa: E402

import run_gpu  # noqa: E402

# Names of the GPU row values, in the same order as the CPU replay dump's CSV columns (FrameState.cc).
# ROW_COLUMN[name] is the index into a GPU row; index 0 of a GPU row is a count, hence the + 1.
ROW_COLUMN_NAMES = ("frame,stage,timerMs,raceFrame,px,py,pz,qx,qy,qz,qw,mqx,mqy,mqz,mqw,evx,evy,evz,ivx,ivy,ivz,"
                    "speed,speedRatio,driftState,mtCharge,hopStickX,kclSpeedFactor,flags,stickX,stickY,buttons,trick,"
                    "completion,checkpoint,lap,wrongWay,mushrooms").split(",")
ROW_COLUMN = {name: 1 + i for i, name in enumerate(ROW_COLUMN_NAMES)}

ROW_DOUBLES = 128      # KINOKO_CAPTURE_DOUBLES: [0] count, [1..109] FrameState row, [120] stage, [121] race timer ms
STAGE, TIMER = 120, 121
INPUT_DTYPE = np.dtype([("b", "<i4"), ("sx", "<f4"), ("sy", "<f4"), ("t", "<i4")])  # runtime.cu StepInput


def make_inputs(buttons, trick, sx, sy):
    """cupy arrays -> cupy INPUT_DTYPE array (as raw bytes, which is what the kernel reads)."""
    n = buttons.shape[0]
    raw = cp.empty((n, 4), cp.int32)
    raw[:, 0] = buttons
    raw[:, 1] = sx.astype(cp.float32).view(cp.int32)
    raw[:, 2] = sy.astype(cp.float32).view(cp.int32)
    raw[:, 3] = trick
    return raw


SLOT_SIZES = os.path.join(HERE, "slot_sizes.json")


def slot_kib(course):
    """Private heap per race slot for a course: measured extent + 20% (tools/gpu_spike/validate_all.py writes
    slot_sizes.json). Too small and a race writes into the shared track data (corruption, then crashes)."""
    import json
    try:
        table = json.load(open(SLOT_SIZES))
    except (OSError, ValueError):
        table = {}
    if str(course) not in table:
        print(f"gpu_engine: no measured slot size for course {course}; using 2048 KiB "
              f"(run tools/gpu_spike/validate_all.py --skip-exact to measure it)", file=sys.stderr)
        return 2048
    return int(table[str(course)])


class Engine:
    def __init__(self, capacity, r_kib=None, stack_kib=32, block=32, course=8, character=22, vehicle=32, auto=False):
        if r_kib is None:
            r_kib = slot_kib(course)
        self.g = run_gpu.GpuRace(stack_kib, course, character, vehicle, auto)
        self.g.init()
        self.r = r_kib * 1024
        self.stride = self.r + run_gpu.STATICS_BYTES
        self.capacity = capacity
        self.block = block
        need = self.stride * capacity
        free, _total = cp.cuda.runtime.memGetInfo()
        if need > 0.9 * free:
            raise MemoryError(f"{capacity} race slots x {self.stride / 2**20:.2f} MiB = {need / 2**30:.2f} GiB, but only "
                              f"{free / 2**30:.2f} GiB of GPU memory is free: use a smaller batch / beam / work")
        self.slots = cp.zeros(need, np.uint8)
        k = self.g.kernel
        self._clone, self._layout, self._copy = k("k_clone"), k("k_layout"), k("k_copy_slots")
        self._step, self._rows = k("k_step"), k("k_rows")
        self._probe = k("k_probe")
        self._layout_at = None

    def ptr(self, slot):
        return self.slots.data.ptr + slot * self.stride

    def clone_template(self, first, count):
        """Slots first..first+count-1 become copies of the template race (frame 0)."""
        space = self.g.space
        self._clone((count,), (256,), (space, space[run_gpu.MEMORY_SPACE_SIZE:], np.uint64(self.r),
                                       self.slots[first * self.stride:], np.uint64(self.stride), np.int32(count)))
        self._layout_at = None

    def copy(self, src, dst):
        """Slot src[i] -> slot dst[i] (lists of slot numbers; a destination must not also be a source)."""
        if len(src) == 0:
            return
        s = cp.asarray(np.array([self.ptr(i) for i in src], np.uint64))
        d = cp.asarray(np.array([self.ptr(i) for i in dst], np.uint64))
        self._copy((len(src),), (256,), (s, d, np.uint64(self.r), np.int32(len(src))))

    def _use(self, first):
        if self._layout_at != first:
            self._layout((1,), (1,), (self.slots[first * self.stride:], np.uint64(self.stride), np.uint64(self.r)))
            self._layout_at = first

    def step(self, first, count, inputs):
        """One frame for the races in slots first..first+count-1; inputs = make_inputs(...) with `count` rows."""
        self._use(first)
        blocks = (count + self.block - 1) // self.block
        self._step((blocks,), (self.block,), (inputs, np.int32(1), np.int32(count), np.int32(1)))

    def probe(self, first, count):
        """Wall proximity per race, cupy float32 (count, 2): [visible walls, invisible walls] = smallest extra hitbox radius,
        in units, at which a kart hitbox overlaps such a driver wall by the game's own collision test (0 = touching,
        300 = none within 240). See runtime.cu k_probe."""
        self._use(first)
        out = cp.empty((count, 2), cp.float32)
        blocks = (count + self.block - 1) // self.block
        self._probe((blocks,), (self.block,), (out, np.int32(count)))
        return out

    def rows(self, first, count, frame):
        """State rows of the races in slots first..first+count-1: cupy (count, ROW_DOUBLES) float64."""
        self._use(first)
        out = cp.empty((count, ROW_DOUBLES), cp.float64)
        blocks = (count + self.block - 1) // self.block
        self._rows((blocks,), (self.block,), (out, np.uint32(frame), np.int32(count)))
        return out
