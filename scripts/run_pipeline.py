"""
Полный пайплайн ежедневного обновления дашборда IMOEX.

Порядок:
  1. Fetch данных: IMOEX+USDRUB, Brent, ОФЗ 5Y, CNY/RUB, USDCNY
  2. Fetch геополитических рынков: Polymarket, Kalshi
  3. Собрать очищенные факторы (imoex_factors.csv)
  4. Оценить базовую модель (model_imoex.py)
  5. Построить синтетический индекс (synthetic_index.py)
  6. Построить дашборд (build_dashboard_v2.py)
  7. Добавить синтетический блок (add_synthetic_to_dashboard.py)
  8. Убрать backtest (remove_backtest.py) и лишние блоки (cleanup_dashboard.py)

Всё пишется в $WORKDIR (по умолчанию /home/user/workspace).
GitHub Actions запускает с WORKDIR=$GITHUB_WORKSPACE/data.
"""
import os
import sys
import subprocess
import time
from pathlib import Path

WORKDIR = os.environ.get("WORKDIR", str(Path(__file__).parent.parent / "data"))
SCRIPTS_DIR = Path(__file__).parent
os.makedirs(WORKDIR, exist_ok=True)
os.environ["WORKDIR"] = WORKDIR

print(f"=== IMOEX Dashboard Pipeline ===")
print(f"WORKDIR: {WORKDIR}")
print(f"Scripts: {SCRIPTS_DIR}")
print()

steps = [
    ("Fetch IMOEX & USD/RUB", "fetch_imoex_usdrub.py"),
    ("Fetch Brent",           "fetch_brent.py"),
    ("Fetch OFZ 5Y",          "fetch_ofz5y.py"),
    ("Fetch FX alternatives", "fetch_fx_alternatives.py"),
    ("Rebuild with CNY/RUB",  "rebuild_with_cnyrub.py"),
    ("Fetch Polymarket",      "fetch_polymarket2.py"),
    ("Fetch Kalshi",          "kalshi_analysis.py"),
    ("Model IMOEX",           "model_imoex.py"),
    ("Synthetic index",       "synthetic_index.py"),
    ("Build dashboard v2",    "build_dashboard_v2.py"),
    ("Add synthetic block",   "add_synthetic_to_dashboard.py"),
    ("Remove backtest",       "remove_backtest.py"),
    ("Cleanup dashboard",     "cleanup_dashboard.py"),
]

failed = []
t_start = time.time()
for label, script in steps:
    path = SCRIPTS_DIR / script
    if not path.exists():
        print(f"[SKIP] {label} — no {script}")
        continue
    print(f"[RUN]  {label} ({script})")
    t0 = time.time()
    try:
        result = subprocess.run(
            [sys.executable, str(path)],
            cwd=WORKDIR,
            capture_output=True,
            text=True,
            timeout=600,
        )
        dt = time.time() - t0
        if result.returncode == 0:
            print(f"[OK]   {label} — {dt:.1f}s")
        else:
            print(f"[FAIL] {label} — exit {result.returncode}, {dt:.1f}s")
            print(f"       stdout tail: {result.stdout[-400:]}")
            print(f"       stderr tail: {result.stderr[-400:]}")
            failed.append(label)
    except subprocess.TimeoutExpired:
        print(f"[TIMEOUT] {label} — >600s")
        failed.append(label)
    except Exception as e:
        print(f"[ERROR] {label} — {e}")
        failed.append(label)
    print()

# Копируем финальный HTML в корень репо, где его подхватит Pages
dashboard = Path(WORKDIR) / "IMOEX_model_dashboard.html"
if dashboard.exists():
    target = Path(__file__).parent.parent / "index.html"
    target.write_bytes(dashboard.read_bytes())
    print(f"[COPY] {dashboard} -> {target}")

dt = time.time() - t_start
print(f"=== Total: {dt:.1f}s, failed: {len(failed)} ===")
if failed:
    print("Failed steps:", failed)
    # Не падаем — данные могут быть частично устаревшими,
    # но дашборд лучше показывать старую версию, чем ошибку
    sys.exit(0 if dashboard.exists() else 1)
