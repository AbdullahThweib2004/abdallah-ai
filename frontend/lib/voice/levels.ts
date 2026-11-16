/** Number of waveform bars on the avatar. */
export const BAR_COUNT = 9;

/** Reads per-bar levels (0..1) from an AnalyserNode, smoothed, for the avatar waveform. */
export class LevelMeter {
  private readonly bins: Uint8Array<ArrayBuffer>;
  private readonly samples: Float32Array<ArrayBuffer>;
  private readonly smoothed = new Array<number>(BAR_COUNT).fill(0);

  constructor(private readonly analyser: AnalyserNode) {
    analyser.fftSize = 256;
    analyser.smoothingTimeConstant = 0.6;
    this.bins = new Uint8Array(analyser.frequencyBinCount);
    this.samples = new Float32Array(analyser.fftSize);
  }

  /** Speech-band energy per bar (low to high, mirrored so the loudest bars sit centered). */
  bars(): number[] {
    this.analyser.getByteFrequencyData(this.bins);
    const half = Math.ceil(BAR_COUNT / 2);
    const bands: number[] = [];
    for (let band = 0; band < half; band++) {
      // Roughly 170 Hz – 4 kHz at 44.1/48 kHz: where speech energy lives.
      const from = 1 + Math.round(band * 4);
      const to = from + 4;
      let sum = 0;
      for (let bin = from; bin < to; bin++) sum += this.bins[bin] ?? 0;
      bands.push(Math.min(1, (sum / (to - from) / 255) * 1.6));
    }
    // Center = lowest band (strongest), edges = highest.
    const ordered = [...bands.slice(1).reverse(), ...bands].slice(0, BAR_COUNT);
    for (let i = 0; i < BAR_COUNT; i++) {
      this.smoothed[i] = this.smoothed[i] * 0.5 + (ordered[i] ?? 0) * 0.5;
    }
    return [...this.smoothed];
  }

  /** Root-mean-square amplitude of the current frame (0..~1). */
  rms(): number {
    this.analyser.getFloatTimeDomainData(this.samples);
    let sum = 0;
    for (const sample of this.samples) sum += sample * sample;
    return Math.sqrt(sum / this.samples.length);
  }
}
