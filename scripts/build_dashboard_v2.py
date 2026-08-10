"""
Собирает автономный HTML-дашборд с интерактивным сценарным блоком.
Слайдеры Brent / USD/RUB / ОФЗ 5Y и горизонт в JS считают прогноз IMOEX
по коэффициентам моделей A и B из model_results.json.
"""
import json
import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
import plotly.io as pio

import os as _os
WORKDIR = _os.environ.get("WORKDIR", "/home/user/workspace")

df = pd.read_csv(f"{WORKDIR}/imoex_model_output.csv", parse_dates=["date"])
wf = pd.read_csv(f"{WORKDIR}/walkforward.csv", parse_dates=["date"])
equity = pd.read_csv(f"{WORKDIR}/backtest_equity.csv", parse_dates=["date"])
metrics = pd.read_csv(f"{WORKDIR}/backtest_metrics.csv")
positions = pd.read_csv(f"{WORKDIR}/backtest_positions.csv", parse_dates=["date"])
expanding = pd.read_csv(f"{WORKDIR}/expanding_model.csv", parse_dates=["date"])

with open(f"{WORKDIR}/model_results.json") as f:
    res = json.load(f)
with open(f"{WORKDIR}/scenario_results.json") as f:
    scen = json.load(f)
with open(f"{WORKDIR}/backtest_summary.json") as f:
    bt = json.load(f)

RANGESEL = dict(buttons=list([
    dict(count=1, label="1М", step="month", stepmode="backward"),
    dict(count=3, label="3М", step="month", stepmode="backward"),
    dict(count=6, label="6М", step="month", stepmode="backward"),
    dict(count=1, label="YTD", step="year", stepmode="todate"),
    dict(count=1, label="1Г", step="year", stepmode="backward"),
    dict(count=5, label="5Л", step="year", stepmode="backward"),
    dict(step="all", label="Всё"),
]))
CRISIS = "2022-02-24"

# ==================== Fig 1: панели факторов ====================
fig1 = make_subplots(
    rows=4, cols=1, shared_xaxes=True, vertical_spacing=0.04,
    subplot_titles=("IMOEX", "Brent × USD/RUB (сглаженная 3М)", "USD/RUB", "ОФЗ 5Y, %"),
    row_heights=[0.28, 0.24, 0.24, 0.24],
)
fig1.add_trace(go.Scatter(x=df["date"], y=df["imoex"], name="IMOEX",
                          line=dict(color="#1f77b4", width=1.4)), row=1, col=1)
fig1.add_trace(go.Scatter(x=df["date"], y=df["brent_rub_ma3m"], name="Brent×USDRUB, MA3M",
                          line=dict(color="#d62728", width=1.4)), row=2, col=1)
fig1.add_trace(go.Scatter(x=df["date"], y=df["brent_rub"], name="Brent×USDRUB (без сглаж.)",
                          line=dict(color="#d62728", width=0.6, dash="dot"), opacity=0.4), row=2, col=1)
fig1.add_trace(go.Scatter(x=df["date"], y=df["usdrub"], name="USD/RUB",
                          line=dict(color="#2ca02c", width=1.4)), row=3, col=1)
fig1.add_trace(go.Scatter(x=df["date"], y=df["ofz5y"], name="ОФЗ 5Y",
                          line=dict(color="#9467bd", width=1.4)), row=4, col=1)
for i in range(1, 5):
    fig1.add_vline(x=CRISIS, line_dash="dash", line_color="gray", opacity=0.5, row=i, col=1)
fig1.update_xaxes(rangeslider=dict(visible=True, thickness=0.04), rangeselector=RANGESEL, row=4, col=1)
fig1.update_layout(height=900, hovermode="x unified", showlegend=False,
                   margin=dict(l=60, r=30, t=40, b=60),
                   title="Факторы модели IMOEX (2014–2026), пунктиром — 24.02.2022")

# ==================== Fig 2: факт vs модель ====================
fig2 = go.Figure()
fig2.add_trace(go.Scatter(x=df["date"], y=df["imoex"], name="IMOEX факт", line=dict(color="#1f77b4", width=1.8)))
fig2.add_trace(go.Scatter(x=df["date"], y=df["fair_value_A"], name="Модель A", line=dict(color="#ff7f0e", width=1.4, dash="dash")))
fig2.add_trace(go.Scatter(x=df["date"], y=df["fair_value_B"], name="Модель B (со сдвигом)", line=dict(color="#2ca02c", width=1.4)))
fig2.add_vline(x=CRISIS, line_dash="dash", line_color="gray", opacity=0.5)
fig2.update_xaxes(rangeslider=dict(visible=True, thickness=0.05), rangeselector=RANGESEL)
fig2.update_layout(height=520, hovermode="x unified", title="Фактический vs справедливый IMOEX",
                   yaxis_title="Пункты", legend=dict(orientation="h", y=-0.25, x=0.5, xanchor="center"),
                   margin=dict(l=60, r=30, t=60, b=80))

