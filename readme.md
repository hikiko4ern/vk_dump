<div align="center">

## VK Dump Tool

[![](https://img.shields.io/github/release/hikiko4ern/vk_dump.svg?style=for-the-badge&logo=github&logoColor=white&labelColor=101010&color=2196f3)](https://github.com/hikiko4ern/vk_dump/releases/latest) ![](https://img.shields.io/static/v1.svg?message=5.95&logo=vk&logoColor=white&label=API&labelColor=101010&color=a938e4&style=for-the-badge)

[![](https://img.shields.io/lgtm/grade/python/g/hikiko4ern/vk_dump.svg?labelColor=101010&color=4426bb&label=grade&logo=lgtm&logoColor=white&style=for-the-badge)](https://lgtm.com/projects/g/hikiko4ern/vk_dump/context:python) ![](https://img.shields.io/codacy/grade/a30e0216250b407883c093c01dffd867.svg?logo=codacy&logoColor=white&labelColor=101010&color=dc143c&style=for-the-badge) [![](https://img.shields.io/codecov/c/github/hikiko4ern/vk_dump.svg?style=for-the-badge&logo=codecov&logoColor=white&labelColor=101010&color=f01f7a&token=702f6d148dca4a33920d934b0c91a145)](https://codecov.io/gh/hikiko4ern/vk_dump)

</div>

## Внимание

На данный момент иногда пользователи определяются как `{unknown user}`. Решения проблемы пока нет ([#24](/../../issues/24)).

## Установка

- склонировать/скачать репозиторий
- установить зависимости

## Установка зависимостей

```bash
pip3 install -r requirements.txt
```

Для загрузки видео из некоторых сторонних источников (напр, RuTube) [`youtube-dl`](https://github.com/ytdl-org/youtube-dl) использует [`ffmpeg`](https://ffmpeg.org), который необходимо установить отдельно.

Если Вы используете Windows ниже 10 версии, необходимо дополнительно установить пакет `colorama`:

```bash
pip3 install colorama
```

## CLI

Все доступные аргументы можно посмотреть при запуске с `--help`.

Для сохранения нескольких типов данных за один вызов необходимо указывать каждый тип отдельным аргументом `dump`.
Например, для сохранения фото и документов надо запускать `dump.py --dump photo --dump docs`.

## Авторизация

Возможны два способа аутентификации - с помощью пары логин-пароль или токена. Авторизация по логину идёт с данными от Kate Mobile.

Для входа по токену необходимо передать аргумент `token` при запуске:

```bash
python3 dump.py --token your_token_here
```

## Мультипоточная загрузка

Количество процессов, создаваемых для загрузки, по умолчанию равняется `4*потоки`.

При загрузке видео - числу, заданному в настройках, но не больше количества потоков.
Такое ограничение введено ввиду отсутствия смысла в спаме лишними процессами при загрузке больших по размеру видео (однако лимит всё же убирается через настройки).

## Поддерживаемые для сохранения данные

- [x] Фото
- [x] Видео
- [x] Аудио
- [x] Документы
- [x] Диалоги (txt) и вложения (фото, видео, документы, голосовые)
- [x] Вложения понравившихся постов (фото, видео, документы)
- [x] Понравившиеся фотографии
- [x] Понравившиеся видео
- [ ] прочее, прочее, прочее ;)

Любые предложения и репорты о багах приветствуются :з

## Настройка сохраняемых диалогов

Для сохранения или исключения определённых диалогов необходимо вручную подредактировать конфиг `settings.ini`.

ID диалогов перечисляются через запятую. Получить его можно, например, открыв диалог в разделе сообщений, тогда в URL вроде `https://vk.com/im?sel=100` идентификатором будет являться кусок, идущий после `sel=`.

Пример исключения диалога с ID `100` и беседы `c60`:

```ini
[EXCLUDED_DIALOGS]
id = 100,c60
```

Сохранение только диалога с ID `100` и исключения всех остальных:

```ini
[DUMP_DIALOGS_ONLY]
id = 100
```

## Дозапись новых сообщений вместо перезаписывания

Если включена, при кэшировании будут получены не все сообщения, а только с ID больше последнего записанного (последняя строка в файле).

## F.A.Q

**Q: Можно ли не вводить каждый раз логин и пароль (и код 2FA) при авторизации?**\
**A:** Просто передавайте логин аргументом (`--login`) или вводите пустой пароль на экране авторизации. В таком случае данные будут подтянуты из конфига `vk_api`.

**Q: Ошибка vk_api.exceptions.AccessDenied: You don't have permissions to browse user's audio**\
**A:** К сожалению, [`vk_api`](https://github.com/python273/vk_api) не поддерживает сохранение аудио при входе по токену. Ну или же попробуйте удалить файл `vk_config.v2.json` и переавторизироваться, если это не Ваш случай ¯\\\_(ツ)\_/¯

**Q: Ошибка RegexNotFoundError('Unable to extract %s' % \_name)**\
**A:** Обновите `youtube_dl`: `pip3 install --upgrade youtube_dl`.

## License

[![FOSSA Status](https://app.fossa.io/api/projects/git%2Bgithub.com%2Fhikiko4ern%2Fvk_dump.svg?type=large)](https://app.fossa.io/projects/git%2Bgithub.com%2Fhikiko4ern%2Fvk_dump?ref=badge_large)
