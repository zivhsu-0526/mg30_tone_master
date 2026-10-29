"""NUX MG-30 效果器知識庫。

資料來源：
- NUX MG-30 Models List (firmware 4.03)
- NUX MG-30 Control Parameters (2021-02, Aria Guitars 代理商文件)
- NUX 官方產品頁 (V5 / GEN2 韌體更新說明)

所有旋鈕參數在機器與 QuickTone 中皆為 0-100 (除特別標示)。
"""

# 預設訊號鏈 (MG-30 共 11 個可移動 block；MOD / DLY / RVB 可設為並聯)
DEFAULT_CHAIN = ["WAH", "CMP", "EFX", "AMP", "IR", "EQ", "GATE", "S/R", "MOD", "DLY", "RVB"]
PARALLEL_CAPABLE = {"MOD", "DLY", "RVB"}

BLOCK_NAMES = {
    "WAH": "WAH 哇音 / 音量",
    "CMP": "CMP 壓縮",
    "GATE": "GATE 噪音門",
    "EFX": "EFX 前級效果 (破音/過載/Boost/Fuzz)",
    "AMP": "AMP 音箱模擬",
    "IR": "IR 箱體模擬",
    "EQ": "EQ 等化器",
    "S/R": "S/R 外接效果迴路",
    "MOD": "MOD 調變",
    "DLY": "DLY 延遲",
    "RVB": "RVB 殘響",
}

# ---------------- AMP ----------------
# params: 該型號可調參數 (依官方 Control Parameters 表)
_AMP_STD = ["GAIN", "MASTER", "BASS", "MIDDLE", "TREBLE", "PRESENCE", "BIAS", "LEVEL"]
AMPS = {
    "Jazz Clean":  {"based_on": "Roland JC-120", "params": ["GAIN", "MASTER", "BASS", "MIDDLE", "TREBLE", "BRIGHT", "LEVEL"], "ir": "JZ120"},
    "Deluxe Rvb":  {"based_on": "Fender '64 Deluxe Reverb", "params": ["GAIN", "MASTER", "BASS", "MIDDLE", "TREBLE", "BIAS", "LEVEL"], "ir": "DR112"},
    "Bass Mate":   {"based_on": "Fender '59 Bassman", "params": _AMP_STD, "ir": "BS410"},
    "Tweedy":      {"based_on": "Fender '57 Tweed Deluxe", "params": ["GAIN", "TONE", "MASTER", "LEVEL"], "ir": "BS410"},
    "Twin Rvb":    {"based_on": "Fender '65 Twin Reverb", "params": ["GAIN", "MASTER", "BASS", "MIDDLE", "TREBLE", "BRIGHT", "BIAS", "LEVEL"], "ir": "TR212"},
    "Hiwire":      {"based_on": "Hiwatt DR103", "params": _AMP_STD, "ir": "1960"},
    "Cali Crunch": {"based_on": "Mesa/Boogie Mark I", "params": _AMP_STD, "ir": "V412"},
    "Class A 15":  {"based_on": "Vox AC15", "params": ["GAIN", "MASTER", "CUT", "BASS", "TREBLE", "LEVEL"], "ir": "A212"},
    "Class A 30":  {"based_on": "Vox AC30", "params": ["GAIN", "MASTER", "CUT", "BASS", "TREBLE", "LEVEL"], "ir": "A212"},
    "Plexi 100W":  {"based_on": "Marshall '68 Plexi 100W", "params": _AMP_STD, "ir": "GB412"},
    "Plexi 45":    {"based_on": "Marshall '67 JTM45", "params": _AMP_STD, "ir": "GB412"},
    "Brit 800":    {"based_on": "Marshall JCM800", "params": _AMP_STD, "ir": "1960"},
    "1987 X 50W":  {"based_on": "Marshall 1987X 50W", "params": _AMP_STD, "ir": "GB412"},
    "Slo 100":     {"based_on": "Soldano SLO-100", "params": _AMP_STD, "ir": "V412"},
    "Fireman HBE": {"based_on": "Friedman HBE-100", "params": _AMP_STD, "ir": "V412"},
    "Dual Rect":   {"based_on": "Mesa/Boogie Dual Rectifier", "params": _AMP_STD, "ir": "V412"},
    "Die VH4":     {"based_on": "Diezel VH4", "params": _AMP_STD, "ir": "V412"},
    "Vibro King":  {"based_on": "Fender Vibro-King", "params": _AMP_STD, "ir": "TR212"},
    "Budda":       {"based_on": "Budda Superdrive", "params": ["GAIN", "MASTER", "CUT", "BASS", "MIDDLE", "TREBLE", "LEVEL"], "ir": "A212"},
    "Mr Z 38":     {"based_on": "Dr. Z Maz 38", "params": ["GAIN", "MASTER", "CUT", "BASS", "MIDDLE", "TREBLE", "LEVEL"], "ir": "A212"},
    "Super Rvb":   {"based_on": "Fender Super-Sonic", "params": ["GAIN", "MASTER", "BASS", "MIDDLE", "TREBLE", "BRIGHT", "BIAS", "LEVEL"], "ir": "TR212"},
    "Brit Blues":  {"based_on": "Marshall Bluesbreaker (JTM45)", "params": _AMP_STD, "ir": "GB412"},
    "Match":       {"based_on": "Matchless DC-30", "params": ["GAIN", "MASTER", "CUT", "BASS", "TREBLE", "LEVEL"], "ir": "A212"},
    "Brit 2000":   {"based_on": "Marshall JCM2000", "params": _AMP_STD, "ir": "1960"},
    "Uber":        {"based_on": "Bogner Uberschall", "params": _AMP_STD, "ir": "V412"},
}