# ==================== Fig 3: отклонение ====================
fig3 = go.Figure()
fig3.add_trace(go.Scatter(x=df["date"], y=df["deviation_A"]*100, name="Отклонение A", line=dict(color="#ff7f0e", width=1.4)))
fig3.add_trace(go.Scatter(x=df["date"], y=df["deviation_B"]*100, name="Отклонение B", line=dict(color="#2ca02c", width=1.4)))
fig3.add_hline(y=0, line_dash="dot", line_color="gray")
fig3.add_vline(x=CRISIS, line_dash="dash", line_color="gray", opacity=0.5)
fig3.update_xaxes(rangeslider=dict(visible=True, thickness=0.05), rangeselector=RANGESEL)
fig3.update_layout(height=440, hovermode="x unified",
                   title="Отклонение IMOEX от справедливого значения",
                   yaxis_title="%", legend=dict(orientation="h", y=-0.3, x=0.5, xanchor="center"),
                   margin=dict(l=60, r=30, t=60, b=80))

# ==================== Fig 4: walk-forward ====================
mD = res["model_D_walkforward"]
fig4 = go.Figure()
fig4.add_trace(go.Scatter(x=wf["date"], y=wf["imoex_actual"], name="Факт", line=dict(color="#1f77b4", width=1.8)))
fig4.add_trace(go.Scatter(x=wf["date"], y=wf["imoex_pred_ecm"], name="Прогноз ECM (t+1)", line=dict(color="#d62728", width=1.2, dash="dash")))
fig4.add_trace(go.Scatter(x=wf["date"], y=wf["imoex_pred_rw"], name="Random walk (t)", line=dict(color="#7f7f7f", width=1.0, dash="dot")))
fig4.update_xaxes(rangeslider=dict(visible=True, thickness=0.05), rangeselector=RANGESEL)
fig4.update_layout(height=500, hovermode="x unified",
                   title=f"Walk-forward: RMSE_log ECM={mD['rmse_log_ecm']:.4f} vs RW={mD['rmse_log_random_walk']:.4f}, hit={mD['direction_hit_rate_ecm']:.1%}",
                   yaxis_title="IMOEX", legend=dict(orientation="h", y=-0.25, x=0.5, xanchor="center"),
                   margin=dict(l=60, r=30, t=70, b=80))

# ==================== Fig 5: скользящие коэффициенты ====================
window = 252
rolling = []
log_imoex = np.log(df["imoex"].values)
log_oil = np.log(df["brent_rub_ma3m"].values)
ofz = df["ofz5y"].values
for i in range(window, len(df)):
    yw = log_imoex[i-window:i]
    Xw = np.column_stack([np.ones(window), log_oil[i-window:i], ofz[i-window:i]])
    beta, *_ = np.linalg.lstsq(Xw, yw, rcond=None)
    rolling.append((df["date"].iloc[i], beta[0], beta[1], beta[2]))
roll = pd.DataFrame(rolling, columns=["date","const","beta_oil","beta_ofz"])

fig5 = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.06,
                     subplot_titles=("β при log(Brent×USDRUB, MA3M)", "β при ОФЗ 5Y"))
fig5.add_trace(go.Scatter(x=roll["date"], y=roll["beta_oil"], line=dict(color="#d62728", width=1.4)), row=1, col=1)
fig5.add_hline(y=res["model_A"]["coefficients"]["log_brent_rub_ma3m"]["value"], line_dash="dot", line_color="black", row=1, col=1)
fig5.add_trace(go.Scatter(x=roll["date"], y=roll["beta_ofz"], line=dict(color="#9467bd", width=1.4)), row=2, col=1)
fig5.add_hline(y=res["model_A"]["coefficients"]["ofz5y"]["value"], line_dash="dot", line_color="black", row=2, col=1)
fig5.add_vline(x=CRISIS, line_dash="dash", line_color="gray", opacity=0.5, row=1, col=1)
fig5.add_vline(x=CRISIS, line_dash="dash", line_color="gray", opacity=0.5, row=2, col=1)
fig5.update_xaxes(rangeslider=dict(visible=True, thickness=0.04), rangeselector=RANGESEL, row=2, col=1)
fig5.update_layout(height=620, hovermode="x unified", showlegend=False,
                   title="Скользящие коэффициенты модели A (окно 252 дня)",
                   margin=dict(l=60, r=30, t=60, b=60))

# ==================== Fig 6: Бэктест — equity curves ====================
sel_strats = ["BH_buy_hold", "RF_ofz", "S4_long_thr3_rate_filter",
              "S1_long_thr3", "S1_long_thr10", "S2_ls_thr5", "S3_prop_sc10"]
