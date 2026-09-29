"""Generate the apartment plan in the black-and-white survey drawing style."""

from html import escape
from pathlib import Path


OUT = Path(__file__).with_name("plan.svg")
parts: list[str] = []


def n(value: float) -> str:
    return f"{value:g}"


def add(value: str) -> None:
    parts.append(value)


def line(x1: float, y1: float, x2: float, y2: float, kind: str) -> None:
    add(
        f'<line class="{kind}" x1="{n(x1)}" y1="{n(y1)}" '
        f'x2="{n(x2)}" y2="{n(y2)}"/>'
    )


def label(x: float, y: float, value: str, kind: str = "note", **attrs: str) -> None:
    extra = "".join(f' {name.replace("_", "-")}="{escape(item)}"' for name, item in attrs.items())
    add(f'<text class="{kind}" x="{n(x)}" y="{n(y)}"{extra}>{escape(value)}</text>')


def hdim(x1: float, x2: float, y: float, value: str, size: float = 17) -> None:
    line(x1, y, x2, y, "dimension")
    add(
        f'<path class="arrow" d="M{n(x1)} {n(y)} L{n(x1 + 11)} {n(y - 5)} '
        f'V{n(y + 5)} Z M{n(x2)} {n(y)} L{n(x2 - 11)} {n(y - 5)} '
        f'V{n(y + 5)} Z"/>'
    )
    label((x1 + x2) / 2, y - 8, value, "dimension-text", style=f"font-size:{n(size)}px")


def vdim(x: float, y1: float, y2: float, value: str, *, side: str = "left", size: float = 17) -> None:
    line(x, y1, x, y2, "dimension")
    add(
        f'<path class="arrow" d="M{n(x)} {n(y1)} L{n(x - 5)} {n(y1 + 11)} '
        f'H{n(x + 5)} Z M{n(x)} {n(y2)} L{n(x - 5)} {n(y2 - 11)} '
        f'H{n(x + 5)} Z"/>'
    )
    offset = -9 if side == "left" else 23
    midpoint = (y1 + y2) / 2
    add(
        f'<text class="dimension-text" transform="translate({n(x + offset)} '
        f'{n(midpoint)}) rotate(-90)" style="font-size:{n(size)}px">'
        f'{escape(value)}</text>'
    )


add('''<svg xmlns="http://www.w3.org/2000/svg" width="1900" height="1710" viewBox="0 0 1900 1710" role="img" aria-labelledby="title desc">
  <title id="title">Обмерный план квартиры, вид сверху</title>
  <desc id="desc">Весь план квартиры в чёрно-белом стиле обмерного чертежа. Балкон сверху, зал с кухней слева, спальня справа, ванная справа внизу. Главный вход внизу между кухней и ванной. Вход в спальню из кухни, вход в ванную через левую стену ванной. Подписанные размеры в сантиметрах, неизвестные привязки пунктиром.</desc>
  <style>
    text { font-family: Arial, Helvetica, sans-serif; fill: #111; }
    .heading { font-size: 42px; font-weight: 400; }
    .room { font-size: 26px; font-weight: 600; text-anchor: middle; }
    .room-sub { font-size: 16px; text-anchor: middle; }
    .note { font-size: 16px; }
    .small-note { font-size: 13px; }
    .dimension-text { font-size: 17px; text-anchor: middle; }
    .wall { fill: none; stroke: #111; stroke-width: 4; stroke-linecap: square; stroke-linejoin: miter; }
    .window { fill: none; stroke: #111; stroke-width: 1.8; }
    .dimension { fill: none; stroke: #111; stroke-width: 1.45; }
    .guide { fill: none; stroke: #111; stroke-width: 1.1; stroke-dasharray: 6 5; }
    .uncertain { fill: none; stroke: #111; stroke-width: 2.2; stroke-dasharray: 7 5; }
    .arrow { fill: #111; }
  </style>
  <rect width="1900" height="1710" fill="#fff"/>
  <text x="95" y="65" class="heading">ПЛАН КВАРТИРЫ СВЕРХУ</text>
  <text x="1410" y="63" class="note" style="font-size:23px">Размеры в сантиметрах</text>
  <g transform="translate(270 300) scale(1.55)">''')

