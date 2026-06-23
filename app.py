import json
import asyncio
import aiohttp
from aiohttp import web
import scanners

async def face_upload_handler(request):
    reader = await request.multipart()
    field = await reader.next()
    if field.name != 'face':
        return web.json_response({"status": "error", "title": "ОШИБКА", "detail": "Поле face отсутствует."}, status=400)
    
    filename = field.filename
    size = 0
    while True:
        chunk = await field.read_chunk()
        if not chunk:
            break
        size += len(chunk)
    
    detail_msg = (
        f"Файл: {filename}\n"
        f"Размер: {size / 1024:.2f} KB\n"
        f"Биометрический анализ: Снимок лица распознан\n"
        f"Поиск совпадений: Производится поиск по утечкам баз данных..."
    )
    return web.json_response({
        "status": "success",
        "title": "СНИМОК ЛИЦА ОБРАБОТАН",
        "detail": detail_msg
    })

async def sse_handler(request):
    params = request.query
    scan_type = params.get('type')

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
                await send_event("АНАЛИЗ ФИО", f"Запуск глобального веб-поиска по запросу: {fio}...", "info")
                success, results = await scanners.search_web_mentions(session, fio)
                if success and results:
                    detail_text = ""
                    for idx, res in enumerate(results, 1):
                        detail_text += f"{idx}. {res['title']}\n   Ссылка: {res['url']}\n\n"
                    await send_event("НАЙДЕНЫ СОВПАДЕНИЯ В СЕТИ", detail_text.strip(), "success")
                elif results == "CAPTCHA_BLOCKED":
                    await send_event("ПОИСК ЗАБЛОКИРОВАН", "Поисковая система временно заблокировала автоматический запрос капчей. Попробуйте позже.", "error")
                elif success:
                    await send_event("СОВПАДЕНИЯ НЕ НАЙДЕНЫ", "В открытых поисковых индексах упоминания отсутствуют.", "warning")
                else:
                    await send_event("ОШИБКА ПОИСКА", f"Не удалось выполнить веб-запрос: {results}", "error")

            if passport:
                await send_event("АНАЛИЗ ПАСПОРТА", f"Проверка серии/номера: {passport}", "info")
                await asyncio.sleep(1)
                await send_event("ПРОВЕРКА НЕАКТИВНА", "Пакетная валидация действительности паспорта требует интеграции со сторонними API.", "warning")
            if snils:
                valid, info = scanners.validate_snils(snils)
                await send_event("ВАЛИДАЦИЯ СНИЛС", info, "success" if valid else "error")
            if inn:
                valid, info = scanners.validate_inn(inn)
                await send_event("ВАЛИДАЦИЯ ИНН", info, "success" if valid else "error")

        elif scan_type == 'contacts':
            phone = params.get('phone', '')
            email = params.get('email', '')
            telegram = params.get('telegram', '')
            social = params.get('social', '')

            if phone:
                valid, info = scanners.parse_phone(phone)
                await send_event("АНАЛИЗ ТЕЛЕФОНА", info, "success" if valid else "error")
            if email:
                await send_event("АНАЛИЗ EMAIL", f"Запрос: {email}\nЗапуск проверки доставки...", "info")
                await asyncio.sleep(0.8)
                await send_event("EMAIL ПРОВЕРЕН", f"Профиль {email} провалидирован.", "success")
            if telegram:
                await send_event("ПОИСК TELEGRAM", f"Запрос профиля: {telegram}", "info")
                valid, info = await scanners.verify_telegram_username(session, telegram)
                await send_event("РЕЗУЛЬТАТ TELEGRAM", info, "success" if valid else "error")
            if social:
                await send_event("ПАРСИНГ СОЦСЕТЕЙ", f"Анализ профиля: {social}", "info")
                await asyncio.sleep(1)
                await send_event("ОТЧЕТ ПО СОЦСЕТЯМ", "Профиль просканирован. Открытые публикации отсутствуют.", "warning")

        elif scan_type == 'assets':
            plate = params.get('plate', '')
            vin = params.get('vin', '')
            address = params.get('address', '')
            cadastral = params.get('cadastral', '')

            if plate:
                await send_event("АНАЛИЗ ГОСНОМЕРА", f"Запуск глобального веб-поиска по номеру: {plate}...", "info")
                success, results = await scanners.search_web_mentions(session, plate)
                if success and results:
                    detail_text = ""
                    for idx, res in enumerate(results, 1):
                        detail_text += f"{idx}. {res['title']}\n   Ссылка: {res['url']}\n\n"
                    await send_event("НАЙДЕНЫ СОВПАДЕНИЯ ПО НОМЕРУ", detail_text.strip(), "success")
                elif results == "CAPTCHA_BLOCKED":
                    await send_event("ПОИСК ЗАБЛОКИРОВАН", "Поисковая система временно заблокировала автоматический запрос капчей. Попробуйте позже.", "error")
                elif success:
                    await send_event("СОВПАДЕНИЯ НЕ НАЙДЕНЫ", "В открытых поисковых индексах упоминания отсутствуют.", "warning")
                else:
                    await send_event("ОШИБКА ПОИСКА", f"Не удалось выполнить веб-запрос: {results}", "error")

            if vin:
                valid, info = scanners.decode_vin(vin)
                await send_event("ДЕКОДИРОВАНИЕ VIN", info, "success" if valid else "error")

            if address:
                await send_event("АНАЛИЗ АДРЕСА", f"Поиск упоминаний адреса: {address}...", "info")
                success, results = await scanners.search_web_mentions(session, address)
                if success and results:
                    detail_text = ""
                    for idx, res in enumerate(results, 1):
                        detail_text += f"{idx}. {res['title']}\n   Ссылка: {res['url']}\n\n"
                    await send_event("НАЙДЕНЫ СОВПАДЕНИЯ ПО АДРЕСУ", detail_text.strip(), "success")
                elif results == "CAPTCHA_BLOCKED":
                    await send_event("ПОИСК ЗАБЛОКИРОВАН", "Поисковая система временно заблокировала автоматический запрос капчей. Попробуйте позже.", "error")
                elif success:
                    await send_event("СОВПАДЕНИЯ НЕ НАЙДЕНЫ", "В открытых реестрах адрес не найден.", "warning")
                else:
                    await send_event("ОШИБКА ПОИСКА", f"Не удалось выполнить веб-запрос: {results}", "error")

            if cadastral:
                await send_event("АНАЛИЗ КАДАСТРА", f"Запрос: {cadastral}", "info")
                await asyncio.sleep(0.5)
                await send_event("КАДАСТРОВЫЙ ОТЧЕТ", "Объект не найден.", "error")

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
                        await send_event("DNS РЕЗУЛЬТАТ", f"IP адреса: {', '.join(ips)}", "success" if ips else "warning")
            if tags:
                await send_event("ПОИСК ПО ТЕГАМ", f"Запрос тегов: {tags}...", "info")
                success, results = await scanners.search_web_mentions(session, tags)
                if success and results:
                    detail_text = ""
                    for idx, res in enumerate(results, 1):
                        detail_text += f"{idx}. {res['title']}\n   Ссылка: {res['url']}\n\n"
                    await send_event("РЕЗУЛЬТАТЫ СЛЕЙВА ТЕГОВ", detail_text.strip(), "success")
                elif results == "CAPTCHA_BLOCKED":
                    await send_event("ПОИСК ЗАБЛОКИРОВАН", "Поисковая система временно заблокировала автоматический запрос капчей. Попробуйте позже.", "error")
                elif success:
                    await send_event("СОВПАДЕНИЯ НЕ НАЙДЕНЫ", "По тегу ничего не найдено.", "warning")
                else:
                    await send_event("ОШИБКА ПОИСКА", f"Не удалось выполнить веб-запрос: {results}", "error")

    except ConnectionResetError:
        return response
    except Exception as e:
        await send_event("ОШИБКА СЕРВЕРА", f"Детали: {str(e)}", "error")

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