"""
Profildatenbank fuer Walzprofile und Hohlprofile.

Abmessungen nach EN 10365 (IPE, HEA, HEB, HEM) sowie EN 10210 (warmgefertigte
Hohlprofile SHS/RHS/CHS). Die Querschnittswerte werden aus den Abmessungen
berechnet (siehe Section.i_profile / Section.rhs / Section.pipe); sie stimmen
mit den Herstellertabellen auf < 1 % ueberein.

    from statik3d.profiles import make_section, list_profiles
    sec = make_section("HEA 200")
"""
from __future__ import annotations

import re

from .model import Section

# (h, b, tw, tf, r) in mm
IPE = {
    80: (80, 46, 3.8, 5.2, 5), 100: (100, 55, 4.1, 5.7, 7), 120: (120, 64, 4.4, 6.3, 7),
    140: (140, 73, 4.7, 6.9, 7), 160: (160, 82, 5.0, 7.4, 9), 180: (180, 91, 5.3, 8.0, 9),
    200: (200, 100, 5.6, 8.5, 12), 220: (220, 110, 5.9, 9.2, 12), 240: (240, 120, 6.2, 9.8, 15),
    270: (270, 135, 6.6, 10.2, 15), 300: (300, 150, 7.1, 10.7, 15), 330: (330, 160, 7.5, 11.5, 18),
    360: (360, 170, 8.0, 12.7, 18), 400: (400, 180, 8.6, 13.5, 21), 450: (450, 190, 9.4, 14.6, 21),
    500: (500, 200, 10.2, 16.0, 21), 550: (550, 210, 11.1, 17.2, 24), 600: (600, 220, 12.0, 19.0, 24),
}
HEA = {
    100: (96, 100, 5, 8, 12), 120: (114, 120, 5, 8, 12), 140: (133, 140, 5.5, 8.5, 12),
    160: (152, 160, 6, 9, 15), 180: (171, 180, 6, 9.5, 15), 200: (190, 200, 6.5, 10, 18),
    220: (210, 220, 7, 11, 18), 240: (230, 240, 7.5, 12, 21), 260: (250, 260, 7.5, 12.5, 24),
    280: (270, 280, 8, 13, 24), 300: (290, 300, 8.5, 14, 27), 320: (310, 300, 9, 15.5, 27),
    340: (330, 300, 9.5, 16.5, 27), 360: (350, 300, 10, 17.5, 27), 400: (390, 300, 11, 19, 27),
    450: (440, 300, 11.5, 21, 27), 500: (490, 300, 12, 23, 27), 550: (540, 300, 12.5, 24, 27),
    600: (590, 300, 13, 25, 27), 650: (640, 300, 13.5, 26, 27), 700: (690, 300, 14.5, 27, 27),
    800: (790, 300, 15, 28, 30), 900: (890, 300, 16, 30, 30), 1000: (990, 300, 16.5, 31, 30),
}
HEB = {
    100: (100, 100, 6, 10, 12), 120: (120, 120, 6.5, 11, 12), 140: (140, 140, 7, 12, 12),
    160: (160, 160, 8, 13, 15), 180: (180, 180, 8.5, 14, 15), 200: (200, 200, 9, 15, 18),
    220: (220, 220, 9.5, 16, 18), 240: (240, 240, 10, 17, 21), 260: (260, 260, 10, 17.5, 24),
    280: (280, 280, 10.5, 18, 24), 300: (300, 300, 11, 19, 27), 320: (320, 300, 11.5, 20.5, 27),
    340: (340, 300, 12, 21.5, 27), 360: (360, 300, 12.5, 22.5, 27), 400: (400, 300, 13.5, 24, 27),
    450: (450, 300, 14, 26, 27), 500: (500, 300, 14.5, 28, 27), 550: (550, 300, 15, 29, 27),
    600: (600, 300, 15.5, 30, 27), 650: (650, 300, 16, 31, 27), 700: (700, 300, 17, 32, 27),
    800: (800, 300, 17.5, 33, 30), 900: (900, 300, 18.5, 35, 30), 1000: (1000, 300, 19, 36, 30),
}
HEM = {
    100: (120, 106, 12, 20, 12), 120: (140, 126, 12.5, 21, 12), 140: (160, 146, 13, 22, 12),
    160: (180, 166, 14, 23, 15), 180: (200, 186, 14.5, 24, 15), 200: (220, 206, 15, 25, 18),
    220: (240, 226, 15.5, 26, 18), 240: (270, 248, 18, 32, 21), 260: (290, 268, 18, 32.5, 24),
    280: (310, 288, 18.5, 33, 24), 300: (340, 310, 21, 39, 27), 320: (359, 309, 21, 40, 27),
    340: (377, 309, 21, 40, 27), 360: (395, 308, 21, 40, 27), 400: (432, 307, 21, 40, 27),
    450: (478, 307, 21, 40, 27), 500: (524, 306, 21, 40, 27), 550: (572, 306, 21, 40, 27),
    600: (620, 305, 21, 40, 27), 650: (668, 305, 21, 40, 27), 700: (716, 304, 21, 40, 27),
    800: (814, 303, 21, 40, 30), 900: (910, 302, 21, 40, 30), 1000: (1008, 302, 21, 40, 30),
}
# (b, t) in mm, warmgefertigt EN 10210
SHS = [(40, 3), (40, 4), (50, 3), (50, 4), (50, 5), (60, 3), (60, 4), (60, 5), (70, 4), (70, 5),
       (80, 4), (80, 5), (80, 6), (90, 4), (90, 5), (90, 6), (100, 4), (100, 5), (100, 6), (100, 8),
       (120, 5), (120, 6), (120, 8), (120, 10), (140, 5), (140, 6), (140, 8), (140, 10),
       (150, 5), (150, 6), (150, 8), (150, 10), (160, 6), (160, 8), (160, 10), (180, 6), (180, 8),
       (180, 10), (200, 6), (200, 8), (200, 10), (200, 12.5), (250, 8), (250, 10), (250, 12.5),
       (300, 8), (300, 10), (300, 12.5), (300, 16), (350, 10), (350, 12.5), (350, 16),
       (400, 10), (400, 12.5), (400, 16)]
