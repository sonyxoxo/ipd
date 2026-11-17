"""Повторяемое создание пяти учебных ноутбуков из проверенных ячеек."""

import json
from pathlib import Path
from hashlib import sha1


ROOT = Path(__file__).resolve().parents[1]
NOTEBOOK_DIR = ROOT / "ноутбуки python"


def markdown(content):
    return {"cell_type": "markdown", "id": sha1(("md" + content).encode()).hexdigest()[:8], "metadata": {}, "source": content.splitlines(keepends=True)}


def code(content):
    return {"cell_type": "code", "id": sha1(("py" + content).encode()).hexdigest()[:8], "metadata": {},
            "execution_count": None, "outputs": [], "source": content.splitlines(keepends=True)}


BOOTSTRAP = '''# Одна настройка пути к репозиторию. Исходные файлы не загружаются вручную.
from pathlib import Path
import subprocess
import sys

repo_dir = next((p for p in (Path.cwd(), *Path.cwd().parents) if (p / "ipd_analysis.py").is_file()), None)
if repo_dir is None:
    repo_dir = Path("/content/ipd")
    if not (repo_dir / "ipd_analysis.py").is_file():
        subprocess.run(["git", "clone", "--depth", "1", "https://github.com/sonyxoxo/ipd.git", str(repo_dir)], check=True)
sys.path.insert(0, str(repo_dir))

from ipd_analysis import choose_source, load_measurements, regular_minutes, result_folder, save_csv

# Если в data/raw несколько файлов, задайте относительный путь явно:
# source = choose_source("data/raw/household_power_consumption.zip")
source = choose_source()
measurements = load_measurements(source)  # Один pd.read_csv на весь ноутбук.
output_dir = result_folder(source)
output_dir.mkdir(parents=True, exist_ok=True)
print("Источник:", source)
print("Строк:", len(measurements))'''


