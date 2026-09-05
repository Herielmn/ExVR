const EXP = new Uint8Array(512);
const LOG = new Uint8Array(256);
(() => {
  let x = 1;
  for (let i = 0; i < 255; i++) {
    EXP[i] = x;
    LOG[x] = i;
    x <<= 1;
    if (x & 0x100) x ^= 0x11d;
  }
  for (let i = 255; i < 512; i++) EXP[i] = EXP[i - 255];
})();

export const mul = (a, b) => (a === 0 || b === 0 ? 0 : EXP[LOG[a] + LOG[b]]);

export function generator(n) {
  let poly = Uint8Array.of(1);
  for (let i = 0; i < n; i++) {
    const next = new Uint8Array(poly.length + 1);
    for (let j = 0; j < poly.length; j++) {
      next[j] ^= poly[j];
      next[j + 1] ^= mul(poly[j], EXP[i]);
    }
    poly = next;
  }
  return poly;
}

export function remainder(data, n) {
  const gen = generator(n);
  const out = new Uint8Array(n);
  for (const byte of data) {
    const factor = byte ^ out[0];
    out.copyWithin(0, 1);
    out[n - 1] = 0;
    if (factor !== 0) {
      for (let i = 0; i < n; i++) out[i] ^= mul(gen[i + 1], factor);
    }
  }
  return out;
}

export const VERSIONS = {
  1: [26, 10, 1],
  2: [44, 16, 1],
  3: [70, 26, 1],
  4: [100, 18, 2],
  5: [134, 24, 2],
  6: [172, 16, 4],
};

export const REMAINDER_BITS = { 1: 0, 2: 7, 3: 7, 4: 7, 5: 7, 6: 7 };

export const ALIGNMENT = { 1: [], 2: [6, 18], 3: [6, 22], 4: [6, 26], 5: [6, 30], 6: [6, 34] };

export const dataWords = (version) => {
  const [total, ecc, blocks] = VERSIONS[version];
  return total - ecc * blocks;
};

export function versionFor(length) {
  for (const version of [1, 2, 3, 4, 5, 6]) {
    if (dataWords(version) * 8 >= 12 + length * 8) return version;
  }
  return null;
}

export function codewords(bytes, version) {
  const capacity = dataWords(version);
  const bits = [];
  const push = (value, width) => {
    for (let i = width - 1; i >= 0; i--) bits.push((value >> i) & 1);
  };
  push(0b0100, 4);
  push(bytes.length, 8);
  for (const byte of bytes) push(byte, 8);
  push(0, Math.min(4, capacity * 8 - bits.length));
  while (bits.length % 8 !== 0) bits.push(0);
  const data = new Uint8Array(capacity);
  for (let i = 0; i < bits.length; i += 8) {
    let byte = 0;
    for (let j = 0; j < 8; j++) byte = (byte << 1) | bits[i + j];
    data[i / 8] = byte;
  }
  for (let i = bits.length / 8; i < capacity; i++) {
    data[i] = (i - bits.length / 8) % 2 === 0 ? 0xec : 0x11;
  }
  return data;
}

export function interleave(data, version) {
  const [, eccWords, blocks] = VERSIONS[version];
  const perBlock = data.length / blocks;
  const dataBlocks = [];
  const eccBlocks = [];
  for (let b = 0; b < blocks; b++) {
    const block = data.subarray(b * perBlock, (b + 1) * perBlock);
    dataBlocks.push(block);
    eccBlocks.push(remainder(block, eccWords));
  }
  const out = [];
  for (let i = 0; i < perBlock; i++) for (const block of dataBlocks) out.push(block[i]);
  for (let i = 0; i < eccWords; i++) for (const block of eccBlocks) out.push(block[i]);
  return Uint8Array.from(out);
}

export class Matrix {
  constructor(version) {
    this.version = version;
    this.size = version * 4 + 17;
    this.modules = new Uint8Array(this.size * this.size);
    this.fixed = new Uint8Array(this.size * this.size);
  }

  get(x, y) { return this.modules[y * this.size + x]; }

  set(x, y, dark, fixed = false) {
    this.modules[y * this.size + x] = dark ? 1 : 0;
    if (fixed) this.fixed[y * this.size + x] = 1;
  }

