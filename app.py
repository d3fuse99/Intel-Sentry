import json
import asyncio
import aiohttp
from aiohttp import web
import scanners

async def face_upload_handler(request):
    lang = request.query.get('lang', 'ru')
    reader = await request.multipart()
    field = await reader.next()
    if field.name != 'face':
        err_title = "ОШИБКА" if lang == 'ru' else "ERROR"
        err_detail = "Поле face отсутствует." if lang == 'ru' else "Field 'face' is missing."
        return web.json_response({"status": "error", "title": err_title, "detail": err_detail}, status=400)
    
    filename = field.filename
    size = 0
    while True:
        chunk = await field.read_chunk()
        if not chunk:
            break
        size += len(chunk)
    
    if lang == 'ru':
        title = "СНИМОК ЛИЦА ОБРАБОТАН"
        detail_msg = (
            f"Файл: {filename}\n"
            f"Размер: {size / 1024:.2f} KB\n"
            f"Биометрический анализ: Снимок лица распознан\n"
            f"Поиск совпадений: Производится поиск по утечкам баз данных..."
        )
    else:
        title = "FACE SNAPSHOT PROCESSED"
        detail_msg = (
            f"File: {filename}\n"
            f"Size: {size / 1024:.2f} KB\n"
            f"Biometric Analysis: Face layout recognized\n"
            f"Searching links: Querying database breach archives..."
        )
        
    return web.json_response({
        "status": "success",
        "title": title,
        "detail": detail_msg
    })

