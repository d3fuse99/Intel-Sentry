import re
import urllib.parse
import hashlib
import asyncio
import aiohttp

USER_AGENTS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

PLATFORMS = {
    "GitHub": "https://github.com/{}",
    "GitLab": "https://gitlab.com/{}",
    "PyPI": "https://pypi.org/user/{}",
    "DockerHub": "https://hub.docker.com/u/{}",
    "npm": "https://www.npmjs.com/~{}"
}

async def check_platform_username(session, platform_name, url_template, username):
    clean_username = username.lstrip('@')
    url = url_template.format(clean_username)
    try:
        async with session.get(url, headers={"User-Agent": USER_AGENTS}, timeout=5) as resp:
            if resp.status == 200:
                return platform_name, url, "Занят / Найдено"
            elif resp.status == 404:
                return platform_name, None, "Свободен"
            else:
                return platform_name, None, f"Ошибка (Статус {resp.status})"
    except Exception:
        return platform_name, None, "Таймаут / Ошибка подключения"

async def check_all_platforms(session, username):
    tasks = [
        check_platform_username(session, name, template, username)
        for name, template in PLATFORMS.items()
    ]
    return await asyncio.gather(*tasks)

async def query_doh(session, name, record_type):
    url = f"https://cloudflare-dns.com/dns-query?name={name}&type={record_type}"
    headers = {"Accept": "application/dns-json"}
    try:
        async with session.get(url, headers=headers, timeout=5) as resp:
            if resp.status == 200:
                data = await resp.json()
                answers = data.get("Answer", [])
                return [ans["data"] for ans in answers if "data" in ans]
    except Exception:
        pass
    return []

async def audit_email_domain(session, email):
    if "@" not in email:
        return False, "Неверный формат e-mail"
    
    domain = email.split("@")[-1]
    mx_records = await query_doh(session, domain, "MX")
    
    if not mx_records:
        return False, f"Домен {domain} не настроен для приема почты (отсутствуют MX-записи)."
    
    txt_records = await query_doh(session, domain, "TXT")
    has_spf = any("v=spf1" in record for record in txt_records)
    spf_status = "Найдена" if has_spf else "Отсутствует (риск спуфинга!)"
    
    details = (
        f"Домен: {domain}\n"
        f"Почтовые серверы (MX): {', '.join(mx_records[:3])}\n"
        f"Защита SPF: {spf_status}"
    )
    return True, details

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
    status = "Корректен" if calc == check else "Контрольное число не совпадает"
    return calc == check, f"Статус: {status} | Вычислено: {calc:02d} | Указано: {check:02d}"

def validate_inn(inn_str):
    digits = re.sub(r'\D', '', inn_str)
    if len(digits) == 10:
        coeffs = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        val = sum(int(digits[i]) * coeffs[i] for i in range(9))
        calc = (val % 11) % 10
        check = int(digits[9])
        status = "Корректен" if calc == check else "Контрольное число не совпадает"
        return calc == check, f"ИНН Юр. лица (10 цифр) | {status} | Ожидалось: {calc} | Указано: {check}"
    elif len(digits) == 12:
        coeffs1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        val1 = sum(int(digits[i]) * coeffs1[i] for i in range(10))
        calc1 = (val1 % 11) % 10
        coeffs2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        val2 = sum(int(digits[i]) * coeffs2[i] for i in range(11))
        calc2 = (val2 % 11) % 10
        check1, check2 = int(digits[10]), int(digits[11])
        valid = (calc1 == check1) and (calc2 == check2)
        status = "Корректен" if valid else "Контрольные числа не совпадают"
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
    origin = countries.get(wmi[0], "Неизвестный регион")
    years = "A B C D E F G H J K L M N P R S T V W X Y 1 2 3 4 5 6 7 8 9"
    years_list = years.split()
    year_char = clean[9]
    try:
        idx = years_list.index(year_char)
        prod_year = 1980 + idx if idx < 30 else 2010 + (idx - 30)
        year_str = f"~ {prod_year} год"
    except ValueError:
        year_str = "Не определен"
    return True, f"Регион сборки: {origin}\nКод WMI: {wmi}\nКод VDS: {vds}\nКод VIS: {vis}\nПримерный год: {year_str}"

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
                    return True, display_name, url
                return False, f"Профиль @{clean} не зарегистрирован в Telegram.", url
            return False, f"Сервер вернул статус {resp.status}", url
    except Exception as e:
        return False, f"Ошибка соединения: {str(e)}", url

async def search_web_mentions(session, query):
    encoded_query = urllib.parse.quote_plus(query)
    url = f"https://html.duckduckgo.com/html/?q={encoded_query}"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/115.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "ru-RU,ru;q=0.8,en-US;q=0.5,en;q=0.3",
        "Referer": "https://duckduckgo.com/"
    }
    try:
        async with session.get(url, headers=headers, timeout=8) as resp:
            if resp.status == 200:
                html = await resp.text()
                if "ddg-captcha" in html or "captcha" in html:
                    return False, "CAPTCHA_BLOCKED"
                
                matches = re.findall(r'class="result__a"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', html, re.DOTALL)
                
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
                    
                    if "duckduckgo.com" not in clean_link:
                        results.append({"title": clean_title, "url": clean_link})
                return True, results
            return False, f"HTTP {resp.status}"
    except Exception as e:
        return False, str(e)