  isFixed(x, y) { return this.fixed[y * this.size + x] === 1; }

  functionPatterns() {
    const last = this.size - 1;
    for (let i = 0; i < this.size; i++) {
      this.set(6, i, i % 2 === 0, true);
      this.set(i, 6, i % 2 === 0, true);
    }
    for (const [x, y] of [[3, 3], [last - 3, 3], [3, last - 3]]) {
      for (let dy = -4; dy <= 4; dy++) {
        for (let dx = -4; dx <= 4; dx++) {
          const distance = Math.max(Math.abs(dx), Math.abs(dy));
          const xx = x + dx;
          const yy = y + dy;
          if (xx < 0 || xx >= this.size || yy < 0 || yy >= this.size) continue;
          this.set(xx, yy, distance !== 2 && distance !== 4, true);
        }
      }
    }
    const centres = ALIGNMENT[this.version];
    for (const cy of centres) {
      for (const cx of centres) {
        if ((cx === 6 && cy === 6) || (cx === 6 && cy === centres[centres.length - 1])
            || (cy === 6 && cx === centres[centres.length - 1])) continue;
        for (let dy = -2; dy <= 2; dy++) {
          for (let dx = -2; dx <= 2; dx++) {
            this.set(cx + dx, cy + dy, Math.max(Math.abs(dx), Math.abs(dy)) !== 1, true);
          }
        }
      }
    }
    this.reserveFormat();
  }

  reserveFormat() {
    for (let i = 0; i <= 5; i++) this.set(8, i, false, true);
    this.set(8, 7, false, true);
    this.set(8, 8, false, true);
    this.set(7, 8, false, true);
    for (let i = 9; i < 15; i++) this.set(14 - i, 8, false, true);
    for (let i = 0; i < 8; i++) this.set(this.size - 1 - i, 8, false, true);
    for (let i = 8; i < 15; i++) this.set(8, this.size - 15 + i, false, true);
    this.set(8, this.size - 8, true, true);
  }
}

export function dataPositions(matrix) {
  const positions = [];
  let upward = true;
  for (let right = matrix.size - 1; right >= 1; right -= 2) {
    if (right === 6) right = 5;
    for (let step = 0; step < matrix.size; step++) {
      const y = upward ? matrix.size - 1 - step : step;
      for (const x of [right, right - 1]) {
        if (!matrix.isFixed(x, y)) positions.push([x, y]);
      }
    }
    upward = !upward;
  }
  return positions;
}

export const MASKS = [
  (x, y) => (x + y) % 2 === 0,
  (x, y) => y % 2 === 0,
  (x) => x % 3 === 0,
  (x, y) => (x + y) % 3 === 0,
  (x, y) => (Math.floor(y / 2) + Math.floor(x / 3)) % 2 === 0,
  (x, y) => ((x * y) % 2) + ((x * y) % 3) === 0,
  (x, y) => (((x * y) % 2) + ((x * y) % 3)) % 2 === 0,
  (x, y) => (((x + y) % 2) + ((x * y) % 3)) % 2 === 0,
];

export function formatBits(mask) {
  const data = (0b00 << 3) | mask;
  let rest = data << 10;
  for (let i = 4; i >= 0; i--) {
    if (rest & (1 << (i + 10))) rest ^= 0x537 << i;
  }
  return (((data << 10) | rest) ^ 0x5412) & 0x7fff;
}

export function writeFormat(matrix, mask) {
  const bits = formatBits(mask);
  const bit = (i) => ((bits >> i) & 1) === 1;
  for (let i = 0; i <= 5; i++) matrix.set(8, i, bit(i), true);
  matrix.set(8, 7, bit(6), true);
  matrix.set(8, 8, bit(7), true);
  matrix.set(7, 8, bit(8), true);
  for (let i = 9; i < 15; i++) matrix.set(14 - i, 8, bit(i), true);
  for (let i = 0; i < 8; i++) matrix.set(matrix.size - 1 - i, 8, bit(i), true);
  for (let i = 8; i < 15; i++) matrix.set(8, matrix.size - 15 + i, bit(i), true);
  matrix.set(8, matrix.size - 8, true, true);
}