# (h, b, t)
RHS = [(50, 30, 3), (60, 40, 3), (60, 40, 4), (80, 40, 3), (80, 40, 4), (80, 40, 5),
       (90, 50, 4), (90, 50, 5), (100, 50, 3), (100, 50, 4), (100, 50, 5), (100, 50, 6),
       (100, 60, 4), (100, 60, 5), (100, 60, 6), (120, 60, 4), (120, 60, 5), (120, 60, 6),
       (120, 80, 5), (120, 80, 6), (120, 80, 8), (140, 80, 5), (140, 80, 6), (140, 80, 8),
       (150, 100, 5), (150, 100, 6), (150, 100, 8), (150, 100, 10), (160, 80, 5), (160, 80, 6),
       (160, 80, 8), (160, 80, 10), (180, 100, 6), (180, 100, 8), (180, 100, 10),
       (200, 100, 5), (200, 100, 6), (200, 100, 8), (200, 100, 10), (200, 120, 6), (200, 120, 8),
       (200, 120, 10), (250, 150, 6), (250, 150, 8), (250, 150, 10), (250, 150, 12.5),
       (260, 140, 6), (260, 140, 8), (260, 140, 10), (300, 200, 6), (300, 200, 8), (300, 200, 10),
       (300, 200, 12.5), (300, 200, 16), (400, 200, 8), (400, 200, 10), (400, 200, 12.5),
       (400, 200, 16), (500, 300, 10), (500, 300, 12.5), (500, 300, 16)]
