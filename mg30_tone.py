"""NUX MG-30 音色分析工具

用法：
    python mg30_tone.py 目標音檔.wav
    python mg30_tone.py 目標音檔.mp3 --compare 我用MG30錄的.wav
    python mg30_tone.py 目標音檔.wav --start 30 --length 20     (只分析 0:30 開始的 20 秒)

輸出：同資料夾下的 <檔名>_mg30.md (設定報告) 與 <檔名>_mg30.json
"""
import argparse
import json
import os
import sys
import tempfile

import numpy as np
import soundfile as sf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import features  # noqa: E402
import mg30_db as db  # noqa: E402
import recommend  # noqa: E402
import calibrate  # noqa: E402


def _cut(path, start, length):
    if not start and not length:
        return path
    data, sr = features.read_any(path)
    s = int((start or 0) * sr)
    data = data[s: s + int(length * sr)] if length else data[s:]
    fd, tmp = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    sf.write(tmp, data, sr)
    return tmp


def _conf(c):
    if c is None:
        return "—"
    return "高" if c >= 0.7 else ("中" if c >= 0.45 else "低")


def render_blocks(L, preset):
    r = preset["routing"]
    for b in db.DEFAULT_CHAIN:
        if b not in preset["blocks"]:
            continue
        blk = preset["blocks"][b]
        mode = " (並聯)" if b in r["parallel"] else ""
        L.append(f"### {db.BLOCK_NAMES[b]}{mode} — **ON**\n")
        L.append(f"- 型號：**{blk['model']}**  (原型：{blk['based_on']})")
        if blk.get("alternatives"):
            L.append(f"- 備選型號：{'、'.join(blk['alternatives'])}")
        L.append(f"- 判斷依據：{blk['why']}\n")
        L.append("| 參數 | 設定值 |")
        L.append("|---|---|")
        for p, v in blk["params"].items():
            L.append(f"| {p} | {v} |")
        L.append("")


def render_calibration(L, mine_name, tips, changes, pre, new_preset):
    L.append(f"## 校正：與「{mine_name}」比對\n")
    L.append("### 差異摘要\n")
    for tip in tips:
        L.append(f"- {tip}")
    L.append("")
    if changes:
        L.append("### 要改的旋鈕 (已套用 80%，避免一次調過頭)\n")
        L.append("| Block | 參數 | 原本 | → 改成 | 原因 |")
        L.append("|---|---|---|---|---|")
        for c in changes:
            L.append(f"| {c['block']} | {c['param']} | {c['old']} | **{c['new']}** | {c['why']} |")
        L.append("")
    if any(abs(v) >= 1.5 for v in pre.values()):
        L.append("### 如果每一段比對都偏同一個方向 → 是吉他造成的\n")
        L.append("這時候不要每個 Patch 各自修，改在 **GLOBAL SETTING → PRE EQ** 補償吉他，所有 Patch 一次生效：\n")
        L.append("| PRE EQ | 建議 |")
        L.append("|---|---|")
        for kk, v in pre.items():
            L.append(f"| {kk} | {v:+.1f} dB |")
        L.append("\n用了 PRE EQ 之後，把上表中 Patch EQ 的修正改回原本的值，再重新比對一次。"
                 "注意 PRE EQ 在音箱之前：在高增益音箱前減低頻會讓破音更緊、加高頻會讓破音更刺，效果比 Patch EQ 更明顯。\n")
    L.append("### 校正後的完整設定\n")
    render_blocks(L, new_preset)


