import re
import urllib.parse
import asyncio
import aiohttp

USER_AGENTS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def validate_snils(snils_str):
    digits = re.sub(r'\D', '', snils_str)
    if len(digits) != 11:
        return False, "Неверная длина СНИЛС (должно быть 11 цифр)"
    num = digits[:9]
    check = int(digits[9:])
    val = sum(int(num[i]) * (9 - i) for i in range(9))
    if val < 100:
        calc = val
    elif val in (100, 101):
        calc = 0
    else:
        calc = val % 101
        if calc == 100:
            calc = 0
    status = "Действителен" if calc == check else "Контрольная сумма не совпадает"
    return calc == check, f"Статус: {status} | Вычислено: {calc:02d} | Указано: {check:02d}"

def validate_inn(inn_str):
    digits = re.sub(r'\D', '', inn_str)
    if len(digits) == 10:
        coeffs = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        val = sum(int(digits[i]) * coeffs[i] for i in range(9))
        calc = (val % 11) % 10
        check = int(digits[9])
        status = "Действителен" if calc == check else "Контрольное число не совпадает"
        return calc == check, f"ИНН Юр. лица (10 цифр) | {status} | Контрольное: {calc} | Указано: {check}"
    elif len(digits) == 12:
        coeffs1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        val1 = sum(int(digits[i]) * coeffs1[i] for i in range(10))
        calc1 = (val1 % 11) % 10
        coeffs2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        val2 = sum(int(digits[i]) * coeffs2[i] for i in range(11))
        calc2 = (val2 % 11) % 10
        check1, check2 = int(digits[10]), int(digits[11])
        valid = (calc1 == check1) and (calc2 == check2)
        status = "Действителен" if valid else "Ошибка в контрольных числах"
        return valid, f"ИНН Физ. лица (12 цифр) | {status} | Ожидалось: {calc1}{calc2} | Введено: {check1}{check2}"
    return False, "Неверная длина ИНН (должно быть 10 или 12 цифр)"

def decode_vin(vin):
    clean = re.sub(r'[^A-HJ-NPR-Z0-9]', '', vin.upper())
    if len(clean) != 17:
        return False, "Неверная длина VIN (необходимо 17 символов без I, O, Q)"
    wmi, vds, vis = clean[:3], clean[3:9], clean[9:]
    countries = {
        '1': 'США', '2': 'Канада', '3': 'Мексика', '4': 'США', '5': 'США',
        'J': 'Япония', 'K': 'Южная Корея', 'L': 'Китай', 'M': 'Индия',
        'S': 'Великобритания', 'W': 'Германия', 'X': 'РФ / СНГ', 'Y': 'Швеция', 'Z': 'Италия'
    }
    origin = countries.get(wmi[0], "Неизвестная страна")
    years = "A B C D E F G H J K L M N P R S T V W X Y 1 2 3 4 5 6 7 8 9"
    years_list = years.split()
    year_char = clean[9]
    try:
        idx = years_list.index(year_char)
        prod_year = 1980 + idx if idx < 30 else 2010 + (idx - 30)
        year_str = f"~ {prod_year} год"
    except ValueError:
        year_str = "Не определен"
    return True, f"Страна: {origin}\nКод WMI: {wmi}\nКод VDS: {vds}\nКод VIS: {vis}\nГод выпуска: {year_str}"

