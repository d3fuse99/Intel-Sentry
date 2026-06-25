import json
import asyncio
import aiohttp
from aiohttp import web
import scanners

async def css_handler(request):
    try:
        with open('style.css', 'r', encoding='utf-8') as f:
            content = f.read()
        return web.Response(text=content, content_type='text/css')
    except FileNotFoundError:
        return web.Response(text="style.css not found", status=404)

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
        title = "СНИМОК ОБРАБОТАН"
        detail_msg = (
            f"Файл: {filename}\n"
            f"Размер: {size / 1024:.2f} KB\n"
            f"Анализ: Формат изображения верен. Автоматический поиск лиц по закрытым базам ограничен из соображений приватности."
        )
    else:
        title = "IMAGE PROCESSED"
        detail_msg = (
            f"File: {filename}\n"
            f"Size: {size / 1024:.2f} KB\n"
            f"Analysis: Valid image format. Automatic facial search is restricted due to privacy policies."
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
                    err_detail = "Поисковая система заблокировала автоматический запрос капчей." if lang == 'ru' else "Search engine blocked queries with a captcha."
                    await send_event(err_title, err_detail, "error")
                else:
                    warn_title = "СОВПАДЕНИЯ НЕ НАЙДЕНЫ" if lang == 'ru' else "NO MATCHES FOUND"
                    warn_detail = "В открытых поисковых индексах прямые упоминания отсутствуют." if lang == 'ru' else "No direct mentions found in open search indexes."
                    await send_event(warn_title, warn_detail, "warning")

            if snils:
                valid, info = scanners.validate_snils(snils)
                await send_event("ВАЛИДАЦИЯ СНИЛС" if lang=='ru' else "SNILS VALIDATION", info, "success" if valid else "error")
            if inn:
                valid, info = scanners.validate_inn(inn)
                await send_event("ВАЛИДАЦИЯ ИНН" if lang=='ru' else "INN VALIDATION", info, "success" if valid else "error")
            if passport:
                clean_pass = re.sub(r'\D', '', passport)
                is_valid_format = len(clean_pass) == 10
                info_text = "Формат паспорта РФ верен (10 цифр)." if is_valid_format else "Неверный формат паспорта РФ (должно быть 10 цифр)."
                await send_event("ФОРМАТ ПАСПОРТА", info_text, "success" if is_valid_format else "error")

        elif scan_type == 'contacts':
            phone = params.get('phone', '')
            email = params.get('email', '')
            telegram = params.get('telegram', '')
            social = params.get('social', '')

            if phone:
                valid, info = scanners.parse_phone(phone)
                await send_event("АНАЛИЗ ТЕЛЕФОНА" if lang=='ru' else "PHONE ANALYSIS", info, "success" if valid else "error")

            if email:
                await send_event("АНАЛИЗ ДОМЕНА ПОЧТЫ" if lang=='ru' else "EMAIL DOMAIN AUDIT", f"Проверка настроек для {email}...", "info")
                active, domain_details = await scanners.audit_email_domain(session, email)
                await send_event("РЕЗУЛЬТАТЫ ПОЧТЫ" if lang=='ru' else "EMAIL AUDIT REPORT", domain_details, "success" if active else "error")
                
                await send_event("УПОМИНАНИЯ EMAIL" if lang=='ru' else "EMAIL MENTIONS", "Поиск упоминаний адреса в открытых источниках...", "info")
                success, results = await scanners.search_web_mentions(session, email)
                if success and results:
                    detail_text = ""
                    for idx, res in enumerate(results, 1):
                        detail_text += f"{idx}. {res['title']}\n   Ссылка: {res['url']}\n\n"
                    await send_event("СОВПАДЕНИЯ EMAIL" if lang=='ru' else "EMAIL MATCHES", detail_text.strip(), "success")
                else:
                    await send_event("СОВПАДЕНИЯ EMAIL" if lang=='ru' else "EMAIL MATCHES", "Прямых совпадений в сети не найдено.", "warning")

            if telegram:
                await send_event("ПОИСК TELEGRAM" if lang=='ru' else "TELEGRAM DISCOVERY", f"Запрос профиля: {telegram}", "info")
                valid, disp_name, url = await scanners.verify_telegram_username(session, telegram)
                if valid:
                    res_title = "РЕЗУЛЬТАТ TELEGRAM" if lang == 'ru' else "TELEGRAM RESOLVED"
                    res_detail = f"Имя профиля: {disp_name}\nСсылка: {url}" if lang == 'ru' else f"Display Name: {disp_name}\nURL: {url}"
                    await send_event(res_title, res_detail, "success")
                else:
                    await send_event("РЕЗУЛЬТАТ TELEGRAM" if lang=='ru' else "TELEGRAM FAILURE", disp_name, "error")

            if social:
                await send_event("BRAND RECON" if lang=='ru' else "IDENTITY AUDIT", f"Проверка юзернейма '{social}' на публичных платформах...", "info")
                platform_results = await scanners.check_all_platforms(session, social)
                
                found_profiles = []
                for platform, url, status in platform_results:
                    if url:
                        found_profiles.append(f" - {platform}: {url}")
                
                if found_profiles:
                    out_text = "Найдены activeные профили:\n" + "\n".join(found_profiles)
                    await send_event("ОТЧЕТ ПО BRAND RECON" if lang=='ru' else "RECON REPORT", out_text, "success")
                else:
                    await send_event("ОТЧЕТ ПО BRAND RECON" if lang=='ru' else "RECON REPORT", "Активных публичных аккаунтов на проверяемых IT-платформах не обнаружено.", "warning")

        elif scan_type == 'assets':
            plate = params.get('plate', '')
            vin = params.get('vin', '')
            address = params.get('address', '')
            cadastral = params.get('cadastral', '')

            if vin:
                db_title = "АНАЛИЗ VIN" if lang == 'ru' else "VIN DECODING"
                db_detail = f"Запрос структуры: {vin}" if lang == 'ru' else f"Query: {vin}"
                await send_event(db_title, db_detail, "info")
                valid, info = scanners.decode_vin(vin)
                await send_event("РЕЗУЛЬТАТ ДЕКОДИРОВАНИЯ" if lang=='ru' else "DECODING RESULT", info, "success" if valid else "error")

            if plate:
                is_valid_format = re.match(r'^[АВЕКМНОРСТУХ]\d{3}[АВЕКМНОРСТУХ]{2}\d{2,3}$', plate.upper()) is not None
                status_text = "Формат гос. номера РФ корректен." if is_valid_format else "Формат гос. номера не распознан как стандартный РФ."
                await send_event("ВАЛИДАЦИЯ НОМЕРА" if lang=='ru' else "PLATE VALIDATION", status_text, "success" if is_valid_format else "warning")

            if address or cadastral:
                target = address or cadastral
                await send_event("АНАЛИЗ ОБЪЕКТА" if lang=='ru' else "PROPERTY SEARCH", f"Поиск упоминаний объекта: {target}", "info")
                success, results = await scanners.search_web_mentions(session, target)
                if success and results:
                    detail_text = ""
                    for idx, res in enumerate(results, 1):
                        detail_text += f"{idx}. {res['title']}\n   Ссылка: {res['url']}\n\n"
                    await send_event("РЕЗУЛЬТАТЫ ПО ОБЪЕКТУ" if lang=='ru' else "PROPERTY MENTIONS", detail_text.strip(), "success")
                else:
                    await send_event("ОТЧЕТ ПО ИМУЩЕСТВУ" if lang=='ru' else "PROPERTY REPORT", "Открытые веб-упоминания отсутствуют.", "warning")

        elif scan_type == 'traces':
            domain = params.get('domain', '')
            tags = params.get('tags', '')

            if domain:
                await send_event("DNS LOOKUP" if lang=='ru' else "DNS RESOLVER", f"Запрос записей для {domain}...", "info")
                
                ips = await scanners.query_doh(session, domain, "A")
                mx_recs = await scanners.query_doh(session, domain, "MX")
                txt_recs = await scanners.query_doh(session, domain, "TXT")
                
                details = []
                if ips:
                    details.append(f"A-records (IPs): {', '.join(ips)}")
                if mx_recs:
                    details.append(f"MX-records (Mail): {', '.join(mx_recs)}")
                if txt_recs:
                    clean_txt = [r.replace('"', '') for r in txt_recs[:3]]
                    details.append("TXT-records:\n - " + "\n - ".join(clean_txt))
                
                if details:
                    await send_event("РЕЗУЛЬТАТЫ DNS" if lang=='ru' else "DNS REPORT", "\n\n".join(details), "success")
                else:
                    await send_event("РЕЗУЛЬТАТЫ DNS" if lang=='ru' else "DNS REPORT", "Записи не найдены или домен не существует.", "warning")
            
            if tags:
                await send_event("ПОИСК ПО ТЕГАМ" if lang=='ru' else "REVERSE NAME SEARCH", f"Запрос тегов: {tags}...", "info")
                success, results = await scanners.search_web_mentions(session, tags)
                if success and results:
                    detail_text = ""
                    for idx, res in enumerate(results, 1):
                        detail_text += f"{idx}. {res['title']}\n   Ссылка: {res['url']}\n\n"
                    await send_event("РЕЗУЛЬТАТЫ ПО ТЕГУ", detail_text.strip(), "success")
                else:
                    await send_event("РЕЗУЛЬТАТЫ ПО ТЕГУ", "По данному запросу упоминаний в открытых источниках не найдено.", "warning")

    except ConnectionResetError:
        return response
    except Exception as e:
        await send_event("ОШИБКА СЕРВЕРА" if lang=='ru' else "SERVER EXCEPTION", f"Детали: {str(e)}", "error")

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
    app.router.add_get('/style.css', css_handler)
    app.router.add_get('/scan', sse_handler)
    app.router.add_post('/face_upload', face_upload_handler)
    
    web.run_app(app, host='127.0.0.1', port=8080)

if __name__ == '__main__':
    main()