labels = {
    "BH_buy_hold": "Buy & Hold IMOEX",
    "RF_ofz": "ОФЗ 5Y (кэш)",
    "S4_long_thr3_rate_filter": "S4: long dev<-3% + ставка стабильна",
    "S1_long_thr3": "S1: long dev<-3%",
    "S1_long_thr10": "S1: long dev<-10%",
    "S2_ls_thr5": "S2: long/short |dev|>5%",
    "S3_prop_sc10": "S3: пропорц., scale=10%",
}
colors = {
    "BH_buy_hold": "#1f77b4",
    "RF_ofz": "#7f7f7f",
    "S4_long_thr3_rate_filter": "#2ca02c",
    "S1_long_thr3": "#ff7f0e",
    "S1_long_thr10": "#e377c2",
    "S2_ls_thr5": "#d62728",
    "S3_prop_sc10": "#9467bd",
}
# Стартуем equity curves после burn-in (первые 1000 дней — NaN в expanding)
mask_bt = equity["date"] >= pd.Timestamp("2018-01-01")
eq_bt = equity.loc[mask_bt].reset_index(drop=True)
# Нормализуем на начало периода
for col in sel_strats:
    eq_bt[col] = eq_bt[col] / eq_bt[col].iloc[0]

fig6 = go.Figure()
for s in sel_strats:
    fig6.add_trace(go.Scatter(x=eq_bt["date"], y=eq_bt[s], name=labels[s],
                              line=dict(color=colors[s], width=1.6 if s == "S4_long_thr3_rate_filter" else 1.2)))
fig6.update_xaxes(rangeslider=dict(visible=True, thickness=0.05), rangeselector=RANGESEL)
fig6.update_layout(height=520, hovermode="x unified",
                   title="Бэктест: equity curves (нормировано на 2018-01-01)",
                   yaxis_title="Множитель капитала",
                   legend=dict(orientation="h", y=-0.25, x=0.5, xanchor="center"),
                   margin=dict(l=60, r=30, t=60, b=80))

# ==================== Fig 7: позиции S4 vs отклонение ====================
fig7 = make_subplots(rows=2, cols=1, shared_xaxes=True, vertical_spacing=0.08,
                     subplot_titles=("Отклонение от fair value (expanding, модель A)", "Позиция стратегии S4"),
                     row_heights=[0.6, 0.4])
mask_exp = expanding["fair_expanding"].notna()
fig7.add_trace(go.Scatter(x=expanding.loc[mask_exp, "date"],
                          y=expanding.loc[mask_exp, "deviation_pct"],
                          line=dict(color="#1f77b4", width=1.2)), row=1, col=1)
fig7.add_hline(y=-3, line_dash="dash", line_color="#2ca02c", row=1, col=1, annotation_text="порог -3%")
fig7.add_hline(y=0, line_dash="dot", line_color="gray", row=1, col=1)

# Позиция S4
pos_s4 = positions[["date", "position_S1_thr3"]].copy()  # S1_thr3 не то, нужен S4
# Пересчитаем позицию S4 из expanding
merged = expanding.merge(df[["date","ofz5y"]], on="date", how="left", suffixes=("","_y"))
merged["ofz_20d"] = merged["ofz5y"].diff(20)
merged["pos_S4"] = ((merged["deviation_pct"] < -3) & (merged["ofz_20d"] <= 0.5)).astype(int)
fig7.add_trace(go.Scatter(x=merged["date"], y=merged["pos_S4"],
                          line=dict(color="#2ca02c", width=1.4, shape="hv"), fill="tozeroy",
                          fillcolor="rgba(44,160,44,0.2)"), row=2, col=1)
fig7.update_xaxes(rangeslider=dict(visible=True, thickness=0.04), rangeselector=RANGESEL, row=2, col=1)
fig7.update_yaxes(title_text="%", row=1, col=1)
fig7.update_yaxes(title_text="LONG=1 / CASH=0", range=[-0.1, 1.1], row=2, col=1)
fig7.update_layout(height=650, hovermode="x unified", showlegend=False,
                   title="Сигналы S4: когда стратегия в LONG",
                   margin=dict(l=60, r=30, t=60, b=60))

def fig_to_div(fig, div_id):
    return pio.to_html(fig, include_plotlyjs=False, full_html=False, div_id=div_id)

# ==================== Данные для JS-калькулятора сценариев ====================
mA_c = res["model_A"]["coefficients"]
mB_c = res["model_B"]["coefficients"]
mC = res["model_C_ECM"]

