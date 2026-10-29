"""產生已知效果的合成吉他音檔，用來驗證分析工具。"""
import os
import sys

import numpy as np
import soundfile as sf
from scipy import signal

SR = 44100
rng = np.random.default_rng(1)


def pluck(freq, dur):
    """加法合成的撥弦：輕微走音、弦的非諧性、高次諧波衰減較快、撥弦雜音。"""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f0 = freq * (1 + rng.normal(0, 0.002))
    B = 1e-4
    pos = rng.uniform(0.12, 0.2)  # 撥弦位置
    out = np.zeros(n)
    for h in range(1, 60):
        fh = h * f0 * np.sqrt(1 + B * h * h)
        if fh > 9000:
            break
        amp = abs(np.sin(np.pi * h * pos)) / h ** 1.6
        tau = 1.2 / (1 + 0.5 * h)
        env = 0.6 * np.exp(-t / tau) + 0.4 * np.exp(-t / (0.08 + 0.1 / h))  # 起音後的快速衰減
        out += amp * env * np.sin(2 * np.pi * fh * t + rng.uniform(0, 2 * np.pi))
    att = int(0.004 * SR)
    out[:att] += rng.standard_normal(att) * np.linspace(0.3, 0, att)
    return out


def chord(freqs, dur, strum=0.012):
    n = int(dur * SR)
    out = np.zeros(n)
    for j, fq in enumerate(freqs):
        s = int(j * strum * SR)
        out[s:] += pluck(fq, dur)[: n - s]
    return out / len(freqs)