# ---------------- IR / CAB ----------------
IRS = {
    "JZ120": "Roland JC-120 2x12",
    "DR112": "Fender Deluxe Reverb 1x12",
    "BS410": "Fender Bassman 4x10",
    "A212":  "Vox AC30 2x12",
    "TR212": "Fender Twin Reverb 2x12",
    "1960":  "Marshall 1960 4x12",
    "GB412": "Marshall 4x12 Greenback",
    "V412":  "Marshall 4x12 Vintage 30",
}
IR_PARAMS = ["MIC", "MIC AXIS", "LEVEL(-12~+12dB)", "LO CUT(20Hz~1kHz)", "HI CUT(5k~20kHz)"]
MICS = {"S57": "Shure SM57", "DYN421": "Sennheiser MD421", "U87": "Neumann U87",
        "R121": "Royer R-121", "R122": "Royer R-122", "C414": "AKG C414",
        "C3000": "AKG C3000", "B52": "Shure Beta 52A"}

# ---------------- EFX (前級) ----------------
EFX = {
    "Distortion+": {"based_on": "MXR Distortion+", "params": ["OUTPUT", "SENSITIVITY"], "type": "dist"},
    "RC Boost":    {"based_on": "Xotic RC Booster", "params": ["GAIN", "VOL", "BASS", "TREBLE"], "type": "boost"},
    "AC Boost":    {"based_on": "Xotic AC Booster", "params": ["GAIN", "VOL", "BASS", "TREBLE"], "type": "boost"},
    "Dist One":    {"based_on": "Boss DS-1", "params": ["LEVEL", "TONE", "DRIVE"], "type": "dist"},
    "T Scream":    {"based_on": "Ibanez TS808 Tube Screamer", "params": ["DRIVE", "TONE", "LEVEL"], "type": "od"},
    "Blues Drv":   {"based_on": "Boss BD-2 Blues Driver", "params": ["LEVEL", "TONE", "GAIN"], "type": "od"},
    "Morning Drv": {"based_on": "JHS Morning Glory", "params": ["VOLUME", "DRIVE", "TONE"], "type": "od"},
    "Eat Dist":    {"based_on": "ProCo RAT", "params": ["DISTORTION", "FILTER", "VOLUME"], "type": "dist"},
    "Red Dirt":    {"based_on": "Keeley Red Dirt", "params": ["DRIVE", "TONE", "LEVEL"], "type": "od"},
    "Crunch":      {"based_on": "JHS Angry Charlie", "params": ["VOLUME", "TONE", "GAIN"], "type": "dist"},
    "Muff Fuzz":   {"based_on": "EHX Big Muff Pi", "params": ["VOLUME", "TONE", "SUSTAIN"], "type": "fuzz"},
    "Katana":      {"based_on": "Keeley Katana Clean Boost", "params": ["BOOST SW", "VOLUME"], "type": "boost"},
    "Red Fuzz":    {"based_on": "Arbiter Fuzz Face", "params": ["VOLUME", "FUZZ"], "type": "fuzz"},
    "Touch Wah":   {"based_on": "Musitronics Mu-Tron III", "params": ["SENSITIVITY", "RANGE", "MIX"], "type": "filter"},
}