# Коэффициенты моделей + текущее состояние в JS
js_data = {
    "model_A": {
        "const": mA_c["const"]["value"],
        "b_oil": mA_c["log_brent_rub_ma3m"]["value"],
        "b_ofz": mA_c["ofz5y"]["value"],
    },
    "model_B": {
        "const": mB_c["const"]["value"],
        "b_oil": mB_c["log_brent_rub_ma3m"]["value"],
        "b_ofz": mB_c["ofz5y"]["value"],
        "post": mB_c["post2022"]["value"],
        "b_oil_post": mB_c["oil_post"]["value"],
        "b_ofz_post": mB_c["ofz_post"]["value"],
    },
    "gamma": abs(mC["coefficients"]["ect"]["value"]),
    "current": {
        "date": scen["starting"]["date"],
        "imoex": scen["starting"]["imoex"],
        "brent": scen["starting"]["brent"],
        "usdrub": scen["starting"]["usdrub"],
        "brent_rub_ma3m_now": res["fair_value_now"]["inputs"]["brent_rub_ma3m"],
        "ofz5y": scen["starting"]["ofz5y"],
        "fair_A": scen["starting"]["fair_A"],
        "fair_B": scen["starting"]["fair_B"],
        "dev_A": scen["starting"]["dev_A_pct"],
        "dev_B": scen["starting"]["dev_B_pct"],
    }
}

# ==================== Сборка HTML ====================
mA = res["model_A"]; mB = res["model_B"]; mC = res["model_C_ECM"]
mD = res["model_D_walkforward"]; fv = res["fair_value_now"]
eg = res["engle_granger"]

# Сводка моделей
summary_html = f"""
<div class="summary">
<h2>Результаты моделей</h2>
<table>
<tr><th>Параметр</th><th>Модель A</th><th>Модель B (со сдвигом)</th></tr>
<tr><td>n набл.</td><td>{mA['n_obs']}</td><td>{mB['n_obs']}</td></tr>
<tr><td>R²</td><td>{mA['r_squared']:.4f}</td><td>{mB['r_squared']:.4f}</td></tr>
<tr><td>β log(Brent×USDRUB)</td><td>{mA['coefficients']['log_brent_rub_ma3m']['value']:+.4f}</td><td>{mB['coefficients']['log_brent_rub_ma3m']['value']:+.4f}</td></tr>
<tr><td>β ОФЗ 5Y</td><td>{mA['coefficients']['ofz5y']['value']:+.4f}</td><td>{mB['coefficients']['ofz5y']['value']:+.4f}</td></tr>
<tr><td>ofz × post-2022</td><td>—</td><td>{mB['coefficients']['ofz_post']['value']:+.3f}</td></tr>
<tr><td>Const</td><td>{mA['coefficients']['const']['value']:+.3f}</td><td>{mB['coefficients']['const']['value']:+.3f}</td></tr>
</table>
<p><b>ECM:</b> γ = {mC['coefficients']['ect']['value']:+.5f}, полураспад ≈ <b>{mC['half_life_days']:.0f} дней</b>.
<b>Walk-forward:</b> ECM обыгрывает Random Walk по RMSE на 14%, hit rate {mD['direction_hit_rate_ecm']:.1%}.</p>
</div>
"""

# Бэктест таблица
metrics_sorted = metrics.sort_values("sharpe", ascending=False)
bt_rows = ""
for _, row in metrics_sorted.iterrows():
    strat_class = "highlight" if row["strategy"] == "S4_long_thr3_rate_filter" else ""
    bt_rows += f"""<tr class="{strat_class}">
<td>{row['name']}</td>
<td>{row['CAGR_pct']:+.2f}%</td>
<td>{row['sharpe']:.2f}</td>
<td>{row['max_drawdown_pct']:.1f}%</td>
<td>{row['vol_ann_pct']:.1f}%</td>
<td>{row['total_return_pct']:+.1f}%</td>
</tr>"""

backtest_html = f"""
<div class="summary">
<h2>Бэктест торговых стратегий (2018–2026, expanding window)</h2>
<p>Модель на каждый день переоценивается только по прошлым данным.
Комиссия round-trip 0.1%. Кэш всегда сидит в ОФЗ по годовой ставке.</p>
<table>
<tr><th>Стратегия</th><th>CAGR</th><th>Sharpe</th><th>MaxDD</th><th>Vol ann.</th><th>Total ret.</th></tr>
{bt_rows}
</table>
<p><b>Ключевой вывод:</b> long/short варианты (S2, S3) убыточны — модель почти всегда сигналит «дорого»
из-за структурного разрыва 2022, шорт получает отрицательное carry. Long-only с фильтром по стабильности
ставки (<b>S4</b>) — единственная стратегия с осмысленным Sharpe > 1 при MaxDD 16%.</p>
</div>
"""

