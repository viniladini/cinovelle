"""Gera arte vetorial local para as obras fictícias, sem serviços externos."""
from html import escape
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.services.demo import ROWS


def generate():
    directory = ROOT / 'app' / 'static' / 'posters'
    directory.mkdir(parents=True, exist_ok=True)
    palettes = [('#252c35','#b6947b','#d4b99a'),('#24312f','#839a82','#d3c9a6'),
                ('#192d40','#8c9ca5','#e0d2ba'),('#3d2833','#a87d81','#e7ccbb'),
                ('#202e49','#c98871','#e5cfb4'),('#32313e','#c4ac8c','#e7d8bb')]
    for index, row in enumerate(ROWS, 1):
        bg, mid, light = palettes[(index - 1) % len(palettes)]
        title = row[1]
        words = title.split()
        lines, line = [], ''
        for word in words:
            if len(line + word) > 17:
                lines.append(line.strip())
                line = ''
            line += word + ' '
        lines.append(line.strip())
        text = ''.join(f'<text x="200" y="{430 + n * 35}" text-anchor="middle" fill="{light}" font-family="Georgia,serif" font-size="30">{escape(line)}</text>' for n, line in enumerate(lines))
        motif = index % 4
        if motif == 1:
            art = f'<circle cx="230" cy="205" r="100" fill="{mid}"/><path d="M0 390 L155 210 L225 310 L295 180 L400 350 V600 H0Z" fill="{bg}"/><path d="M170 150 V395 M198 155 V395 M226 155 V395" stroke="{bg}" stroke-width="13" opacity=".75"/><path d="M0 365 Q200 310 400 365" stroke="{light}" fill="none" opacity=".4"/>'
        elif motif == 2:
            art = f'<path d="M68 390 V165 Q200 15 332 165 V390Z" fill="{mid}"/><path d="M100 390 V180 Q200 65 300 180 V390Z" fill="{bg}"/><circle cx="200" cy="230" r="73" fill="{light}" opacity=".7"/><path d="M0 380 L400 280 V400 H0Z" fill="{bg}"/><path d="M200 220 L200 390" stroke="{mid}" stroke-width="2"/>'
        elif motif == 3:
            art = f'<circle cx="200" cy="220" r="110" stroke="{mid}" fill="none" stroke-width="1"/><ellipse cx="200" cy="220" rx="160" ry="55" stroke="{light}" fill="none" transform="rotate(-35 200 220)"/><circle cx="200" cy="220" r="65" fill="{mid}"/><circle cx="302" cy="130" r="13" fill="{light}"/><path d="M90 330 L140 380 M110 310 L160 360 M130 290 L180 340" stroke="{light}" opacity=".4"/>'
        else:
            art = f'<path d="M0 345 Q50 120 125 250 T275 200 T400 120 V400 H0Z" fill="{mid}" opacity=".5"/><circle cx="265" cy="150" r="55" fill="{light}"/><path d="M0 375 Q100 200 200 315 T400 260 V400 H0Z" fill="{mid}"/><path d="M200 395 Q100 280 210 160 Q300 300 200 395" fill="{bg}"/><path d="M200 390 L210 205" stroke="{light}" stroke-width="1"/>'
        svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="400" height="600" viewBox="0 0 400 600"><rect width="400" height="600" fill="{bg}"/><rect x="19" y="19" width="362" height="562" fill="none" stroke="{mid}" opacity=".35"/><text x="200" y="55" text-anchor="middle" fill="{light}" font-family="sans-serif" font-size="8" letter-spacing="4">CINOVELLE · IMAGINED STORIES</text>{art}{text}<text x="200" y="551" text-anchor="middle" fill="{light}" font-family="sans-serif" font-size="8" letter-spacing="2">{row[3]} · {'UMA SÉRIE' if row[0] == 'tv' else 'UM FILME'} · FICÇÃO DEMONSTRATIVA</text></svg>'''
        (directory / f'{index}.svg').write_text(svg, encoding='utf-8')


if __name__ == '__main__':
    generate()
    print('18 pôsteres demonstrativos gerados.')
