import asyncio
import re
import os
import uuid
import logging
import base64
import random
import time
from datetime import datetime
from io import BytesIO
import httpx
from PIL import Image as PILImage
from openpyxl import Workbook
from openpyxl.drawing.image import Image as ExcelImage
from flask import Flask
from dotenv import load_dotenv
from playwright.async_api import async_playwright, TimeoutError, Error
from utils import get_public_ip, log_event, sanitize_filename
from database import insert_into_db
from limit_checker import update_product_count

# Load environment
load_dotenv()
PROXY_URL = os.getenv("PROXY_URL")

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
EXCEL_DATA_PATH = os.path.join(BASE_DIR, 'static', 'ExcelData')
IMAGE_SAVE_PATH = os.path.join(BASE_DIR, 'static', 'Images')
# Resize image if needed
def resize_image(image_data, max_size=(100, 100)):
    try:
        img = PILImage.open(BytesIO(image_data))
        img.thumbnail(max_size, PILImage.LANCZOS)
        buffer = BytesIO()
        img.save(buffer, format="JPEG", quality=85)
        return buffer.getvalue()
    except Exception as e:
        log_event(f"Error resizing image: {e}")
        return image_data

# Transform URL to get high-res image
def modify_image_url(image_url):
    if not image_url or image_url == "N/A":
        return image_url
    query_params = ""
    if "?" in image_url:
        image_url, query_params = image_url.split("?", 1)
        query_params = f"?{query_params}"
    modified_url = re.sub(r'(_260)(?=\.\w+$)', '_1200', image_url)
    return modified_url + query_params

# Async image downloader
async def download_image_async(image_url, product_name, timestamp, image_folder, unique_id, retries=3):
    if not image_url or image_url == "N/A":
        return "N/A"

    image_filename = f"{unique_id}_{timestamp}.jpg"
    image_full_path = os.path.join(image_folder, image_filename)
    modified_url = modify_image_url(image_url)

    async with httpx.AsyncClient(timeout=10.0) as client:
        for attempt in range(retries):
            try:
                response = await client.get(modified_url)
                response.raise_for_status()
                with open(image_full_path, "wb") as f:
                    f.write(response.content)
                return image_full_path
            except httpx.RequestError as e:
                logging.warning(f"Retry {attempt + 1}/{retries} - Error downloading {product_name}: {e}")
    logging.error(f"Failed to download {product_name} after {retries} attempts.")
    return "N/A"

# Human-like delay
def random_delay(min_sec=1, max_sec=3):
    time.sleep(random.uniform(min_sec, max_sec))

# Reliable page.goto wrapper
async def safe_goto_and_wait(page, url, retries=3):
    for attempt in range(retries):
        try:
            print(f"[Attempt {attempt + 1}] Navigating to: {url}")
            await page.goto(url, timeout=180_000, wait_until="domcontentloaded")
            await page.wait_for_selector(".main-product-container", state="attached", timeout=30000)
            print("[Success] Product cards loaded.")
            return
        except (Error, TimeoutError) as e:
            logging.warning(f"Attempt {attempt + 1} failed for {url}: {e}")
            if attempt < retries - 1:
                random_delay(1, 3)
            else:
                raise