# Текущий сигнал S4
sig_dev = -5.98
sig_ofz_20d = -0.45
sig_html = f"""
<div class="summary signal-block">
<h2>Текущий сигнал S4 на {scen['starting']['date']}</h2>
<div class="signal-status">СИГНАЛ: <span class="long">LONG (100% IMOEX)</span></div>
<table>
<tr><th>Условие</th><th>Значение</th><th>Порог</th><th>Статус</th></tr>
<tr><td>Отклонение от fair value (модель A, expanding)</td>
    <td><b>{sig_dev:+.2f}%</b></td><td>&lt; −3%</td><td class="ok">✓ Выполнено</td></tr>
<tr><td>Δ ОФЗ 5Y за 20 дней</td>
    <td><b>{sig_ofz_20d:+.2f} п.п.</b></td><td>≤ +0.5 п.п.</td><td class="ok">✓ Выполнено</td></tr>
</table>
<p>Это второй эпизод входа в LONG за всю историю: первый — 15.04.2022 после февральского обвала,
второй начался 22.05.2026 и продолжается. За последние 252 торговых дня стратегия провела в LONG 34 дня (13.5%).</p>
</div>
"""

# Сценарии — таблица + матрица
matrix_rows = ""
brent_grid = [55, 60, 65, 70, 75, 80, 85, 90]
ofz_grid = [10, 12, 14, 15.5, 17, 19]
# Считаем на лету
def project_A(brent_rub_ma3m, ofz5y, dev_now, gamma, days):
    log_fair = mA_c["const"]["value"] + mA_c["log_brent_rub_ma3m"]["value"] * np.log(brent_rub_ma3m) + mA_c["ofz5y"]["value"] * ofz5y
    fair = np.exp(log_fair)
    dev_end = dev_now * np.exp(-gamma * days)
    return fair * (1 + dev_end)

gamma = abs(mC["coefficients"]["ect"]["value"])
dev_A_now = scen["starting"]["dev_A_pct"] / 100
brent_rub_now = res["fair_value_now"]["inputs"]["brent_rub_ma3m"]

matrix_rows_html = ""
for brent in brent_grid:
    row = f"<tr><td><b>${brent}</b></td>"
    for ofz in ofz_grid:
        brent_rub = (brent_rub_now + brent * scen["starting"]["usdrub"]) / 2
        imoex_end = project_A(brent_rub, ofz, dev_A_now, gamma, 126)
        ret = (imoex_end / scen["starting"]["imoex"] - 1) * 100
        color = "#2ca02c" if ret > 5 else ("#d62728" if ret < -5 else "#333")
        row += f'<td style="color:{color}">{ret:+.1f}%</td>'
    row += "</tr>"
    matrix_rows_html += row

ofz_carry = scen["ofz_carry_6m_pct"]

named_scen_rows = ""
for r in scen["scenarios_6m"]:
    named_scen_rows += f"""<tr>
<td><b>{r['name']}</b></td>
<td>${r['brent']:.0f}</td><td>{r['usdrub']:.0f}</td><td>{r['ofz5y']:.1f}%</td>
<td>{r['return_6m_A_ecm']:+.1f}%</td>
<td>{r['return_6m_A_full']:+.1f}%</td>
<td>{r['return_6m_B_ecm']:+.1f}%</td>
</tr>"""

scenario_html = f"""
<div class="summary">
<h2>Сценарный анализ доходности IMOEX</h2>
<p>Прогноз: fair value по модели пересчитывается на новые Brent × USD/RUB × ОФЗ,
плюс частичное закрытие текущего отклонения по ECM с γ = {gamma:.5f} (полураспад ≈ 290 дней).
За 3М закрывается 14%, за 6М — 26%, за 12М — 45% отклонения.</p>

<h3>Матрица доходности IMOEX за 6 месяцев (модель A, USD/RUB = 82.75)</h3>
<table class="matrix">
<tr><th>Brent \\ ОФЗ 5Y</th>{"".join(f"<th>{o:.1f}%</th>" for o in ofz_grid)}</tr>
{matrix_rows_html}
</table>
<p><small>Зелёный: доходность &gt; +5%. Красный: &lt; −5%. Ставка ОФЗ — главный драйвер:
снижение на 3.5 п.п. добавляет ~14 п.п. к доходности.</small></p>

<h3>Именованные сценарии (горизонт 6 месяцев)</h3>
<table>
<tr><th>Сценарий</th><th>Brent</th><th>USD/RUB</th><th>ОФЗ 5Y</th>
    <th>Мод A + ECM</th><th>Мод A + full reversion</th><th>Мод B + ECM</th></tr>
{named_scen_rows}
</table>
<p>Столбец «ECM» — реалистичный (26% отклонения за 6М). «Full reversion» — верхняя граница upside.
Взвешенная доходность по A+ECM: <b>+5.13%</b>. Carry в ОФЗ 5Y за 6М: <b>+{ofz_carry:.2f}%</b>.</p>
</div>
"""

