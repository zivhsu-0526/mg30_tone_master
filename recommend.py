"""把分析出的特徵轉換成 NUX MG-30 的 Patch 設定。

旋鈕數值為 0-100。凡是牽涉「機器內部刻度」的換算 (例如 RATE 旋鈕 ↔ Hz、
DECAY 旋鈕 ↔ 秒) 官方沒有公開對照表，這裡用合理的近似值，並在報告中標註「≈」，
請以耳朵或「比對模式」(--compare) 微調。
"""
import math

import mg30_db as db

# 一般「吉他 → 音箱 → 箱體」錄音的平均頻譜 (相對 400~1200 Hz)，作為中性參考
REF = {"bass": 2.0, "treble": -9.0, "presence": -20.0, "scoop": -3.5}
REF_EQ6 = {100: -1.0, 220: 1.0, 500: 0.0, 1200: -1.5, 2600: -7.0, 6400: -20.0}

# 每台音箱在 GAIN 0 → 100 時大約涵蓋的「破音分數」範圍
AMP_GAIN_RANGE = {
    "Jazz Clean": (0.0, 0.30), "Twin Rvb": (0.0, 0.42), "Deluxe Rvb": (0.0, 0.50),
    "Super Rvb": (0.0, 0.50), "Vibro King": (0.05, 0.55), "Tweedy": (0.05, 0.60),
    "Bass Mate": (0.05, 0.62), "Class A 15": (0.08, 0.60), "Class A 30": (0.10, 0.65),
    "Match": (0.10, 0.65), "Budda": (0.15, 0.70), "Mr Z 38": (0.10, 0.62),
    "Plexi 45": (0.15, 0.65), "Brit Blues": (0.15, 0.68), "Plexi 100W": (0.18, 0.72),
    "1987 X 50W": (0.20, 0.72), "Hiwire": (0.10, 0.62), "Cali Crunch": (0.20, 0.75),
    "Brit 800": (0.30, 0.82), "Brit 2000": (0.35, 0.88), "Slo 100": (0.38, 0.92),
    "Fireman HBE": (0.38, 0.92), "Dual Rect": (0.45, 1.0), "Die VH4": (0.45, 1.0),
    "Uber": (0.48, 1.0),
}


def k(x):
    """夾到 0-100 的整數旋鈕值。"""
    return int(round(min(100, max(0, x))))


def kt(x):
    """音色類旋鈕：參考曲線只是粗估，夾在 15-85 避免極端值。"""
    return int(round(min(85, max(15, x))))


def rate_knob(hz, lo=0.1, hi=10.0):
    hz = min(max(hz, lo), hi)
    return k(100 * math.log(hz / lo) / math.log(hi / lo))


def subdivision(ms, bpm):
    if not bpm:
        return None
    beat = 60000.0 / bpm
    table = {"1/4": 1.0, "1/8D": 0.75, "1/8": 0.5, "1/4T": 2 / 3, "1/16": 0.25, "1/8T": 1 / 3, "1/32": 0.125}
    best = min(table.items(), key=lambda kv: abs(ms / beat - kv[1]) / kv[1])
    err = abs(ms / beat - best[1]) / best[1]
    return best[0] if err < 0.05 else None


