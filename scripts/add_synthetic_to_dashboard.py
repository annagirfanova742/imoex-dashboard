"""
Строит блок с синтетическим индексом и добавляет в существующий IMOEX_model_dashboard.html.
"""
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import json

import os as _os
WORKDIR = _os.environ.get("WORKDIR", "/home/user/workspace")

synth = pd.read_csv(f"{WORKDIR}/synthetic_index.csv", parse_dates=["date"])
merged = pd.read_csv(f"{WORKDIR}/synthetic_index_merged.csv", parse_dates=["date"])
fv_ext = pd.read_csv(f"{WORKDIR}/fair_value_extended.csv", parse_dates=["date"])

# === График 1: синтетический индекс vs IMOEX ===
fig1 = make_subplots(specs=[[{"secondary_y": True}]])
poly_part = synth[synth["source"]=="polymarket"]
kalshi_part = synth[synth["source"]=="kalshi"]

fig1.add_trace(go.Scatter(x=poly_part["date"], y=poly_part["p_synthetic_raw"]*100,
    name="Polymarket ceasefire (до 2026-05-08)", line=dict(color="#1f77b4", width=1.6)), secondary_y=False)
fig1.add_trace(go.Scatter(x=kalshi_part["date"], y=kalshi_part["p_synthetic_raw"]*100,
    name="Kalshi Zelensky-Putin (с 2026-05-09)", line=dict(color="#ff7f0e", width=1.6)), secondary_y=False)

fig1.add_trace(go.Scatter(x=merged["date"], y=merged["imoex"],
    name="IMOEX", line=dict(color="#2ca02c", width=1.4)), secondary_y=True)

fig1.add_vline(x=pd.Timestamp("2026-05-08"), line=dict(color="red", dash="dash", width=1.5),
               annotation_text="точка сшивания", annotation_position="top")

fig1.update_layout(title="Синтетический геополитический индекс vs IMOEX",
    hovermode="x unified", height=440, template="plotly_white",
    legend=dict(orientation="h", y=-0.15))
fig1.update_yaxes(title_text="Вероятность, %", secondary_y=False, range=[0, 100])
fig1.update_yaxes(title_text="IMOEX", secondary_y=True)

# === График 2: три версии стыковки на общем окне ===
fig2 = go.Figure()
fig2.add_trace(go.Scatter(x=synth["date"], y=synth["p_synthetic_raw"], name="RAW",
    line=dict(color="#1f77b4", width=1.5)))
if "p_synthetic_lm" in synth.columns:
    # Level-match видна как продолжение — Kalshi сдвинут вниз на 0.245
    lm = synth.dropna(subset=["p_synthetic_lm"])
    fig2.add_trace(go.Scatter(x=lm["date"], y=lm["p_synthetic_lm"], name="LEVEL-MATCH (Kalshi сдвинут)",
        line=dict(color="#ff7f0e", width=1.5, dash="dot")))
# Z-score показывать в отдельной оси не нужно — покажем нормированный обратно к [0,1] для наглядности
if "p_synthetic_z" in synth.columns:
    z = synth.dropna(subset=["p_synthetic_z"]).copy()
    zmin, zmax = z["p_synthetic_z"].min(), z["p_synthetic_z"].max()
    z["p_z_scaled"] = (z["p_synthetic_z"] - zmin) / (zmax - zmin)
    fig2.add_trace(go.Scatter(x=z["date"], y=z["p_z_scaled"], name="Z-SCORE (нормировано на [0,1])",
        line=dict(color="#2ca02c", width=1.5, dash="dashdot")))

fig2.add_vline(x=pd.Timestamp("2026-05-08"), line=dict(color="red", dash="dash", width=1.5))
fig2.update_layout(title="Три версии стыковки синтетического индекса",
    hovermode="x unified", height=380, template="plotly_white",
    yaxis_title="Индекс",
    legend=dict(orientation="h", y=-0.2))

