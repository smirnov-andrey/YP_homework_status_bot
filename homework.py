import logging
import os
import sys
import time
from http import HTTPStatus

import requests
import telegram
from dotenv import load_dotenv

import exceptions


load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}

HOMEWORK_VERDICTS = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logger = logging.getLogger(__name__)


def send_message(bot, message):
    """Отправляет сообщение о статусе домашней работы в Telegram чат."""
    logger.debug(f'Отправляем сообщение в Telegram. message={message}')
    try:
        bot.send_message(
            chat_id=TELEGRAM_CHAT_ID,
            text=message
        )
        logger.info(f'Отправлено сообщение в чат. chat_id={TELEGRAM_CHAT_ID} '
                    f'text={message}')
        return True
    except telegram.error.TelegramError:
        logger.error(f'Сбой отправки сообщения в чат. '
                     f'chat_id={TELEGRAM_CHAT_ID} text={message}')
        return False


def get_api_answer(current_timestamp):
    """Делает запрос к единственному эндпоинту API-сервиса."""
    logger.debug('Получаем данные по API Yandex Practicum')
    api_request_params = {
        'url': ENDPOINT,
        'headers': HEADERS,
        'params': {'from_date': current_timestamp}
    }
    try:
        logger.debug('Делаем запрос API с параметрами: url: {url} headers: {'
                     'headers} params:{params}'.format(**api_request_params))
        response = requests.get(**api_request_params)
        if response.status_code != HTTPStatus.OK:
            raise exceptions.APIAccessException(
                f'API Yandex Practicum недоступен. Код ответа: '
                f'{response.status_code}')
        logger.info('Статус ответа API: OK')
        logger.debug('Данные API получены')
        return response.json()
    except Exception as error:
        raise ConnectionError(
            'Неизвестный сбой API Yandex Practicum. error: {error} url: {url} '
            'headers: {headers} params:{params}'.format(
                error=error, **api_request_params))


def check_response(response):
    """Проверяет ответ API на корректность."""
    logger.debug('Проверяем ответ API на корректность.')
    if not isinstance(response, dict):
        raise TypeError(
            f'Ответ от API не является словарем: response = {response}.'
        )
    if 'homeworks' not in response or 'current_date' not in response:
        raise exceptions.KeysCheckException(
            'Ключи homeworks или current_date отсутствуют в словаре')
    homeworks = response.get('homeworks')
    if not isinstance(homeworks, list):
        raise KeyError(
            'Список домашних работ не является списком')
    logger.debug('Проверка API: OK')
    return homeworks


def parse_status(homework):
    """Извлекает статус домашней работы."""
    logger.debug('Извлекаем статус домашней работы')
    if 'homework_name' not in homework:
        raise KeyError(f'Отсутствует ключ homework_name в {homework}')
    if 'status' not in homework:
        raise KeyError(f'Отсутствует ключ status в {homework}')
    homework_name = homework.get('homework_name')
    homework_status = homework.get('status')
    if homework_status not in HOMEWORK_VERDICTS:
        raise ValueError(f'Недокументированный статус домашней работы: '
                         f'{homework_status}')
    logger.info(f'Статус домашней работы {homework_name}: '
                f'{homework_status}')
    return (f'Изменился статус проверки работы "{homework_name}".'
            f' {HOMEWORK_VERDICTS[homework_status]}')


def check_tokens():
    """Проверяет доступность переменных окружения."""
    logger.debug('Проверяем переменные окружения.')
    tokens_to_check = (PRACTICUM_TOKEN,
                       TELEGRAM_TOKEN,
                       TELEGRAM_CHAT_ID)
    token_check_result = True
    for token in tokens_to_check:
        if token is None:
            logger.critical(f'Отсутствует обязательная переменная окружения '
                            f'{token}')
            token_check_result = False
    logger.debug('Проверка переменных окружения завершена')
    return token_check_result


def main():
    """Основная логика работы бота."""
    logger.info('Бот запущен')
    if not check_tokens():
        raise exceptions.EnvironmentVariablesException(
            'Отсутствует обязательная переменная окружения.'
            'Программа принудительно остановлена.')
    logger.info('Переменные окружения: ОК')
    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = 0
    current_report = {'message_output': '', }
    prev_report = current_report.copy()
    while True:
        try:
            response = get_api_answer(current_timestamp)
            homeworks = check_response(response)
            if homeworks:
                homework = homeworks[0]
                verdict_message = parse_status(homework)
                current_report['message_output'] = homework['status']
                if current_report != prev_report:
                    if send_message(bot, verdict_message):
                        prev_report = current_report.copy()
                        current_timestamp = response.get('current_date',
                                                         current_timestamp)
                else:
                    logger.info('Нет новых статусов домашних работ')
            else:
                logger.info('Нет новых статусов домашних работ')
        except exceptions.KeysCheckException as error:
            logger.error(error)
        except Exception as error:
            error_message = f'Сбой в работе программы {error}'
            logger.error(error_message)
            current_report['message_output'] = error_message
            if current_report != prev_report:
                send_message(bot, error_message)
                prev_report = current_report.copy()
        finally:
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    LOG_FILE = os.path.join(BASE_DIR, __file__ + '.log')
    logging.basicConfig(
        format=('%(asctime)s - %(levelname)s - %(funcName)s - %(lineno)d - '
                '%(message)s'),
        level=logging.DEBUG,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOG_FILE, encoding='UTF-8')
        ]
    )
    main()