# ---------------------------------------------------------------- 主函式
def build_preset(F):
    g, tone, dyn = F["gain"], F["tone"], F["dynamics"]
    bright = tone["treble_rel_db"] - REF["treble"]
    scoop = tone["mid_scoop_db"] - REF["scoop"]  # >0：中頻凹陷；<0：中頻突出
    warm = tone["low_mid_rel_db"]
    blocks = {}
    notes = []

    # ---------- 特殊：Fuzz 特徵 (極平坦頻譜 + 極低峰值因數)
    fuzz = g["flatness_db"] > -9.5 and g["crest_db"] < 6.0 and g["score"] > 0.8

    # ---------- AMP
    cls = g["class"]
    chorus_hint = F["modulation"].get("pitch", {}).get("chorus")
    if fuzz:
        amp, alts = "Plexi 45", ["Bass Mate", "Tweedy"]
    elif cls == "clean":
        if chorus_hint and bright > 2:
            amp, alts = "Jazz Clean", ["Twin Rvb"]
        elif bright >= 0:
            amp, alts = "Twin Rvb", ["Jazz Clean", "Super Rvb"]
        else:
            amp, alts = "Deluxe Rvb", ["Twin Rvb", "Vibro King"]
    elif cls == "edge_of_breakup":
        if bright > 3:
            amp, alts = "Class A 30", ["Match", "Class A 15"]
        elif warm > 2:
            amp, alts = "Tweedy", ["Bass Mate", "Deluxe Rvb"]
        else:
            amp, alts = "Deluxe Rvb", ["Bass Mate", "Mr Z 38"]
    elif cls == "crunch":
        if bright > 3:
            amp, alts = "Class A 30", ["Match", "Budda"]
        elif warm > 2:
            amp, alts = "Plexi 45", ["Brit Blues", "Bass Mate"]
        else:
            amp, alts = "Plexi 100W", ["1987 X 50W", "Brit 800"]
    elif cls == "high_gain":
        if scoop > 4:
            amp, alts = "Dual Rect", ["Uber", "Brit 2000"]
        elif bright > 2:
            amp, alts = "Brit 800", ["Brit 2000", "Fireman HBE"]
        else:
            amp, alts = "Slo 100", ["Fireman HBE", "Brit 2000"]
    else:
        if scoop > 3:
            amp, alts = "Dual Rect", ["Uber", "Die VH4"]
        else:
            amp, alts = "Die VH4", ["Uber", "Fireman HBE"]

    # ---------- EFX (前級)
    efx = None
    score_for_amp = g["score"]
    if fuzz:
        efx = ("Muff Fuzz", {"VOLUME": 55, "TONE": kt(50 + 4 * bright), "SUSTAIN": 70},
               "頻譜非常平坦且峰值因數極低，像 Fuzz 的特徵；也可試 Red Fuzz (Fuzz Face)")
        score_for_amp = 0.3
    elif cls in ("high_gain", "very_high_gain"):
        efx = ("T Scream", {"DRIVE": 5, "TONE": 60, "LEVEL": 80},
               "高增益常用手法：TS 當「緊縮推進」(Drive 低、Level 高) 讓低頻更緊、顆粒更清楚")
        score_for_amp = g["score"] - 0.05
    elif cls == "crunch" and scoop < -2:
        efx = ("T Scream", {"DRIVE": 40, "TONE": kt(50 + 3 * bright), "LEVEL": 60},
               "中頻明顯突出，像 Tube Screamer 推 Crunch 音箱")
        score_for_amp = g["score"] - 0.12
    elif cls == "edge_of_breakup" and dyn["compression_score"] > 0.6:
        efx = ("Blues Drv", {"LEVEL": 55, "TONE": kt(50 + 3 * bright), "GAIN": 25},
               "輕微推動，增加延音與顆粒感")
        score_for_amp = g["score"] - 0.08

    lo, hi = AMP_GAIN_RANGE[amp]
    amp_gain = k((score_for_amp - lo) / (hi - lo) * 100)
    amp_gain = max(amp_gain, 8)
    spec = db.AMPS[amp]
    vals = {}
    for p in spec["params"]:
        if p == "GAIN":
            vals[p] = amp_gain
        elif p == "MASTER":
            vals[p] = 50
        elif p == "BASS":
            vals[p] = kt(50 + 3.5 * (tone["bass_rel_db"] - REF["bass"]))
        elif p == "MIDDLE":
            vals[p] = kt(50 - 4.0 * scoop)
        elif p == "TREBLE":
            vals[p] = kt(50 + 3.5 * bright)
        elif p == "PRESENCE":
            vals[p] = kt(50 + 2.5 * (tone["presence_rel_db"] - REF["presence"]))
        elif p == "CUT":
            vals[p] = kt(50 - 3.0 * (tone["presence_rel_db"] - REF["presence"]))
        elif p == "TONE":
            vals[p] = kt(50 + 3.5 * bright)
        elif p == "BRIGHT":
            vals[p] = "ON" if bright > 4 else "OFF"
        elif p == "BIAS":
            vals[p] = 50
        elif p == "LEVEL":
            vals[p] = 50
    blocks["AMP"] = {"model": amp, "based_on": spec["based_on"], "params": vals,
                     "alternatives": alts, "why": f"破音程度判定為「{_cls_zh(cls)}」(分數 {g['score']:.2f})，"
                                                    f"高頻 {bright:+.1f} dB、中頻凹陷 {scoop:+.1f} dB (相對中性參考)"}

    if efx:
        name, p, why = efx
        blocks["EFX"] = {"model": name, "based_on": db.EFX[name]["based_on"], "params": p, "why": why}

    # ---------- IR
    ir = spec["ir"]
    if amp in ("Dual Rect", "Die VH4", "Uber", "Slo 100", "Fireman HBE") and bright < -1:
        ir = "1960"
    mic = "S57"
    if bright < -3:
        mic = "R121"
    elif bright > 5:
        mic = "C414"
    axis = "CENTER" if bright > 2 else ("EDGE" if bright < -2 else "MIDDLE")
    lo_cut = 120 if tone["bass_rel_db"] < -2 else (60 if tone["bass_rel_db"] > 6 else 80)
    pres = tone["presence_rel_db"]
    hi_cut = 6500 if pres < -30 else (9000 if pres < -24 else (12000 if pres < -16 else 18000))
    blocks["IR"] = {"model": ir, "based_on": db.IRS[ir],
                    "params": {"MIC": f"{mic} ({db.MICS[mic]})", "MIC AXIS": axis, "LEVEL": "0 dB",
                               "LO CUT": f"{lo_cut} Hz", "HI CUT": f"{hi_cut} Hz"},
                    "why": "依音箱搭配原廠箱體；麥克風位置依高頻量決定 (CENTER 較亮，EDGE 較暗)"}

    # ---------- CMP
    comp = dyn["compression_score"]
    wet_fx = bool(F["delay"].get("detected") or F["reverb"].get("detected"))
    # 延遲/殘響本身會把延音撐長，看起來像壓縮，所以有空間效果時門檻提高
    if comp > (0.8 if wet_fx else 0.55) and cls in ("clean", "edge_of_breakup"):
        if comp > 0.8:
            blocks["CMP"] = {"model": "Rose Comp", "based_on": db.CMPS["Rose Comp"]["based_on"],
                             "params": {"SUSTAIN": k(40 + comp * 40), "LEVEL": 55},
                             "why": f"動態非常扁平 (壓縮分數 {comp:.2f})，像 Ross/Dyna 類的強壓縮 (Funk/Country 常見)"}
        else:
            blocks["CMP"] = {"model": "K Comp", "based_on": db.CMPS["K Comp"]["based_on"],
                             "params": {"SUSTAIN": k(20 + comp * 50), "LEVEL": 55, "CLIPPING": 30},
                             "why": f"動態被壓縮 (壓縮分數 {comp:.2f})，用 Keeley C4 類的透明壓縮"}

    # ---------- WAH
    wah = F["wah"]
    eq_para = None
    if wah.get("detected"):
        if wah["kind"] == "pedal":
            blocks["WAH"] = {"model": "Cry BB", "based_on": db.WAHS["Cry BB"]["based_on"],
                             "params": {"PEDAL": "指定給 EXP 踏板 (內建踏板)"},
                             "why": f"共振峰在 {wah['center_hz']:.0f} Hz 附近大幅掃動 {wah['sweep_octaves']:.1f} 個八度"}
        elif wah["kind"] == "auto":
            if "EFX" in blocks:
                notes.append("偵測到自動哇 (Touch Wah)，但 EFX 已用於破音；MG-30 只有一個 EFX block，"
                             "可改用 WAH block 的 Cry BB 手動踩，或捨棄 EFX 破音改用音箱 GAIN。")
            else:
                blocks["EFX"] = {"model": "Touch Wah", "based_on": db.EFX["Touch Wah"]["based_on"],
                                 "params": {"SENSITIVITY": 60, "RANGE": 60, "MIX": 100},
                                 "why": "共振峰隨彈奏力度上下移動 (與音量相關)，像 Envelope Filter"}
        else:
            eq_para = wah["center_hz"]
            notes.append(f"偵測到固定位置的共振峰 (半踩哇 / cocked wah) 約 {wah['center_hz']:.0f} Hz。"
                         "已在 EQ 用 Para EQ 模擬；也可以開 Cry BB 把踏板停在半踩位置。")

    # ---------- EQ
    eq6 = tone["eq6_rel_db"]
    dev = {b: eq6[b] - REF_EQ6[b] for b in REF_EQ6}
    mean_dev = sum(dev.values()) / len(dev)
    eqv = {b: round(max(-6, min(6, 0.4 * (dev[b] - mean_dev))), 1) for b in dev}
    if eq_para:
        blocks["EQ"] = {"model": "Para", "based_on": db.EQS["Para"]["based_on"],
                        "params": {"BAND1 FREQ": f"{eq_para:.0f} Hz", "BAND1 GAIN": "+8 dB", "BAND1 Q": "高 (窄)",
                                   "BAND2 GAIN": "0 dB", "BAND3 GAIN": "0 dB"},
                        "why": "模擬固定哇的共振峰"}
    elif max(abs(v) for v in eqv.values()) >= 2.5:
        blocks["EQ"] = {"model": "6-Band", "based_on": db.EQS["6-Band"]["based_on"],
                        "params": {**{_hz(b): f"{v:+.1f} dB" for b, v in eqv.items()}, "LEVEL": "0 dB"},
                        "why": "音箱 EQ 旋鈕之外剩下的頻率差異 (粗估；建議用 --compare 精修)"}

    # ---------- GATE
    if cls in ("high_gain", "very_high_gain") or fuzz:
        sens = 55 if dyn["noise_floor_db"] > -60 else 45
        blocks["GATE"] = {"model": "Noise Gate", "based_on": db.GATE["Noise Gate"]["based_on"],
                          "params": {"SENSITIVITY": sens, "DECAY": 40},
                          "why": "高增益必開；若切音後聽得到底噪就提高 SENSITIVITY，若尾音被切斷就降低"}
    elif cls == "crunch":
        blocks["GATE"] = {"model": "Noise Gate", "based_on": db.GATE["Noise Gate"]["based_on"],
                          "params": {"SENSITIVITY": 30, "DECAY": 50},
                          "why": "Crunch 輕度降噪，避免影響延音"}

    # ---------- MOD (只有一個 MOD block，選最明顯的)
    mod = F["modulation"]
    bpm = F["tempo"].get("bpm") if F["tempo"].get("confidence", 0) > 0.2 else None
    mod_cands = []  # (優先順序, block)

    def rtxt(hz, lo, hi):
        return f"≈{rate_knob(hz, lo, hi)} ({hz:.2f} Hz)" if hz else "≈35 (速率無法可靠量測，請以耳朵調整)"

    t = mod.get("tremolo", {})
    if t.get("detected"):
        mod_cands.append((5, {
            "model": "Tremolo", "based_on": db.MODS["Tremolo"]["based_on"],
            "params": {"RATE": rtxt(t["rate_hz"], 0.5, 15), "DEPTH": k(t["depth_db_pp"] * 5)},
            "why": f"音量以 {t['rate_hz']:.2f} Hz 週期起伏，深度約 {t['depth_db_pp']:.1f} dB"}))
    pt = mod.get("pitch", {})
    width = F["stereo_width"].get("width", 0)
    if pt.get("vibrato"):
        mod_cands.append((4, {
            "model": "Vibrator", "based_on": db.MODS["Vibrator"]["based_on"],
            "params": {"RATE": rtxt(pt.get("rate_hz"), 0.1, 10), "DEPTH": k(pt["depth_cents_pp"] * 1.2)},
            "why": f"每個音的音高都規律擺動約 {pt['depth_cents_pp']:.0f} cents (全濕訊號 → Vibrato)"}))
    elif pt.get("chorus"):
        depth = k(30 + pt["depth_cents_pp"] * 2.5)
        if F["stereo"] and width > 0.15:
            m, p = "St. Chorus", {"INTENSITY": depth, "WIDTH": 70, "RATE": rtxt(pt.get("rate_hz"), 0.1, 10)}
        elif amp == "Jazz Clean":
            m, p = "CE-1", {"INTENSITY": 60, "DEPTH": depth, "RATE": rtxt(pt.get("rate_hz"), 0.1, 10)}
        else:
            m, p = "CE-2", {"RATE": rtxt(pt.get("rate_hz"), 0.1, 10), "DEPTH": depth}
        mod_cands.append((3, {
            "model": m, "based_on": db.MODS[m]["based_on"], "params": p,
            "why": f"每個音都有輕微的音高擺動 (約 {pt['depth_cents_pp']:.0f} cents)，且原音與調變音混合 → Chorus"
                   + ("；立體聲很寬，用立體聲 Chorus" if m == "St. Chorus" else "")}))
    s = mod.get("sweep", {})
    if s.get("detected"):
        if s["kind"] == "flanger":
            mod_cands.append((2, {
                "model": "Flanger", "based_on": db.MODS["Flanger"]["based_on"],
                "params": {"LEVEL": 60, "RATE": rtxt(s["rate_hz"], 0.05, 8),
                           "WIDTH": k(30 + s["amount_db"] * 10), "F.BACK": 50},
                "why": "頻譜出現多個週期性移動的梳狀凹口 → Flanger"}))
        else:
            vibe = 0.5 < s["rate_hz"] < 4 and cls in ("crunch", "edge_of_breakup") and s["amount_db"] > 4
            model = "U-Vibe" if vibe else "Phase 90"
            p = ({"SPEED": rtxt(s["rate_hz"], 0.05, 8), "VOLUME": 50,
                  "INTENSITY": k(30 + s["amount_db"] * 10), "CHORUS/VIBRATO": "CHORUS"}
                 if vibe else {"SPEED": rtxt(s["rate_hz"], 0.05, 8)})
            mod_cands.append((1, {
                "model": model, "based_on": db.MODS[model]["based_on"], "params": p,
                "why": f"同一個音持續時，頻譜形狀以約 {s['rate_hz']:.2f} Hz 週期性掃動 (Phaser 類)"}))
    if mod_cands:
        mod_cands.sort(key=lambda c: -c[0])
        blocks["MOD"] = mod_cands[0][1]
        if len(mod_cands) > 1:
            others = "、".join(c[1]["model"] for c in mod_cands[1:])
            notes.append(f"同時偵測到其他調變 ({others})，但 MG-30 一個 Patch 只有一個 MOD block；"
                         "可改用 Modulation Delay 補 Chorus 感，或用 S/R 外接效果器。")

    # ---------- DLY
    d = F["delay"]
    if d.get("detected"):
        ms = d["time_ms"]
        lvl = k(d["mix_ratio"] * 90)
        fbk = k(d["feedback"] * 100)
        kind = d["kind"]
        sub = subdivision(ms, bpm)
        tinfo = f"{ms:.0f} ms" + (f" (= {bpm} BPM 的 {sub})" if sub else "")
        if kind == "pingpong":
            model, p = "Pan Delay", {"TIME": tinfo, "REPEAT": fbk, "LEVEL": lvl}
            why = "回音在左右聲道交替出現 (Ping-Pong)"
        elif kind == "analog":
            model, p = "Analog", {"REPEAT (時間)": tinfo, "ECHO (音量)": lvl, "INTENSITY (回授)": fbk}
            why = f"回音高頻明顯衰減 (高頻保留比 {d['hi_freq_ratio']:.2f})，屬溫暖的類比延遲 (Tape Echo 也可試)"
            if ms > 300:
                why += f"；若 Analog 的時間調不到 {ms:.0f} ms，改用 Tape Echo 或 Digital 並把 TONE 調暗"
        elif kind == "tape":
            model, p = "Tape Echo", {"TIME": tinfo, "LEVEL": lvl, "REPEAT": fbk}
            why = "回音偏暗且時間有抖動 (wow/flutter)，像磁帶迴音"
        elif kind == "modulated":
            model, p = "Modulation", {"TIME": tinfo, "LEVEL": lvl, "MOD": 40, "REPEAT": fbk}
            why = "回音明亮但時間有輕微搖晃 → 調變延遲"
        else:
            model, p = "Digital", {"E.LEVEL": lvl, "FEEDBACK": fbk, "TIME": tinfo}
            why = "回音清晰、與原音幾乎一模一樣 → 數位延遲"
        if sub:
            p["SUB DIV"] = f"{sub} (按 TAP / 設定 BPM={bpm})"
        blocks["DLY"] = {"model": model, "based_on": db.DLYS[model]["based_on"], "params": p,
                         "why": why + f"；第一個回音約 {d['mix_db']:.1f} dB，回授 {d['feedback']:.2f}，"
                                      f"約可聽到 {d['repeats_audible']} 次重複"}

    # ---------- RVB
    r = F["reverb"]
    if r.get("detected"):
        rt, wet = r["rt60_s"], r["wet_db"]
        level = k(100 + wet * 2.5)
        if rt < 0.8:
            m, p = "Room", {"DECAY": k(rt / 2.0 * 100), "TONE": kt(50 + 2 * bright), "LEVEL": level}
        elif rt < 1.8:
            m, p = "Plate", {"DECAY": k((rt - 0.3) / 4.5 * 100), "LEVEL": level}
        else:
            m, p = "Hall", {"DECAY": k((rt - 0.8) / 6.0 * 100), "PRE DELAY": 20, "LIVELINESS": 50, "LEVEL": level}
        alt = []
        if amp in ("Deluxe Rvb", "Twin Rvb", "Super Rvb", "Vibro King") and 0.6 < rt < 2.5:
            alt = ["Spring (Fender 彈簧殘響質感)"]
        why = f"估計殘響時間 RT60 ≈ {rt:.2f} 秒，殘響位準約 {wet:.0f} dB (相對原音)"
        if r.get("rt60_uncertain"):
            p["LEVEL"] = min(p["LEVEL"], 30)
            why = ("切音後的尾音被延遲回音撐住，無法確定是否另外有殘響；先用小量殘響，"
                   "關掉 RVB 比較看看哪個比較像")
        blocks["RVB"] = {"model": m, "based_on": db.RVBS[m]["based_on"], "params": p, "alternatives": alt,
                         "why": why}
    elif r.get("detected") is None:
        notes.append("音檔中沒有明顯的停頓，無法可靠量測殘響。可先用 Room / Plate，LEVEL 30 左右試聽。")

    # ---------- 訊號鏈與串並聯
    chain = [b for b in db.DEFAULT_CHAIN if b in blocks]
    parallel = []
    if "DLY" in blocks and "RVB" in blocks:
        big_rvb = not r.get("rt60_uncertain") and (r.get("rt60_s", 0) > 1.5 or r.get("wet_db", -99) > -14)
        if big_rvb:
            parallel = ["DLY", "RVB"]
    routing = {
        "order": chain,
        "parallel": parallel,
        "explain": (
            "DLY 與 RVB 設為「並聯」：殘響較大，並聯能讓延遲的重複音保持清楚，不會被殘響糊成一團。"
            if parallel else
            "全部「串聯」：這是最接近一般踏板板的接法 (殘響會加在延遲的重複音上)。"
            + (" 若覺得回音被殘響糊掉，可以把 DLY 與 RVB 改成並聯試聽。" if "DLY" in blocks and "RVB" in blocks else "")
        ),
        "howto": db.ROUTING_HOWTO,
    }
    if bpm and F["tempo"]["confidence"] > 0.3:
        notes.append(f"推估歌曲速度約 {bpm} BPM，可以在 Patch 中設定 BPM / TAP，讓 DLY 與 MOD 同步。")

    return {"blocks": blocks, "routing": routing, "notes": notes, "bpm": bpm}