# Интерактивный сценарный калькулятор
interactive_html = f"""
<div class="summary interactive">
<h2>Интерактивный сценарный калькулятор</h2>
<p>Двигайте слайдеры и смотрите, как меняется прогноз IMOEX и ожидаемая доходность.
Расчёт в реальном времени по коэффициентам моделей A и B.</p>

<div class="calc-grid">
  <div class="slider-group">
    <label>Brent, $/барр: <span id="brent-val">{scen['starting']['brent']:.1f}</span></label>
    <input type="range" id="brent" min="40" max="120" step="0.5" value="{scen['starting']['brent']:.1f}">
    <div class="slider-labels"><span>$40</span><span>$120</span></div>
  </div>
  <div class="slider-group">
    <label>USD/RUB: <span id="usdrub-val">{scen['starting']['usdrub']:.2f}</span></label>
    <input type="range" id="usdrub" min="60" max="120" step="0.25" value="{scen['starting']['usdrub']:.2f}">
    <div class="slider-labels"><span>60</span><span>120</span></div>
  </div>
  <div class="slider-group">
    <label>ОФЗ 5Y, %: <span id="ofz-val">{scen['starting']['ofz5y']:.2f}</span></label>
    <input type="range" id="ofz" min="5" max="22" step="0.1" value="{scen['starting']['ofz5y']:.2f}">
    <div class="slider-labels"><span>5%</span><span>22%</span></div>
  </div>
  <div class="slider-group">
    <label>Горизонт, дней: <span id="horizon-val">126</span> (<span id="horizon-months">6</span>М)</label>
    <input type="range" id="horizon" min="21" max="504" step="21" value="126">
    <div class="slider-labels"><span>1М</span><span>2 года</span></div>
  </div>
</div>

<div class="calc-results">
  <div class="result-card">
    <div class="result-label">IMOEX сейчас</div>
    <div class="result-value">{scen['starting']['imoex']:,.0f}</div>
  </div>
  <div class="result-card">
    <div class="result-label">Fair value (A) на конец периода</div>
    <div class="result-value" id="fair-A">—</div>
  </div>
  <div class="result-card">
    <div class="result-label">Fair value (B) на конец периода</div>
    <div class="result-value" id="fair-B">—</div>
  </div>
  <div class="result-card highlight-card">
    <div class="result-label">Прогноз IMOEX (модель A)</div>
    <div class="result-value" id="imoex-proj-A">—</div>
    <div class="result-sub" id="ret-A">—</div>
  </div>
  <div class="result-card highlight-card">
    <div class="result-label">Прогноз IMOEX (модель B)</div>
    <div class="result-value" id="imoex-proj-B">—</div>
    <div class="result-sub" id="ret-B">—</div>
  </div>
  <div class="result-card">
    <div class="result-label">Реверсия отклонения</div>
    <div class="result-value" id="reversion">—</div>
    <div class="result-sub" id="reversion-sub">за выбранный горизонт</div>
  </div>
</div>

<div class="preset-buttons">
  <button onclick="setPreset(55,100,17,126)">Пессимистичный</button>
  <button onclick="setPreset(68,92,14,126)">Базовый</button>
  <button onclick="setPreset(80,85,12,126)">Оптимистичный</button>
  <button onclick="setPreset({scen['starting']['brent']:.1f},{scen['starting']['usdrub']:.2f},{scen['starting']['ofz5y']:.2f},126)">Статус-кво</button>
</div>
</div>

<script>
const M = {json.dumps(js_data, ensure_ascii=False)};

function project(brent, usdrub, ofz, days) {{
  const brent_rub = brent * usdrub;
  const brent_rub_ma3m = (M.current.brent_rub_ma3m_now + brent_rub) / 2;
  const log_oil = Math.log(brent_rub_ma3m);

  // Модель A
  const log_fair_A = M.model_A.const + M.model_A.b_oil * log_oil + M.model_A.b_ofz * ofz;
  const fair_A = Math.exp(log_fair_A);

  // Модель B (post-2022 режим)
  const log_fair_B = M.model_B.const + M.model_B.b_oil * log_oil + M.model_B.b_ofz * ofz
                     + M.model_B.post + M.model_B.b_oil_post * log_oil + M.model_B.b_ofz_post * ofz;
  const fair_B = Math.exp(log_fair_B);

  // Реверсия
  const remaining = Math.exp(-M.gamma * days);
  const dev_A_now = M.current.dev_A / 100;
  const dev_B_now = M.current.dev_B / 100;

  const dev_A_end = dev_A_now * remaining;
  const dev_B_end = dev_B_now * remaining;

  const imoex_A = fair_A * (1 + dev_A_end);
  const imoex_B = fair_B * (1 + dev_B_end);

  return {{fair_A, fair_B, imoex_A, imoex_B, reversion: (1 - remaining) * 100}};
}}

function update() {{
  const brent = parseFloat(document.getElementById('brent').value);
  const usdrub = parseFloat(document.getElementById('usdrub').value);
  const ofz = parseFloat(document.getElementById('ofz').value);
  const days = parseInt(document.getElementById('horizon').value);

  document.getElementById('brent-val').textContent = brent.toFixed(1);
  document.getElementById('usdrub-val').textContent = usdrub.toFixed(2);
  document.getElementById('ofz-val').textContent = ofz.toFixed(2);
  document.getElementById('horizon-val').textContent = days;
  document.getElementById('horizon-months').textContent = (days / 21).toFixed(1);

  const r = project(brent, usdrub, ofz, days);
  const imoex_now = M.current.imoex;

  document.getElementById('fair-A').textContent = r.fair_A.toLocaleString('ru-RU', {{maximumFractionDigits: 0}});
  document.getElementById('fair-B').textContent = r.fair_B.toLocaleString('ru-RU', {{maximumFractionDigits: 0}});
  document.getElementById('imoex-proj-A').textContent = r.imoex_A.toLocaleString('ru-RU', {{maximumFractionDigits: 0}});
  document.getElementById('imoex-proj-B').textContent = r.imoex_B.toLocaleString('ru-RU', {{maximumFractionDigits: 0}});

  const ret_A = (r.imoex_A / imoex_now - 1) * 100;
  const ret_B = (r.imoex_B / imoex_now - 1) * 100;

  document.getElementById('ret-A').textContent = (ret_A >= 0 ? '+' : '') + ret_A.toFixed(2) + '%';
  document.getElementById('ret-A').style.color = ret_A >= 0 ? '#2ca02c' : '#d62728';
  document.getElementById('ret-B').textContent = (ret_B >= 0 ? '+' : '') + ret_B.toFixed(2) + '%';
  document.getElementById('ret-B').style.color = ret_B >= 0 ? '#2ca02c' : '#d62728';

  document.getElementById('reversion').textContent = r.reversion.toFixed(1) + '%';
}}

function setPreset(brent, usdrub, ofz, days) {{
  document.getElementById('brent').value = brent;
  document.getElementById('usdrub').value = usdrub;
  document.getElementById('ofz').value = ofz;
  document.getElementById('horizon').value = days;
  update();
}}

document.getElementById('brent').addEventListener('input', update);
document.getElementById('usdrub').addEventListener('input', update);
document.getElementById('ofz').addEventListener('input', update);
document.getElementById('horizon').addEventListener('input', update);
update();
</script>
"""

