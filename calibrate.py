"""校正：吉他建議 + 依「目標 vs 你的錄音」差異直接算出修正後的旋鈕數值。"""
import copy
import re

from recommend import REF, k, _hz

# ---------------------------------------------------------------- 吉他資料
GUITARS = {
    "azes40": {
        "name": "Ibanez AZES40",
        "pickups": "HSS：Bridge = Accord 雙線圈 (陶瓷磁鐵)，Middle / Neck = Essentials 單線圈；dyna-MIX9 + Alter Switch",
        "positions": {
            1: ("Neck 單線圈", "Neck + Middle 串聯 (變成雙線圈)"),
            2: ("Neck + Middle", "Neck + Bridge 外側線圈"),
            3: ("Middle 單線圈", "三顆全開 (Neck+Middle 串聯)"),
            4: ("Middle + Bridge 內側線圈", "Bridge 內側單線圈"),
            5: ("Bridge 雙線圈", "Bridge 雙線圈"),
        },
        "notes": ("Accord 是輸出中等、偏亮的陶瓷雙線圈；接高增益音箱時高頻容易刺 (fizz)，"
                  "低頻也比 Seymour Duncan / EMG 這類常見錄音用拾音器鬆。"),
    },
}


def guitar_advice(F, preset, guitar):
    g = GUITARS[guitar]
    cls = F["gain"]["class"]
    bright = F["tone"]["treble_rel_db"] - REF["treble"]
    pos = g["positions"]
    tips = []
    if cls in ("high_gain", "very_high_gain"):
        tips.append(f"拾音器：**第 5 段 ({pos[5][0]})**，Alter 不影響；Volume 10")
        tips.append("Tone 旋鈕 **7~8**：Accord 在高增益下高頻偏刺，先在吉他端收一點，比在 MG-30 砍高頻自然")
        tips.append("若低頻轟轟糊掉：IR 的 LO CUT 提高到 90~110 Hz，或 EFX 的 T Scream LEVEL 再加 5~10 (收緊低頻)")
    elif cls == "crunch":
        if bright > 3:
            tips.append(f"拾音器：**第 4 段，Alter OFF ({pos[4][0]})** — 半單線圈的亮脆顆粒，接近 Vox 類 Crunch")
            tips.append(f"若顆粒不夠：改 **第 5 段 ({pos[5][0]})**，AMP GAIN 減 5~10")
        else:
            tips.append(f"拾音器：**第 5 段 ({pos[5][0]})**；Volume 8~9 (稍微收音量可以讓破音更有層次)")
        tips.append("Tone 旋鈕 8~10")
    else:
        if bright > 0:
            tips.append(f"拾音器：**第 4 段，Alter OFF ({pos[4][0]})** 或 **第 2 段，Alter OFF ({pos[2][0]})** — 亮、帶鼻音的乾淨音")
        else:
            tips.append(f"拾音器：**第 1 段，Alter OFF ({pos[1][0]})** — 溫暖圓潤")
            tips.append(f"若底噪明顯或想更厚：**第 1 段，Alter ON ({pos[1][1]})**，抗雜訊的雙線圈聲音")
        tips.append("Tone 旋鈕 8~10、Volume 10")
    tips.append(g["notes"])
    return tips


# ---------------------------------------------------------------- 數值工具
def _db_val(v):
    m = re.search(r"[-+]?\d+(\.\d+)?", str(v))
    return float(m.group()) if m else 0.0


def _fmt_db(x):
    return f"{x:+.1f} dB"


DLY_KEYS = {  # model: (level 參數, feedback 參數, time 參數)
    "Digital": ("E.LEVEL", "FEEDBACK", "TIME"),
    "Analog": ("ECHO (音量)", "INTENSITY (回授)", "REPEAT (時間)"),
    "Tape Echo": ("LEVEL", "REPEAT", "TIME"),
    "Modulation": ("LEVEL", "REPEAT", "TIME"),
    "Pan Delay": ("LEVEL", "REPEAT", "TIME"),
}