# Balcony and measured balcony-side walls.
add('<rect class="window" x="0" y="-92" width="616" height="76"/>')
label(308, -64, "БАЛКОН · 8,05 м²", "room-sub")
label(158.25, -31, "проём ≈176,5", "small-note", text_anchor="middle")
label(458.9, -31, "проём ≈176,8", "small-note", text_anchor="middle")
add('<path class="wall" d="M0 0 H70 M246.5 0 H305 M320 0 H370.5 M547.3 0 H616"/>')
add('<path class="window" d="M70 -4 H246.5 M70 4 H246.5 M370.5 -4 H547.3 M370.5 4 H547.3"/>')
label(35, 25, "70", "small-note", text_anchor="middle")
label(276, 25, "58,5", "small-note", text_anchor="middle")
label(345, 25, "50,5", "small-note", text_anchor="middle")
label(581, 25, "68,7", "small-note", text_anchor="middle")
for x in (0, 305, 320, 616):
    line(x, -154, x, -106, "guide")
hdim(0, 305, -128, "305")
hdim(320, 616, -128, "296")

# Living room with kitchen. The return toward the bedroom remains schematic.
add('<path class="wall" d="M0 0 V770.5 M305 0 V426.5 M0 770.5 H337 M445 770.5 H457"/>')
add('<path class="uncertain" d="M305 426.5 H320 M305 426.5 V440"/>')
label(152, 212, "ЗАЛ + КУХНЯ", "room")
label(152, 235, "28,26 м² по застройщику", "room-sub")
label(111, 573, "КУХОННАЯ ЗОНА", "note", text_anchor="middle")
label(365, 714, "ВХОД В КВАРТИРУ", "note", text_anchor="middle")
label(388, 751, "ширина ?", "small-note", text_anchor="middle")
line(-45, 0, 0, 0, "guide")
line(-45, 552, 0, 552, "guide")
line(-112, 770.5, 0, 770.5, "guide")
vdim(-64, 0, 552, "552")
vdim(-105, 0, 770.5, "770,5*", size=15)
vdim(278, 0, 426.5, "426,5", size=15)
line(0, 770.5, 0, 840, "guide")
line(457, 770.5, 457, 840, "guide")
hdim(0, 457, 816, "457")
label(166, 752, "участок стены 337", "small-note", text_anchor="middle")

# Blender places the kitchen niche on the left wall near the apartment entrance.
# The 218.3 cm clear span and 30.7 cm projection are measured; the y placement is provisional.
add('<path class="wall" d="M0 534.2 H30.7 V546.2 H0"/>')
add('<path class="uncertain" d="M30.7 546.2 V764.5"/>')
line(0, 522, 0, 534.2, "guide")
line(30.7, 522, 30.7, 534.2, "guide")
hdim(0, 30.7, 520, "30,7", size=12)
line(30.7, 546.2, 76, 546.2, "guide")
line(30.7, 764.5, 76, 764.5, "guide")
vdim(69, 546.2, 764.5, "218,3", side="right", size=15)
label(160, 638, "НИША КУХНИ", "note", text_anchor="middle")
label(160, 660, "высота 267,5", "small-note", text_anchor="middle")

# Bedroom, with passage from the kitchen on the left of the niche.
add('<path class="wall" d="M320 0 V426 M616 0 V505.5 M441.5 426 V505.5"/>')
add('<path class="uncertain" d="M441.5 505.5 H616"/>')
label(466, 205, "СПАЛЬНЯ", "room")
label(466, 228, "14,51 м² по застройщику", "room-sub")
vdim(343, 0, 426, "426", side="right", size=15)
line(616, 0, 656, 0, "guide")
line(616, 505.5, 656, 505.5, "guide")
vdim(648, 0, 505.5, "505,5", side="right", size=16)
line(320, 398, 320, 426, "guide")
line(441.5, 398, 441.5, 426, "guide")
hdim(320, 441.5, 395, "121,5", size=15)
label(379, 456, "проход из кухни", "small-note", text_anchor="middle")
label(528, 454, "НИША", "note", text_anchor="middle")
hdim(451, 610, 490, "175,5*", size=14)