# Финальный вывод
final_html = f"""
<div class="summary">
<h2>Итоговые выводы</h2>
<ul>
<li><b>Рублёвая нефть — доминирующий драйвер IMOEX</b> с эластичностью 0.65–0.78. ОФЗ 5Y — вторичный.</li>
<li><b>После 24.02.2022 связь IMOEX с ОФЗ фактически исчезла</b> — коэффициент упал с −0.09 до +0.02.
Это статистически подтверждённый структурный разрыв.</li>
<li><b>Долгосрочная коинтеграция на границе значимости</b> (Engle-Granger p=0.017),
возврат к равновесию медленный — полураспад ≈ 290 дней.</li>
<li><b>Стратегия «покупать под fair value» работает только в long-only варианте</b>
с фильтром по стабильности ставки (S4). Long/short варианты убыточны из-за постоянного шорт-сигнала
и отрицательного carry.</li>
<li><b>Сейчас S4 в LONG</b> (второй раз за 8 лет). Ожидаемая доходность за 6М по базовому сценарию
+5–6%, что примерно на 1.5 п.п. ниже безрискового carry в ОФЗ (+7.4%).</li>
<li><b>Асимметрия риска в пользу лонга:</b> при снижении ставки до 12% и Brent $80
потенциал +17%, при худшем сценарии −9%. Ставка на смягчение ДКП — ключевой триггер.</li>
</ul>
</div>
"""

