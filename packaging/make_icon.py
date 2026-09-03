"""Programmsymbol statik3d.ico aus einfachen Formen erzeugen (Pillow)."""
import os
from PIL import Image, ImageDraw

here = os.path.dirname(os.path.abspath(__file__))
sizes = [256, 128, 64, 48, 32, 16]
frames = []
for s in sizes:
    im = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    r = s * 0.19
    d.rounded_rectangle([0, 0, s - 1, s - 1], radius=r, fill=(28, 39, 51, 255))
    w = max(1, round(s * 0.055))
    col = (242, 210, 58, 255)
    x0, x1, yt, yb, ym = s * 0.22, s * 0.78, s * 0.41, s * 0.75, s * 0.235
    d.line([(x0, yb), (x0, yt), (s / 2, ym), (x1, yt), (x1, yb)], fill=col, width=w, joint="curve")
    d.line([(x0, yb), (x1, yb)], fill=col, width=w)
    d.line([(x0, yt), (x1, yt)], fill=col, width=w)
    g = (89, 193, 90, 255)
    t = s * 0.07
    for x in (x0, x1):
        d.polygon([(x, yb + w * 0.4), (x - t, yb + w * 0.4 + 1.6 * t), (x + t, yb + w * 0.4 + 1.6 * t)], fill=g)
    o = (229, 112, 28, 255)
    d.line([(s / 2, s * 0.06), (s / 2, s * 0.19)], fill=o, width=w)
    d.polygon([(s / 2 - t * 0.8, s * 0.14), (s / 2 + t * 0.8, s * 0.14), (s / 2, s * 0.21)], fill=o)
    frames.append(im)
out = os.path.join(here, "statik3d.ico")
frames[0].save(out, format="ICO", sizes=[(s, s) for s in sizes], append_images=frames[1:])
print(out)