# Bathroom follows the corrected square-step drawing. The 1 cm closure is accepted.
add('<path class="wall" d="M457 516 H638 V747.5 H559.5 V770.5 H457 V682 M457 516 V584.5"/>')
label(548, 615, "ВАННАЯ", "room", style="font-size:21px")
label(548, 638, "4,45 м² по застройщику", "room-sub", style="font-size:12px")
label(390, 641, "ВХОД В ВАННУЮ", "small-note", text_anchor="middle")
label(390, 658, "≈97,5", "small-note", text_anchor="middle")
line(457, 516, 457, 547, "guide")
line(638, 516, 638, 547, "guide")
hdim(457, 638, 542, "181", size=15)
line(638, 516, 670, 516, "guide")
line(638, 747.5, 670, 747.5, "guide")
vdim(662, 516, 747.5, "231,5", side="right", size=14)
line(457, 770.5, 457, 804, "guide")
line(559.5, 770.5, 559.5, 804, "guide")
line(638, 747.5, 638, 804, "guide")
hdim(457, 559.5, 790, "102,5", size=14)
hdim(559.5, 638, 790, "77,5", size=13)
label(535, 741, "23,5", "small-note", text_anchor="middle")
label(477, 566, "68,5", "small-note")
label(477, 740, "88,5", "small-note")

add('</g>')

# Notes for the placed niche: its location follows the provisional Blender model.
label(1400, 326, "КУХОННАЯ НИША", "note", style="font-size:29px")
label(1400, 382, "Слева у входа, как в модели Blender.", "note", style="font-size:21px")
label(1400, 420, "Вдоль стены: 218,3 см.", "note", style="font-size:22px")
label(1400, 458, "Выступ внутрь кухни: 30,7 см.", "note", style="font-size:22px")
label(1400, 496, "Высота под балкой: 267,5 см.", "note", style="font-size:22px")
label(1400, 550, "Место вдоль стены - предварительное.", "note", style="font-size:21px")
label(1400, 597, "3370 на чертеже: если мм, то 337 см.", "note", style="font-size:20px")
label(1400, 630, "2675 вдоль плана - нужен ответ,", "note", style="font-size:20px")
label(1400, 659, "длина ли это по полу.", "note", style="font-size:20px")

label(1400, 755, "НИША СПАЛЬНИ", "note", style="font-size:29px")
label(1400, 806, "Задняя стенка: 175,5 см.", "note", style="font-size:23px")
label(1400, 846, "Глубина по эскизу: 93,5 см*.", "note", style="font-size:23px")
label(1400, 886, "Проход из кухни: 121,5 см.", "note", style="font-size:23px")
label(1400, 957, "* Разница длинных стен даёт 79,5 см.", "note", style="font-size:21px")
label(1400, 990, "Положение задней стенки нужно уточнить.", "note", style="font-size:21px")

label(1400, 1097, "ВАННАЯ", "note", style="font-size:29px")
label(1400, 1144, "Вход через левую стену.", "note", style="font-size:23px")
label(1400, 1184, "Справа внизу уступ: 23,5 и 77,5 см.", "note", style="font-size:23px")
label(1400, 1224, "Высота: 306 см. Допуск: ±1 см.", "note", style="font-size:23px")

line(1390, 1327, 1840, 1327, "dimension")
label(1400, 1384, "Сплошная линия - стена.", "note", style="font-size:22px")
label(1400, 1423, "Разрыв - вход или балконная дверь.", "note", style="font-size:22px")
label(1400, 1462, "Пунктир - край балки или примерная привязка.", "note", style="font-size:21px")

label(95, 1644, "* Общая длина зала 770,5 см и глубина ниши спальни требуют проверки точек отсчёта.", "note", style="font-size:22px")
label(95, 1680, "Размеры ванной: принят допуск ±1 см. Проёмы с ≈ вычислены по участкам стены.", "note", style="font-size:22px")
add('</svg>')

OUT.write_text("\n".join(parts) + "\n", encoding="utf-8")
