"""對 test_audio/ 中的合成音檔跑分析，印出關鍵偵測結果。"""
import glob
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import features  # noqa: E402
import recommend  # noqa: E402

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

for path in sorted(glob.glob(os.path.join(os.path.dirname(os.path.abspath(__file__)), "test_audio", "*.wav"))):
    F = features.analyze(path)
    pr = recommend.build_preset(F)
    g, d, r, m = F["gain"], F["delay"], F["reverb"], F["modulation"]
    print("=" * 70)
    print(os.path.basename(path))
    print(f"  gain   {g['class']:<16} score={g['score']} crest={g['crest_db']} flat={g['flatness_db']} hf={g['hf_ratio_db']} drop={g['sustain_drop_db']}")
    print(f"  tempo  {F['tempo']}")
    print(f"  delay  " + (f"{d['time_ms']}ms mix={d['mix_ratio']} fb={d['feedback']} kind={d['kind']} hi={d['hi_freq_ratio']} w={d['peak_width_ms']} z={d['z']}"
                          if d.get("detected") else f"none (pk={d['peak_corr']} z={d['z']})"))
    print(f"  reverb {r}")
    print(f"  trem   {m['tremolo']}")
    print(f"  sweep  {m['sweep']}")
    print(f"  pitch  {m['pitch']}")
    print(f"  wah    {F['wah']}")
    print(f"  dyn    comp={F['dynamics']['compression_score']}  width={F['stereo_width']}")
    print("  -> " + " | ".join(f"{b}:{blk['model']}" for b, blk in pr["blocks"].items()), " parallel=", pr["routing"]["parallel"])
