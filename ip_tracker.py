import pymssql
from datetime import datetime
import hashlib
import os
from dotenv import load_dotenv
from utils import get_public_ip
# Load environment variables
load_dotenv()
# Database Configuration

DB_CONFIG = {
    "server": os.getenv("DB_SERVER"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
}


def insert_scrape_log(id, scrape_id, name, url, max_pages, region, type_User, status='active'):
    ip_address = get_public_ip()
    timestamp = datetime.now()

    try:
        conn = pymssql.connect(**DB_CONFIG)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO scraping_logs (
                id, scrape_id, name, url, max_pages, region, type, ip_address, request_time, status
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (id, scrape_id, name, url, max_pages, region, type_User, ip_address, timestamp, status))

        conn.commit()
    except Exception as e:
        print("DB Insert Error:", e)
    finally:
        conn.close()


def update_scrape_status(scrape_id, status):
    conn = pymssql.connect(**DB_CONFIG)
    cursor = conn.cursor()
    cursor.execute(
        "UPDATE scraping_logs SET status = %s WHERE scrape_id = %s", (status, scrape_id))
    conn.commit()
    conn.close()