# (d, t)
CHS = [(21.3, 2.3), (26.9, 2.3), (33.7, 2.6), (33.7, 3.2), (42.4, 2.6), (42.4, 3.2), (48.3, 3.2),
       (48.3, 4), (60.3, 3.2), (60.3, 4), (76.1, 3.2), (76.1, 4), (76.1, 5), (88.9, 3.6), (88.9, 4),
       (88.9, 5), (101.6, 4), (101.6, 5), (114.3, 4), (114.3, 5), (114.3, 6.3), (139.7, 4),
       (139.7, 5), (139.7, 6.3), (139.7, 8), (168.3, 5), (168.3, 6.3), (168.3, 8), (168.3, 10),
       (193.7, 5), (193.7, 6.3), (193.7, 8), (193.7, 10), (219.1, 6.3), (219.1, 8), (219.1, 10),
       (219.1, 12.5), (244.5, 6.3), (244.5, 8), (244.5, 10), (244.5, 12.5), (273, 6.3), (273, 8),
       (273, 10), (273, 12.5), (323.9, 8), (323.9, 10), (323.9, 12.5), (323.9, 16), (355.6, 8),
       (355.6, 10), (355.6, 12.5), (355.6, 16), (406.4, 10), (406.4, 12.5), (406.4, 16),
       (457, 10), (457, 12.5), (457, 16), (508, 10), (508, 12.5), (508, 16), (610, 12.5), (610, 16)]

# --------------------------------------------------------------------------
# U-Profile:  (h, b, tw, tf, r) in mm.  UPN nach DIN 1026-1 (geneigte Flansche,
# Neigung 8 %), UPE nach DIN 1026-2 (parallele Flansche).
# --------------------------------------------------------------------------
UPN = {
    50: (50, 38, 5, 7, 7), 65: (65, 42, 5.5, 7.5, 7.5), 80: (80, 45, 6, 8, 8),
    100: (100, 50, 6, 8.5, 8.5), 120: (120, 55, 7, 9, 9), 140: (140, 60, 7, 10, 10),
    160: (160, 65, 7.5, 10.5, 10.5), 180: (180, 70, 8, 11, 11), 200: (200, 75, 8.5, 11.5, 11.5),
    220: (220, 80, 9, 12.5, 12.5), 240: (240, 85, 9.5, 13, 13), 260: (260, 90, 10, 14, 14),
    280: (280, 95, 10, 15, 15), 300: (300, 100, 10, 16, 16), 320: (320, 100, 14, 17.5, 17.5),
    350: (350, 100, 14, 16, 16), 380: (380, 102, 13.5, 16, 16), 400: (400, 110, 14, 18, 18),
}
UPE = {
    80: (80, 50, 4, 7, 10), 100: (100, 55, 4.5, 7.5, 10), 120: (120, 60, 5, 8, 12),
    140: (140, 65, 5, 9, 12), 160: (160, 70, 5.5, 9.5, 12), 180: (180, 75, 5.5, 10.5, 12),
    200: (200, 80, 6, 11, 13), 220: (220, 85, 6.5, 12, 13), 240: (240, 90, 7, 12.5, 15),
    270: (270, 95, 7.5, 13.5, 15), 300: (300, 100, 9.5, 15, 15), 330: (330, 105, 11, 16, 18),
    360: (360, 110, 12, 17, 18), 400: (400, 115, 13.5, 18, 18),
}
# Winkel EN 10056-1: gleichschenklig (a, t, r), ungleichschenklig (h, b, t, r) in mm
L_EQ = [(20, 3, 3.5), (25, 3, 3.5), (25, 4, 3.5), (30, 3, 5), (30, 4, 5), (35, 4, 5),
        (40, 4, 6), (40, 5, 6), (45, 5, 7), (50, 5, 7), (50, 6, 7), (60, 6, 8), (60, 8, 8),
        (70, 7, 9), (70, 9, 9), (80, 8, 10), (80, 10, 10), (90, 9, 11), (90, 11, 11),
        (100, 10, 12), (100, 12, 12), (120, 12, 13), (120, 15, 13), (130, 12, 14),
        (150, 15, 16), (150, 18, 16), (180, 18, 18), (200, 20, 18), (200, 24, 18), (250, 28, 24)]