# Main scraper function
async def handle_shane_co(url, max_pages):
    ip_address = get_public_ip()
    logging.info(f"Scraping started for: {url} from IP: {ip_address}, max_pages: {max_pages}")

    os.makedirs(EXCEL_DATA_PATH, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    image_folder = os.path.join(IMAGE_SAVE_PATH, timestamp)
    os.makedirs(image_folder, exist_ok=True)

    wb = Workbook()
    sheet = wb.active
    sheet.title = "Products"
    headers = ["Current Date", "Header", "Product Name", "Image", "Kt", "Price", "Total Dia wt", "Time", "ImagePath"]
    sheet.append(headers)

    all_records = []
    filename = f"handle_shane_co_{datetime.now().strftime('%Y-%m-%d_%H.%M')}.xlsx"
    file_path = os.path.join(EXCEL_DATA_PATH, filename)

    page_count = 1
    current_url = url
    prev_prod_count = 0
    while current_url and (page_count <= max_pages):
        logging.info(f"Processing page {page_count}: {current_url}")
        browser = None
        context = None
        try:
            async with async_playwright() as p:
                browser = await p.chromium.connect_over_cdp(PROXY_URL)
                context = await browser.new_context()
                page = await context.new_page()
                page.set_default_timeout(120000)

                await safe_goto_and_wait(page, current_url)
                log_event(f"Successfully loaded: {current_url}")

                # Scroll to load all items
                prev_count = 0
                for _ in range(10):
                    await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                    await asyncio.sleep(random.uniform(1, 2))
                    count = await page.locator('.main-product-container').count()
                    if count == prev_count:
                        break
                    prev_count = count

                page_title = await page.title()
                current_date = datetime.now().strftime("%Y-%m-%d")
                time_only = datetime.now().strftime("%H.%M")

                product_wrapper = await page.query_selector("div.main-product-container")
                products = await product_wrapper.query_selector_all("div.tile-container") if product_wrapper else []
                products = products[prev_prod_count:]
                logging.info(f"Total products scraped:{page_count} :{len(products)}")
                records = []
                image_tasks = []

                for row_num, product in enumerate(products, start=len(sheet["A"]) + 1):
                    try:
                        name_tag = await product.query_selector("h3.text-body-menu.product-details__name-value")
                        product_name = (await name_tag.inner_text()).strip() if name_tag else "N/A"
                    except Exception:
                        product_name = "N/A"

                    try:
                        price_tag = await product.query_selector("div.product-details__price-center-stone-container h4.text-body-strong")
                        price = (await price_tag.inner_text()).strip() if price_tag else "N/A"
                    except Exception:
                        price = "N/A"

                    try:
                        image_tag = await product.query_selector("img.product-image")
                        image_url = await image_tag.get_attribute("data-url") if image_tag else "N/A"
                    except Exception:
                        image_url = "N/A"

                    gold_type_pattern = r"\b\d{1,2}(?:K|ct)?\s*(?:White|Yellow|Rose)?\s*Gold\b|\bPlatinum\b|\bSilver\b"
                    gold_type_match = re.search(gold_type_pattern, product_name, re.IGNORECASE)
                    kt = gold_type_match.group() if gold_type_match else "Not found"

                    diamond_weight_pattern = r"\b\d+(\.\d+)?\s*(?:ct|tcw)\b"
                    diamond_weight_match = re.search(diamond_weight_pattern, product_name, re.IGNORECASE)
                    diamond_weight = diamond_weight_match.group() if diamond_weight_match else "N/A"

                    unique_id = str(uuid.uuid4())
                    image_tasks.append((row_num, unique_id, asyncio.create_task(
                        download_image_async(image_url, product_name, timestamp, image_folder, unique_id)
                    )))

                    records.append((unique_id, current_date, page_title, product_name, None, kt, price, diamond_weight))
                    sheet.append([current_date, page_title, product_name, None, kt, price, diamond_weight, time_only, image_url])

                for row_num, unique_id, task in image_tasks:
                    try:
                        image_path = await asyncio.wait_for(task, timeout=60)
                        if image_path != "N/A":
                            try:
                                img = ExcelImage(image_path)
                                img.width, img.height = 100, 100
                                sheet.add_image(img, f"D{row_num}")
                            except Exception as e:
                                logging.error(f"Error embedding image: {e}")
                                image_path = "N/A"
                        for i, record in enumerate(records):
                            if record[0] == unique_id:
                                records[i] = (record[0], record[1], record[2], record[3], image_path, record[5], record[6], record[7])
                                break
                    except asyncio.TimeoutError:
                        logging.warning(f"Image download timed out for row {row_num}")

                all_records.extend(records)

                # Check for next page
                
                next_button = page.locator("a.product-category-carousel__pagination")
                if await next_button.count() > 0:
                    next_link = await next_button.first.get_attribute("href")
                    if next_link:
                        current_url = next_link
                            

                prev_prod_count += len(products)
                wb.save(file_path)
                
        except Exception as e:
            logging.error(f"Error on page {page_count}: {str(e)}")
            wb.save(file_path)
        finally:
            if page: await page.close()
            if browser: await browser.close()
            await asyncio.sleep(random.uniform(2, 5))

        page_count += 1

    wb.save(file_path)
    log_event(f"Data saved to {file_path}")
    with open(file_path, "rb") as file:
        base64_encoded = base64.b64encode(file.read()).decode("utf-8")

    insert_into_db(all_records)
    update_product_count(len(all_records))

    return base64_encoded, filename, file_path
