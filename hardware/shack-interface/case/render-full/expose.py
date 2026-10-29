# Exposure lift for the CPU ray-traced PNGs (M-106): sRGB -> linear, x 2^EV, Reinhard-style shoulder, -> sRGB.
import sys, numpy as np
from PIL import Image
ev = float(sys.argv[1])
for p in sys.argv[2:]:
    a = np.asarray(Image.open(p).convert("RGB")).astype(np.float64) / 255.0
    lin = np.where(a <= 0.04045, a / 12.92, ((a + 0.055) / 1.055) ** 2.4) * 2 ** ev
    lin = lin / (1 + lin / 4.0) * 1.25                     # soft shoulder: white 1.0 stays near 1.0
    s = np.where(lin <= 0.0031308, lin * 12.92, 1.055 * np.clip(lin, 0, None) ** (1 / 2.4) - 0.055)
    Image.fromarray((np.clip(s, 0, 1) * 255 + 0.5).astype(np.uint8)).save(p.replace(".png", "-ev.png"))
    print(p)
