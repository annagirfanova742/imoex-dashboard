"""
Убираем из дашборда все бэктест-связанные секции:
  - Текущий сигнал S4 (это торговый сигнал бэктест-стратегии)
  - Бэктест торговых стратегий (таблица метрик)
  - График 'Бэктест: equity curves'
  - График 'Сигналы S4 во времени'
"""
import re

import os as _os
WORKDIR = _os.environ.get("WORKDIR", "/home/user/workspace")

with open(f"{WORKDIR}/IMOEX_model_dashboard.html","r",encoding="utf-8") as f:
    html = f.read()

start_len = len(html)
print(f"До: {start_len:,} символов")

def remove_h2_section(html, heading_text):
    pattern = rf'<h2[^>]*>[^<]*{re.escape(heading_text)}[^<]*</h2>.*?(?=<h2|<div class="section"|</body>)'
    new_html, n = re.subn(pattern, '', html, flags=re.DOTALL)
    print(f"  удалено h2 '{heading_text}': {n}")
    return new_html

def remove_h3_section(html, heading_text):
    pattern = rf'<h3[^>]*>[^<]*{re.escape(heading_text)}[^<]*</h3>.*?(?=<h[23]|<div class="section"|</body>)'
    new_html, n = re.subn(pattern, '', html, flags=re.DOTALL)
    print(f"  удалено h3 '{heading_text}': {n}")
    return new_html

# 1. Текущий сигнал S4 (это по сути бэктест-стратегия)
print("\n[1] Убираем 'Текущий сигнал S4'")
html = remove_h2_section(html, "Текущий сигнал S4")

# 2. Бэктест торговых стратегий (таблица)
print("\n[2] Убираем 'Бэктест торговых стратегий'")
html = remove_h2_section(html, "Бэктест торговых стратегий")

# 3. График equity curves
print("\n[3] Убираем график 'Бэктест: equity curves'")
html = remove_h3_section(html, "Бэктест: equity curves")

# 4. Сигналы S4 во времени
print("\n[4] Убираем 'Сигналы S4 во времени'")
html = remove_h3_section(html, "Сигналы S4 во времени")

# Перенумеровываем оставшиеся заголовки в блоке Графики
print("\n[5] Перенумеровываем графики")
graphs_section = re.search(r'(<h2[^>]*>[^<]*Графики[^<]*</h2>)(.*?)(?=<h2|<div class="section"|</body>)',
                            html, flags=re.DOTALL)
if graphs_section:
    inner = graphs_section.group(2)
    h3s = re.findall(r'<h3[^>]*>(\d+)\.\s*([^<]+)</h3>', inner)
    print(f"  найдено h3 в 'Графики': {len(h3s)}")
    for i, (old_num, title) in enumerate(h3s, 1):
        old = f'<h3>{old_num}. {title}</h3>'
        new = f'<h3>{i}. {title}</h3>'
        if old in inner:
            inner = inner.replace(old, new, 1)
    html = html[:graphs_section.start(2)] + inner + html[graphs_section.end(2):]

end_len = len(html)
print(f"\nПосле: {end_len:,} символов")
print(f"Удалено: {start_len - end_len:,} символов ({(start_len-end_len)/start_len*100:.1f}%)")

print("\n=== Оставшиеся заголовки ===")
for m in re.finditer(r'<h[123][^>]*>([^<]+)</h[123]>', html):
    print(f"  {m.group(0)[:100]}")

with open(f"{WORKDIR}/IMOEX_model_dashboard.html","w",encoding="utf-8") as f:
    f.write(html)
print("\nСохранено")