def phrase(bpm=120, bars=8, mute_gap=True):
    """8 小節：和弦/單音交替，每 2 小節最後半拍切音 (給殘響量測)。"""
    beat = 60 / bpm
    total = int(bars * 4 * beat * SR) + SR * 3
    out = np.zeros(total)
    chords = [[82.4, 123.5, 164.8, 207.7], [110, 164.8, 220, 277.2], [98, 146.8, 196, 246.9], [73.4, 110, 146.8, 185]]
    melody = [329.6, 392, 440, 493.9, 440, 392]
    t = 0.0
    for bar in range(bars):
        if bar % 2 == 0:
            seg = chord(chords[(bar // 2) % 4], 4 * beat * 0.95)
        else:
            seg = np.zeros(int(4 * beat * SR))
            for i, m in enumerate(melody[:4]):
                s = int(i * beat * SR)
                note = pluck(m * (1 + 0.5 * (bar % 4 == 3)), beat * 0.98)
                seg[s:s + len(note)] += note * 0.8
        if mute_gap:
            cut = int(len(seg) * 0.85)
            fade = int(0.01 * SR)
            seg[cut:cut + fade] *= np.linspace(1, 0, fade)
            seg[cut + fade:] = 0
        s = int(t * SR)
        out[s:s + len(seg)] += seg[: total - s]
        t += 4 * beat
    return out


def cab(x):
    sos = signal.butter(2, [90, 5000], btype="band", fs=SR, output="sos")
    return signal.sosfilt(sos, x)


def dist(x, drive):
    return np.tanh(drive * x / (np.abs(x).max() + 1e-9))


def delay(x, ms, fb, mix, lp=None, wobble=0.0):
    d = int(ms * SR / 1000)
    y = x.copy()
    wet = np.zeros_like(x)
    tap = x.copy()
    for k in range(1, 25):
        tap = np.concatenate([np.zeros(d), tap[:-d]])
        if lp:
            tap = signal.sosfilt(signal.butter(1, lp, fs=SR, output="sos"), tap)
        if wobble:
            # 輕微的時間抖動
            idx = np.arange(len(tap)) + wobble * SR / 1000 * np.sin(2 * np.pi * 0.7 * np.arange(len(tap)) / SR)
            tap = np.interp(idx, np.arange(len(tap)), tap)
        wet += tap * (fb ** (k - 1))
        if fb ** (k - 1) < 1e-3:
            break
    return y + mix * wet


def reverb(x, rt60, mix):
    n = int(rt60 * SR)
    t = np.arange(n) / SR
    ir = rng.standard_normal(n) * 10 ** (-3 * t / rt60)
    ir = signal.sosfilt(signal.butter(1, 6000, fs=SR, output="sos"), ir)
    ir /= np.sqrt((ir ** 2).sum())
    wet = signal.fftconvolve(x, ir)[: len(x)]
    return x + mix * wet / (np.std(wet) + 1e-9) * np.std(x)


def tremolo(x, rate, depth):
    t = np.arange(len(x)) / SR
    return x * (1 - depth * 0.5 * (1 + np.sin(2 * np.pi * rate * t)))


def chorus_st(x, rate=0.8, depth_ms=2.0, base_ms=15):
    t = np.arange(len(x)) / SR
    outs = []
    for ph in (0, np.pi / 2):
        dl = (base_ms + depth_ms * np.sin(2 * np.pi * rate * t + ph)) * SR / 1000
        idx = np.arange(len(x)) - dl
        outs.append(0.7 * x + 0.7 * np.interp(idx, np.arange(len(x)), x))
    return np.stack(outs, axis=1)


def phaser(x, rate=0.4):
    t = np.arange(len(x)) / SR
    y = x.copy()
    fc = 300 * (2 ** (2.5 * (0.5 + 0.5 * np.sin(2 * np.pi * rate * t))))
    for _ in range(4):
        out = np.zeros_like(y)
        z = 0.0
        prev = 0.0
        for i in range(len(y)):
            tn = np.tan(np.pi * fc[i] / SR)
            a = (tn - 1) / (tn + 1)
            o = a * y[i] + prev - a * z
            prev = y[i]
            z = o
            out[i] = o
        y = out
    return 0.5 * x + 0.5 * y


def wah_pedal(x):
    """共振帶通，中心頻率依「腳踩」的平滑隨機曲線在 400~2000 Hz 移動。"""
    n = len(x)
    ctrl = signal.sosfiltfilt(signal.butter(2, 0.8, fs=SR, output="sos"), rng.standard_normal(n))
    ctrl = (ctrl - ctrl.min()) / (ctrl.max() - ctrl.min())
    fc = 400 * 5 ** ctrl
    q = 5.0
    y = np.zeros(n)
    low = band = 0.0
    for i in range(n):
        F = 2 * np.sin(np.pi * fc[i] / SR)
        high = x[i] - low - band / q
        band += F * high
        low += F * band
        y[i] = band
    return y


def write(name, x):
    x = x / (np.abs(x).max() + 1e-9) * 0.9
    sf.write(name, x, SR)
    print("wrote", name)


if __name__ == "__main__":
    outdir = sys.argv[1] if len(sys.argv) > 1 else "test_audio"
    os.makedirs(outdir, exist_ok=True)
    dry = phrase()
    p = lambda n: os.path.join(outdir, n)
    write(p("01_clean_dry.wav"), cab(dry))
    write(p("02_clean_digital_delay_375ms_plate.wav"),
          reverb(delay(cab(dry), 375, 0.35, 0.45), 1.3, 0.35))
    write(p("03_high_gain_dry.wav"), cab(dist(dry, 40)))
    write(p("04_clean_tremolo_5hz.wav"), tremolo(cab(dry), 5.0, 0.7))
    write(p("05_clean_stereo_chorus.wav"), chorus_st(cab(dry)))
    write(p("06_crunch_analog_delay_hall.wav"),
          reverb(delay(cab(dist(dry, 6)), 450, 0.45, 0.4, lp=1500), 2.8, 0.5))
    write(p("07_clean_phaser.wav"), phaser(cab(dry)))
    write(p("08_crunch_wah_pedal.wav"), cab(dist(wah_pedal(dry), 8)))
    write(p("09_clean_tape_echo_only.wav"), delay(cab(dry), 300, 0.4, 0.5, lp=2000, wobble=0.6))
