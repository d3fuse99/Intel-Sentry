import re
import urllib.parse
import hashlib
import random
from datetime import datetime, timedelta
import asyncio
import aiohttp

USER_AGENTS = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

def get_rng(source_str):
    clean = source_str.strip().lower()
    h = hashlib.sha256(clean.encode('utf-8')).digest()
    seed = int.from_bytes(h[:4], 'big')
    return random.Random(seed)

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
                    return True, display_name, url
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

async def check_duolingo(session, email):
    url = f"https://www.duolingo.com/2017-06-30/users?email={email}"
    try:
        async with session.get(url, headers={"User-Agent": USER_AGENTS}, timeout=5) as resp:
            if resp.status == 200:
                data = await resp.json()
                users = data.get("users", [])
                if users:
                    username = users[0].get("username", "unknown")
                    name = users[0].get("name", "unknown")
                    return True, f"Duolingo (username: {username}, name: {name})"
    except Exception:
        pass
    return False, None

async def check_gravatar(session, email):
    clean = email.strip().lower()
    m = hashlib.md5(clean.encode('utf-8')).hexdigest()
    url = f"https://ru.gravatar.com/{m}.json"
    try:
        async with session.get(url, headers={"User-Agent": USER_AGENTS}, timeout=5) as resp:
            if resp.status == 200:
                data = await resp.json()
                entry = data.get("entry", [{}])[0]
                username = entry.get("preferredUsername", "unknown")
                display_name = entry.get("displayName", "unknown")
                return True, f"Gravatar (username: {username}, name: {display_name})"
    except Exception:
        pass
    return False, None

def generate_telegram_osint_data(username, lang="ru"):
    rng = get_rng(username)
    clean_user = username.lstrip('@').lower()
    tg_id = rng.randint(100000000, 999999999) if rng.random() > 0.3 else rng.randint(5000000000, 6999999999)
    country_code = rng.choice(["380", "7"])
    if country_code == "380":
        prefix = rng.choice(["50", "66", "95", "99", "67", "68", "96", "97", "98", "63", "73", "93"])
        phone = f"+380{prefix}{rng.randint(100, 999)}{rng.randint(10, 99)}{rng.randint(10, 99)}"
    else:
        prefix = rng.choice(["901", "903", "905", "910", "915", "920", "925", "926", "950", "999"])
        phone = f"+7{prefix}{rng.randint(100, 999)}{rng.randint(10, 99)}{rng.randint(10, 99)}"
        
    history = []
    current_date = datetime.now()
    date_str = current_date.strftime("%d.%m.%Y")
    history.append(f"{date_str} {'→' if lang=='ru' else '->'} @{clean_user}")
    
    prev_names = [f"{clean_user}_old", f"{clean_user}_priv", f"{clean_user}_tgr", f"{clean_user}roblox", f"taniya_{clean_user}", f"sherlock_{clean_user}"]
    rng.shuffle(prev_names)
    for i in range(1, rng.randint(3, 5)):
        past_date = current_date - timedelta(days=i*rng.randint(30, 120))
        history.append(f"{past_date.strftime('%d.%m.%Y')} {'→' if lang=='ru' else '->'} @{prev_names[i % len(prev_names)]}")
        
    contacts = []
    for _ in range(rng.randint(1, 3)):
        c_code = rng.choice(["380", "7"])
        if c_code == "380":
            contacts.append(f"+380{rng.choice(['50', '67', '63'])}{rng.randint(1000000, 9999999)}")
        else:
            contacts.append(f"+7{rng.choice(['910', '926', '903'])}{rng.randint(1000000, 9999999)}")
            
    gifts = [str(rng.randint(1000000000, 9999999999)) for _ in range(rng.randint(5, 12))]
    
    return {
        "id": tg_id,
        "phone": phone,
        "history": history,
        "contacts": contacts,
        "gifts": gifts
    }

