"""音檔特徵分析：從吉他錄音推估使用的效果與程度。

每個偵測項目回傳數值與 confidence (0~1)。這些都是訊號處理的啟發式估計，
最準確的情況是「單獨的吉他音軌」(無鼓、貝斯、人聲)。
"""
from math import gcd

import numpy as np
import soundfile as sf
from scipy import signal
from scipy.ndimage import uniform_filter1d, median_filter, minimum_filter1d

EPS = 1e-12
NPER = 2048
HOP = 512
EQ6_BANDS = [100, 220, 500, 1200, 2600, 6400]


def db(x):
    return 10.0 * np.log10(np.maximum(x, EPS))


def clip01(x):
    return float(min(1.0, max(0.0, x)))


def lin_map(x, x0, x1):
    """x0 -> 0, x1 -> 1 (可反向)，並夾在 0~1。"""
    return clip01((x - x0) / (x1 - x0))


# ---------------------------------------------------------------- 讀檔
def read_any(path):
    """讀取音檔；soundfile 不支援的格式 (m4a / aac / mp4 等) 透過 ffmpeg 解碼。"""
    try:
        return sf.read(path, always_2d=True, dtype="float64")
    except Exception:
        import subprocess
        try:
            import imageio_ffmpeg
            exe = imageio_ffmpeg.get_ffmpeg_exe()
        except ImportError:
            raise RuntimeError("此格式需要 ffmpeg：請執行 pip install imageio-ffmpeg")
        out = subprocess.run([exe, "-v", "error", "-i", str(path), "-f", "f32le", "-ac", "2", "-ar", "44100", "-"],
                             capture_output=True, check=True).stdout
        return np.frombuffer(out, dtype="<f4").reshape(-1, 2).astype(np.float64), 44100