NOTEBOOKS = {
    "первичный аудит данных.ipynb": [
        markdown('''# Этап 1. Первичный аудит исходных данных

Исходные измерения открываются **непосредственно из клона GitHub-репозитория**. Файл читается в `pandas` один раз. Ни одна ячейка не загружает файлы из интерфейса Google Colab.

## Параметры и переменные

- `repo_dir` — каталог клонированного репозитория `ipd`, в котором находится общий модуль анализа.
- `source` — полный путь к конкретному исходному TXT/CSV/TSV/ZIP в репозитории.
- `measurements` — исходные измерения в рабочей таблице `pandas`, где даты уже распознаны, а измерения преобразованы в числа.
- `output_dir` — отдельная папка результата именно этого файла; исходник в ней не изменяется.
- `timestamp` — дата и время соответствующего измерения.
- `Global_active_power` — средняя активная мощность за минуту в кВт.
- `valid_Global_active_power` — признак физически допустимого измерения мощности (`True` — корректно).

Если файлов несколько, раскройте одну строку `source = choose_source("data/raw/ИМЯ.csv")` и укажите файл. Для автоматического анализа всех файлов используйте `python run_analysis.py --all`.'''),
        code(BOOTSTRAP),
        markdown('''## Проверка формы и содержания таблицы

- `audit_table` — одна строка контроля: число строк, начало/конец ряда, повторные и неравномерные временные метки, отсутствующая мощность.
- `sample_rows` — первые десять строк, выбранные лишь для просмотра, а не для анализа вместо полного файла.
- `unknown_values` — словарь количества нечисловых значений по каждому исходному измеряемому столбцу. Значения `?` и пустые ячейки становятся `NaN`, а не нулём.

Контрольные показатели исходного UCI (2 075 259 строк, 25 979 отсутствующих мощностей) полезны для **сравнения**, но не блокируют анализ другого файла.'''),
        code('''from ipd_analysis import audit

audit_table = audit(measurements)
sample_rows = measurements.head(10)
unknown_values = measurements.attrs["unknown_values"]
display(audit_table)
display(sample_rows)
print("Нечисловые обозначения (кроме стандартных пропусков):", unknown_values)
save_csv(audit_table, output_dir / "01_audit.csv")'''),
        markdown('''## Проверка временной сетки

- `minutes` — таблица с **каждой ожидаемой минутой** между началом и концом записи.
- `missing_timestamp_rows` — сколько минут целиком отсутствует в исходном файле. Это **не то же самое**, что строка с `NaN` в мощности.
- `missing_measurements` — сколько минут не имеют пригодной активной мощности после учёта обоих видов пропусков.

Повторяющиеся временные метки сначала нужно исследовать: программа сообщит об ошибке, а не удалит повторы без вашего решения.'''),
        code('''minutes = regular_minutes(measurements)
missing_timestamp_rows = len(minutes) - len(measurements)
missing_measurements = int((~minutes["valid_Global_active_power"]).sum())
print("Пропущенных временных меток:", missing_timestamp_rows)
print("Минут без корректного измерения:", missing_measurements)'''),
    ],
    "проверка_времени_и_полноты_данных.ipynb": [
        markdown('''# Этап 2. Время и полнота измерений

Таблица считывается из репозитория **один раз**. Здесь оцениваются также минуты, для которых в файле вообще нет строки. Пропуски не восстанавливаются интерполяцией.

## Имена переменных

- `source` — файл в репозитории; `measurements` — все его измерения в `pandas`.
- `minutes` — полная минутная сетка от первой до последней даты.
- `output_dir` — папка результатов выбранного файла.
- `coverage_table` — полнота активной мощности по месяцам.
- `run_table` — непрерывные последовательности отсутствующих измерений.
- `expected_in_record` — число ожидаемых минут **внутри фактического периода записи**.
- `expected_calendar` — число минут целого календарного месяца, включая дни до начала или после конца файла.
- `valid_power` — число минут с пригодной активной мощностью.
- `coverage_record_pct` — доля пригодных минут в пределах периода записи, в процентах.
- `coverage_calendar_pct` — доля пригодных минут во всём календарном месяце, в процентах.
- `missing_or_invalid` — минуты с отсутствующей/непригодной мощностью.
- `crosses_month` — пересекает ли непрерывный пропуск границу месяца.'''),
        code(BOOTSTRAP),
        markdown('''## Расчёт полноты и последовательностей пропусков

Сначала `regular_minutes()` добавляет в **расчётную** таблицу отсутствующие временные метки. Обратите внимание: добавляются только строки со значениями `NaN`, не измеренные значения мощности.

`monthly_coverage()` не предполагает, что каждый файл содержит полный месяц. `missing_runs()` ищет непрерывные пропуски на единой временной сетке, поэтому пропуск между двумя соседними строками не теряется.'''),
        code('''from ipd_analysis import monthly_coverage, missing_runs

minutes = regular_minutes(measurements)
coverage_table = monthly_coverage(minutes)
run_table = missing_runs(minutes)
display(coverage_table)
display(run_table.head(10))
save_csv(coverage_table, output_dir / "02_monthly_coverage.csv")
save_csv(run_table, output_dir / "02_missing_runs.csv")
print("Всего минут без корректной мощности:", int(coverage_table["missing_or_invalid"].sum()))'''),
    ],
    "преобразование физических величин.ipynb": [
        markdown('''# Этап 3. Преобразование физических величин

Важно не путать **мощность** с **энергией**. Для средней мощности `P` за интервал в одну минуту энергия `E = P × (1/60 ч)`.

## Имена переменных и единицы измерения

- `source` — файл измерений в репозитории; `measurements` — его таблица в `pandas`.
- `minutes` — минутная сетка с явно отмеченными пропусками.
- `energy_table` — независимая рабочая копия с расчётными столбцами энергии.
- `Global_active_power` — средняя активная мощность за минуту, **кВт**.
- `active_energy_kwh` — энергия за конкретную минуту, **кВт·ч**, равна `Global_active_power / 60`.
- `Sub_metering_1`/`2`/`3` — энергия, зарегистрированная дополнительными счётчиками за минуту, **Вт·ч**.
- `sub_1_energy_kwh`, `sub_2_energy_kwh`, `sub_3_energy_kwh` — те же показания, переведённые в **кВт·ч** делением на 1000.
- `energy_columns` — список столбцов для сохранения: время и вычисленная энергия.

В UCI для `Global_reactive_power` подписано «киловатт», но в электротехнике единицей реактивной мощности является **квар**. Мы не используем этот столбец для вычисления активной энергии.

Неизвестные измерения остаются `NaN`. Сумма известных минутных энергий неполного месяца **не является** энергией всего месяца.'''),
        code(BOOTSTRAP),
        markdown('''## Расчёт и независимая проверка

`convert_energy()` проверяет обратное действие: умножение рассчитанной энергии за одну минуту на 60 восстанавливает исходную среднюю мощность. Данные не заполняются нулями. В этой операции для каждой известной минуты предполагается одинаковый минутный интервал.'''),
        code('''from ipd_analysis import convert_energy

minutes = regular_minutes(measurements)
energy_table = convert_energy(minutes)
energy_columns = [name for name in energy_table.columns if name == "timestamp" or name.endswith("_kwh")]
display(energy_table[energy_columns].head(10))
save_csv(energy_table[energy_columns], output_dir / "03_energy_kwh.csv")
print("Рассчитанных минут:", len(energy_table))'''),
    ],
    "Визуализация_электропотребления.ipynb": [
        markdown('''# Этап 4. Визуализация электропотребления

Данные берутся из `data/raw` внутри клона GitHub. Профили считаются по исходным минутным значениям, а не из повторно загружаемых ZIP предыдущих этапов.

## Имена переменных

- `source` — выбранный исходный файл; `measurements` — прочитанные измерения в `pandas`.
- `minutes` — равномерная минутная сетка; `month_ids` — коды выбранных месяцев в формате `YYYY-MM`.
- `profile_table` — по 1440 минут суточного профиля каждого месяца.
- `minute_of_day` — номер минуты суток от 0 (00:00) до 1439 (23:59).
- `mean_kw` — средняя мощность по дням для этой минуты суток, в кВт.
- `n_observed` — число дней, для которых измерение этой минуты известно.
- `n_expected` — число ожидаемых измерений этой минуты внутри исследуемого периода.
- `coverage_pct` — полнота этой минуты: `100 × n_observed / n_expected`, в процентах.
- `labplot_table` — таблица для LabPlot: `Hour` — время суток в часах; `P_YYYY-MM_kW` — средняя мощность месяца; `Coverage_YYYY-MM_pct` — полнота месяца.

Месяцы 2008 года используются, если они есть в источнике. Для другого файла автоматически берутся первые доступные месяцы; называть их всеми сезонами года без проверки **нельзя**.'''),
        code(BOOTSTRAP),
        markdown('''## Расчёт суточных профилей и файл LabPlot

`select_months()` выбирает существующие месяцы. `daily_profiles()` создаёт 1440 минут каждого выбранного месяца с правильным учётом отсутствующих строк. `export_labplot()` формирует широкий формат, который удобно импортировать в LabPlot.

**Важно:** если какие-то минуты вообще не наблюдались, соответствующее среднее будет `NaN`, а не нулём.'''),
        code('''from ipd_analysis import select_months, daily_profiles, export_labplot

minutes = regular_minutes(measurements)
month_ids = select_months(minutes)
profile_table = daily_profiles(minutes, month_ids)
labplot_table = export_labplot(profile_table)
display(profile_table.head())
save_csv(profile_table, output_dir / "04_daily_profiles.csv")
save_csv(labplot_table, output_dir / "04_labplot_profiles.csv")
print("Месяцы:", month_ids)'''),
        markdown('''## Графики мощности и полноты

- `chart_path` — путь к изображению PNG в папке результатов этого исходного файла.
- На верхнем графике — средняя активная мощность, **кВт**; на нижнем — полнота, **%**. Различные единицы не смешиваются.
- `daily_chart_path` — график одного фактически наблюдавшегося дня.
- `missing_chart_path` — график недели вокруг самой длинной серии пропусков.
- `month_chart_path` — сравнение двух месяцев, включая различие в полноте наблюдений.
- Графики сохраняются в папку репозитория `результаты/…`, а не в архивы из Colab.'''),
        code('''from run_analysis import plot_profiles, plot_one_day, plot_missing_week, plot_month_comparison

chart_path = output_dir / "04_daily_profiles.png"
daily_chart_path = output_dir / "04_one_day.png"
missing_chart_path = output_dir / "04_missing_week.png"
month_chart_path = output_dir / "04_month_comparison.png"
plot_profiles(profile_table, chart_path)
plot_one_day(minutes, daily_chart_path)
plot_missing_week(minutes, missing_chart_path)
plot_month_comparison(minutes, month_chart_path)
print("Графики сохранены в:", output_dir)
from IPython.display import Image, display
display(Image(filename=str(chart_path)))'''),
    ],
    "статистика_мощности.ipynb": [
        markdown('''# Этап 5. Статистическая обработка мощности

Все расчёты используют один исходный файл из репозитория и общие функции. Нет повторных диалогов загрузки архивов. `NaN` не заменяется нулём, а у каждого результата сохраняется связь с конкретным исходным файлом.

## Имена переменных

- `source` — путь к исходному файлу; `measurements` — считанная **один раз** таблица `pandas`.
- `minutes` — полная минутная сетка, включая отсутствующие строки.
- `statistics_table` — описательная статистика поминутной активной мощности по месяцам.
- `hourly_table` — средняя мощность по каждому часу суток, рассчитанная по доступным минутам.
- `month_ids` — список выбранных для профилей месяцев; `profile_table` — характеристики 1440 минут суток.
- `mean_kw` и `median_kw` — соответственно среднее арифметическое и медиана мощности, кВт.
- `std_kw` — стандартное отклонение наблюдений с `ddof=0`, кВт.
- `q1_kw`, `q3_kw` — первый и третий квартили мощности, кВт.
- `iqr_kw` — межквартильный размах `q3_kw − q1_kw`, кВт.
- `observations` — число пригодных измерений, а не число всех минут месяца.
- `coverage_record_pct` — полнота периода наблюдений, %; `coverage_calendar_pct` — полнота календарного месяца, %.

Статистика неполного месяца описывает **только известные минуты**. Усреднение не доказывает, что пропуски случайны.'''),
        code(BOOTSTRAP),
        markdown('''## Описательная статистика и почасовые профили

Среднее по часу рассчитывается по **всем известным минутам соответствующего часа**, а не как простое среднее из средних при разном числе наблюдений.

- `statistics_table` — одна строка на месяц со средним, медианой, минимумом, максимумом, стандартным отклонением и квартилями.
- `hourly_table` — по одной строке на час месяца, с `n_observed` и `n_expected` для проверки полноты.'''),
        code('''from ipd_analysis import monthly_statistics, hourly_profiles, select_months, daily_profiles
from run_analysis import plot_hourly

minutes = regular_minutes(measurements)
month_ids = select_months(minutes)
statistics_table = monthly_statistics(minutes)
hourly_table = hourly_profiles(minutes, month_ids)
profile_table = daily_profiles(minutes, month_ids)
display(statistics_table.round(3))
display(hourly_table.head(8))
save_csv(statistics_table, output_dir / "05_monthly_statistics.csv")
save_csv(hourly_table, output_dir / "05_hourly_profiles.csv")
plot_hourly(hourly_table, output_dir / "05_hourly_profiles.png")
save_csv(profile_table, output_dir / "05_daily_profiles_quantiles.csv")'''),
        markdown('''## Сглаживание суточного профиля

- `smoothed_table` — копия исходных средних профилей с новыми столбцами `smooth_15_kw` и `smooth_61_kw`.
- `smoothing_table` — таблица отличий между исходным и сглаженным профилями.
- `window_minutes` — ширина окна скользящего среднего: 15 или 61 минута.
- `mae_kw` — среднее абсолютное отличие двух профилей, кВт.
- `rmse_kw` — корень из среднего квадрата отличий, кВт.
- `peak_reduction_pct` — уменьшение максимума профиля после сглаживания, %.

Профиль продлевается циклически через полночь, потому что это **типичные сутки**, а не непрерывный исходный ряд. Около полуночи такая модель — допущение. Для неопределённых точек требуется не менее 80% известных соседних значений.'''),
        code('''from ipd_analysis import smooth_profiles
from run_analysis import plot_smoothing

smoothed_table, smoothing_table = smooth_profiles(profile_table)
display(smoothing_table.round(4))
save_csv(smoothed_table, output_dir / "05_smoothed_profiles.csv")
save_csv(smoothing_table, output_dir / "05_smoothing_metrics.csv")
plot_smoothing(smoothed_table, output_dir / "05_smoothing.png")'''),
        markdown('''## Просмотр рисунка

- `smoothing_chart_path` — изображение результата сглаживания для всех выбранных месяцев. Оно хранится в каталоге результатов и отображается ниже.'''),
        code('''from IPython.display import Image, display

smoothing_chart_path = output_dir / "05_smoothing.png"
display(Image(filename=str(smoothing_chart_path)))'''),
        markdown('''## Проверка влияния пропусков

- `experiment_profiles` — суточные профили при трёх вариантах: исходный месяц, случайные пропуски и непрерывный пропуск.
- `experiment_metrics` — сравнение сценариев, где `missing_count` — число удалённых измерений и `mae_kw` — отличие от исходного профиля.
- `incomplete_month_ids` — месяцы с отсутствующей или недопустимой мощностью.
- `complete_day_profiles` — сравнение профиля по всем известным измерениям с профилем только полных суток.
- `complete_day_metrics` — число полных суток и отличие между методами.

**Как читать рисунок:** верхняя панель показывает абсолютные суточные профили, нижняя — разность `P_с_пропусками − P_исходная` в кВт. Тонкая линия внизу — настоящие поминутные различия; толстая — только их скользящее среднее за 15 минут для наглядности. Показатель `MAE` рассчитывается по исходным различиям, без сглаживания.

Эксперимент проводится **только если есть целый календарный месяц без пропусков**. Если его нет, это честно сообщается, а не создаётся вымышленный «эталон». У новых файлов числа 43200, 8120 и 7226 не предполагаются.'''),
        code('''from ipd_analysis import monthly_coverage, missing_experiment, compare_complete_days
from run_analysis import plot_missing_experiment, plot_complete_days

experiment_profiles, experiment_metrics = missing_experiment(minutes)
if experiment_metrics.empty:
    print("Эксперимент пропущен: нет полного календарного месяца без пропусков.")
else:
    display(experiment_metrics)
    save_csv(experiment_profiles, output_dir / "05_missing_experiment_profiles.csv")
    save_csv(experiment_metrics, output_dir / "05_missing_experiment_metrics.csv")
    plot_missing_experiment(experiment_profiles, output_dir / "05_missing_experiment.png")

incomplete_month_ids = monthly_coverage(minutes).loc[
    lambda table: table["missing_or_invalid"].gt(0), "month"
].tolist()
complete_day_profiles, complete_day_metrics = compare_complete_days(minutes, incomplete_month_ids)
if not complete_day_metrics.empty:
    display(complete_day_metrics)
    save_csv(complete_day_profiles, output_dir / "05_complete_day_profiles.csv")
    save_csv(complete_day_metrics, output_dir / "05_complete_day_metrics.csv")
    plot_complete_days(complete_day_profiles, output_dir / "05_complete_day_profiles.png")'''),
    ],
}


def main():
    for filename, cells in NOTEBOOKS.items():
        notebook = {
            "cells": cells,
            "metadata": {"kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
                         "language_info": {"name": "python"}},
            "nbformat": 4, "nbformat_minor": 5,
        }
        destination = NOTEBOOK_DIR / filename
        destination.write_text(json.dumps(notebook, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        print(f"Обновлён: {destination.name} ({len(cells)} ячеек)")


if __name__ == "__main__":
    main()
