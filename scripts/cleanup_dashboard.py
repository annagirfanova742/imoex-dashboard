"""
Убираем из дашборда лишние секции без прямых торговых выводов:
  1. Скользящие коэффициенты (окно 252 дня)
  2. Очистка USD/RUB после санкций OFAC
  3. Три версии стыковки — таблица сравнения (внутри блока синт индекса)
  4. Результаты моделей (методологическая таблица)
  5. Фактический vs модельный IMOEX (дублирует отклонение)
  6. Матрица доходности IMOEX за 6М (дублирует калькулятор)

Также убираем связанные графики и подписи в навигации.
Оставляем: сигнал S4, калькулятор, именованные сценарии, бэктест,
факторы, отклонение, walk-forward, equity curves, синт индекс (упрощённый).
"""
import re

import os as _os
WORKDIR = _os.environ.get("WORKDIR", "/home/user/workspace")

with open(f"{WORKDIR}/IMOEX_model_dashboard.html","r",encoding="utf-8") as f:
    html = f.read()

start_len = len(html)
print(f"До: {start_len:,} символов")

# ================================================================
# Функция: удаляет секцию <h2>...</h2> вместе со всем содержимым
# до следующего <h2> или </body>
# ================================================================
def remove_h2_section(html, heading_text):
    # Ищем <h2> содержащий heading_text и удаляем всё до следующего <h2> или </body>
    pattern = rf'<h2[^>]*>[^<]*{re.escape(heading_text)}[^<]*</h2>.*?(?=<h2|<div class="section"|</body>)'
    new_html, n = re.subn(pattern, '', html, flags=re.DOTALL)
    print(f"  удалено секций '{heading_text}': {n}")
    return new_html

# Функция: удаляет <div class="section" id="X">...</div> целиком
def remove_section_by_id(html, section_id):
    pattern = rf'<div class="section" id="{section_id}">.*?(?=<div class="section"|</body>)'
    new_html, n = re.subn(pattern, '', html, flags=re.DOTALL)
    print(f"  удалено секций id={section_id}: {n}")
    return new_html

# Функция: удаляет h3 с его подсодержимым до следующего h2/h3
def remove_h3_section(html, heading_text):
    pattern = rf'<h3[^>]*>[^<]*{re.escape(heading_text)}[^<]*</h3>.*?(?=<h[23]|<div class="section"|</body>)'
    new_html, n = re.subn(pattern, '', html, flags=re.DOTALL)
    print(f"  удалено h3 '{heading_text}': {n}")
    return new_html

# ================================================================
# 1. Убираем блок "Очистка USD/RUB" (отдельная секция id=fx-cleanup)
# ================================================================
print("\n[1] Убираем 'Очистка USD/RUB'")
html = remove_section_by_id(html, "fx-cleanup")

# ================================================================
# 2. Убираем "Результаты моделей" — h2 в основном дашборде
# ================================================================
print("\n[2] Убираем 'Результаты моделей'")
html = remove_h2_section(html, "Результаты моделей")

# ================================================================
# 3. Убираем h3 "Скользящие коэффициенты (окно 252 дня)" со графиком
# ================================================================
print("\n[3] Убираем 'Скользящие коэффициенты'")
html = remove_h3_section(html, "Скользящие коэффициенты")

# ================================================================
# 4. Убираем h3 "Фактический vs модельный IMOEX"
# ================================================================
print("\n[4] Убираем 'Фактический vs модельный'")
html = remove_h3_section(html, "Фактический vs модельный IMOEX")

# ================================================================
# 5. Убираем h3 "Матрица доходности IMOEX за 6 месяцев"
# ================================================================
print("\n[5] Убираем 'Матрица доходности'")
html = remove_h3_section(html, "Матрица доходности IMOEX")

# ================================================================
# 6. Внутри блока "Синтетический геополитический индекс":
#    убираем h3 "Три версии стыковки — сравнение"
# ================================================================
print("\n[6] Убираем 'Три версии стыковки — сравнение'")
html = remove_h3_section(html, "Три версии стыковки — сравнение")

# ================================================================
# 7. Убираем плитку "Медианный сдвиг" и график "Три версии стыковки" (fig2)
#    внутри блока синт индекса
# ================================================================
print("\n[7] Убираем плитку 'Медианный сдвиг'")
# Удаляем metric-card с "Медианный сдвиг"
html = re.sub(
    r'<div class="metric-card">\s*<div class="metric-label">Медианный сдвиг</div>.*?</div>\s*</div>',
    '', html, flags=re.DOTALL, count=1)

print("\n[8] Убираем график 'synth_versions' (три версии стыковки)")
html = re.sub(
    r'<div class="chart-container">[^<]*<div[^>]*id="synth_versions"[^>]*>.*?</div>\s*</div>\s*</div>',
    '', html, flags=re.DOTALL, count=1)
# Fallback: убираем весь div, содержащий synth_versions
html = re.sub(
    r'<div[^>]*id="synth_versions"[^>]*>.*?</div>(\s*</div>)?',
    '', html, flags=re.DOTALL, count=1)

# ================================================================
# 9. Удаляем ссылки в навигации на убранные секции
# ================================================================
print("\n[9] Чистим навигацию")
for nav_text in ["Очистка USD/RUB", "Результаты моделей", "fx-cleanup"]:
    html = re.sub(
        rf'<a href="[^"]*"[^>]*>{re.escape(nav_text)}</a>',
        '', html)

# ================================================================
# 10. Перенумеровываем заголовки графиков (если остались "3.", "4." и т.д.)
# ================================================================
print("\n[10] Перенумеровываем оставшиеся h3 графики")
# Находим блок "Графики" и заголовки внутри
graphs_section = re.search(r'(<h2[^>]*>[^<]*Графики[^<]*</h2>)(.*?)(?=<h2|<div class="section"|</body>)',
                            html, flags=re.DOTALL)
if graphs_section:
    inner = graphs_section.group(2)
    # Находим все h3 с номером в начале
    h3s = re.findall(r'<h3[^>]*>(\d+)\.\s*([^<]+)</h3>', inner)
    print(f"  найдено h3 в 'Графики': {len(h3s)}")
    for i, (old_num, title) in enumerate(h3s, 1):
        old = f'<h3>{old_num}. {title}</h3>'
        new = f'<h3>{i}. {title}</h3>'
        if old in inner:
            inner = inner.replace(old, new, 1)
    html = html[:graphs_section.start(2)] + inner + html[graphs_section.end(2):]

# Финал
end_len = len(html)
print(f"\nПосле: {end_len:,} символов")
print(f"Удалено: {start_len - end_len:,} символов ({(start_len-end_len)/start_len*100:.1f}%)")

# Финальный список h2/h3
print("\n=== Оставшиеся заголовки ===")
for m in re.finditer(r'<h[123][^>]*>([^<]+)</h[123]>', html):
    print(f"  {m.group(0)[:100]}")

with open(f"{WORKDIR}/IMOEX_model_dashboard.html","w",encoding="utf-8") as f:
    f.write(html)
print(f"\nСохранено")
