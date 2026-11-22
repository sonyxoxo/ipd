"""Один раз приводит заголовки опубликованных CSV к латинским именам.

Меняется только первая строка файла; все значения, точность и порядок строк
остаются побайтно неизменными. Исходники из data/raw не затрагиваются.
"""

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
HEADER_MAP = {
    "Месяц": "month",
    "Ожидалось за полный месяц": "expected_calendar",
    "Ожидалось в период записи": "expected_in_record",
    "Уникальных временных меток": "unique_timestamps",
    "Корректных измерений": "valid_measurements",
    "Без корректного измерения": "missing_or_invalid",
    "Полнота периода, %": "coverage_record_pct",
    "Полнота месяца, %": "coverage_calendar_pct",
    "Неполных дней": "incomplete_days",
    "Максимальный пропуск, мин": "max_missing_run_minutes",
    "Есть пропуск от 60 мин": "has_gap_ge_60_min",
    "Начало": "start",
    "Конец": "end",
    "Продолжительность, мин": "duration_minutes",
    "Пересекает месяцы": "crosses_month",
    "Вариант": "scenario",
    "Средняя мощность, кВт": "mean_kw",
    "Пик профиля, кВт": "profile_peak_kw",
    "Время пика": "peak_time",
    "MAE, кВт": "mae_kw",
    "RMSE, кВт": "rmse_kw",
    "Полнота, %": "coverage_pct",
    "Час": "hour",
    "Минута": "minute_of_day",
    "Минута_суток": "minute_of_day",
    "P_Полный_кВт": "original_mean_kw",
    "N_Полный": "original_n_observed",
    "P_Случайный_кВт": "random_mean_kw",
    "N_Случайный": "random_n_observed",
    "P_Длительный_кВт": "continuous_mean_kw",
    "N_Длительный": "continuous_n_observed",
    "Всего минут": "total_minutes",
    "Пропусков": "missing_minutes",
    "Средняя известная мощность, кВт": "mean_observed_kw",
    "Самая длинная пауза, мин": "longest_gap_minutes",
    "Период самой длинной паузы": "longest_gap_period",
    "Средняя_кВт": "mean_kw",
    "Медиана_кВт": "median_kw",
    "Q1_кВт": "q1_kw",
    "Q3_кВт": "q3_kw",
    "IQR_кВт": "iqr_kw",
    "Разница_кВт": "difference_kw",
    "Средняя_15мин_кВт": "smooth_15_kw",
    "Средняя_61мин_кВт": "smooth_61_kw",
    "Пик среднего, кВт": "mean_peak_kw",
    "Пик медианы, кВт": "median_peak_kw",
    "Время пика среднего": "mean_peak_time",
    "Время пика медианы": "median_peak_time",
    "Среднее |различие|, кВт": "mean_absolute_difference_kw",
    "Средний IQR, кВт": "mean_iqr_kw",
    "Окно, мин": "window_minutes",
    "Исходный пик, кВт": "original_peak_kw",
    "Сглаженный пик, кВт": "smoothed_peak_kw",
    "Снижение пика, %": "peak_reduction_pct",
    "Время исходного пика": "original_peak_time",
    "Время сглаженного пика": "smoothed_peak_time",
    "наблюдений": "observations",
    "средняя_кВт": "mean_kw",
    "медиана_кВт": "median_kw",
    "минимум_кВт": "min_kw",
    "максимум_кВт": "max_kw",
    "станд_откл_кВт": "std_kw",
    "всего_минут": "total_minutes",
    "полнота_pct": "coverage_pct",
    "Максимум_минуты_кВт": "max_minute_kw",
    "Когда_минутный_максимум": "max_minute_time",
    "Минимум_минуты_кВт": "min_minute_kw",
    "Когда_минутный_минимум": "min_minute_time",
    "Максимум_среднего_профиля_кВт": "max_profile_kw",
    "Время_максимума_профиля": "max_profile_time",
    "Минимум_среднего_профиля_кВт": "min_profile_kw",
    "Время_минимума_профиля": "min_profile_time",
    "Исходный столбец": "source_column",
    "Физический смысл": "physical_quantity",
    "Исходная единица": "input_unit",
    "Преобразование": "conversion",
    "Единица результата": "output_unit",
    "mean": "mean_kw", "count": "n_observed", "size": "n_expected",
}


def convert_file(path: Path) -> bool:
    original = path.read_bytes()
    first_line, separator, remainder = original.partition(b"\n")
    carriage_return = b"\r" if first_line.endswith(b"\r") else b""
    columns = first_line.removesuffix(carriage_return).decode("utf-8-sig").split(";")
    renamed = [HEADER_MAP.get(column, column) for column in columns]
    if not all(column.isascii() for column in renamed):
        raise ValueError(f"Остались кириллические заголовки в {path}: {renamed}")
    if len(set(renamed)) != len(renamed):
        raise ValueError(f"Повторные названия столбцов в {path}: {renamed}")
    if renamed == columns:
        return False
    bom = b"\xef\xbb\xbf" if original.startswith(b"\xef\xbb\xbf") else b""
    replacement = bom + ";".join(renamed).encode("utf-8") + carriage_return + separator + remainder
    assert replacement.partition(b"\n")[2] == original.partition(b"\n")[2]
    path.write_bytes(replacement)
    return True


def main() -> None:
    folders = ("обработанные данные", "статистические результаты", "научная документация")
    changed = 0
    for folder in folders:
        for path in sorted((REPO_ROOT / folder).glob("*.csv")):
            if convert_file(path):
                print(f"Заголовки исправлены: {path.relative_to(REPO_ROOT)}")
                changed += 1
    print(f"Обновлено файлов: {changed}")


if __name__ == "__main__":
    main()