L_UNEQ = [(100, 50, 8, 9), (100, 65, 7, 10), (100, 65, 9, 10), (100, 75, 8, 10),
          (120, 80, 8, 11), (120, 80, 10, 11), (125, 75, 8, 11), (130, 65, 8, 11),
          (130, 65, 10, 11), (150, 75, 9, 12), (150, 90, 10, 12), (150, 90, 12, 12),
          (150, 100, 10, 12), (150, 100, 12, 12), (200, 100, 10, 15), (200, 100, 12, 15),
          (200, 150, 12, 15), (200, 150, 15, 15)]

# --------------------------------------------------------------------------
# Grossbritannien BS 4-1: UB/UC (h, b, tw, tf, r) in mm, PFC als U-Profil
# --------------------------------------------------------------------------
UB = {
    "203x133x25": (203.2, 133.2, 5.7, 7.8, 7.6), "203x133x30": (206.8, 133.9, 6.4, 9.6, 7.6),
    "254x146x31": (251.4, 146.1, 6.0, 8.6, 7.6), "254x146x43": (259.6, 147.3, 7.2, 12.7, 7.6),
    "305x165x40": (303.4, 165.0, 6.0, 10.2, 8.9), "305x165x54": (310.4, 166.9, 7.9, 13.7, 8.9),
    "356x171x51": (355.0, 171.5, 7.4, 11.5, 10.2), "356x171x67": (363.4, 173.2, 9.1, 15.7, 10.2),
    "406x178x60": (406.4, 177.9, 7.9, 12.8, 10.2), "406x178x74": (412.8, 179.5, 9.5, 16.0, 10.2),
    "457x191x74": (457.0, 190.4, 9.0, 14.5, 10.2), "457x191x98": (467.2, 192.8, 11.4, 19.6, 10.2),
    "533x210x92": (533.1, 209.3, 10.1, 15.6, 12.7), "533x210x122": (544.5, 211.9, 12.7, 21.3, 12.7),
    "610x229x113": (607.6, 228.2, 11.1, 17.3, 12.7), "610x229x140": (617.2, 230.2, 13.1, 22.1, 12.7),
    "686x254x125": (677.9, 253.0, 11.7, 16.2, 15.2), "762x267x147": (754.0, 265.2, 12.8, 17.5, 16.5),
    "838x292x176": (834.9, 291.7, 14.0, 18.8, 17.8), "914x305x201": (903.0, 303.3, 15.1, 20.2, 19.1),
}
UC = {
    "152x152x37": (161.8, 154.4, 8.0, 11.5, 7.6), "152x152x51": (170.2, 157.4, 11.0, 15.7, 7.6),
    "203x203x60": (209.6, 205.8, 9.4, 14.2, 10.2), "203x203x86": (222.2, 209.1, 12.7, 20.5, 10.2),
    "254x254x73": (254.1, 254.6, 8.6, 14.2, 12.7), "254x254x89": (260.3, 256.3, 10.3, 17.3, 12.7),
    "254x254x132": (276.3, 261.3, 15.3, 25.3, 12.7), "305x305x97": (307.9, 305.3, 9.9, 15.4, 15.2),
    "305x305x137": (320.5, 309.2, 13.8, 21.7, 15.2), "305x305x198": (339.9, 314.5, 19.1, 31.4, 15.2),
    "356x368x153": (362.0, 370.5, 12.6, 20.7, 15.2), "356x368x177": (368.2, 372.6, 14.4, 23.8, 15.2),
}
PFC = {
    "100x50x10": (100, 50, 5.0, 8.5, 9.0), "125x65x15": (125, 65, 5.5, 9.5, 12.0),
    "150x75x18": (150, 75, 5.5, 10.0, 12.0), "180x75x20": (180, 75, 6.0, 10.5, 12.0),
    "200x75x23": (200, 75, 6.0, 12.5, 12.0), "200x90x30": (200, 90, 7.0, 14.0, 12.0),
    "230x75x26": (230, 75, 6.5, 12.5, 12.0), "260x75x28": (260, 75, 7.0, 12.0, 12.0),
    "260x90x35": (260, 90, 8.0, 14.0, 12.0), "300x90x41": (300, 90, 9.0, 15.5, 12.0),
    "300x100x46": (300, 100, 9.0, 16.5, 15.0), "380x100x54": (380, 100, 9.5, 17.5, 15.0),
    "430x100x64": (430, 100, 11.0, 19.0, 15.0),
}

