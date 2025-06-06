import os
import pymssql
import logging
from dotenv import load_dotenv
from utils import log_event

# Load environment variables
load_dotenv()

# Database Configuration
DB_CONFIG = {
    "server": os.getenv("DB_SERVER"),
    "user": os.getenv("DB_USER"),
    "password": os.getenv("DB_PASSWORD"),
    "database": os.getenv("DB_NAME"),
}


def create_table():
    """Ensure the Products table exists before inserting data."""
    try:
        with pymssql.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cursor:
                create_table_query = """
                IF NOT EXISTS (SELECT * FROM Webstudy.INFORMATION_SCHEMA.TABLES WHERE TABLE_NAME = 'IBM_Algo_Webstudy_Products' AND TABLE_SCHEMA = 'dbo')
                BEGIN
                    CREATE TABLE dbo.IBM_Algo_Webstudy_Products (
                        unique_id NVARCHAR(255) PRIMARY KEY,
                        CurrentDate DATETIME,
                        Header NVARCHAR(255),
                        ProductName NVARCHAR(255),
                        ImagePath NVARCHAR(MAX),
                        Kt NVARCHAR(255),  
                        Price NVARCHAR(255),
                        TotalDiaWt NVARCHAR(255),
                        Time DATETIME DEFAULT GETDATE()
                    )
                END
                """
                cursor.execute(create_table_query)
                conn.commit()
                logging.info("Table 'Products' checked/created successfully.")
    except pymssql.DatabaseError as e:
        logging.error(f"Database error: {e}")


def insert_into_db(data):
    """Insert scraped data into the MSSQL database."""
    if not data:
        log_event("No data to insert into the database.")
        return
    try:
        with pymssql.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cursor:
                query = """
                    INSERT INTO dbo.IBM_Algo_Webstudy_Products (unique_id, CurrentDate, Header, ProductName, ImagePath, Kt, Price, TotalDiaWt)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """
                cursor.executemany(query, data)
                conn.commit()
                logging.info(f"Inserted {len(data)} records successfully.")
    except pymssql.DatabaseError as e:
        logging.error(f"Database error: {e}")


# Function to fetch scraping settings
def get_scraping_settings():
    """Fetches current scraping settings from the database."""
    try:
        with pymssql.connect(**DB_CONFIG) as conn:
            with conn.cursor(as_dict=True) as cursor:
                cursor.execute("""
                    SELECT daily_limit, products_fetched_today, last_reset
                    FROM dbo.IBM_Algo_Webstudy_scraping_settings
                """)
                data = cursor.fetchone()
                if not data:
                    return {"success": False, "message": "No data found."}
                return {"success": True, "data": data}
    except pymssql.Error as e:
        return {"success": False, "error": f"Database error: {str(e)}"}


create_table()


def reset_scraping_limit():
    """Resets `products_fetched_today` to 0 and `is_disabled` to 0 using pymssql."""
    try:
        with pymssql.connect(**DB_CONFIG) as conn:
            with conn.cursor() as cursor:
                update_query = """
                    UPDATE dbo.IBM_Algo_Webstudy_scraping_settings
                    SET products_fetched_today = 0, is_disabled = 0
                """
                cursor.execute(update_query)
                conn.commit()

        return {"success": True, "message": "Limits have been reset successfully."}

    except pymssql.Error as e:
        return {"success": False, "error": f"Database error: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": f"Unexpected error: {str(e)}"}


def create_table_logs():
    try:
        conn = pymssql.connect(**DB_CONFIG)
        cursor = conn.cursor()
        cursor.execute("""
            IF NOT EXISTS (
                SELECT * FROM INFORMATION_SCHEMA.TABLES 
                WHERE TABLE_NAME = 'IBM_Algo_Webstudy_scraping_logs'
            )
            BEGIN
                CREATE TABLE IBM_Algo_Webstudy_scraping_logs (
                    id VARCHAR(255),
                    scrape_id VARCHAR(100),
                    name VARCHAR(255),
                    url VARCHAR(MAX),
                    max_pages INT,
                    region VARCHAR(10),
                    type VARCHAR(50),
                    ip_address VARCHAR(45),
                    request_time DATETIME,
                    status VARCHAR(20) CHECK (status IN ('active', 'inactive', 'error'))
                )
            END
        """)
        conn.commit()
        print("Table 'scraping_logs' created or already exists.")
    except Exception as e:
        print("Error creating table:", e)
    finally:
        conn.close()


create_table_logs()


# scaping all data call
def get_all_scraped_products():
    """Fetches all product data from the database."""
    try:
        with pymssql.connect(**DB_CONFIG) as conn:
            with conn.cursor(as_dict=True) as cursor:
                cursor.execute("""
                    SELECT TOP (1000) [unique_id], [CurrentDate], [Header], [ProductName],
                        [ImagePath], [Kt], [Price], [TotalDiaWt], [Time]
                    FROM dbo.IBM_Algo_Webstudy_Products
                    ORDER BY CurrentDate DESC
                """)
                products = cursor.fetchall()
                if not products:
                    return {"success": False, "message": "No products found."}
                return {"success": True, "data": products}
    except pymssql.Error as e:
        return {"success": False, "error": f"Database error: {str(e)}"}
    
    
def get_all_scraped_logs():
    """Fetches all scraping logs from the database."""
    try:
        with pymssql.connect(**DB_CONFIG) as conn:
            with conn.cursor(as_dict=True) as cursor:
                cursor.execute("""
                    SELECT *
                    FROM dbo.[IBM_Algo_Webstudy_scraping_logs]
                """)
                logs = cursor.fetchall()
                print(logs)

                if not logs:
                    return {"success": False, "message": "No logs found."}

                return {"success": True, "data": logs}
    except pymssql.Error as e:
        return {"success": False, "error": f"Database error: {str(e)}"}
