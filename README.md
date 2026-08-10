# IMOEX Dashboard

Автоматически обновляемый дашборд справедливой стоимости индекса Мосбиржи (IMOEX).

Живая версия: **https://annagirfanova742.github.io/imoex-dashboard/**

## Что это

Интерактивный статический HTML-дашборд с моделью fair value IMOEX:

- Спецификация модели: `ln(IMOEX) = c + β₁·ln(Brent×USD/RUB, MA3M) + β₂·ОФЗ5Y + ε`
- Данные с 2014 года по сегодня, ~3000 дневных наблюдений
- Интерактивный сценарный калькулятор (нефть в рублях, ОФЗ 5Y)
- Именованные сценарии (базовый/пессимист/оптимист)
- Walk-forward валидация ECM
- Синтетический геополитический индекс на основе Polymarket + Kalshi

## Автообновление

Ежедневно в **06:00 UTC (09:00 MSK)** через GitHub Actions:

1. Fetch данных: IMOEX, USD/RUB, Brent (фьючерсы MOEX FORTS), ОФЗ 5Y, CNY/RUB
2. Сбор факторов с очисткой USD/RUB после санкций OFAC (12.06.2024)
3. Оценка модели
4. Fetch Polymarket + Kalshi для синт. индекса
5. Сборка HTML-дашборда
6. Публикация на GitHub Pages

## Локальный запуск

```bash
pip install -r requirements.txt
WORKDIR=./data python scripts/run_pipeline.py
```

Результат: `index.html` в корне репо.

## Источники данных

- **MOEX ISS API** — IMOEX, USD/RUB (до 12.06.2024), Brent фьючерсы, CNY/RUB
- **CBR XML** — официальный курс USD/RUB после 12.06.2024
- **MOEX RGBITR + ставка** — доходность ОФЗ 5Y
- **Polymarket Gamma/CLOB API** — вероятности мира до 08.05.2026 (закрыт с YES)
- **Kalshi Elections API** — вероятности встречи Zelensky×Putin с 25.07.2025

## Структура

```
imoex-dashboard/
├── .github/workflows/update.yml  # cron 06:00 UTC ежедневно
├── scripts/
│   ├── run_pipeline.py           # главный оркестратор
│   ├── fetch_*.py                # загрузчики данных
│   ├── rebuild_with_cnyrub.py    # очистка USD/RUB
│   ├── model_imoex.py            # оценка модели
│   ├── synthetic_index.py        # Polymarket+Kalshi индекс
│   └── build_dashboard_v2.py     # сборка HTML
├── data/                          # cached CSV (обновляются в Actions)
├── index.html                     # финальный дашборд (deployed to Pages)
└── requirements.txt
```