def parse_phone(phone):
    digits = re.sub(r'\D', '', phone)
    if digits.startswith('8') and len(digits) == 11:
        digits = '7' + digits[1:]
    if not digits:
        return False, "Пустой запрос"
    if digits.startswith('7'):
        if len(digits) != 11:
            return False, f"Неверная длина номера РФ: {len(digits)} цифр"
        prefix = digits[1:4]
        carriers = {
            "901": "Tele2", "902": "Tele2 / Ростелеком", "903": "Билайн", "904": "Tele2",
            "905": "Билайн", "906": "Билайн", "909": "Билайн", "910": "МТС", "911": "МТС",
            "912": "МТС", "913": "МТС", "914": "МТС", "915": "МТС", "916": "МТС", "917": "МТС",
            "918": "МТС", "919": "МТС", "920": "МегаФон", "921": "МегаФон", "922": "МегаФон",
            "923": "МегаФон", "924": "МегаФон", "925": "МегаФон", "926": "МегаФон", "927": "МегаФон",
            "928": "МегаФон", "929": "МегаФон", "930": "МегаФон", "931": "МегаФон", "932": "МегаФон",
            "950": "Tele2", "951": "Tele2", "952": "Tele2", "953": "Tele2", "960": "Билайн",
            "999": "Yota"
        }
        carrier = carriers.get(prefix, "Неизвестный оператор")
        return True, f"Регион: РФ (+7)\nПрефикс: {prefix}\nПровайдер: {carrier}"
    elif digits.startswith('380'):
        if len(digits) != 12:
            return False, f"Неверная длина номера Украины: {len(digits)} цифр"
        prefix = digits[3:5]
        carriers = {
            "50": "Vodafone", "66": "Vodafone", "95": "Vodafone", "99": "Vodafone",
            "67": "Kyivstar", "68": "Kyivstar", "96": "Kyivstar", "97": "Kyivstar", "98": "Kyivstar",
            "63": "Lifecell", "73": "Lifecell", "93": "Lifecell", "91": "3Mob", "92": "PeopleNet",
            "94": "Intertelecom"
        }
        carrier = carriers.get(prefix, "Неизвестный оператор")
        return True, f"Регион: Украина (+380)\nПрефикс: 0{prefix}\nПровайдер: {carrier}"
    return False, "Неподдерживаемый диапазон номеров (доступны РФ / Украина)"

async def verify_telegram_username(session, username):
    clean = username.lstrip('@')
    url = f"https://t.me/{clean}"
    try:
        async with session.get(url, headers={"User-Agent": USER_AGENTS}, timeout=6) as resp:
            if resp.status == 200:
                html = await resp.text()
                if "tgme_page_title" in html:
                    match = re.search(r'<div class="tgme_page_title"[^>]*>\s*<span[^>]*>(.*?)</span>', html, re.DOTALL)
                    display_name = match.group(1).strip() if match else f"@{clean}"
                    display_name = re.sub(r'<[^>]+>', '', display_name)
                    return True, f"Профиль найден: {url}\nИмя: {display_name}"
                return False, f"Профиль @{clean} не зарегистрирован в Telegram."
            return False, f"Сервер вернул статус {resp.status}"
    except Exception as e:
        return False, f"Ошибка соединения: {str(e)}"

async def search_web_mentions(session, query):
    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7"
    }
    try:
        async with session.get(url, headers=headers, timeout=8) as resp:
            if resp.status == 200:
                html = await resp.text()
                if "ddg-captcha" in html or "captcha" in html:
                    return False, "CAPTCHA_BLOCKED"
                
                matches = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL)
                
                if not matches:
                    lite_url = "https://lite.duckduckgo.com/lite/"
                    async with session.post(lite_url, data={"q": query}, headers=headers, timeout=6) as lite_resp:
                        if lite_resp.status == 200:
                            lite_html = await lite_resp.text()
                            lite_matches = re.findall(r'<a href="([^"]+)"[^>]*class="result-link"[^>]*>(.*?)</a>', lite_html, re.DOTALL)
                            if not lite_matches:
                                lite_matches = re.findall(r'<a href="([^"]+)"[^>]*>(.*?)</a>', lite_html, re.DOTALL)
                                lite_matches = [m for m in lite_matches if not any(x in m[0] for x in ["duckduckgo.com", "html/settings", "lite/settings"])]
                            matches = lite_matches
                
                results = []
                for link, title in matches[:5]:
                    clean_title = re.sub(r'<[^>]+>', '', title).strip()
                    clean_link = urllib.parse.unquote(link)
                    if "uddg=" in clean_link:
                        parts = clean_link.split("uddg=")
                        if len(parts) > 1:
                            clean_link = urllib.parse.unquote(parts[1].split("&")[0])
                    if clean_link.startswith("//"):
                        clean_link = "https:" + clean_link
                    results.append({"title": clean_title, "url": clean_link})
                return True, results
            return False, f"HTTP {resp.status}"
    except Exception as e:
        return False, str(e)