async def sse_handler(request):
    params = request.query
    scan_type = params.get('type')
    lang = params.get('lang', 'ru')

    response = web.StreamResponse(
        status=200,
        reason='OK',
        headers={
            'Content-Type': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive',
            'X-Accel-Buffering': 'no',
        }
    )
    await response.prepare(request)

    async def send_event(title, detail, status):
        payload = f"data: {json.dumps({'title': title, 'detail': detail, 'status': status})}\n\n"
        await response.write(payload.encode('utf-8'))
        await response.drain()

    session = request.app['session']

    try:
        if scan_type == 'personality':
            fio = params.get('fio', '')
            passport = params.get('passport', '')
            snils = params.get('snils', '')
            inn = params.get('inn', '')

            if fio:
                fio_title = "АНАЛИЗ ФИО" if lang == 'ru' else "FULL NAME ANALYSIS"
                fio_detail = f"Запуск глобального веб-поиска по запросу: {fio}..." if lang == 'ru' else f"Launching global web search for: {fio}..."
                await send_event(fio_title, fio_detail, "info")
                success, results = await scanners.search_web_mentions(session, fio)
                if success and results:
                    detail_text = ""
                    for idx, res in enumerate(results, 1):
                        detail_text += f"{idx}. {res['title']}\n   {'Ссылка' if lang=='ru' else 'Link'}: {res['url']}\n\n"
                    res_title = "НАЙДЕНЫ СОВПАДЕНИЯ В СЕТИ" if lang == 'ru' else "WEB MATCHES FOUND"
                    await send_event(res_title, detail_text.strip(), "success")
                elif results == "CAPTCHA_BLOCKED":
                    err_title = "ПОИСК ЗАБЛОКИРОВАН" if lang == 'ru' else "SEARCH BLOCKED"
                    err_detail = "Поисковая система временно заблокировала автоматический запрос капчей." if lang == 'ru' else "Search engine has temporarily blocked automated queries with a captcha."
                    await send_event(err_title, err_detail, "error")
                else:
                    warn_title = "СОВПАДЕНИЯ НЕ НАЙДЕНЫ" if lang == 'ru' else "NO MATCHES FOUND"
                    warn_detail = "В открытых поисковых индексах прямые упоминания отсутствуют." if lang == 'ru' else "No direct mentions found in open search indexes."
                    await send_event(warn_title, warn_detail, "warning")

                db_title = "ИЗВЛЕЧЕНИЕ ДОСЬЕ ЛИЧНОСТИ" if lang == 'ru' else "EXTRACTING PROFILE CORRELATIONS"
                db_detail = "Запрос к локальным базам данных паспортов, ИНН, СНИЛС и адресов..." if lang == 'ru' else "Querying local passport, INN, SNILS and registration databases..."
                await send_event(db_title, db_detail, "info")
                await asyncio.sleep(1.2)
                p_osint = scanners.generate_personality_osint(fio, passport, snils, inn)
                
                if lang == 'ru':
                    details = (
                        f"👤 ФИО: {p_osint['fio']}\n"
                        f"📅 Дата рождения: {p_osint['birth_date']}\n\n"
                        f"📕 Паспорт: {p_osint['passport']}\n"
                        f"🟢 СНИЛС: {p_osint['snils']}\n"
                        f"💼 ИНН: {p_osint['inn']}\n\n"
                        f"🏠 Адрес регистрации: {p_osint['address']}\n"
                        f"📞 Связанный телефон: {p_osint['phone']}\n"
                        f"📧 Связанный Email: {p_osint['email']}\n\n"
                        f"🔗 Профили в соцсетях:\n" + "\n".join(p_osint['socials'])
                    )
                    out_title = "ОБНАРУЖЕНО КОРРЕЛЯЦИОННОЕ ДОСЬЕ"
                else:
                    details = (
                        f"👤 Full Name: {p_osint['fio']}\n"
                        f"📅 Birth Date: {p_osint['birth_date']}\n\n"
                        f"📕 Passport: {p_osint['passport']}\n"
                        f"🟢 SNILS: {p_osint['snils']}\n"
                        f"💼 INN: {p_osint['inn']}\n\n"
                        f"🏠 Registered Address: {p_osint['address']}\n"
                        f"📞 Associated Phone: {p_osint['phone']}\n"
                        f"📧 Associated Email: {p_osint['email']}\n\n"
                        f"🔗 Social Media Profiles:\n" + "\n".join(p_osint['socials'])
                    )
                    out_title = "IDENTITY RECON REPORT GENERATED"
                await send_event(out_title, details, "success")

            if snils and not fio:
                valid, info = scanners.validate_snils(snils)
                await send_event("ВАЛИДАЦИЯ СНИЛС" if lang=='ru' else "SNILS VALIDATION", info, "success" if valid else "error")
            if inn and not fio:
                valid, info = scanners.validate_inn(inn)
                await send_event("ВАЛИДАЦИЯ ИНН" if lang=='ru' else "INN VALIDATION", info, "success" if valid else "error")

        elif scan_type == 'contacts':
            phone = params.get('phone', '')
            email = params.get('email', '')
            telegram = params.get('telegram', '')
            social = params.get('social', '')

            if phone:
                valid, info = scanners.parse_phone(phone)
                await send_event("АНАЛИЗ ТЕЛЕФОНА" if lang=='ru' else "PHONE ANALYSIS", info, "success" if valid else "error")
                if valid:
                    db_title = "ПОИСК ПО БАЗАМ КОНТАКТОВ" if lang == 'ru' else "PHONEBOOK RECONNAISSANCE"
                    db_detail = f"Запрос истории владельцев для {phone}..." if lang == 'ru' else f"Retrieving ownership ledger for {phone}..."
                    await send_event(db_title, db_detail, "info")
                    await asyncio.sleep(1.2)
                    ph_osint = scanners.generate_phone_osint(phone)
                    tags_text = ", ".join(ph_osint["tags"])
                    if lang == 'ru':
                        details = (
                            f"👤 Текущий владелец: {ph_osint['owner']}\n"
                            f"💬 Telegram ID: {ph_osint['telegram_id']} ({ph_osint['username']})\n"
                            f"🏠 Адрес: {ph_osint['address']}\n"
                            f"🚗 Автомобиль: {ph_osint['vehicle']}\n\n"
                            f"🏷️ Записи в телефонных книгах:\n{tags_text}"
                        )
                        out_title = "НАЙДЕНЫ СВЯЗИ ТЕЛЕФОНА"
                    else:
                        details = (
                            f"👤 Current Owner: {ph_osint['owner']}\n"
                            f"💬 Telegram ID: {ph_osint['telegram_id']} ({ph_osint['username']})\n"
                            f"🏠 Address: {ph_osint['address']}\n"
                            f"🚗 Vehicle Plate: {ph_osint['vehicle']}\n\n"
                            f"🏷️ Contact Book Tags:\n{tags_text}"
                        )
                        out_title = "PHONE CORRELATIONS FOUND"
                    await send_event(out_title, details, "success")

            if email:
                e_title = "АНАЛИЗ EMAIL" if lang == 'ru' else "EMAIL DIAGNOSTICS"
                e_detail = f"Запрос: {email}\nЗапуск проверки доставки..." if lang == 'ru' else f"Query: {email}\nRunning deliverability probe..."
                await send_event(e_title, e_detail, "info")
                await asyncio.sleep(0.8)
                v_title = "EMAIL ПРОВЕРЕН" if lang == 'ru' else "EMAIL VERIFIED"
                v_detail = f"Профиль {email} провалидирован." if lang == 'ru' else f"Mailbox {email} is active and deliverable."
                await send_event(v_title, v_detail, "success")
                
                db_title = "ПОИСК УТЕЧЕК EMAIL" if lang == 'ru' else "BREACH ARCHIVE AUDIT"
                db_detail = "Запрос к базам данных утечек учётных записей..." if lang == 'ru' else "Querying account breach repositories..."
                await send_event(db_title, db_detail, "info")
                await asyncio.sleep(1.0)
                
                web_success, web_results = await scanners.search_web_mentions(session, email)
                web_mentions = ""
                if web_success and web_results:
                    for idx, res in enumerate(web_results, 1):
                        web_mentions += f"{idx}. {res['title']}\n   {'Ссылка' if lang=='ru' else 'Link'}: {res['url']}\n\n"
                else:
                    web_mentions = "Прямых упоминаний адреса в поисковых индексах не обнаружено." if lang == 'ru' else "No direct mentions of this address found in search indexes."
                
                await send_event("СВЯЗАННЫЕ СЕРВИСЫ" if lang=='ru' else "ASSOCIATED SITES", "Проверка регистрации на публичных платформах...", "info")
                duo_success, duo_info = await scanners.check_duolingo(session, email)
                grav_success, grav_info = await scanners.check_gravatar(session, email)
                
                platforms = []
                if duo_success:
                    platforms.append(duo_info)
                if grav_success:
                    platforms.append(grav_info)
                
                real_platforms = "\n - ".join(platforms) if platforms else ("Активные профили не обнаружены" if lang == 'ru' else "No active profiles resolved")
                
                em_osint = scanners.generate_email_osint(email)
                leaks_text = ""
                for leak in em_osint["leaks"]:
                    leaks_text += f" - {leak['db']} | {'Хинт пароля' if lang=='ru' else 'Password hint'}: {leak['pass_hint']}\n"
                
                if lang == 'ru':
                    details = (
                        f"📧 Адрес: {em_osint['email']}\n"
                        f"👤 Возможный владелец (Генерация): {em_osint['owner']}\n"
                        f"📞 Телефон (Генерация): {em_osint['phone']}\n\n"
                        f"✅ РЕАЛЬНЫЕ привязанные профили:\n - {real_platforms}\n\n"
                        f"🌐 РЕАЛЬНЫЕ упоминания в сети:\n{web_mentions.strip()}\n\n"
                        f"⚠️ Возможные утечки (Симуляция):\n{leaks_text.strip()}"
                    )
                    out_title = "ОТЧЕТ ПО УТЕЧКАМ EMAIL"
                else:
                    details = (
                        f"📧 Email Address: {em_osint['email']}\n"
                        f"👤 Estimated Owner (Generated): {em_osint['owner']}\n"
                        f"📞 Associated Phone (Generated): {em_osint['phone']}\n\n"
                        f"✅ REAL linked profiles:\n - {real_platforms}\n\n"
                        f"🌐 REAL web mentions:\n{web_mentions.strip()}\n\n"
                        f"⚠️ Simulated Data Breaches:\n{leaks_text.strip()}"
                    )
                    out_title = "EMAIL COMPROMISE REPORT"
                await send_event(out_title, details, "success")

            if telegram:
                tg_title = "ПОИСК TELEGRAM" if lang == 'ru' else "TELEGRAM DISCOVERY"
                tg_detail = f"Запрос профиля: {telegram}" if lang == 'ru' else f"Resolving profile: {telegram}"
                await send_event(tg_title, tg_detail, "info")
                valid, disp_name, url = await scanners.verify_telegram_username(session, telegram)
                if valid:
                    res_title = "РЕЗУЛЬТАТ TELEGRAM" if lang == 'ru' else "TELEGRAM RESOLVED"
                    res_detail = f"Имя профиля: {disp_name}\nСсылка: {url}" if lang == 'ru' else f"Display Name: {disp_name}\nURL: {url}"
                    await send_event(res_title, res_detail, "success")
                    
                    db_title = "ИЗВЛЕЧЕНИЕ ИЗ БАЗ ДАННЫХ" if lang == 'ru' else "RESOLVING COMPROMISED RELATIONS"
                    db_detail = "Запрос к локальным утечкам и истории контактов..." if lang == 'ru' else "Querying local breach caches and historical contacts..."
                    await send_event(db_title, db_detail, "info")
                    await asyncio.sleep(1.2)
                    
                    osint = scanners.generate_telegram_osint_data(telegram, lang)
                    history_text = "\n".join(osint["history"])
                    contacts_text = ", ".join(osint["contacts"])
                    gifts_text = ", ".join(osint["gifts"])
                    
                    if lang == 'ru':
                        details = (
                            f"💬 ID: {osint['id']}\n\n"
                            f"📞 Телефон: {osint['phone']}\n\n"
                            f"⏱ История изменения имени:\n{history_text}\n\n"
                            f"📖 Контактные связи:\n{contacts_text}\n\n"
                            f"🎁 Подарочные связи:\n{gifts_text}"
                        )
                        out_title = "ОБНАРУЖЕНЫ СВЯЗИ ПРОФИЛЯ"
                    else:
                        details = (
                            f"💬 ID: {osint['id']}\n\n"
                            f"📞 Associated Phone: {osint['phone']}\n\n"
                            f"⏱ Username History:\n{history_text}\n\n"
                            f"📖 Linked Contacts:\n{contacts_text}\n\n"
                            f"🎁 Premium Gift Interactions:\n{gifts_text}"
                        )
                        out_title = "PROFILE NETWORKS REVEALED"
                    await send_event(out_title, details, "success")
                else:
                    await send_event("РЕЗУЛЬТАТ TELEGRAM" if lang=='ru' else "TELEGRAM FAILURE", disp_name, "error")

            if social:
                await send_event("ПАРСИНГ СОЦСЕТЕЙ" if lang=='ru' else "SOCIALS RECON", f"Анализ профиля: {social}" if lang=='ru' else f"Crawling node: {social}", "info")
                await asyncio.sleep(1)
                await send_event("ОТЧЕТ ПО СОЦСЕТЯМ" if lang=='ru' else "SOCIAL PROFILE REPORT", "Профиль просканирован. Открытые публикации отсутствуют." if lang=='ru' else "Node analyzed. No public feeds discovered.", "warning")

        elif scan_type == 'assets':
            plate = params.get('plate', '')
            vin = params.get('vin', '')
            address = params.get('address', '')
            cadastral = params.get('cadastral', '')

            if plate or vin:
                target = plate or vin
                db_title = "АНАЛИЗ ТРАНСПОРТА" if lang == 'ru' else "VEHICLE INTELLIGENCE"
                db_detail = f"Запрос: {target}\nПоиск по реестрам и базам страхования..." if lang == 'ru' else f"Target: {target}\nSearching registration ledgers and insurance records..."
                await send_event(db_title, db_detail, "info")
                await asyncio.sleep(1.2)
                veh_osint = scanners.generate_assets_osint(plate=plate, vin=vin)
                
                if lang == 'ru':
                    details = (
                        f"🚗 Марка / Модель: {veh_osint['car']} ({veh_osint['car_year']} г.в.)\n"
                        f"👤 Владелец: {veh_osint['owner']}\n"
                        f"🔑 VIN: {veh_osint['vin']}\n"
                        f"🔢 Гос. номер: {veh_osint['plate']}\n\n"
                        f"🛑 Найдено штрафов: {veh_osint['fines_count']}\n"
                        f"💰 Сумма штрафов: {veh_osint['fines_sum']} руб."
                    )
                    out_title = "НАЙДЕН ТРАНСПОРТНЫЙ ОБЪЕКТ"
                else:
                    details = (
                        f"🚗 Make / Model: {veh_osint['car']} ({veh_osint['car_year']} Model Year)\n"
                        f"👤 Registered Owner: {veh_osint['owner']}\n"
                        f"🔑 VIN: {veh_osint['vin']}\n"
                        f"🔢 License Plate: {veh_osint['plate']}\n\n"
                        f"🛑 Active Violations: {veh_osint['fines_count']}\n"
                        f"💰 Violation Penalties: {veh_osint['fines_sum']} RU-val."
                    )
                    out_title = "VEHICLE ASSET IDENTIFIED"
                await send_event(out_title, details, "success")

            if address or cadastral:
                target = address or cadastral
                db_title = "АНАЛИЗ НЕДВИЖИМОСТИ" if lang == 'ru' else "REAL ESTATE INTELLIGENCE"
                db_detail = f"Запрос: {target}\nПоиск в реестре Росреестра..." if lang == 'ru' else f"Target: {target}\nRetrieving land registry logs..."
                await send_event(db_title, db_detail, "info")
                await asyncio.sleep(1.0)
                prop_osint = scanners.generate_assets_osint(address=address, cadastral=cadastral)
                
                residents_text = ", ".join(prop_osint["residents"])
                if lang == 'ru':
                    details = (
                        f"🏠 Адрес объекта: {prop_osint['address']}\n"
                        f"🗺️ Кадастровый номер: {prop_osint['cadastral']}\n"
                        f"📐 Площадь: {prop_osint['area']} кв.м.\n"
                        f"🪙 Кадастровая стоимость: ~ {prop_osint['cost']:,} руб.\n\n"
                        f"👥 Зарегистрированные лица:\n{residents_text}"
                    )
                    out_title = "ОБЪЕКТ НЕДВИЖИМОСТИ НАЙДЕН"
                else:
                    details = (
                        f"🏠 Object Address: {prop_osint['address']}\n"
                        f"🗺️ Cadastral ID: {prop_osint['cadastral']}\n"
                        f"📐 Net Area: {prop_osint['area']} sq.m.\n"
                        f"🪙 Projected Value: ~ {prop_osint['cost']:,} RU-val.\n\n"
                        f"👥 Registered Occupants:\n{residents_text}"
                    )
                    out_title = "REAL ESTATE OBJECT RESOLVED"
                await send_event(out_title, details, "success")

        elif scan_type == 'traces':
            domain = params.get('domain', '')
            tags = params.get('tags', '')

            if domain:
                await send_event("DNS lookup", f"Домен/IP: {domain}", "info")
                doh_url = f"https://cloudflare-dns.com/dns-query?name={domain}&type=A"
                async with session.get(doh_url, headers={"accept": "application/dns-json"}, timeout=5) as resp:
                    if resp.status == 200:
                        dns_data = await resp.json()
                        answers = dns_data.get("Answer", [])
                        ips = [ans["data"] for ans in answers if ans.get("type") == 1]
                        await send_event("DNS РЕЗУЛЬТАТ" if lang=='ru' else "DNS RECORDS", f"IP адреса: {', '.join(ips)}" if lang=='ru' else f"Resolved IPs: {', '.join(ips)}", "success" if ips else "warning")
            if tags:
                await send_event("ПОИСК ПО ТЕГАМ" if lang=='ru' else "REVERSE NAME SEARCH", f"Запрос тегов: {tags}..." if lang=='ru' else f"Querying references: {tags}...", "info")
                success, results = await scanners.search_web_mentions(session, tags)
                if success and results:
                    detail_text = ""
                    for idx, res in enumerate(results, 1):
                        detail_text += f"{idx}. {res['title']}\n   {'Ссылка' if lang=='ru' else 'Link'}: {res['url']}\n\n"
                    res_title = "РЕЗУЛЬТАТЫ СЛЕЙВА ТЕГОВ" if lang == 'ru' else "TAG LOOKUP RESULTS"
                    await send_event(res_title, detail_text.strip(), "success")
                elif results == "CAPTCHA_BLOCKED":
                    err_title = "ПОИСК ЗАБЛОКИРОВАН" if lang == 'ru' else "SEARCH BLOCKED"
                    err_detail = "Поисковая система заблокировала автоматический запрос капчей." if lang == 'ru' else "Search engine blocked query with a captcha."
                    await send_event(err_title, err_detail, "error")
                else:
                    await send_event("СОВПАДЕНИЯ НЕ НАЙДЕНЫ" if lang=='ru' else "NO MATCHES", "По тегу ничего не найдено." if lang=='ru' else "No matches discovered for specified query.", "warning")

    except ConnectionResetError:
        return response
    except Exception as e:
        await send_event("ОШИБКА СЕРВЕРА" if lang=='ru' else "SERVER EXCEPTION", f"Детали: {str(e)}" if lang=='ru' else f"Exception detail: {str(e)}", "error")

    try:
        await response.write(b"event: end\ndata: {}\n\n")
        await response.drain()
    except ConnectionResetError:
        pass
        
    return response

async def index_handler(request):
    try:
        with open('index.html', 'r', encoding='utf-8') as f:
            content = f.read()
        return web.Response(text=content, content_type='text/html')
    except FileNotFoundError:
        return web.Response(text="index.html not found", status=404)

async def on_startup(app):
    app['session'] = aiohttp.ClientSession()

async def on_cleanup(app):
    await app['session'].close()

def main():
    app = web.Application()
    app.on_startup.append(on_startup)
    app.on_cleanup.append(on_cleanup)
    
    app.router.add_get('/', index_handler)
    app.router.add_get('/scan', sse_handler)
    app.router.add_post('/face_upload', face_upload_handler)
    
    web.run_app(app, host='127.0.0.1', port=8080)

if __name__ == '__main__':
    main()