# --------------------------------------------------------------------------
# USA (AISC): W-Profile (d, bf, tw, tf) in Zoll, C-Profile, HSS und Pipe.
# Die Ausrundung wird mit r ~ 0.6 tf angenaehert.
# --------------------------------------------------------------------------
INCH = 0.0254
W_US = {
    "W6x15": (5.99, 5.99, 0.230, 0.260), "W8x18": (8.14, 5.25, 0.230, 0.330),
    "W8x31": (8.00, 8.00, 0.285, 0.435), "W10x22": (10.2, 5.75, 0.240, 0.360),
    "W10x33": (9.73, 7.96, 0.290, 0.435), "W10x49": (10.0, 10.0, 0.340, 0.560),
    "W12x26": (12.2, 6.49, 0.230, 0.380), "W12x40": (11.9, 8.01, 0.295, 0.515),
    "W12x65": (12.1, 12.0, 0.390, 0.605), "W14x22": (13.7, 5.00, 0.230, 0.335),
    "W14x53": (13.9, 8.06, 0.370, 0.660), "W14x90": (14.0, 14.5, 0.440, 0.710),
    "W16x26": (15.7, 5.50, 0.250, 0.345), "W16x40": (16.0, 7.00, 0.305, 0.505),
    "W18x35": (17.7, 6.00, 0.300, 0.425), "W18x50": (18.0, 7.50, 0.355, 0.570),
    "W21x44": (20.7, 6.50, 0.350, 0.450), "W21x62": (21.0, 8.24, 0.400, 0.615),
    "W24x55": (23.6, 7.01, 0.395, 0.505), "W24x76": (23.9, 8.99, 0.440, 0.680),
    "W27x94": (26.9, 9.99, 0.490, 0.745), "W30x108": (29.8, 10.5, 0.545, 0.760),
    "W33x118": (32.9, 11.5, 0.550, 0.740), "W36x150": (35.9, 12.0, 0.625, 0.940),
}
C_US = {   # (d, bf, tw, tf) in Zoll, geneigte Flansche (Neigung 1:6 = 0.167)
    "C6x8.2": (6.00, 1.92, 0.200, 0.343), "C8x11.5": (8.00, 2.26, 0.220, 0.390),
    "C10x15.3": (10.0, 2.60, 0.240, 0.436), "C12x20.7": (12.0, 2.94, 0.282, 0.501),
    "C15x33.9": (15.0, 3.40, 0.400, 0.650),
}
HSS_US = {  # (h, b, t_nominal) in Zoll; Bemessungsdicke = 0.93 * t
    "HSS4x4x1/4": (4, 4, 0.25), "HSS5x5x3/8": (5, 5, 0.375), "HSS6x6x3/8": (6, 6, 0.375),
    "HSS8x8x1/2": (8, 8, 0.5), "HSS10x10x1/2": (10, 10, 0.5), "HSS12x12x1/2": (12, 12, 0.5),
    "HSS6x4x3/8": (6, 4, 0.375), "HSS8x6x1/2": (8, 6, 0.5), "HSS10x6x1/2": (10, 6, 0.5),
    "HSS12x8x1/2": (12, 8, 0.5), "HSS16x8x1/2": (16, 8, 0.5),
}
PIPE_US = {  # (Aussendurchmesser, Nennwanddicke) in Zoll; gerechnet mit 0.93 t (AISC)
    "PIPE 2 STD": (2.375, 0.154), "PIPE 3 STD": (3.5, 0.216), "PIPE 4 STD": (4.5, 0.237),
    "PIPE 6 STD": (6.625, 0.280), "PIPE 8 STD": (8.625, 0.322), "PIPE 10 STD": (10.75, 0.365),
    "PIPE 12 STD": (12.75, 0.375),
}