# === График 3: fair value с синтетическим фактором vs базовая ===
fig3 = go.Figure()
fig3.add_trace(go.Scatter(x=fv_ext["date"], y=fv_ext["imoex"], name="IMOEX факт",
    line=dict(color="#1f77b4", width=1.6)))
fig3.add_trace(go.Scatter(x=fv_ext["date"], y=fv_ext["fair_value_A"], name="Fair value базовый (oil+ofz)",
    line=dict(color="#7f7f7f", width=1.4, dash="dot")))
fig3.add_trace(go.Scatter(x=fv_ext["date"], y=fv_ext["fair_ext"], name="Fair value + синт. индекс",
    line=dict(color="#d62728", width=1.6)))
fig3.add_vline(x=pd.Timestamp("2026-05-08"), line=dict(color="red", dash="dash", width=1.2))
fig3.update_layout(title="Расширенная модель: fair value с синтетическим индексом",
    hovermode="x unified", height=440, template="plotly_white",
    yaxis_title="Значение",
    legend=dict(orientation="h", y=-0.15))

# === График 4: scatter Δp(20d) vs IMOEX(20d) ===
sub = merged.dropna(subset=["dp_20d","r_imoex_20d"])
from scipy import stats
r = stats.pearsonr(sub["dp_20d"], sub["r_imoex_20d"])
fig4 = go.Figure()
fig4.add_trace(go.Scatter(x=sub["dp_20d"]*100, y=sub["r_imoex_20d"]*100, mode="markers",
    marker=dict(size=4, color=sub["date"].astype(np.int64), colorscale="Viridis",
                colorbar=dict(title="Дата")),
    name="Δp / IMOEX 20d"))
# Линия регрессии
slope, intercept = np.polyfit(sub["dp_20d"], sub["r_imoex_20d"], 1)
xs = np.linspace(sub["dp_20d"].min(), sub["dp_20d"].max(), 100)
fig4.add_trace(go.Scatter(x=xs*100, y=(slope*xs+intercept)*100, mode="lines",
    line=dict(color="red", width=2), name=f"β={slope:.2f}"))
fig4.update_layout(title=f"Изменения синтетического индекса за 20 дней vs доходность IMOEX (r={r.statistic:+.3f}, p={r.pvalue:.1e})",
    xaxis_title="Δp за 20 дней, п.п.",
    yaxis_title="IMOEX 20d return, %",
    hovermode="closest", height=440, template="plotly_white")