def generate_personality_osint(fio, passport_in="", snils_in="", inn_in=""):
    rng = get_rng(fio)
    
    parts = fio.split()
    surname = parts[0] if len(parts) > 0 else "Иванов"
    name = parts[1] if len(parts) > 1 else "Иван"
    patronymic = parts[2] if len(parts) > 2 else "Иванович"
    
    birth_year = rng.randint(1970, 2005)
    birth_month = rng.randint(1, 12)
    birth_day = rng.randint(1, 28)
    birth_date = f"{birth_day:02d}.{birth_month:02d}.{birth_year}"
    
    passport = passport_in if passport_in else f"{rng.randint(10, 99)} {rng.randint(10, 99)} {rng.randint(100000, 999999)}"
    snils = snils_in if snils_in else f"{rng.randint(100, 999)}-{rng.randint(100, 999)}-{rng.randint(100, 999)} {rng.randint(10, 99)}"
    inn = inn_in if inn_in else f"{rng.randint(770000000000, 779999999999)}"
    
    city = rng.choice(["Москва", "Киев", "Санкт-Петербург", "Минск", "Новосибирск", "Одесса"])
    street = rng.choice(["Ленина", "Хрещатик", "Мира", "Шевченко", "Победы", "Гагарина"])
    address = f"г. {city}, ул. {street}, д. {rng.randint(1, 150)}, кв. {rng.randint(1, 450)}"
    
    phones = [f"+7910{rng.randint(1000000, 9999999)}", f"+38067{rng.randint(1000000, 9999999)}"]
    phone = rng.choice(phones)
    
    emails = [f"{surname.lower()}_{rng.randint(10,99)}@mail.ru", f"{name.lower()}{birth_year}@gmail.com"]
    email = rng.choice(emails)
    
    socials = [f"vk.com/id{rng.randint(1000000, 99999999)}", f"instagram.com/{surname.lower()}_{name.lower()}"]
    
    return {
        "fio": f"{surname} {name} {patronymic}",
        "birth_date": birth_date,
        "passport": passport,
        "snils": snils,
        "inn": inn,
        "address": address,
        "phone": phone,
        "email": email,
        "socials": socials
    }

def generate_phone_osint(phone):
    rng = get_rng(phone)
    digits = re.sub(r'\D', '', phone)
    
    surnames = ["Иванов", "Петров", "Сидоров", "Зеленко", "Коваленко", "Смирнов", "Морозов"]
    names = ["Алексей", "Дмитрий", "Сергей", "Андрей", "Михаил", "Николай", "Роман"]
    patronymics = ["Александрович", "Петрович", "Владимирович", "Игоревич", "Сергеевич"]
    
    fio = f"{rng.choice(surnames)} {rng.choice(names)} {rng.choice(patronymics)}"
    tg_id = rng.randint(100000000, 999999999)
    username = f"@{rng.choice(names).lower()}_{rng.randint(100, 999)}"
    
    city = rng.choice(["Москва", "Киев", "Минск", "Харьков", "Днепр"])
    address = f"г. {city}, ул. {rng.choice(['Грушевского', 'Тверская', 'Московская'])}, д. {rng.randint(1, 100)}"
    
    vehicle = f"{rng.choice(['А', 'В', 'Е', 'К', 'М', 'Н', 'О', 'Р', 'С', 'Т', 'У', 'Х'])}{rng.randint(100, 999)}{rng.choice(['А', 'В', 'Е', 'К', 'М', 'Н', 'О', 'Р', 'С', 'Т', 'У', 'Х'])}{rng.choice(['А', 'В', 'Е', 'К', 'М', 'Н', 'О', 'Р', 'С', 'Т', 'У', 'Х'])}{rng.randint(10, 199)}"
    
    tags = [f"{fio.split()[1]} Рабочий", f"Андрюха Машина", f"Алексей {city}", f"Сосед {rng.randint(10,99)}"]
    
    return {
        "phone": f"+{digits}",
        "owner": fio,
        "telegram_id": tg_id,
        "username": username,
        "address": address,
        "vehicle": vehicle,
        "tags": tags
    }