# ---------------- CMP ----------------
CMPS = {
    "Rose Comp":   {"based_on": "Ross Compressor", "params": ["SUSTAIN", "LEVEL"]},
    "K Comp":      {"based_on": "Keeley C4 4-knob", "params": ["SUSTAIN", "LEVEL", "CLIPPING"]},
    "Studio Comp": {"based_on": "Studio Compressor", "params": ["THRESHOLD", "RATIO", "GAIN", "RELEASE"]},
}

# ---------------- WAH ----------------
WAHS = {
    "Clyde":  {"based_on": "Fulltone Clyde", "params": ["PEDAL(EXP)"]},
    "Cry BB": {"based_on": "Dunlop Cry Baby", "params": ["PEDAL(EXP)"]},
    "V847":   {"based_on": "Vox V847", "params": ["PEDAL(EXP)"]},
    "Horse Wah": {"based_on": "Morley Bad Horsie", "params": ["CONTOUR", "RANGE"]},
    "Octave Shift": {"based_on": "DigiTech Whammy", "params": ["UP/DOWN"]},
}

# ---------------- EQ ----------------
EQS = {
    "6-Band":  {"based_on": "Boss GE-6", "bands": [100, 220, 500, 1200, 2600, 6400]},
    "Align":   {"based_on": "LR Baggs Align EQ", "bands": [110, 340, 660, 1300, 2600, 5000]},
    "10-Band": {"based_on": "MXR 10-Band", "bands": [31.25, 62.5, 125, 250, 500, 1000, 2000, 4000, 8000, 16000]},
    "Para":    {"based_on": "3-band Parametric", "bands": []},
}

# ---------------- MOD ----------------
SUBDIVS = ["1/4", "1/8D", "1/8", "1/4T", "1/16", "1/8T", "1/32"]
MODS = {
    "CE-1":       {"based_on": "Boss CE-1", "params": ["INTENSITY", "DEPTH", "RATE"], "type": "chorus"},
    "CE-2":       {"based_on": "Boss CE-2", "params": ["RATE", "DEPTH"], "type": "chorus"},
    "St. Chorus": {"based_on": "MXR M134 Stereo Chorus", "params": ["INTENSITY", "WIDTH", "RATE"], "type": "chorus"},
    "Vibrator":   {"based_on": "Boss VB-2", "params": ["RATE", "DEPTH"], "type": "vibrato"},
    "Detune":     {"based_on": "NUX 原創", "params": ["SHIFT L", "OUT MIX", "SHIFT R"], "type": "detune"},
    "Flanger":    {"based_on": "Boss BF-3", "params": ["LEVEL", "RATE", "WIDTH", "F.BACK"], "type": "flanger"},
    "Phase 90":   {"based_on": "MXR Phase 90", "params": ["SPEED"], "type": "phaser"},
    "Phase 100":  {"based_on": "MXR Phase 100", "params": ["INTENSITY", "SPEED"], "type": "phaser"},
    "S.C.F.":     {"based_on": "TC Electronic SCF", "params": ["SPEED", "WIDTH", "MODE", "INTENSITY"], "type": "chorus"},
    "U-Vibe":     {"based_on": "Dunlop UV-1 Uni-Vibe", "params": ["SPEED", "VOLUME", "INTENSITY", "CHORUS/VIBRATO"], "type": "phaser"},
    "Tremolo":    {"based_on": "Boss TR-2", "params": ["RATE", "DEPTH"], "type": "tremolo"},
    "Rotary":     {"based_on": "Strymon Lex", "params": ["BALANCE", "SPEED"], "type": "rotary"},
    "Harmonist":  {"based_on": "DigiTech Harmony Man", "params": ["KEY", "SCALE", "HARM", "BLEND"], "type": "pitch"},
}