FAMILIES = ("IPE", "HEA", "HEB", "HEM", "UPN", "UPE", "L", "LU", "SHS", "RHS", "CHS",
            "UB", "UC", "PFC", "W", "C", "HSS", "PIPE")

# Land -> (Bezeichnung, Norm, Familien)
COUNTRIES = {
    "EU": ("Europa / Deutschland", "EN 10365, DIN 1026, EN 10056, EN 10210",
           ["IPE", "HEA", "HEB", "HEM", "UPN", "UPE", "L", "LU", "SHS", "RHS", "CHS"]),
    "GB": ("Grossbritannien", "BS 4-1, BS EN 10365", ["UB", "UC", "PFC"]),
    "US": ("USA / Kanada", "AISC Steel Construction Manual", ["W", "C", "HSS", "PIPE"]),
}
FAMILY_INFO = {
    "IPE": ("Doppel-T schmal (EN 10365)", "EU"), "HEA": ("Breitflansch HE-A (EN 10365)", "EU"),
    "HEB": ("Breitflansch HE-B (EN 10365)", "EU"), "HEM": ("Breitflansch HE-M (EN 10365)", "EU"),
    "UPN": ("U-Profil geneigte Flansche (DIN 1026-1)", "EU"),
    "UPE": ("U-Profil parallele Flansche (DIN 1026-2)", "EU"),
    "L": ("Winkel gleichschenklig (EN 10056-1)", "EU"),
    "LU": ("Winkel ungleichschenklig (EN 10056-1)", "EU"),
    "SHS": ("Quadratrohr (EN 10210)", "EU"), "RHS": ("Rechteckrohr (EN 10210)", "EU"),
    "CHS": ("Rundrohr (EN 10210)", "EU"),
    "UB": ("Universal Beam (BS 4-1)", "GB"), "UC": ("Universal Column (BS 4-1)", "GB"),
    "PFC": ("Parallel Flange Channel (BS 4-1)", "GB"),
    "W": ("Wide Flange (AISC)", "US"), "C": ("American Standard Channel (AISC)", "US"),
    "HSS": ("Hollow Structural Section (AISC)", "US"), "PIPE": ("Rohr Standard (AISC)", "US"),
}


def countries() -> list[tuple]:
    """[(Kuerzel, Bezeichnung, Norm, Familien)] der Laender in der Datenbank."""
    return [(k, v[0], v[1], list(v[2])) for k, v in COUNTRIES.items()]


def country_of(family: str) -> str:
    return FAMILY_INFO.get(family.upper(), ("", "EU"))[1]


def families(country: str = None) -> list[str]:
    if country is None:
        return list(FAMILIES)
    c = COUNTRIES.get(country.upper())
    if c is None:
        raise KeyError(f"Land '{country}' unbekannt ({list(COUNTRIES)})")
    return list(c[2])


_FAMILY_INDEX = None


def family_of(designation: str) -> str:
    """Die Profilreihe zu einer Bezeichnung.

    Leer, wenn die Bezeichnung nicht in der Datenbank steht - dann ist der
    Querschnitt frei eingegeben und nicht aus dem Katalog.
    """
    global _FAMILY_INDEX
    if _FAMILY_INDEX is None:
        _FAMILY_INDEX = {}
        for fam in FAMILIES:
            try:
                namen = list_profiles(fam)
            except KeyError:
                continue
            for name in namen:
                _FAMILY_INDEX.setdefault(re.sub(r"\s+", "", name.upper()), fam)
    return _FAMILY_INDEX.get(re.sub(r"\s+", "", str(designation).upper()), "")


def _norm(designation: str) -> str:
    s = designation.upper().replace(",", ".")
    s = re.sub(r"\s+", " ", s.strip())
    s = s.replace("×", "X").replace(" X ", "X").replace("X ", "X").replace(" X", "X")
    s = s.replace("HE ", "HE").replace("QHP", "SHS").replace("RHP", "RHS").replace("RO ", "CHS ")
    # "HE200A" -> "HEA 200", "HE 200 B" -> "HEB 200"
    mm = re.match(r"HE\s?(\d+)\s?([ABM])$", s)
    if mm:
        s = f"HE{mm.group(2)} {mm.group(1)}"
    mm = re.match(r"(IPE|HEA|HEB|HEM)(\d+)$", s)
    if mm:
        s = f"{mm.group(1)} {mm.group(2)}"
    return s