def generate_email_osint(email):
    rng = get_rng(email)
    user_part = email.split('@')[0]
    
    surnames = ["Иванов", "Зайцев", "Кузнецов", "Кравченко", "Шевченко", "Попов", "Лебедев"]
    names = ["Артем", "Максим", "Евгений", "Олег", "Илья", "Владислав", "Антон"]
    
    fio = f"{rng.choice(surnames)} {rng.choice(names)}"
    phone = f"+7926{rng.randint(1000000, 9999999)}" if rng.random() > 0.5 else f"+38050{rng.randint(1000000, 9999999)}"
    
    platforms = ["Github", "Steam", "Reddit", "VK", "DockerHub", "Pornhub", "Vimeo", "Telegram"]
    rng.shuffle(platforms)
    registered = platforms[:rng.randint(3, 6)]
    
    leaks = []
    available_leaks = [
        {"db": "Canva (2019)", "pass_hint": "art***12"},
        {"db": "Rambler (2016)", "pass_hint": "qwerty***"},
        {"db": "Adobe (2013)", "pass_hint": "12345***"},
        {"db": "Yandex Food (2022)", "pass_hint": "none_hash"},
        {"db": "Gemini Alt (2024)", "pass_hint": "pass_un***"}
    ]
    rng.shuffle(available_leaks)
    for i in range(rng.randint(1, 3)):
        leaks.append(available_leaks[i])
        
    return {
        "email": email,
        "owner": fio,
        "phone": phone,
        "registered_on": registered,
        "leaks": leaks
    }

def generate_assets_osint(plate="", vin="", address="", cadastral=""):
    source = plate or vin or address or cadastral
    rng = get_rng(source)
    
    brands = ["BMW 530i", "Mercedes-Benz E200", "Lada Vesta", "Audi A6", "Hyundai Solaris", "Toyota Camry"]
    car = rng.choice(brands)
    car_year = rng.randint(2010, 2024)
    
    owner_surname = rng.choice(["Клименко", "Васильев", "Соколов", "Козлов", "Новиков", "Федоров"])
    owner_name = rng.choice(["Павел", "Виталий", "Александр", "Игорь", "Денис"])
    owner = f"{owner_surname} {owner_name}"
    
    car_vin = vin if vin else f"XTA211440C{rng.randint(1000000, 9999999)}"
    car_plate = plate if plate else f"X{rng.randint(100, 999)}XX{rng.randint(77, 199)}"
    
    fine_count = rng.randint(0, 8)
    fine_sum = fine_count * rng.choice([500, 1000, 1500, 5000])
    
    cad = cadastral if cadastral else f"{rng.randint(10, 99)}:{rng.randint(10, 99)}:{rng.randint(1000000, 9999999)}:{rng.randint(1000, 9999)}"
    addr = address if address else f"г. Москва, ул. Арбат, д. {rng.randint(1, 50)}, кв. {rng.randint(1, 100)}"
    area = rng.randint(35, 120)
    cost = area * rng.choice([150000, 220000, 310000])
    
    residents = [f"{rng.choice(['Иванов', 'Петров', 'Коваленко'])} {rng.choice(['А.', 'С.', 'Д.'])}."]
    if rng.random() > 0.5:
        residents.append(f"{rng.choice(['Смирнов', 'Морозов'])} {rng.choice(['И.', 'В.', 'М.'])}.")
        
    return {
        "car": car,
        "car_year": car_year,
        "owner": owner,
        "vin": car_vin,
        "plate": car_plate,
        "fines_count": fine_count,
        "fines_sum": fine_sum,
        "cadastral": cad,
        "address": addr,
        "area": area,
        "cost": cost,
        "residents": residents
    }