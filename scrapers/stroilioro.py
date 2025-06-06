import asyncio
import re
import os
import uuid
import logging
import base64
from datetime import datetime
from openpyxl import Workbook
from openpyxl.drawing.image import Image
from flask import Flask
from dotenv import load_dotenv
from utils import get_public_ip, log_event, sanitize_filename
from database import insert_into_db
from limit_checker import update_product_count
import httpx
from playwright.async_api import async_playwright, TimeoutError

# Load .env variables
load_dotenv()
PROXY_URL = os.getenv("PROXY_URL")

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
EXCEL_DATA_PATH = os.path.join(BASE_DIR, 'static', 'ExcelData')
IMAGE_SAVE_PATH = os.path.join(BASE_DIR, 'static', 'Images')



def modify_image_url(image_url, high_res=True):
    """Modify image URLs to use high-resolution if available."""
    if not image_url or image_url == "N/A":
        return image_url

    # Extract and preserve query parameters
    query_params = ""
    if "?" in image_url:
        image_url, query_params = image_url.split("?", 1)
        query_params = f"?{query_params}"

    if high_res:
        # Force high resolution by changing sw and sh to 1024
        query_params = re.sub(r"(\?|&)sw=\d+", r"\1sw=1024", query_params)
        query_params = re.sub(r"(\?|&)sh=\d+", r"\1sh=1024", query_params)

    return image_url + query_params


async def download_image(session: httpx.AsyncClient, image_url: str, product_name: str, timestamp: str, image_folder: str, unique_id: str):
    """Download an image using httpx, attempting high-res first."""
    if not image_url or image_url == "N/A":
        return "N/A"

    image_filename = f"{unique_id}_{timestamp}.jpg"
    image_full_path = os.path.join(image_folder, image_filename)

    # Try high resolution first, then fallback to original
    high_res_url = modify_image_url(image_url, high_res=True)
    original_url = modify_image_url(image_url, high_res=False)

    for attempt in range(3):
        for url_to_try in [high_res_url, original_url]:
            try:
                response = await session.get(url_to_try, timeout=10)
                response.raise_for_status()
                with open(image_full_path, "wb") as f:
                    f.write(response.content)
                return image_full_path
            except Exception as e:
                logging.warning(f"Attempt {attempt + 1}/3 - Error downloading from {url_to_try} for {product_name}: {e}")
                if url_to_try == original_url:
                    break

    logging.error(f"Failed to download image for {product_name} after 3 attempts.")
    return "N/A"