def render_markdown(F, preset, compare_tips=None, mine_name=None, extra=None):
    L = []
    name = os.path.basename(F["file"])
    L.append(f"# NUX MG-30 音色建議：{name}\n")
    L.append(f"- 長度 {F['duration_s']} 秒、{'立體聲' if F['stereo'] else '單聲道'}、{F['sample_rate']} Hz")
    if preset["bpm"]:
        L.append(f"- 推估速度：{preset['bpm']} BPM (信心 {_conf(F['tempo']['confidence'])})")
    L.append("")

    # 訊號鏈
    r = preset["routing"]
    L.append("## 1. 訊號鏈 (由左到右)\n")
    serial = [b for b in r["order"] if b not in r["parallel"]]
    if r["parallel"]:
        par = " ∥ ".join(r["parallel"])
        L.append("```")
        L.append("吉他 → " + " → ".join(serial) + f" → [ {par} ] (並聯) → 輸出")
        L.append("```")
    else:
        L.append("```")
        L.append("吉他 → " + " → ".join(r["order"]) + " → 輸出   (全部串聯)")
        L.append("```")
    L.append(r["explain"])
    L.append("")
    L.append(f"> {r['howto']}")
    L.append("")
    off = [b for b in db.DEFAULT_CHAIN if b not in preset["blocks"]]
    if off:
        L.append(f"**關閉 (OFF) 的 block：** {', '.join(off)}\n")

    # 各 block
    L.append("## 2. 各 Block 設定\n")
    render_blocks(L, preset)

    # 偵測摘要
    L.append("## 3. 分析摘要 (偵測到了什麼)\n")
    g, d, rv, w, m = F["gain"], F["delay"], F["reverb"], F["wah"], F["modulation"]
    L.append("| 項目 | 結果 | 信心 |")
    L.append("|---|---|---|")
    L.append(f"| 破音程度 | {recommend._cls_zh(g['class'])} (分數 {g['score']:.2f}；峰值因數 {g['crest_db']} dB、頻譜平坦度 {g['flatness_db']} dB) | {_conf(g['confidence'])} |")
    t = F["tone"]
    L.append(f"| 頻率響應 | 低頻 {t['bass_rel_db']:+.1f} / 中高 {t['upper_mid_rel_db']:+.1f} / 高頻 {t['treble_rel_db']:+.1f} / 空氣感 {t['presence_rel_db']:+.1f} dB (相對中頻) | 中 |")
    L.append(f"| 壓縮 | 分數 {F['dynamics']['compression_score']:.2f}，動態範圍 {F['dynamics']['dynamic_range_db']} dB | 中 |")
    if d.get("detected"):
        L.append(f"| 延遲 | **有**：{d['time_ms']:.0f} ms、{d['mix_db']:.1f} dB、回授 {d['feedback']:.2f}、類型 {d['kind']} | {_conf(d['confidence'])} |")
    else:
        L.append(f"| 延遲 | 未偵測到 | {_conf(d.get('confidence'))} |")
    if rv.get("detected") and rv.get("rt60_uncertain"):
        L.append("| 殘響 | **可能有** (被延遲回音遮住，長度無法確定) | 低 |")
    elif rv.get("detected"):
        L.append(f"| 殘響 | **有**：RT60 ≈ {rv['rt60_s']} 秒、位準 {rv['wet_db']} dB (量測 {rv['num_tails']} 段尾音) | {_conf(rv['confidence'])} |")
    elif rv.get("detected") is None:
        L.append("| 殘響 | 無法量測 (沒有停頓) | 低 |")
    else:
        L.append(f"| 殘響 | 很少或沒有 | {_conf(rv.get('confidence'))} |")
    L.append(f"| 哇音 | {'**有** (' + w['kind'] + ')' if w.get('detected') else '未偵測到'} | {_conf(w.get('confidence'))} |")
    tr, sw, pt = m.get("tremolo", {}), m.get("sweep", {}), m.get("pitch", {})
    L.append(f"| Tremolo | {'**有** ' + str(tr['rate_hz']) + ' Hz' if tr.get('detected') else '未偵測到'} | — |")
    L.append(f"| Phaser/Flanger | {'**有** ' + sw['kind'] + ' ' + str(sw['rate_hz']) + ' Hz' if sw.get('detected') else '未偵測到'} | — |")
    pm = "未偵測到"
    rate = f"{pt['rate_hz']} Hz / " if pt.get("rate_hz") else ""
    if pt.get("vibrato"):
        pm = f"**Vibrato** {rate}{pt['depth_cents_pp']} cents"
    elif pt.get("chorus"):
        pm = f"**Chorus** {rate}{pt['depth_cents_pp']} cents"
    L.append(f"| Chorus/Vibrato | {pm} | — |")
    if F["stereo"]:
        L.append(f"| 立體聲寬度 | {F['stereo_width']['width']:.2f} (0 = 單聲道) | — |")
    L.append("")

    if preset["notes"]:
        L.append("## 4. 注意事項\n")
        for n in preset["notes"]:
            L.append(f"- {n}")
        L.append("")

    if extra:
        L.extend(extra)

    L.append("## 微調建議\n")
    L.append("- 標示「≈」的數值是由 Hz / 秒換算的近似旋鈕位置，請以機器畫面顯示的數值與耳朵為準。")
    L.append("- 先調 AMP 的 GAIN 與 EQ，再調空間系 (DLY / RVB)；最後用 Patch LEVEL 平衡音量。")
    L.append("- 最準確的流程：用 MG-30 照此設定錄一段相同樂句 → 執行 `--compare` 比對 → 依建議修正，重複 1~2 次。")
    L.append(f"- {db.FIRMWARE_NOTES}")
    L.append("- 分析最準的素材是「單獨的吉他音軌」。若是完整混音 (含鼓、貝斯、人聲)，EQ、破音與殘響的估計會受影響。")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser(description="分析吉他音檔並產生 NUX MG-30 設定建議")
    ap.add_argument("audio", help="目標音檔 (wav / flac / mp3 / ogg)")
    ap.add_argument("--compare", help="你用 MG-30 錄的音檔，用來和目標比對並給出修正建議")
    ap.add_argument("--start", type=float, default=0, help="從第幾秒開始分析")
    ap.add_argument("--length", type=float, default=0, help="分析幾秒 (預設最多 90 秒)")
    ap.add_argument("--compare-start", type=float, default=None, help="你的錄音從第幾秒開始 (預設同 --start)")
    ap.add_argument("--compare-length", type=float, default=None, help="你的錄音分析幾秒 (預設同 --length)")
    ap.add_argument("--preset", help="你實際使用的設定 (上一次輸出的 .json)；校正會以它為基準")
    ap.add_argument("--guitar", choices=sorted(calibrate.GUITARS), help="你的吉他，用來給拾音器/旋鈕建議")
    ap.add_argument("--out", help="輸出檔名前綴 (預設與音檔同名)")
    a = ap.parse_args(argv)

    src = _cut(a.audio, a.start, a.length)
    print(f"分析中：{a.audio} ...")
    F = features.analyze(src)
    F["file"] = a.audio
    preset = recommend.build_preset(F)

    if a.preset:
        with open(a.preset, encoding="utf-8") as fh:
            saved = json.load(fh)
        preset = saved.get("calibrated_preset") or saved["preset"]
        print(f"使用你的設定作為基準：{a.preset}")

    extra, tips, calibrated = [], None, None
    if a.guitar:
        extra.append(f"## 吉他設定：{calibrate.GUITARS[a.guitar]['name']}\n")
        extra.append(f"- {calibrate.GUITARS[a.guitar]['pickups']}")
        extra.extend(f"- {t}" for t in calibrate.guitar_advice(F, preset, a.guitar))
        extra.append("")
    if a.compare:
        print(f"比對中：{a.compare} ...")
        cs = a.start if a.compare_start is None else a.compare_start
        cl = a.length if a.compare_length is None else a.compare_length
        mine = features.analyze(_cut(a.compare, cs, cl))
        diff = features.compare(F, mine)
        tips = recommend.compare_advice(diff)
        calibrated, changes, pre = calibrate.calibrate(preset, diff)
        render_calibration(extra, os.path.basename(a.compare), tips, changes, pre, calibrated)

    md = render_markdown(F, preset, tips, os.path.basename(a.compare) if a.compare else None, extra)
    base = a.out or os.path.splitext(a.audio)[0] + "_mg30"
    with open(base + ".md", "w", encoding="utf-8") as fh:
        fh.write(md)
    with open(base + ".json", "w", encoding="utf-8") as fh:
        json.dump({"features": F, "preset": preset, "compare_tips": tips, "calibrated_preset": calibrated}, fh, ensure_ascii=False, indent=2,
                  default=lambda o: o.item() if isinstance(o, np.generic) else str(o))
    print(md)
    print(f"已輸出：{base}.md / {base}.json")


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()