# ---------------------------------------------------------------- 校正
def calibrate(preset, diff, strength=0.8):
    """把差異套用到 preset，回傳 (新 preset, 變更清單, Global PRE EQ 建議)。
    strength < 1：每次只修正 80%，避免一次調過頭 (反覆 2~3 次收斂)。"""
    new = copy.deepcopy(preset)
    B = new["blocks"]
    changes = []

    def chg(block, param, old, val, why):
        changes.append({"block": block, "param": param, "old": old, "new": val, "why": why})

    # --- EQ (AMP 之後的 6-Band，直接修正輸出頻響)
    eq = diff["eq6_db"]
    if any(abs(v) >= 1.0 for v in eq.values()):
        if "EQ" not in B or B["EQ"]["model"] != "6-Band":
            old_eq = B.get("EQ")
            B["EQ"] = {"model": "6-Band", "based_on": "Boss GE-6",
                       "params": {**{_hz(b): "+0.0 dB" for b in eq}, "LEVEL": "0 dB"},
                       "why": "校正用"}
            if old_eq:
                changes.append({"block": "EQ", "param": "MODEL", "old": old_eq["model"], "new": "6-Band",
                                "why": "校正需要 6 段等化器"})
        for b, d in eq.items():
            if abs(d) < 1.0:
                continue
            key = _hz(b)
            old = _db_val(B["EQ"]["params"].get(key, 0))
            val = max(-12.0, min(12.0, round((old + strength * d) * 2) / 2))
            if val != old:
                B["EQ"]["params"][key] = _fmt_db(val)
                chg("EQ", key, _fmt_db(old), _fmt_db(val), f"目標比你的錄音 {'多' if d > 0 else '少'} {abs(d):.1f} dB")

    # --- GAIN
    gs = diff["gain_score"]
    if abs(gs) > 0.1 and "AMP" in B:
        p = B["AMP"]["params"]
        old = p.get("GAIN", 50)
        val = k(old + strength * gs * 150)
        if val > 85 and "EFX" in B and "LEVEL" in B["EFX"]["params"]:
            # GAIN 已經很高：改推前級
            eo = B["EFX"]["params"]["LEVEL"]
            ev = k(eo + (val - 85))
            B["EFX"]["params"]["LEVEL"] = ev
            chg("EFX", "LEVEL", eo, ev, "AMP GAIN 已接近上限，改用前級推動")
            val = 85
        if val != old:
            p["GAIN"] = val
            chg("AMP", "GAIN", old, val, "破音" + ("不夠" if gs > 0 else "太多"))

    # --- 壓縮
    cp = diff["compression"]
    if abs(cp) > 0.15 and "CMP" in B:
        p = B["CMP"]["params"]
        key = "SUSTAIN" if "SUSTAIN" in p else ("RATIO" if "RATIO" in p else None)
        if key:
            old = p[key]
            val = k(old + strength * cp * 60)
            p[key] = val
            chg("CMP", key, old, val, "動態" + ("需要更扁平" if cp > 0 else "壓太多"))

    # --- Delay
    if "DLY" in B and "delay_mix_db" in diff:
        m = B["DLY"]["model"]
        lk, fk, tk = DLY_KEYS.get(m, ("LEVEL", "REPEAT", "TIME"))
        p = B["DLY"]["params"]
        if abs(diff["delay_mix_db"]) > 1.5 and isinstance(p.get(lk), int):
            old = p[lk]
            val = k(old * 10 ** (strength * diff["delay_mix_db"] / 20))
            p[lk] = val
            chg("DLY", lk, old, val, f"回音音量差 {diff['delay_mix_db']:+.1f} dB")
        if abs(diff["delay_feedback"]) > 0.08 and isinstance(p.get(fk), int):
            old = p[fk]
            val = k(old + strength * diff["delay_feedback"] * 100)
            p[fk] = val
            chg("DLY", fk, old, val, f"回授差 {diff['delay_feedback']:+.2f}")
        if abs(diff.get("delay_time_ms", 0)) > 10:
            changes.append({"block": "DLY", "param": tk, "old": p.get(tk), "new": "回到目標時間 (見 SUB DIV / BPM)",
                            "why": f"你的延遲時間差了 {diff['delay_time_ms']:+.0f} ms"})
    td, md = diff["delay_presence"]
    if td and not md:
        changes.append({"block": "DLY", "param": "ON/OFF", "old": "?", "new": "確認 DLY 有打開",
                        "why": "目標有延遲，你的錄音沒有偵測到"})
    if md and not td and "DLY" not in B:
        changes.append({"block": "DLY", "param": "ON/OFF", "old": "ON", "new": "OFF",
                        "why": "你的錄音有延遲，但目標沒有"})

    # --- Reverb
    if "RVB" in B and "rt60_s" in diff:
        p = B["RVB"]["params"]
        if abs(diff["reverb_wet_db"]) > 2 and isinstance(p.get("LEVEL"), int):
            old = p["LEVEL"]
            val = k(old + strength * diff["reverb_wet_db"] * 2.5)
            p["LEVEL"] = val
            chg("RVB", "LEVEL", old, val, f"殘響量差 {diff['reverb_wet_db']:+.1f} dB")
        if abs(diff["rt60_s"]) > 0.25 and isinstance(p.get("DECAY"), int):
            old = p["DECAY"]
            val = k(old + strength * diff["rt60_s"] * 20)
            p["DECAY"] = val
            chg("RVB", "DECAY", old, val, f"殘響長度差 {diff['rt60_s']:+.2f} 秒")

    # --- Global PRE EQ：整體傾斜 (低 / 中 / 高) 通常是吉他本身造成
    def avg(*bs):
        return sum(eq[b] for b in bs) / len(bs)
    pre = {"BASS 80Hz": avg(100, 220), "MID 500Hz": avg(500, 1200), "TREBLE 4kHz": avg(2600, 6400)}
    pre = {kk: max(-12.0, min(12.0, round(strength * v * 2) / 2)) for kk, v in pre.items()}
    return new, changes, pre