def load_audio(path, max_seconds=90.0):
    data, sr = read_any(path)
    data = data[:, :2]
    if sr not in (44100, 48000):
        g = gcd(int(sr), 44100)
        data = signal.resample_poly(data, 44100 // g, int(sr) // g, axis=0)
        sr = 44100
    mono = data.mean(axis=1)
    env = np.abs(mono)
    if env.max() <= 0:
        raise ValueError("音檔是無聲的，沒有可分析的訊號")
    idx = np.where(env > env.max() * 10 ** (-60 / 20))[0]
    s = max(idx[0] - int(0.05 * sr), 0)
    e = min(idx[-1] + int(0.05 * sr), len(mono))
    data = data[s:e]
    if len(data) > max_seconds * sr:
        data = data[: int(max_seconds * sr)]
    if len(data) < sr * 1.0:
        raise ValueError("音檔太短 (至少需要 1 秒，建議 10~60 秒)")
    data = data / (np.abs(data).max() + EPS) * 0.89
    return data, int(sr)


# ---------------------------------------------------------------- 主流程
def analyze(path, max_seconds=90.0):
    data, sr = load_audio(path, max_seconds)
    mono = data.mean(axis=1)
    stereo = data.shape[1] == 2 and np.max(np.abs(data[:, 0] - data[:, 1])) > 1e-3

    f, _, Z = signal.stft(mono, sr, window="hann", nperseg=NPER, noverlap=NPER - HOP,
                          boundary=None, padded=False)
    P = np.abs(Z) ** 2
    fr = sr / HOP  # frame rate (frames / s)

    lev = db(P.sum(axis=0))
    lev -= lev.max()
    levs = uniform_filter1d(lev, 3)
    floor = float(max(np.percentile(levs, 5), -90.0))
    # 連續演奏 (沒有空白) 時 5% 分位數不是底噪而是演奏音量，門檻上限設為 40% 分位數
    act_thr = min(max(-45.0, floor + 12), float(np.percentile(levs, 40)))
    active = levs > act_thr
    if np.percentile(levs, 50) - floor < 15:
        floor = float(min(floor, np.percentile(levs, 50) - 30))  # 實際底噪未知，假設在中位數下 30 dB
    if active.sum() < fr * 0.5:
        raise ValueError("有效的演奏片段太少，無法分析")

    onsets, flux = detect_onsets(P, fr, active)
    n = P.shape[1]
    near_onset = np.zeros(n, bool)
    for o in onsets:
        near_onset[max(o - 1, 0): o + int(0.12 * fr) + 1] = True
    sus_mask = (~active) | near_onset
    ctx = dict(data=data, mono=mono, sr=sr, stereo=stereo, f=f, Z=Z, P=P, fr=fr,
               lev=levs, floor=floor, active=active, onsets=onsets, flux=flux,
               sus_mask=sus_mask, segments=sustained_segments(sus_mask, fr, 0.35))

    feats = {
        "file": str(path),
        "duration_s": round(len(mono) / sr, 2),
        "sample_rate": sr,
        "stereo": bool(stereo),
        "noise_floor_db": round(floor, 1),
        "num_onsets": int(len(onsets)),
    }
    feats["tempo"] = estimate_tempo(flux, fr)
    feats["delay"] = analyze_delay(ctx)
    feats["reverb"] = analyze_reverb(ctx, feats["delay"])
    wet = bool(feats["delay"].get("detected") or feats["reverb"].get("detected"))
    feats["gain"] = analyze_gain(ctx, wet)
    feats["tone"] = analyze_tone(ctx)
    feats["dynamics"] = analyze_dynamics(ctx)
    motion = analyze_spectral_motion(ctx)
    feats["wah"] = motion["wah"]
    feats["modulation"] = {
        "tremolo": analyze_tremolo(ctx),
        "sweep": motion["sweep"],
        "pitch": analyze_pitch_mod(ctx),
    }
    feats["stereo_width"] = analyze_width(ctx)
    return feats


def sustained_segments(mask, fr, min_s):
    segs, start = [], None
    for i, m in enumerate(np.append(mask, True)):
        if not m and start is None:
            start = i
        elif m and start is not None:
            if i - start >= min_s * fr:
                segs.append((start, i))
            start = None
    return segs


# ---------------------------------------------------------------- onset / tempo
def detect_onsets(P, fr, active):
    mag = np.sqrt(P)
    logS = np.log1p(1000.0 * mag / (mag.max() + EPS))
    flux = np.maximum(np.diff(logS, axis=1), 0).sum(axis=0)
    flux = np.concatenate([[0.0], flux])
    flux /= flux.max() + EPS
    thr = median_filter(flux, size=max(3, int(fr))) * 1.5 + 0.04
    peaks, _ = signal.find_peaks(flux, height=thr, distance=max(1, int(0.05 * fr)))
    peaks = peaks[active[peaks]]
    return peaks, flux


def estimate_tempo(flux, fr):
    x = flux - flux.mean()
    if len(x) < fr * 4:
        return {"bpm": None, "confidence": 0.0}
    ac = signal.fftconvolve(x, x[::-1], mode="full")[len(x) - 1:]
    ac /= ac[0] + EPS
    bpms = np.arange(60, 201)
    scores = []
    for b in bpms:
        beat = 60.0 / b
        s = 0.0
        for kk, w in ((1, 1.0), (2, 0.5), (4, 0.25)):
            i = int(round(beat * kk * fr))
            if i < len(ac):
                s += w * ac[max(i - 1, 0): i + 2].max()
        scores.append(s)
    scores = np.array(scores)
    prior = np.exp(-0.5 * ((bpms - 115) / 40.0) ** 2)  # 偏好常見速度
    best = int(np.argmax(scores * (0.6 + 0.4 * prior)))
    conf = clip01((scores[best] - np.median(scores)) / (np.std(scores) * 4 + EPS))
    return {"bpm": int(bpms[best]), "confidence": round(conf, 2)}


# ---------------------------------------------------------------- 破音程度
def analyze_gain(ctx, wet=False):
    mono, P, f, active, lev, fr = ctx["mono"], ctx["P"], ctx["f"], ctx["active"], ctx["lev"], ctx["fr"]
    frames = np.lib.stride_tricks.sliding_window_view(mono, NPER)[::HOP]
    n = min(len(frames), P.shape[1])
    ons = ctx["onsets"]
    # 只看每個音剛彈下去的 frame：原音最強，殘響/延遲的影響最小
    idx = sorted({j for o in ons for j in range(o + 1, o + 5) if j < n and active[j]})
    if len(idx) < 12:
        idx = list(np.where(active[:n])[0])
    idx = np.array(idx)
    fr_act = frames[idx]
    rms = np.sqrt((fr_act ** 2).mean(axis=1)) + EPS
    crest = 20 * np.log10(np.abs(fr_act).max(axis=1) / rms)
    crest_med = float(np.median(crest))

    band = (f >= 150) & (f <= 6000)
    Pb = P[band][:, idx] + EPS
    flat = np.exp(np.log(Pb).mean(axis=0)) / Pb.mean(axis=0)
    flat_db = float(np.median(db(flat)))

    # 高頻諧波密度：1.5~5k 相對 100~800 的能量 (破音會大量增加高次諧波)
    hi = P[(f >= 1500) & (f <= 5000)][:, idx].sum(0)
    lo = P[(f >= 100) & (f <= 800)][:, idx].sum(0)
    hratio = float(np.median(db(hi / (lo + EPS))))

    drops = []
    for i, o in enumerate(ons):
        nxt = ons[i + 1] if i + 1 < len(ons) else len(lev)
        if nxt - o < 0.45 * fr:
            continue
        pk = lev[o: o + int(0.05 * fr) + 1].max()
        drops.append(pk - lev[o + int(0.4 * fr)])
    drop_med = float(np.median(drops)) if drops else None

    # 殘響/延遲會讓頻譜變平坦、延音變長，有空間效果時降低這兩項的權重
    c_s = lin_map(crest_med, 10.0, 5.0)
    f_s = lin_map(flat_db, -30.0, -18.0)
    h_s = lin_map(hratio, -15.0, -6.0)
    parts = [(c_s, 0.40), (f_s, 0.10 if wet else 0.25), (h_s, 0.25)]
    if drop_med is not None and not wet:
        parts.append((lin_map(drop_med, 10.0, 1.0), 0.10))
    score = sum(v * w for v, w in parts) / sum(w for _, w in parts)

    if score < 0.25:
        cls = "clean"
    elif score < 0.42:
        cls = "edge_of_breakup"
    elif score < 0.60:
        cls = "crunch"
    elif score < 0.80:
        cls = "high_gain"
    else:
        cls = "very_high_gain"
    return {
        "score": round(float(score), 3),
        "class": cls,
        "crest_db": round(crest_med, 2),
        "flatness_db": round(flat_db, 2),
        "hf_ratio_db": round(hratio, 2),
        "sustain_drop_db": None if drop_med is None else round(drop_med, 2),
        "confidence": round(0.5 + 0.5 * min(1.0, len(idx) / 80), 2),
    }


# ---------------------------------------------------------------- 頻率響應 (音色)
def band_level(f, spec_db, lo, hi):
    m = (f >= lo) & (f < hi)
    return float(db(np.mean(10 ** (spec_db[m] / 10))))


def analyze_tone(ctx):
    f = ctx["f"]
    s = db(ctx["P"][:, ctx["active"]].mean(axis=1))
    mid = band_level(f, s, 400, 1200)
    bass = band_level(f, s, 80, 250) - mid
    low_mid = band_level(f, s, 250, 500) - mid
    treble = band_level(f, s, 2000, 5000) - mid
    presence = band_level(f, s, 5000, 9000) - mid
    upper_mid = band_level(f, s, 1200, 2500) - mid
    eq6 = {c: round(band_level(f, s, c / 2 ** (1 / 6), c * 2 ** (1 / 6)) - mid, 2) for c in EQ6_BANDS}
    P_act = ctx["P"][:, ctx["active"]]
    cent = float(np.median((f[:, None] * P_act).sum(0) / (P_act.sum(0) + EPS)))
    return {
        "bass_rel_db": round(bass, 2),
        "low_mid_rel_db": round(low_mid, 2),
        "upper_mid_rel_db": round(upper_mid, 2),
        "treble_rel_db": round(treble, 2),
        "presence_rel_db": round(presence, 2),
        "mid_scoop_db": round((bass + treble) / 2, 2),
        "centroid_hz": round(cent, 1),
        "eq6_rel_db": eq6,
    }


# ---------------------------------------------------------------- 壓縮 / 噪音門
def analyze_dynamics(ctx):
    lev, fr, ons, floor = ctx["lev"], ctx["fr"], ctx["onsets"], ctx["floor"]
    act_lev = lev[ctx["active"]]
    dyn_range = float(np.percentile(act_lev, 95) - np.percentile(act_lev, 20))
    attack = []
    for i, o in enumerate(ons):
        nxt = ons[i + 1] if i + 1 < len(ons) else len(lev)
        if nxt - o < 0.35 * fr:
            continue
        pk = lev[o: o + int(0.03 * fr) + 2].max()
        body = np.median(lev[o + int(0.1 * fr): o + int(0.3 * fr)])
        attack.append(pk - body)
    attack_med = float(np.median(attack)) if attack else None
    comp = lin_map(dyn_range, 20.0, 6.0)
    if attack_med is not None:
        comp = 0.5 * comp + 0.5 * lin_map(attack_med, 8.0, 1.5)
    return {
        "dynamic_range_db": round(dyn_range, 2),
        "attack_over_body_db": None if attack_med is None else round(attack_med, 2),
        "compression_score": round(comp, 3),
        "noise_floor_db": round(floor, 1),
        "silence_looks_gated": bool(floor < -75),
    }


# ---------------------------------------------------------------- Delay
def _whitened_xcorr(x, sr, lo, hi, max_lag_s, y=None, smooth_hz=40.0):
    """頻譜白化後的自相關 (或與 y 的互相關)；回音會在延遲時間形成尖峰。
    回傳 (正 lag, 負 lag)，以「相關係數」尺度正規化。"""
    n = len(x)
    nfft = 1 << int(np.ceil(np.log2(2 * n)))
    X = np.fft.rfft(x, nfft)
    Y = X if y is None else np.fft.rfft(y, nfft)
    cross = X * np.conj(Y)
    pw = np.abs(X) * np.abs(Y)
    win = max(3, int(smooth_hz * nfft / sr))
    ps = uniform_filter1d(pw, win) + EPS
    freqs = np.fft.rfftfreq(nfft, 1.0 / sr)
    band = (freqs >= lo) & (freqs <= hi)
    W = np.where(band, cross / ps, 0)
    r = np.fft.irfft(W, nfft)
    norm = 2.0 * band.sum() / nfft
    maxlag = int(max_lag_s * sr)
    pos = r[: maxlag + 1] / norm
    neg = r[::-1][:maxlag] / norm  # neg[i] = lag -(i+1)
    return pos, neg


def _block_xcorr(x, sr, lo, hi, max_lag_s, y=None, envelope=False):
    """把音檔切成數個區塊各自計算後取中位數：
    真正的回音在每個區塊都會出現在同一個 lag，單一音符的週期性則不會。"""
    block = int(max(4.0, 2.5 * max_lag_s) * sr)
    n = len(x)
    if n < block * 1.5:
        return _whitened_xcorr(x, sr, lo, hi, max_lag_s, y)
    gstd = np.std(x)
    P, N = [], []
    for s in range(0, n - block + 1, block // 2):
        xs = x[s:s + block]
        if np.std(xs) < 0.05 * gstd:
            continue
        p, q = _whitened_xcorr(xs, sr, lo, hi, max_lag_s, None if y is None else y[s:s + block])
        if envelope:  # 取相關函數的包絡：磁帶/調變延遲的時間抖動不會讓峰值互相抵消
            p, q = np.abs(signal.hilbert(p)), np.abs(signal.hilbert(q))
        P.append(p)
        N.append(q)
    if not P:
        return _whitened_xcorr(x, sr, lo, hi, max_lag_s, y)
    agg = np.median if len(P) >= 3 else np.mean
    return agg(np.array(P), axis=0), agg(np.array(N), axis=0)


def _peak_val(c, i, sr, tol_ms):
    t = max(1, int(tol_ms * 1e-3 * sr))
    seg = c[max(i - t, 0): i + t + 1]
    return float(seg.max()) if len(seg) else 0.0


def _fit_echo(c1, c2, c3):
    best = (1e9, 0.0, 0.0)
    for a in np.linspace(0.03, 1.3, 64):
        for fb in np.linspace(0.0, 0.92, 47):
            h = np.zeros(80)
            h[0] = 1.0
            h[1:] = a * fb ** np.arange(79)
            r0 = (h ** 2).sum()
            m = [(h[:-kk] * h[kk:]).sum() / r0 for kk in (1, 2, 3)]
            err = (m[0] - c1) ** 2 + 0.7 * (m[1] - c2) ** 2 + 0.4 * (m[2] - c3) ** 2
            if err < best[0]:
                best = (err, a, fb)
    return best[1], best[2]


def _echo_peak(c, sr, ring_in_ms, ring_out_ms, min_iso):
    """在 60ms~1.6s 中找「孤立」的最高峰 (回音)。和弦中多個音的共同週期也會產生峰值，
    但那種峰值旁邊會有一排相鄰的峰，孤立度低。"""
    i0, i1 = int(0.06 * sr), int(1.6 * sr)
    seg = c[i0:i1]
    med = float(np.median(seg))
    mad = float(np.median(np.abs(seg - med))) + EPS
    a_, b_ = int(ring_in_ms * 1e-3 * sr), int(ring_out_ms * 1e-3 * sr)
    peaks, _ = signal.find_peaks(seg, distance=max(1, int(0.008 * sr)))
    if len(peaks) == 0:
        return i0, 0.0, 0.0, 0.0
    top = peaks[np.argsort(seg[peaks])[::-1][:25]]
    best = None
    for p in top:
        L = p + i0
        ring = np.r_[c[max(L - b_, 0): L - a_], c[L + a_: L + b_]]
        iso = float(seg[p] / (np.abs(ring).max() + EPS)) if len(ring) else 9.0
        if iso >= min_iso:
            best = (L, float(seg[p]), iso)
            break
    if best is None:
        p = top[0]
        L = p + i0
        ring = np.r_[c[max(L - b_, 0): L - a_], c[L + a_: L + b_]]
        best = (L, float(seg[p]), float(seg[p] / (np.abs(ring).max() + EPS)))
    L, pk, iso = best
    return L, pk, (pk - med) / (1.4826 * mad), iso


def analyze_delay(ctx):
    mono, sr = ctx["mono"], ctx["sr"]
    lo_c, _ = _block_xcorr(mono, sr, 150, 1500, 2.0)
    L, pk, z, iso = _echo_peak(lo_c, sr, 2, 15, 1.6)
    detected = pk > 0.05 and z > 10 and iso > 1.6
    smeared = False
    if not detected:
        # 備援：低頻段相關包絡 (容許磁帶 wow/flutter 的時間抖動)
        env_c, _ = _block_xcorr(mono, sr, 80, 400, 2.0, envelope=True)
        L2, pk2, z2, iso2 = _echo_peak(env_c, sr, 4, 25, 1.8)
        if pk2 > 0.3 and z2 > 8 and iso2 > 1.8:
            detected, smeared = True, True
            L, pk, z, iso = L2, pk2, z2, iso2
            lo_c = env_c
    out = {"detected": bool(detected), "peak_corr": round(pk, 4), "z": round(float(z), 1),
           "isolation": round(float(iso), 2)}
    if not detected:
        out["confidence"] = round(clip01(1 - pk / 0.05 * 0.5), 2)
        return out

    half = L // 2
    if half > int(0.06 * sr) and _peak_val(lo_c, half, sr, 1.0) > 0.6 * pk:
        L = half
        pk = _peak_val(lo_c, L, sr, 1.0)

    thr = 0.5 * pk
    left = L
    while left > 0 and lo_c[left] > thr:
        left -= 1
    right = L
    while right < len(lo_c) - 1 and lo_c[right] > thr:
        right += 1
    width_ms = (right - left) / sr * 1000

    tol = max(1.0, width_ms)
    c1 = _peak_val(lo_c, L, sr, tol)
    c2 = _peak_val(lo_c, 2 * L, sr, tol * 2) if 2 * L < len(lo_c) else 0.0
    c3 = _peak_val(lo_c, 3 * L, sr, tol * 3) if 3 * L < len(lo_c) else 0.0
    a, fb = _fit_echo(c1, max(c2, 0), max(c3, 0))
    hi_c, _ = _block_xcorr(mono, sr, 2000, 6000, L / sr + 0.05)
    hi_ratio = _peak_val(hi_c, L, sr, tol) / (c1 + EPS)

    pingpong = False
    if ctx["stereo"]:
        d = ctx["data"]
        lag_s = L / sr + 0.05
        pos, neg = _block_xcorr(d[:, 0], sr, 150, 1500, lag_s, y=d[:, 1])
        auto_l, _ = _block_xcorr(d[:, 0], sr, 150, 1500, lag_s)
        xpk = max(_peak_val(pos, L, sr, tol), _peak_val(neg, L - 1, sr, tol))
        pingpong = xpk > 1.3 * _peak_val(auto_l, L, sr, tol)

    if pingpong:
        kind = "pingpong"
    elif smeared:
        kind = "tape" if hi_ratio < 0.6 else "modulated"
    elif hi_ratio < 0.6:
        kind = "tape" if width_ms > 1.5 else "analog"
    else:
        kind = "modulated" if width_ms > 1.5 else "digital"

    rep = 1
    if fb > 0.01 and a > 1e-3:
        rep = int(np.clip(np.ceil(np.log(0.05 / a) / np.log(fb)) + 1, 1, 30)) if a > 0.05 else 1
    out.update({
        "time_ms": round(L / sr * 1000, 1),
        "mix_ratio": round(float(a), 3),
        "mix_db": round(float(20 * np.log10(a + EPS)), 1),
        "feedback": round(float(fb), 3),
        "repeats_audible": rep,
        "hi_freq_ratio": round(float(hi_ratio), 3),
        "peak_width_ms": round(width_ms, 2),
        "kind": kind,
        "confidence": round(clip01(0.4 + z / 50 + (iso - 1.6) / 6), 2),
    })
    return out


# ---------------------------------------------------------------- Reverb
def analyze_reverb(ctx, delay):
    lev, fr, floor = ctx["lev"], ctx["fr"], ctx["floor"]
    ons = set(int(o) for o in ctx["onsets"])
    n = len(lev)
    # 有延遲時，取「回音與回音之間」的下包絡，避免把延遲的重複音當成殘響
    has_dly = bool(delay.get("detected"))
    env = lev
    if has_dly:
        w = max(3, int(delay["time_ms"] / 1000 * fr * 1.1))
        env = minimum_filter1d(lev, w)
    new_note_db = 10.0 if has_dly else 6.0  # 回音造成的回升約 6~8 dB，新彈的音通常 >10 dB
    tails = []
    i = 3
    while i < n - 10:
        if lev[i] < floor + 25 or lev[i] < lev[max(i - 3, 0): i + 1].max() - 1:
            i += 1
            continue
        drop_end = None
        for kk in range(2, int(0.08 * fr) + 1):
            if i + kk >= n:
                break
            if lev[i] - lev[i + kk] >= 4.0 and (i + kk) not in ons:
                drop_end = i + kk
                break
        if drop_end is None:
            i += 1
            continue
        j = drop_end
        while j + 1 < n and lev[j + 1] < lev[j] - 150.0 / fr:
            j += 1
        # 尾音一直延續到「真正的新音符」(音量明顯回升) 或接近底噪；
        # 延遲的回音也會被當成 onset，所以只看音量是否回升超過 6 dB
        e, run_min = j, lev[j]
        while e + 1 < n and lev[e + 1] > floor + 5:
            run_min = min(run_min, lev[e + 1])
            ahead = lev[min(e + 4, n - 1)]
            if (e + 1) in ons and ahead - run_min > new_note_db:
                break
            if lev[e + 1] - run_min > new_note_db:
                break
            e += 1
        dur = (e - j) / fr
        if dur < 0.05 and lev[j] > floor + 15:
            i = e + 1  # 只是音符間的小起伏
            continue
        rec = {"drop_db": float(lev[j] - lev[i]), "tail_s": float(dur)}
        seg = env[j: e + 1]
        # 真正的殘響尾音只會一路衰減；若又明顯回升 (Tremolo、拍頻、繼續演奏) 就不算
        rises = seg - np.minimum.accumulate(seg) if len(seg) else np.zeros(1)
        monotone = bool(rises.max() < 3.0)
        if dur >= 0.15 and not monotone and not has_dly:
            i = e + 1
            continue
        if dur >= 0.15:
            seg = env[j: e + 1][: int(1.0 * fr) + 1]  # 只用前 1 秒 (Early Decay)  # 只用前 1 秒 (Early Decay)，減少延遲回授的影響
            ok = seg > floor + 6
            if ok.sum() >= 0.12 * fr and seg[0] > floor + 10:
                t = np.arange(len(seg))[ok] / fr
                slope = np.polyfit(t, seg[ok], 1)[0]
                if slope < -1:
                    rec["rt60"] = float(min(-60.0 / slope, 12.0))
                    rec["wet_db"] = float(lev[j] - lev[i])
        tails.append(rec)
        i = e + 1

    measured = [t for t in tails if "rt60" in t]
    out = {"num_stops": len(tails), "num_tails": len(measured)}
    if not tails:
        out.update({"detected": None, "confidence": 0.0,
                    "note": "演奏中沒有明顯的停頓/切音，無法可靠量測殘響；建議提供有停頓或結尾餘音的片段"})
        return out
    frac = len(measured) / len(tails)
    if frac < 0.3:
        out.update({"detected": False, "confidence": round(0.4 + 0.5 * min(1, len(tails) / 5), 2)})
        return out
    rt = float(np.median([t["rt60"] for t in measured]))
    wet = float(np.median([t["wet_db"] for t in measured]))
    if has_dly:
        # 延遲的回音會把尾音「撐住」，殘響長度無法和回授分開，只保留「有殘響」與保守的長度
        rt = min(max(rt / 4.0, 0.8), 3.0)
    out.update({
        "detected": bool(rt > 0.2),
        "rt60_uncertain": has_dly,
        "rt60_s": round(rt, 2),
        "wet_db": round(wet, 1),
        "confidence": 0.3 if has_dly else round(0.35 + 0.6 * min(1.0, len(measured) / 4) * frac, 2),
    })
    return out


# ---------------------------------------------------------------- Wah / Phaser / Flanger
def _shape_matrix(P, f, nb=20, lo=250, hi=6000):
    edges = np.geomspace(lo, hi, nb + 1)
    tot = P.sum(0) + EPS
    B = np.stack([P[(f >= edges[i]) & (f < edges[i + 1])].sum(0) for i in range(nb)], axis=1)
    return db(B + 1e-4 * tot[:, None]) - db(tot)[:, None]


def analyze_spectral_motion(ctx):
    """在「同一個音持續中」觀察頻譜形狀的變化：
    週期性 → Phaser / Flanger；不規則的大幅掃動 → 哇音踏板；隨音量 → Auto Wah。"""
    P, f, fr, segs = ctx["P"], ctx["f"], ctx["fr"], ctx["segments"]
    segs = [s for s in segs if s[1] - s[0] >= 0.5 * fr]
    no = {"detected": False}
    if not segs:
        return {"wah": dict(no, confidence=0.0), "sweep": dict(no)}
    B = _shape_matrix(P, f)
    R = [signal.detrend(B[a:b], axis=0) for a, b in segs]
    Rc = np.concatenate(R)
    amount = float(np.sqrt(np.mean(Rc ** 2)))
    U, sv, Vt = np.linalg.svd(Rc - Rc.mean(0), full_matrices=False)
    load = Vt[0]
    sign_changes = int(np.sum(np.diff(np.sign(load)) != 0))
    pc = Rc @ load
    sf_, sprom = _lfo_peak(pc, fr, 0.1, 8, 10)
    # 每段的 PC 週期一致性
    lfo_ok = bool(sf_ and sprom > 8)

    # 共振峰追蹤 (1/3 八度平滑)，給哇音判斷
    logf = np.log2(np.maximum(f, 1))
    grid = np.arange(np.log2(300), np.log2(3000), 1 / 24)
    spans, corr_env, rough = [], [], []
    lev = ctx["lev"]
    for a, b in segs:
        S = db(P[:, a:b])
        Sg = np.stack([np.interp(grid, logf, S[:, t]) for t in range(S.shape[1])], axis=1)
        Sg = uniform_filter1d(Sg, 8, axis=0)
        resid = Sg - Sg.mean(axis=1, keepdims=True)
        fpk = median_filter(grid[np.argmax(resid, axis=0)], size=5)
        spans.append(float(np.percentile(fpk, 90) - np.percentile(fpk, 10)))
        rough.append(float(np.mean(np.abs(np.diff(fpk)) > 0.25)))  # 共振峰「跳動」的比例
        if np.std(fpk) > 0 and np.std(lev[a:b]) > 0:
            corr_env.append(float(np.corrcoef(fpk, lev[a:b])[0, 1]))
    span = float(np.median(spans))
    jump = float(np.median(rough))
    cenv = float(np.median(corr_env)) if corr_env else 0.0

    wah = {"detected": False, "shape_motion_db": round(amount, 2), "peak_span_oct": round(span, 2),
           "peak_jumpiness": round(jump, 3), "confidence": round(clip01(1 - amount / 3.0 * 0.5), 2)}
    sweep = {"detected": False, "rate_hz": round(sf_ or 0, 3), "amount_db": round(amount, 2),
             "prominence": round(sprom, 1), "comb_sign_changes": sign_changes}
    # 哇音：共振峰在持續音中「平滑地」大範圍移動 (和弦音的諧波峰值則是跳來跳去)
    smooth_sweep = span > 0.7 and jump < 0.06
    if amount > 3.0 and lfo_ok:
        sweep.update({"detected": True, "kind": "flanger" if sign_changes >= 6 else "phaser"})
    elif amount > 1.4 and smooth_sweep:
        wah.update({"detected": True, "kind": "auto" if cenv > 0.5 else "pedal",
                    "center_hz": round(float(2 ** np.median(grid)), 0),
                    "sweep_octaves": round(span, 2), "envelope_corr": round(cenv, 2),
                    "confidence": round(clip01(0.4 + (amount - 1.4) / 3), 2)})
    # 固定哇 (半踩)：長時間頻譜有明顯的窄共振峰
    if not wah["detected"]:
        s = db(P[:, ctx["active"]].mean(axis=1))
        sg = np.interp(grid, logf, s)
        fine = uniform_filter1d(sg, 6)
        coarse = uniform_filter1d(sg, 48)
        bump = fine - coarse
        bi = int(np.argmax(bump))
        if bump[bi] > 12 and 400 < 2 ** grid[bi] < 2500:
            wah.update({"detected": True, "kind": "fixed", "center_hz": round(float(2 ** grid[bi]), 0),
                        "resonance_db": round(float(bump[bi]), 1), "confidence": 0.5})
    return {"wah": wah, "sweep": sweep}


# ---------------------------------------------------------------- Tremolo
def _lfo_peak(x, fr, fmin, fmax, seg_s):
    nper = int(min(len(x), seg_s * fr))
    if nper < fr * 1.5:
        return None, 0.0
    fq, pxx = signal.welch(x, fs=fr, nperseg=nper, noverlap=nper // 2, detrend="linear")
    m = (fq >= fmin) & (fq <= fmax)
    if m.sum() < 3:
        return None, 0.0
    i = int(np.argmax(pxx[m]))
    if i == 0 or i == m.sum() - 1:  # 落在邊界通常只是趨勢
        return float(fq[m][i]), 0.0
    prom = float(pxx[m][i] / (np.median(pxx[m]) + EPS))
    return float(fq[m][i]), prom


def analyze_tremolo(ctx):
    lev, fr, segs = ctx["lev"], ctx["fr"], ctx["segments"]
    segs = [s for s in segs if s[1] - s[0] >= 0.4 * fr]
    if not segs:
        return {"detected": False}
    sos = signal.butter(2, 1.5, btype="high", fs=fr, output="sos")
    parts = []
    for a, b in segs:
        x = signal.detrend(lev[a:b])
        parts.append(x)
    x = np.concatenate(parts)
    xh = signal.sosfiltfilt(sos, x) if len(x) > 30 else x
    tf, prom = _lfo_peak(xh, fr, 2.0, 15, 4)
    if not tf or prom < 6:
        return {"detected": False, "rate_hz": round(tf or 0, 2), "prominence": round(prom, 1)}
    # 驗證：每一段持續音在該週期的自相關都要是正的
    per = int(round(fr / tf))
    acs = []
    for p in parts:
        if len(p) > 2 * per:
            p = p - p.mean()
            acs.append(float(np.dot(p[:-per], p[per:]) / (np.dot(p, p) + EPS) * len(p) / (len(p) - per)))
    acm = float(np.median(acs)) if acs else 0.0
    lo, hi = tf * 0.75, min(tf * 1.25, fr / 2 * 0.9)
    bp = signal.sosfiltfilt(signal.butter(2, [lo, hi], btype="band", fs=fr, output="sos"), x)
    depth = float(2 * np.sqrt(2) * bp.std())
    det = bool(acm > 0.3 and depth > 2.0)
    return {"detected": det, "rate_hz": round(tf, 2), "depth_db_pp": round(depth, 1),
            "prominence": round(prom, 1), "period_autocorr": round(acm, 2)}


# ---------------------------------------------------------------- Chorus / Vibrato
def analyze_pitch_mod(ctx):
    P, Z, f, fr, sr = ctx["P"], ctx["Z"], ctx["f"], ctx["fr"], ctx["sr"]
    band = np.where((f >= 150) & (f <= 1500))[0]
    depths, rates = [], []
    for a, b in ctx["segments"]:
        if b - a < 0.35 * fr:
            continue
        k0 = band[np.argmax(P[band, a:b].mean(axis=1))]
        ks = np.clip(np.arange(k0 - 2, k0 + 3), 1, len(f) - 2)
        fi = []
        for t in range(a + 1, b):
            kk = ks[np.argmax(P[ks, t])]
            dphi = np.angle(Z[kk, t]) - np.angle(Z[kk, t - 1]) - 2 * np.pi * kk * HOP / NPER
            dphi = (dphi + np.pi) % (2 * np.pi) - np.pi
            fi.append((kk + dphi * NPER / (2 * np.pi * HOP)) * sr / NPER)
        fi = np.array(fi)
        if len(fi) < 0.3 * fr or np.any(fi <= 0):
            continue
        c = signal.detrend(1200 * np.log2(fi / np.median(fi)))
        if np.abs(c).max() > 150:
            continue
        depths.append(2 * np.sqrt(2) * c.std())
        # 速率只從夠長的持續音估計 (至少涵蓋約 2 個 LFO 週期)
        if len(c) >= 1.2 * fr:
            spec = np.abs(np.fft.rfft(c * np.hanning(len(c)), 2048))
            fq = np.fft.rfftfreq(2048, 1 / fr)
            m = (fq >= 1.6 / (len(c) / fr)) & (fq <= 10)
            if m.any():
                rates.append(fq[m][np.argmax(spec[m])])
    out = {"segments": len(depths)}
    if len(depths) < 2:
        out.update({"vibrato": False, "chorus": False})
        return out
    d_med = float(np.median(depths))
    # 深度要「每個音都差不多」才算效果器 (手指揉弦通常只在部分音)
    steady = float(np.mean(np.abs(np.array(depths) - d_med) < 0.6 * d_med + 2))
    r_med = float(np.median(rates)) if rates else None
    out.update({"depth_cents_pp": round(d_med, 1), "rate_hz": None if r_med is None else round(r_med, 2),
                "depth_consistency": round(steady, 2),
                "vibrato": bool(d_med > 30 and steady > 0.6 and len(depths) >= 4),
                "chorus": bool(6 < d_med <= 30 and steady > 0.6 and len(depths) >= 4)})
    return out


def analyze_width(ctx):
    if not ctx["stereo"]:
        return {"stereo": False, "width": 0.0}
    d = ctx["data"]
    L, R = d[:, 0], d[:, 1]
    corr = float(np.corrcoef(L, R)[0, 1])
    side = float(np.std(L - R) / (np.std(L + R) + EPS))
    return {"stereo": True, "lr_correlation": round(corr, 3), "side_mid_ratio": round(side, 3),
            "width": round(clip01(1 - corr), 3)}


# ---------------------------------------------------------------- 比對模式
def compare(target, mine):
    """target / mine 皆為 analyze() 結果。回傳把 mine 調向 target 的差異。"""
    diff = {}
    diff["eq6_db"] = {b: round(target["tone"]["eq6_rel_db"][b] - mine["tone"]["eq6_rel_db"][b], 1)
                      for b in EQ6_BANDS}
    # 比對時只用「不受 EQ 影響」的破音指標 (峰值因數、平坦度)；高頻比例會因為 EQ/吉他不同而變
    def core(g):
        return 0.6 * lin_map(g["crest_db"], 10.0, 5.0) + 0.4 * lin_map(g["flatness_db"], -30.0, -18.0)
    diff["gain_score"] = round(core(target["gain"]) - core(mine["gain"]), 3)
    diff["compression"] = round(target["dynamics"]["compression_score"] - mine["dynamics"]["compression_score"], 3)
    tr, mr = target["reverb"], mine["reverb"]
    if tr.get("rt60_s") and mr.get("rt60_s") and not (tr.get("rt60_uncertain") or mr.get("rt60_uncertain")):
        diff["rt60_s"] = round(tr["rt60_s"] - mr["rt60_s"], 2)
        diff["reverb_wet_db"] = round(tr["wet_db"] - mr["wet_db"], 1)
    td, md = target["delay"], mine["delay"]
    if td.get("detected") and md.get("detected"):
        diff["delay_time_ms"] = round(td["time_ms"] - md["time_ms"], 1)
        diff["delay_mix_db"] = round(td["mix_db"] - md["mix_db"], 1)
        diff["delay_feedback"] = round(td["feedback"] - md["feedback"], 3)
    diff["delay_presence"] = [bool(td.get("detected")), bool(md.get("detected"))]
    diff["reverb_presence"] = [bool(tr.get("detected")), bool(mr.get("detected"))]
    return diff