# ---------------- DLY ----------------
DLYS = {
    "Analog":     {"based_on": "Boss DM-2", "params": ["REPEAT", "ECHO", "INTENSITY"], "char": "暖、暗，重複音高頻衰減"},
    "Digital":    {"based_on": "Boss DD-7", "params": ["E.LEVEL", "FEEDBACK", "TIME"], "char": "乾淨清晰的數位延遲"},
    "Modulation": {"based_on": "Ibanez DML-10", "params": ["TIME", "LEVEL", "MOD", "REPEAT"], "char": "帶調變的延遲 (重複音輕微搖晃)"},
    "Tape Echo":  {"based_on": "Roland RE-101 / Echoplex", "params": ["TIME", "LEVEL", "REPEAT"], "char": "磁帶迴音，略暗且帶抖動"},
    "Reverse":    {"based_on": "TC Alter Ego (Reverse)", "params": ["TIME", "MIX", "FEEDBACK"], "char": "反轉延遲"},
    "Pan Delay":  {"based_on": "Ibanez DPL-10", "params": ["TIME", "REPEAT", "LEVEL"], "char": "左右聲道交替 (Ping-Pong)"},
    "Duotime":    {"based_on": "NUX Duotime", "params": ["LEVEL", "TIME1", "REPEAT1", "TIME2", "REPEAT2", "PARALLEL"], "char": "雙延遲"},
    "Phi":        {"based_on": "NUX 原創", "params": ["TIME", "LEVEL", "REPEAT"], "char": "NUX 原創延遲"},
}

# ---------------- RVB ----------------
RVBS = {
    "Room":    {"based_on": "Room reverb", "params": ["DECAY", "TONE", "LEVEL"]},
    "Hall":    {"based_on": "Lexicon 224/480L Hall", "params": ["DECAY", "PRE DELAY", "LIVELINESS", "LEVEL"]},
    "Plate":   {"based_on": "EMT 140 Plate", "params": ["DECAY", "LEVEL"]},
    "Spring":  {"based_on": "Vintage Spring (Boss FRV-1)", "params": ["DECAY", "LEVEL"]},
    "Shimmer": {"based_on": "Neunaber Seraphim", "params": ["MIX", "DECAY", "SHIM"]},
}

GATE = {"Noise Gate": {"based_on": "Boss NF-1", "params": ["SENSITIVITY", "DECAY"]}}

FIRMWARE_NOTES = (
    "型號依韌體 4.x / V5 標準清單。GEN2 韌體另新增 EFX：FULL-OD HP、HORSEMAN、NOB ODR、"
    "RIV BLUEFLOG COMBO、TURBO OD；MOD：MONO OCTAVE；AMP 區塊可載入 NAM 模型。"
    "若你的機器顯示的型號名稱與此略有不同，請以機器上最接近的名稱為準。"
)

ROUTING_HOWTO = (
    "設定並聯：在 Patch 編輯模式下按住 5-way 編碼器「UP」進入 Block 位置編輯，"
    "移到 MOD / DLY / RVB block 後按 KNOB 3 或 KNOB 4 切換串聯/並聯；"
    "也可以在 QuickTone 編輯軟體的訊號鏈中直接拖曳與切換 Series / Parallel。"
)