# === Собираем HTML блок ===
html_block = f"""
<div class="section" id="synthetic-index">
  <h2>Синтетический геополитический индекс</h2>
  <div class="metric-grid">
    <div class="metric-card">
      <div class="metric-label">Источник до 08.05.2026</div>
      <div class="metric-value">Polymarket</div>
      <div class="metric-sub">6 склеенных ceasefire-рынков, 997 дней</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">Источник с 09.05.2026</div>
      <div class="metric-value">Kalshi</div>
      <div class="metric-sub">Zelensky-Putin meet by 2029, 94 дня</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">Значение сегодня</div>
      <div class="metric-value">33.5%</div>
      <div class="metric-sub">Kalshi last, dev к базовой модели −16.9%</div>
    </div>
    <div class="metric-card">
      <div class="metric-label">Медианный сдвиг</div>
      <div class="metric-value">−24.5 п.п.</div>
      <div class="metric-sub">Kalshi выше Polymarket на 167-дневном перекрытии</div>
    </div>
  </div>

  <div class="chart-container">{fig1.to_html(full_html=False, include_plotlyjs=False, div_id="synth_main")}</div>
  <div class="chart-container">{fig2.to_html(full_html=False, include_plotlyjs=False, div_id="synth_versions")}</div>
  <div class="chart-container">{fig3.to_html(full_html=False, include_plotlyjs=False, div_id="synth_fv")}</div>
  <div class="chart-container">{fig4.to_html(full_html=False, include_plotlyjs=False, div_id="synth_scatter")}</div>

  <h3>Три версии стыковки — сравнение</h3>
  <table class="stats-table">
    <thead><tr>
      <th>Версия</th>
      <th>Корр. с deviation_A</th>
      <th>Δ R² в регрессии</th>
      <th>β в регрессии</th>
      <th>t-stat</th>
      <th>Комментарий</th>
    </tr></thead>
    <tbody>
      <tr><td>RAW</td><td>+0.305</td><td>+0.003</td><td>+0.028</td><td>+0.34</td>
        <td>Ступенька на стыке ломает регрессию — уровни несопоставимы</td></tr>
      <tr><td>LEVEL-MATCH</td><td>+0.506</td><td>+0.068</td><td>+0.158</td><td>+3.24</td>
        <td>Kalshi сдвинут на −24.5 п.п., плавная стыковка</td></tr>
      <tr><td><b>Z-SCORE</b></td><td>+0.611</td><td><b>+0.161</b></td><td>+0.044</td><td>+4.59</td>
        <td>Лучшая по объясняющей силе — «относительный трек»</td></tr>
    </tbody>
  </table>

  <h3>Корреляции изменений (Z-SCORE устойчив, RAW тоже работает на изменениях)</h3>
  <table class="stats-table">
    <thead><tr><th>Пара</th><th>Pearson</th><th>p-value</th><th>n</th></tr></thead>
    <tbody>
      <tr><td>Δp 1 день vs Δlog(IMOEX)</td><td>+0.166</td><td>&lt;0.001</td><td>756</td></tr>
      <tr><td>Δp 5 дней vs IMOEX 5d ret</td><td>+0.240</td><td>&lt;0.001</td><td>752</td></tr>
      <tr><td><b>Δp 20 дней vs IMOEX 20d ret</b></td><td><b>+0.382</b></td><td>&lt;0.001</td><td>737</td></tr>
    </tbody>
  </table>

  <h3>Интерпретация текущего сигнала</h3>
  <div class="callout">
    <p>Расширенная модель (oil + ofz + z-нормированный геополитический индекс) даёт fair value <b>2,764</b> при факте <b>2,296</b> — отклонение <b>−16.9%</b>. Это больше, чем в базовой модели (−6%): рынок закладывает пониженную вероятность реальной деэскалации (33.5% на Kalshi против пиков 60%+ в марте 2026). Если геополитический трек к встрече лидеров развернётся в позитив, синтетический индекс объясняет <b>около 10 п.п. дополнительной доходности</b>.</p>
    <p>Однако важное замечание: Kalshi имеет всего 202 дня истории в модели, а его коэффициент отдельно (без Polymarket) был не значим. Расширенная спецификация работает благодаря длинной истории Polymarket 2023–2026. Прогноз на Kalshi-периоде — экстраполяция.</p>
  </div>
</div>
"""

# === Вставляем в существующий HTML ===
with open(f"{WORKDIR}/IMOEX_model_dashboard.html","r",encoding="utf-8") as f:
    dashboard = f.read()

# Вставляем перед </body>
if "id=\"synthetic-index\"" in dashboard:
    # Заменяем существующий блок
    import re
    dashboard = re.sub(
        r'<div class="section" id="synthetic-index">.*?</div>\s*(?=<div class="section"|</body>)',
        html_block, dashboard, flags=re.DOTALL)
else:
    # Добавляем перед </body>
    dashboard = dashboard.replace("</body>", html_block + "\n</body>")

# И добавим ссылку в навигацию, если есть
if 'href="#synthetic-index"' not in dashboard and '<nav' in dashboard:
    # Найдём nav и добавим ссылку
    import re
    dashboard = re.sub(
        r'(<nav[^>]*>[\s\S]*?</nav>)',
        lambda m: m.group(1).replace('</nav>',
            '<a href="#synthetic-index">Синт. индекс</a></nav>'),
        dashboard, count=1)

with open(f"{WORKDIR}/IMOEX_model_dashboard.html","w",encoding="utf-8") as f:
    f.write(dashboard)

print(f"Дашборд обновлён, размер {len(dashboard):,} символов")