def _hz(b):
    return f"{b/1000:g} kHz" if b >= 1000 else f"{b} Hz"


def _cls_zh(c):
    return {"clean": "乾淨 Clean", "edge_of_breakup": "微破 Edge of breakup", "crunch": "Crunch",
            "high_gain": "高增益 High Gain", "very_high_gain": "極高增益 Metal"}[c]


def compare_advice(diff):
    """比對模式：把差異翻成具體的旋鈕建議。"""
    tips = []
    eq = diff["eq6_db"]
    eq_line = "、".join(f"{_hz(b)} {v:+.1f} dB" for b, v in eq.items() if abs(v) >= 1.0)
    if eq_line:
        tips.append(f"在 EQ block 選 6-Band，依序調整：{eq_line} (正值 = 目標比你的錄音多)")
    gs = diff["gain_score"]
    if abs(gs) > 0.1:
        tips.append(f"破音程度{'不足' if gs > 0 else '太多'}：AMP GAIN {'加' if gs > 0 else '減'}約 {k(abs(gs) * 150)}")
    cp = diff["compression"]
    if abs(cp) > 0.15:
        tips.append(f"動態{'需要更多壓縮' if cp > 0 else '壓縮太多'}：CMP SUSTAIN {'加' if cp > 0 else '減'}約 {k(abs(cp) * 60)}")
    tp, mp = diff["delay_presence"]
    if tp and not mp:
        tips.append("目標有延遲，但你的錄音沒有偵測到延遲 → 打開 DLY")
    elif mp and not tp:
        tips.append("你的錄音有延遲，但目標沒有 → 關閉 DLY 或大幅降低 LEVEL")
    if "delay_time_ms" in diff:
        if abs(diff["delay_time_ms"]) > 10:
            tips.append(f"延遲時間差 {diff['delay_time_ms']:+.0f} ms")
        if abs(diff["delay_mix_db"]) > 1.5:
            tips.append(f"延遲音量差 {diff['delay_mix_db']:+.1f} dB → LEVEL {'加' if diff['delay_mix_db'] > 0 else '減'}")
        if abs(diff["delay_feedback"]) > 0.08:
            tips.append(f"回授差 {diff['delay_feedback']:+.2f} → FEEDBACK/REPEAT {'加' if diff['delay_feedback'] > 0 else '減'}約 {k(abs(diff['delay_feedback']) * 100)}")
    tr, mr = diff["reverb_presence"]
    if tr and not mr:
        tips.append("目標有殘響，但你的錄音偵測不到 → 打開 RVB")
    if "rt60_s" in diff:
        if abs(diff["rt60_s"]) > 0.25:
            tips.append(f"殘響長度差 {diff['rt60_s']:+.2f} 秒 → DECAY {'加' if diff['rt60_s'] > 0 else '減'}")
        if abs(diff["reverb_wet_db"]) > 2:
            tips.append(f"殘響量差 {diff['reverb_wet_db']:+.1f} dB → LEVEL {'加' if diff['reverb_wet_db'] > 0 else '減'}")
    if not tips:
        tips.append("兩者已經非常接近 🎉")
    return tips