export function penalty(matrix) {
  const size = matrix.size;
  const at = (x, y) => matrix.get(x, y);
  let score = 0;

  for (let outer = 0; outer < size; outer++) {
    for (const horizontal of [true, false]) {
      let run = 1;
      for (let inner = 1; inner < size; inner++) {
        const previous = horizontal ? at(inner - 1, outer) : at(outer, inner - 1);
        const current = horizontal ? at(inner, outer) : at(outer, inner);
        if (current === previous) {
          run += 1;
          if (run === 5) score += 3;
          else if (run > 5) score += 1;
        } else {
          run = 1;
        }
      }
    }
  }

  for (let y = 0; y < size - 1; y++) {
    for (let x = 0; x < size - 1; x++) {
      const value = at(x, y);
      if (value === at(x + 1, y) && value === at(x, y + 1) && value === at(x + 1, y + 1)) {
        score += 3;
      }
    }
  }

  const FINDER = [1, 0, 1, 1, 1, 0, 1];
  const line = (fixed, from, horizontal) =>
    (offset) => (horizontal ? at(from + offset, fixed) : at(fixed, from + offset));
  for (let fixed = 0; fixed < size; fixed++) {
    for (const horizontal of [true, false]) {
      for (let start = 0; start + 7 <= size; start++) {
        const read = line(fixed, start, horizontal);
        let matches = true;
        for (let i = 0; i < 7; i++) if (read(i) !== FINDER[i]) { matches = false; break; }
        if (!matches) continue;
        const light = (from, count) => {
          for (let i = 0; i < count; i++) {
            const index = from + i;
            if (index < 0 || index >= size) continue;
            if ((horizontal ? at(index, fixed) : at(fixed, index)) !== 0) return false;
          }
          return true;
        };
        if (light(start - 4, 4) || light(start + 7, 4)) score += 40;
      }
    }
  }

  let dark = 0;
  for (let i = 0; i < matrix.modules.length; i++) dark += matrix.modules[i];
  const percent = (dark * 100) / (size * size);
  score += 10 * Math.floor(Math.abs(percent - 50) / 5);
  return score;
}

export function encode(text) {
  const bytes = new TextEncoder().encode(text);
  const version = versionFor(bytes.length);
  if (version === null) {
    throw new Error(`${bytes.length} bytes: more than version 6 holds at level M`);
  }
  const words = interleave(codewords(bytes, version), version);

  const base = new Matrix(version);
  base.functionPatterns();
  const positions = dataPositions(base);
  const bits = words.length * 8;
  if (positions.length !== bits + REMAINDER_BITS[version]) {
    throw new Error(`version ${version}: ${positions.length} free modules, expected `
      + `${bits + REMAINDER_BITS[version]}`);
  }
  positions.forEach(([x, y], i) => {
    if (i < bits) base.set(x, y, ((words[i >> 3] >> (7 - (i & 7))) & 1) === 1);
  });

  let best = null;
  for (let mask = 0; mask < 8; mask++) {
    const candidate = new Matrix(version);
    candidate.modules.set(base.modules);
    candidate.fixed.set(base.fixed);
    for (const [x, y] of positions) {
      if (MASKS[mask](x, y)) candidate.set(x, y, candidate.get(x, y) === 0);
    }
    writeFormat(candidate, mask);
    const score = penalty(candidate);
    if (best === null || score < best.score) best = { score, mask, matrix: candidate };
  }
  return best.matrix;
}

export function drawQr(canvas, text, target = 148) {
  const matrix = encode(text);
  const QUIET = 4;
  const count = matrix.size + QUIET * 2;
  const scale = Math.max(1, Math.floor(target / count));
  const size = count * scale;
  canvas.width = size;
  canvas.height = size;
  canvas.style.width = `${size}px`;
  canvas.style.height = `${size}px`;

  const context = canvas.getContext("2d");
  context.fillStyle = "#FFFFFF";
  context.fillRect(0, 0, size, size);
  context.fillStyle = "#000000";
  for (let y = 0; y < matrix.size; y++) {
    for (let x = 0; x < matrix.size; x++) {
      if (matrix.get(x, y)) {
        context.fillRect((x + QUIET) * scale, (y + QUIET) * scale, scale, scale);
      }
    }
  }
  return matrix;
}