_US_TABLES = None


def _us_lookup(key: str):
    """(Tabellenname, Werte) zu einer normierten US-Bezeichnung."""
    global _US_TABLES
    if _US_TABLES is None:
        _US_TABLES = {}
        for tab_name, tab in (("W", W_US), ("C", C_US), ("HSS", HSS_US), ("PIPE", PIPE_US)):
            for k, v in tab.items():
                _US_TABLES[re.sub(r"\s+", "", k.upper())] = (tab_name, v)
    return _US_TABLES.get(key)


def _us_key(designation: str) -> str:
    """US-Bezeichnung normieren: 'w14 x 90' -> 'W14x90', 'hss 6x6x3/8' -> 'HSS6x6x3/8'."""
    k = re.sub(r"\s+", "", designation.upper()).replace("×", "X")
    return k


def list_profiles(family: str = None, country: str = None) -> list[str]:
    """Profilbezeichnungen, optional einer Familie oder eines Landes."""
    if family is None and country is not None:
        out = []
        for f in families(country):
            out += list_profiles(f)
        return out
    out = []
    f = family.upper() if family else None
    if f in (None, "IPE"):
        out += [f"IPE {h}" for h in IPE]
    if f in (None, "HEA"):
        out += [f"HEA {h}" for h in HEA]
    if f in (None, "HEB"):
        out += [f"HEB {h}" for h in HEB]
    if f in (None, "HEM"):
        out += [f"HEM {h}" for h in HEM]
    if f in (None, "UPN"):
        out += [f"UPN {h}" for h in UPN]
    if f in (None, "UPE"):
        out += [f"UPE {h}" for h in UPE]
    if f in (None, "L"):
        out += [f"L {a}x{a}x{t:g}" for a, t, _ in L_EQ]
    if f in (None, "LU"):
        out += [f"L {h}x{b}x{t:g}" for h, b, t, _ in L_UNEQ]
    if f in (None, "SHS"):
        out += [f"SHS {b}x{t:g}" for b, t in SHS]
    if f in (None, "RHS"):
        out += [f"RHS {h}x{b}x{t:g}" for h, b, t in RHS]
    if f in (None, "CHS"):
        out += [f"CHS {d:g}x{t:g}" for d, t in CHS]
    if f in (None, "UB"):
        out += [f"UB {k}" for k in UB]
    if f in (None, "UC"):
        out += [f"UC {k}" for k in UC]
    if f in (None, "PFC"):
        out += [f"PFC {k}" for k in PFC]
    if f in (None, "W"):
        out += list(W_US)
    if f in (None, "C"):
        out += list(C_US)
    if f in (None, "HSS"):
        out += list(HSS_US)
    if f in (None, "PIPE"):
        out += list(PIPE_US)
    if f is not None and not out:
        raise KeyError(f"Profilreihe '{family}' unbekannt ({list(FAMILIES)})")
    return out


