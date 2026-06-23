# Intel-Sentry

**INTEL-SENTRY** is a lightweight, high-performance, asynchronous OSINT and digital footprint aggregator. It allows security analysts and OSINT investigators to map digital footprints across usernames, emails, IP addresses, domains, and phone numbers through a unified, fast web dashboard.

Built as a portfolio project to showcase asynchronous network automation, OSINT methodologies, and clean cybersecurity dashboard design.

## Features

* **Asynchronous Username Recon:** Queries dozens of major web platforms (including Telegram, Steam, GitHub, Reddit) concurrently to identify active target profiles without blocking delays.
* **Real-Time Web Mention Scraper:** Integrates a dual-engine (HTML + Lite) search scraper that crawls open indexes to retrieve live matches for FIO (Full Name), addresses, vehicle license plates, or search tags.
* **Network & Domain Reconnaissance:** Extracts host infrastructure details including DNS records (DoH via Cloudflare) and correlates target nodes with IP geolocation telemetry.
* **Validation Engines:** Locally parses and mathematically validates Russian/CIS document checksums (INN, SNILS) and decodes standard 17-character vehicle VIN structures.
* **Interactive Cyberpunk Dashboard:** Dark-themed, high-contrast visual timeline UI utilizing Server-Sent Events (SSE) for seamless progressive result streaming.

## Installation & Usage

1. Clone the repository:
   ```bash
   git clone https://github.com/yourusername/intel-sentry.git
   cd intel-sentry
