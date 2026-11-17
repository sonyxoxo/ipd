# Исходные данные для анализа

Добавляйте сюда файлы `.txt`, `.csv`, `.tsv` или `.zip` (в ZIP — одна таблица).

Для исходного набора UCI поместите сюда архив `household_power_consumption.zip`
(распаковывать не нужно). Архив UCI весит около 20 МБ; TXT в распакованном
виде превышает ограничение GitHub в 100 МБ на один обычный файл.

Контрольная сумма сохранённого здесь архива SHA-256:
`9f84b46ade8a2d8e1286ec4b2b6c2987a45a755c59f263be3b3b3d10dfbda3ff`.
Её можно проверить командой `sha256sum data/raw/household_power_consumption.zip`.

Данные должны содержать `Date` и `Time` (формат `dd/mm/yyyy` и `hh:mm:ss`)
либо `timestamp`/`datetime`, а также `Global_active_power` в кВт.
Дополнительные столбцы `Voltage`, `Global_reactive_power`, `Global_intensity`
и `Sub_metering_1` — `Sub_metering_3` обрабатываются, если присутствуют.

Это *проверяемая схема*, а не универсальное распознавание физических единиц.
Наборы другого формата необходимо сначала явно сопоставить с этой схемой.

После добавления файла выполните `git add data/raw/...`, `git commit`,
`git push`. В Colab обновите клон репозитория через `git pull`.

Источник: https://archive.ics.uci.edu/dataset/235/individual+household+electric+power+consumption
Лицензия источника: CC BY 4.0; при публикации указывайте авторов и DOI.