def make_section(designation: str, name: str = None) -> Section:
    """Section aus Profilbezeichnung, z.B. 'IPE 300', 'HEB 200', 'SHS 100x5',
    'RHS 200x100x8', 'CHS 168.3x5'. Auch 'HE 200 B', 'HE200A', 'Ro 168.3x5'."""
    s = _norm(designation)
    nm = name or s
    mm = re.match(r"(IPE|HEA|HEB|HEM) (\d+)$", s)
    if mm:
        fam, h = mm.group(1), int(mm.group(2))
        tab = {"IPE": IPE, "HEA": HEA, "HEB": HEB, "HEM": HEM}[fam]
        if h not in tab:
            raise KeyError(f"{fam} {h} nicht in der Datenbank")
        H, B, tw, tf, r = tab[h]
        return Section.i_profile(nm, H * 1e-3, B * 1e-3, tw * 1e-3, tf * 1e-3, r * 1e-3)
    mm = re.match(r"SHS (\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)$", s)
    if mm:
        b, t = float(mm.group(1)), float(mm.group(2))
        return Section.rhs(nm, b * 1e-3, b * 1e-3, t * 1e-3)
    mm = re.match(r"RHS (\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)$", s)
    if mm:
        h, b, t = (float(mm.group(i)) for i in (1, 2, 3))
        return Section.rhs(nm, h * 1e-3, b * 1e-3, t * 1e-3)
    mm = re.match(r"CHS (\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)$", s)
    if mm:
        d, t = float(mm.group(1)), float(mm.group(2))
        return Section.pipe(nm, d * 1e-3, t * 1e-3)
    mm = re.match(r"(UPN|UPE) (\d+)$", s)
    if mm:
        fam, h = mm.group(1), int(mm.group(2))
        tab = UPN if fam == "UPN" else UPE
        if h not in tab:
            raise KeyError(f"{fam} {h} nicht in der Datenbank")
        H, B, tw, tf, r = tab[h]
        return Section.channel(nm, H * 1e-3, B * 1e-3, tw * 1e-3, tf * 1e-3, r * 1e-3,
                               taper=0.08 if fam == "UPN" else 0.0)
    mm = re.match(r"L (\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)X(\d+(?:\.\d+)?)$", s)
    if mm:
        h, b, t = (float(mm.group(i)) for i in (1, 2, 3))
        if h < b:
            h, b = b, h
        r = next((rr for a, tt, rr in L_EQ if a == h and tt == t), None) if h == b else \
            next((rr for hh, bb, tt, rr in L_UNEQ if hh == h and bb == b and tt == t), None)
        if r is None:
            r = round(0.9 * t, 1)          # nicht tabelliert: Ausrundung geschaetzt
        return Section.angle(nm, h * 1e-3, b * 1e-3, t * 1e-3, r * 1e-3)
    mm = re.match(r"(UB|UC) (\S+)$", s)
    if mm:
        fam, key = mm.group(1), mm.group(2).lower()
        tab = UB if fam == "UB" else UC
        if key not in tab:
            raise KeyError(f"{fam} {mm.group(2)} nicht in der Datenbank")
        H, B, tw, tf, r = tab[key]
        return Section.i_profile(nm, H * 1e-3, B * 1e-3, tw * 1e-3, tf * 1e-3, r * 1e-3)
    mm = re.match(r"PFC (\S+)$", s)
    if mm:
        key = mm.group(1).lower()
        if key not in PFC:
            raise KeyError(f"PFC {mm.group(1)} nicht in der Datenbank")
        H, B, tw, tf, r = PFC[key]
        return Section.channel(nm, H * 1e-3, B * 1e-3, tw * 1e-3, tf * 1e-3, r * 1e-3)
    hit = _us_lookup(_us_key(designation))
    if hit:
        fam, v = hit
        if fam == "W":
            d, bf, tw, tf = v
            return Section.i_profile(nm, d * INCH, bf * INCH, tw * INCH, tf * INCH, 0.6 * tf * INCH)
        if fam == "C":
            d, bf, tw, tf = v
            return Section.channel(nm, d * INCH, bf * INCH, tw * INCH, tf * INCH,
                                   0.7 * tf * INCH, taper=1 / 6.0)
        if fam == "HSS":
            h, b, t = v
            return Section.rhs(nm, h * INCH, b * INCH, 0.93 * t * INCH, fabrication="cold_formed")
        d, t = v          # AISC: Bemessungswanddicke 0.93 * nominal
        return Section.pipe(nm, d * INCH, 0.93 * t * INCH)
    raise KeyError(f"Profil '{designation}' unbekannt. Verfuegbare Reihen: "
                   + ", ".join(FAMILIES))


def find_profile(designation: str) -> bool:
    try:
        make_section(designation)
        return True
    except KeyError:
        return False