async def handle_stroilioro(url, max_pages):
    ip_address = get_public_ip()
    logging.info(f"Starting scrape for {url} from IP: {ip_address}")

    if not os.path.exists(EXCEL_DATA_PATH):
        os.makedirs(EXCEL_DATA_PATH)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    image_folder = os.path.join(IMAGE_SAVE_PATH, timestamp)
    os.makedirs(image_folder, exist_ok=True)

    wb = Workbook()
    sheet = wb.active
    sheet.title = "Products"
    headers = ["Current Date", "Header", "Product Name", "Image", "Kt", "Price", "Total Dia wt", "Time", "ImagePath"]
    sheet.append(headers)

    current_date = datetime.now().strftime("%Y-%m-%d")
    time_only = datetime.now().strftime("%H.%M")

    seen_ids = set()
    records = []
    image_tasks = []

    async with httpx.AsyncClient() as session:
        current_page = 1
        previous_count = 0
        current_url = url
        while current_page <= max_pages:
            async with async_playwright() as p:
                # Create a new browser instance for each page
                if current_page > 1:
                    current_url =  f"{url}?start={(current_page-1)*41}&sz=41"
                browser = await p.chromium.connect_over_cdp(PROXY_URL)
                page = await browser.new_page()

                try:
                    await page.goto(current_url, timeout=120000)
                except Exception as e:
                    logging.warning(f"Failed to load URL {url}: {e}")
                    await browser.close()
                    continue  # move to the next iteration


                # Handle Didomi cookie consent popup
                try:
                    await page.wait_for_selector("#didomi-popup", timeout=5000)
                    accept_btn = await page.query_selector("button[aria-label='Accepter']")
                    if accept_btn:
                        await accept_btn.click()
                        print("✅ Cookie consent accepted.")
                        await asyncio.sleep(1)
                except:
                    print("ℹ️ No Didomi popup found or already dismissed.")
                    
                all_products = await page.query_selector_all("div.c-grid__item")

                total_products = len(all_products)
                new_products = all_products
                logging.info(f"Page {current_page}: Total = {total_products}, New = {len(new_products)}")

                print(f"Page {current_page}: Scraping {len(new_products)} new products.")
                page_title = await page.title()

                for idx, product in enumerate(new_products):
                    try:
                        name_tag = await product.query_selector("a.c-product-tile__name-link")
                        if name_tag:
                            product_name = await name_tag.inner_text()
                            product_name = product_name.replace('\n', ' ').strip()
                        else:
                            product_name = "N/A"
                    except Exception as e:
                        print(f"[Product Name] Error: {e}")
                        product_name = "N/A"


                    try:
                        price_tag = await product.query_selector("span.c-price__standard")
                        price = await price_tag.inner_text() if price_tag else "N/A"
                    except Exception as e:
                        print(f"[Price] Error: {e}")
                        price = "N/A"


                    try:
                        # await product.scroll_into_view_if_needed()
                        
                        # Locate the first <img> tag inside a <picture> element
                        img_tag = await product.query_selector("div.c-product-tile__image-link picture img")
                        
                        # First, try to get the high-resolution image from `data-src` (for lazy loading)
                        image_url = await img_tag.get_attribute("data-src") if img_tag else None
                        
                        # If `data-src` is not available, fallback to `src` attribute
                        if not image_url:
                            image_url = await img_tag.get_attribute("src") if img_tag else None

                        # Ensure the URL is fully qualified (adds 'https:' if it is a relative URL)
                        if image_url and image_url.startswith("//"):
                            image_url = "https:" + image_url

                        # In case no valid URL was found
                        if not image_url:
                            image_url = "N/A"

                    except Exception as e:
                        print(f"[Image URL] Error: {e}")
                        image_url = "N/A"

                                            
                    
                    # Extract Gold Type (e.g., "14K Yellow Gold").
                    gold_type_match = re.findall(r"(\d{1,2}ct\s*(?:Yellow|White|Rose)?\s*Gold|Platinum|Cubic Zirconia)", product_name, re.IGNORECASE)
                    kt = ", ".join(gold_type_match) if gold_type_match else "N/A"

                    # Extract Diamond Weight (supports "1.85ct", "2ct", "1.50ct", etc.)
                    diamond_weight_match = re.findall(r"(\d+(?:\.\d+)?\s*ct)", product_name, re.IGNORECASE)
                    diamond_weight = ", ".join(diamond_weight_match) if diamond_weight_match else "N/A"

                    unique_id = str(uuid.uuid4())
                    task = asyncio.create_task(download_image(session, image_url, product_name, timestamp, image_folder, unique_id))
                    image_tasks.append((len(sheet['A']) + 1, unique_id, task))
                    if image_url != "N/A":
                        records.append((unique_id, current_date, page_title, product_name, None, kt, price, diamond_weight))
                        sheet.append([current_date, page_title, product_name, None, kt, price, diamond_weight, time_only, image_url])

                # Process image downloads and attach them to Excel
                for row, unique_id, task in image_tasks:
                    image_path = await task
                    if image_path != "N/A":
                        img = Image(image_path)
                        img.width, img.height = 100, 100
                        sheet.add_image(img, f"D{row}")
                    for i, record in enumerate(records):
                        if record[0] == unique_id:
                            records[i] = (record[0], record[1], record[2], record[3], image_path, record[5], record[6], record[7])
                            break

                await browser.close()
            current_page += 1

        # Save Excel
        filename = f'handle_stroilioro_{datetime.now().strftime("%Y-%m-%d_%H.%M")}.xlsx'
        file_path = os.path.join(EXCEL_DATA_PATH, filename)
        wb.save(file_path)
        log_event(f"Data saved to {file_path} | IP: {ip_address}")

        if records:
            insert_into_db(records)
        else:
            logging.info("No data to insert into the database.")

        update_product_count(len(seen_ids))

        with open(file_path, "rb") as f:
            base64_encoded = base64.b64encode(f.read()).decode("utf-8")

        return base64_encoded, filename, file_path