html = f"""<!DOCTYPE html>
<html lang="ru"><head>
<meta charset="utf-8">
<title>Модель IMOEX: полный анализ и сценарии — Perplexity Computer</title>
<script src="https://cdn.plot.ly/plotly-2.35.2.min.js" charset="utf-8"></script>
<style>
body {{ font-family: -apple-system, "Segoe UI", Roboto, sans-serif; margin: 0 auto; max-width: 1400px; padding: 20px; color: #222; background: #fafafa; }}
h1 {{ color: #1a3a5c; border-bottom: 2px solid #1a3a5c; padding-bottom: 8px; }}
h2 {{ color: #1a3a5c; margin-top: 32px; }}
h3 {{ color: #333; margin-top: 20px; }}
.summary {{ background: white; padding: 20px 30px; border-radius: 8px; box-shadow: 0 1px 3px rgba(0,0,0,0.08); margin: 16px 0; }}
table {{ border-collapse: collapse; margin: 10px 0; width: 100%; }}
th, td {{ border: 1px solid #ddd; padding: 6px 12px; text-align: left; font-size: 14px; }}
th {{ background: #f0f4f8; }}
tr.highlight {{ background: #fff3cd; font-weight: 600; }}
table.matrix td {{ text-align: center; font-family: "SF Mono", Monaco, monospace; font-size: 13px; }}
table.matrix th {{ text-align: center; }}
small {{ color: #666; font-size: 12px; }}
.plot {{ background: white; padding: 10px; border-radius: 8px; margin: 16px 0; box-shadow: 0 1px 3px rgba(0,0,0,0.08); }}

.signal-block {{ border-left: 4px solid #2ca02c; }}
.signal-status {{ font-size: 18px; margin: 10px 0; }}
.signal-status .long {{ color: #2ca02c; font-weight: bold; font-size: 22px; }}
td.ok {{ color: #2ca02c; font-weight: 600; }}

.interactive {{ border-left: 4px solid #1a3a5c; }}
.calc-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 20px; margin: 20px 0; }}
.slider-group {{ background: #f8f9fa; padding: 12px 16px; border-radius: 6px; }}
.slider-group label {{ display: block; font-weight: 600; margin-bottom: 8px; font-size: 14px; }}
.slider-group label span {{ color: #1a3a5c; font-family: "SF Mono", Monaco, monospace; }}
.slider-group input[type=range] {{ width: 100%; }}
.slider-labels {{ display: flex; justify-content: space-between; font-size: 11px; color: #888; margin-top: 4px; }}

.calc-results {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 12px; margin: 20px 0; }}
.result-card {{ background: #f0f4f8; padding: 14px 18px; border-radius: 6px; text-align: center; }}
.result-card.highlight-card {{ background: #e7f3ff; border: 2px solid #1a3a5c; }}
.result-label {{ font-size: 12px; color: #666; margin-bottom: 6px; }}
.result-value {{ font-size: 22px; font-weight: bold; color: #1a3a5c; font-family: "SF Mono", Monaco, monospace; }}
.result-sub {{ font-size: 14px; margin-top: 4px; font-family: "SF Mono", Monaco, monospace; }}

.preset-buttons {{ margin-top: 16px; text-align: center; }}
.preset-buttons button {{ margin: 0 6px; padding: 8px 16px; background: #1a3a5c; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; }}
.preset-buttons button:hover {{ background: #2c5282; }}
</style>
</head><body>

<h1>Модель IMOEX: анализ факторов, бэктест стратегий и сценарии</h1>

<div class="summary">
<p><b>Данные:</b> 3 147 дневных наблюдений с 03.02.2014 по 10.08.2026 с MOEX ISS.
<b>Спецификация:</b> ln(IMOEX) = c + β₁·ln(Brent×USD/RUB, MA3M) + β₂·ОФЗ5Y + ε.
HAC-стандартные ошибки с 20 лагами.</p>
</div>

{sig_html}

{interactive_html}

{scenario_html}

{summary_html}

{backtest_html}

<h2>Графики</h2>

<div class="plot"><h3>1. Факторы модели</h3>{fig_to_div(fig1, "fig1")}</div>
<div class="plot"><h3>2. Фактический vs модельный IMOEX</h3>{fig_to_div(fig2, "fig2")}</div>
<div class="plot"><h3>3. Отклонение от справедливого значения</h3>{fig_to_div(fig3, "fig3")}</div>
<div class="plot"><h3>4. Walk-forward валидация ECM</h3>{fig_to_div(fig4, "fig4")}</div>
<div class="plot"><h3>5. Скользящие коэффициенты (окно 252 дня)</h3>{fig_to_div(fig5, "fig5")}
<p>На панели β_ofz виден сдвиг после 24.02.2022: до этой даты коэффициент устойчиво отрицательный,
после — колеблется вокруг нуля.</p></div>
<div class="plot"><h3>6. Бэктест: equity curves</h3>{fig_to_div(fig6, "fig6")}
<p>S4 (зелёная) — единственная стратегия, обыгравшая buy & hold с приемлемым риском.
ОФЗ 5Y как «безрисковый» бенчмарк опережает всех — период 2018–2026 был провальным для IMOEX.</p></div>
<div class="plot"><h3>7. Сигналы S4 во времени</h3>{fig_to_div(fig7, "fig7")}
<p>Всего два эпизода LONG за 8 лет: апрель 2022 и май–август 2026.</p></div>

{final_html}

<p style="text-align:center; color:#888; margin-top:40px; font-size:12px;">
Данные: MOEX ISS. Расчёт: OLS с HAC, ECM, walk-forward валидация, expanding-window бэктест.
</p>
</body></html>
"""

with open(f"{WORKDIR}/IMOEX_model_dashboard.html", "w", encoding="utf-8") as f:
    f.write(html)
print(f"saved IMOEX_model_dashboard.html, size {len(html)/1024:.0f} KB")
