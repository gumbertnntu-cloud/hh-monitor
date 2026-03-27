# hh-monitor (MVP v3)

Локальное desktop-приложение для macOS (Apple Silicon) для мониторинга и парсинга вакансий hh.ru без официального API.

## Что умеет MVP
- GUI на `PySide6` (`./app`) для настройки и запуска.
- Интерактивная авторизация:
  - приложение открывает headful Chromium,
  - вы логинитесь вручную,
  - сессия сохраняется в `state/state.json`.
- Запуск сбора в режимах:
  - `fast`: только выдача,
  - inline `deep`: deep-dive запускается автоматически по тумблеру `DD` в верхней таблице.
- Ограничения:
  - `max_pages` (например 10),
  - `max_age_days` (по умолчанию 30 дней = 1 месяц).
- Фильтры:
  - include/exclude keywords,
  - морфо-нормализация ключевых слов (RU+EN) для учета склонений/форм слов,
  - optional min salary,
  - поля: `title + company + snippet + description (deep)`.
- SQLite:
  - `vacancies`, `runs`, `run_items`, `changes`.
- Дельты: `new / updated / removed`.
- Отчеты:
  - таблица в GUI,
  - HTML preview: `reports/latest.html`,
  - Excel: `exports/hh_report_*.xlsx` (2 листа: `Общий поиск` и `Deep-dive`).
- Внутренний service mode для `launchd` (`./service-run`).

## Требования
- macOS (Apple Silicon)
- Python `3.11+`
- Chromium for Playwright

## Быстрый старт
```bash
cd /Users/steshinaleksandr/codex/hh
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
chmod +x app service-run
```

Запуск GUI:
```bash
./app
```

Запуск как обычное приложение из Finder:
- Откройте `/Users/steshinaleksandr/codex/hh`
- Дважды кликните `HH Monitor.app`

Если macOS блокирует первый запуск:
```bash
xattr -dr com.apple.quarantine "/Users/steshinaleksandr/codex/hh/HH Monitor.app"
```
Или откройте через контекстное меню: `Open`.

## Сценарий работы в GUI
1. Нажмите `Авторизоваться`.
2. В открывшемся браузере выполните вход в hh.ru.
3. Дождитесь сообщения в GUI, что сессия сохранена.
4. Задайте настройки:
   - `Целевые позиции (/)`: многострочное поле (до 4+ строк), по одной фразе на строку.
   - `Блокеры (/)`: многострочное поле (до 4+ строк), по одному стоп-слову на строку.
   - `Max pages`
   - `Max age (days)`
   - min salary (опционально)
5. Нажмите `Запустить поиск` для fast-обновления выдачи.
6. В таблице `Найденные вакансии` включайте тумблеры `DD` для нужных строк.
7. Deep-dive подгружается в фоне автоматически (до 3 вакансий параллельно).
8. Полный текст hh.ru показывается справа для выбранной строки после статуса `готово`.
9. После завершения:
   - `Preview HTML` откроет `reports/latest.html`
   - `Export XLSX` сохранит файл в `exports/`.
10. Справа:
   - панель обновляется только по выбранной строке;
   - показывает и краткий текст выдачи, и deep-статус;
   - при `done` показывает полный текст с hh.ru.
11. Кнопка `Инструкция` в шапке открывает встроенную памятку по работе с приложением.
12. При каждом новом `Запустить поиск` deep-состояния сбрасываются, чтобы соответствовать текущей выдаче.

## Где что хранится
- Настройки GUI: `config/settings.json`
- Сессия браузера: `state/state.json`
- База: `data/hh_monitor.db`
- Логи: `logs/app.log` (+ `launchd.out/err.log` при планировщике)
- HTML отчет: `reports/latest.html`
- Excel: `exports/*.xlsx`

## Внутренний service mode (для launchd)
Запуск из терминала:
```bash
./service-run --settings config/settings.json --mode fast --max-pages 10 --max-age-days 30 --export
```

Пример plist: `launchd/com.user.hhmonitor.plist.example`  
Поставьте абсолютные пути и загрузите:
```bash
launchctl unload ~/Library/LaunchAgents/com.user.hhmonitor.plist 2>/dev/null || true
cp launchd/com.user.hhmonitor.plist.example ~/Library/LaunchAgents/com.user.hhmonitor.plist
# отредактируйте абсолютные пути в plist
launchctl load ~/Library/LaunchAgents/com.user.hhmonitor.plist
```

## Обновление app bundle
Если нужно пересобрать launcher:
```bash
./scripts/rebuild_macos_app.sh
```

Если нужно пересобрать с другой PNG-иконкой:
```bash
./scripts/rebuild_macos_app.sh /absolute/path/to/icon.png
```

## Сборка Windows EXE
Собирать нужно через специальный entrypoint, а не напрямую из `src/hh_monitor/app.py`.

Windows (PowerShell):
```powershell
cd <repo>
.\scripts\build_windows_exe.ps1 -PythonExe python -Clean
```

Windows (cmd):
```cmd
cd <repo>
scripts\build_windows_exe.bat
```

Результат:
- `dist\HH Monitor.exe`

Если при запуске старого `.exe` видите ошибку  
`attempted relative import with no known parent package`:
1. Удалите старый файл `dist\HH Monitor.exe`.
2. Пересоберите через `scripts\build_windows_exe.bat` (или PowerShell-скрипт выше).
3. Запускайте только новый `dist\HH Monitor.exe`.

## Качество
```bash
ruff check src tests
black --check src tests
pytest -q
```

Опционально:
```bash
mypy src
```

## Примечания по устойчивости
- Пагинация идет по `page=` (0-based).
- Параметры `hhtmFrom*` и `searchSessionId` не обязательны.
- Для запросов реализованы retry/backoff на `429/5xx`.
- Между страницами/карточками используется задержка `1..3` сек + jitter.
- Если сессия протухла, нужно заново нажать `Авторизоваться`.
