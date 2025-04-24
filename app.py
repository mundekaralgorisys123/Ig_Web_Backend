import os
import logging
import asyncio
import json
from flask import Flask, render_template, request, jsonify
from flask_cors import CORS
from urllib.parse import urlparse

# Scraper imports
from scrapers.ernest_jones import handle_ernest_jones
from scrapers.shaneco import handle_shane_co
from scrapers.fhinds import handle_fhinds
from scrapers.gabriel import handle_gabriel
from scrapers.hsamuel import handle_h_samuel
from scrapers.kay import handle_kay
from scrapers.jared import handle_jared
from scrapers.tiffany import handle_tiffany
from scrapers.kayoutlet import handle_kayoutlet
from scrapers.zales import handle_zales
from scrapers.anguscoote import handle_anguscoote
from scrapers.bash import handle_bash
from scrapers.hardybrothers import handle_hardybrothers
from scrapers.bevilles import handle_bevilles
from scrapers.apart import handle_apart
from scrapers.peoplesjewellers import handle_peoplesjewellers
from scrapers.tiffany import handle_tiffany


from scrapers.armansfinejewellery import handle_armansfinejewellery
from scrapers.jacquefinejewellery import handle_jacquefinejewellery
from scrapers.medleyjewellery import handle_medleyjewellery
from scrapers.cullenjewellery import handle_cullenjewellery
from scrapers.grahams import handle_grahams
from scrapers.larsenjewellery import handle_larsenjewellery
from scrapers.ddsdiamonds import handle_ddsdiamonds
from scrapers.garenjewellery import handle_garenjewellery
from scrapers.stefandiamonds import handle_stefandiamonds
from scrapers.goodstoneinc import handle_goodstoneinc
from scrapers.natashaschweitzer import handle_natasha
from scrapers.sarahandsebastian import handle_sarahandsebastian
from scrapers.moissanite import handle_moissanite
from scrapers.daimondcollection import handle_diamondcollection
from scrapers.cushlawhiting import handle_cushlawhiting
from scrapers.cerrone import handle_cerrone
from scrapers.briju import handle_briju
from scrapers.histoiredor import handle_histoiredor
from scrapers.marcorian import handle_marcorian
from scrapers.klenotyaurum import handle_klenotyaurum
from scrapers.stroilioro import handle_stroilioro
from scrapers.americanswiss import handle_americanswiss
from scrapers.mariemass import handle_mariemass
from scrapers.mattioli import handle_mattioli
from scrapers.pomellato import handle_pomellato
from scrapers.dior import handle_dior




# Utility modules
from utils import get_public_ip, log_event
from limit_checker import check_daily_limit
from database import reset_scraping_limit, get_scraping_settings, get_all_scraped_products,get_all_scraped_logs
from ip_tracker import insert_scrape_log, update_scrape_status


app = Flask(__name__)
CORS(app)

# Ensure logs folder exists
os.makedirs("logs", exist_ok=True)

# Request count tracking
request_count_file = "logs/proxy_request_count.txt"
request_count = 0
if os.path.exists(request_count_file):
    try:
        with open(request_count_file, "r") as f:
            request_count = int(f.read().strip())
    except ValueError:
        request_count = 0


def log_and_increment_request_count():
    """Increment and log the number of requests made via proxy."""
    global request_count
    request_count += 1
    with open(request_count_file, "w") as f:
        f.write(str(request_count))
    logging.info(f"Total requests via proxy: {request_count}")


def load_websites():
    with open("websites.json", "r") as file:
        return json.load(file)["websites"]


@app.route("/")
def main():
    websites = load_websites()
    return render_template("index.html", websites=websites)


@app.route("/fetch", methods=["POST"])
def fetch_data():
    if not check_daily_limit():
        return jsonify({"400": "Daily limit reached. Scraping is disabled."}), 400
    
    id = request.json.get("id")
    url = request.json.get("url")
    scrape_id = request.json.get("scrape_id")
    name = request.json.get("name")
    region = request.json.get("region")
    type_User = request.json.get("type")
    max_pages = int(request.json.get("maxPages", 1))

    # print(id)
    # print(scrape_id)
    # print(url)
    # print(name)
    # print(region)
    # print(type_User)
    # print(max_pages)

    domain = urlparse(url).netloc.lower()

    insert_scrape_log(id, scrape_id, name, url, max_pages,
                      region, type_User, 'active')

    logging.info(f"Processing request for domain: {domain}")
    log_and_increment_request_count()

    handler_map = {
        "www.jared.com": handle_jared,
        "www.kay.com": handle_kay,
        "www.fhinds.co.uk": handle_fhinds,
        "www.ernestjones.co.uk": handle_ernest_jones,
        "www.gabrielny.com": handle_gabriel,
        "www.hsamuel.co.uk": handle_h_samuel,
        "www.tiffany.co.in": handle_tiffany,
        "www.shaneco.com": handle_shane_co,
        "www.kayoutlet.com": handle_kayoutlet,
        "www.zales.com": handle_zales,
        "www.peoplesjewellers.com": handle_peoplesjewellers,
        "www.anguscoote.com.au": handle_anguscoote,
        "bash.com": handle_bash,
        "www.hardybrothers.com.au": handle_hardybrothers,
        "www.bevilles.com.au": handle_bevilles,
        "armansfinejewellery.com": handle_armansfinejewellery,
        "jacquefinejewellery.com.au": handle_jacquefinejewellery,
        "medleyjewellery.com.au": handle_medleyjewellery,
        "cullenjewellery.com": handle_cullenjewellery,
        "www.grahams.com.au": handle_grahams,
        "www.larsenjewellery.com.au": handle_larsenjewellery,
        "ddsdiamonds.com.au": handle_ddsdiamonds,
        "www.garenjewellery.com.au": handle_garenjewellery,
        "stefandiamonds.com": handle_stefandiamonds,
        "www.goodstoneinc.com": handle_goodstoneinc,
        "natashaschweitzer.com": handle_natasha,
        "www.sarahandsebastian.com": handle_sarahandsebastian,
        "tmcfinejewellers.com": handle_moissanite,
        "diamondcollective.com": handle_diamondcollection,
        "cushlawhiting.com": handle_cushlawhiting,
        "cerrone.com.au": handle_cerrone,
        "www.briju.pl": handle_briju,
        "www.histoiredor.com": handle_histoiredor,
        "www.marc-orian.com": handle_marcorian,
        "www.klenotyaurum.cz": handle_klenotyaurum,
        "www.stroilioro.com": handle_stroilioro,
        "bash.com": handle_americanswiss,
        "mariemas.com": handle_mariemass,
        "mattioli.it": handle_mattioli,
        "www.pomellato.com": handle_pomellato,
        "www.dior.com": handle_dior,
        
    }

    handler = handler_map.get(domain)
    if not handler:
        log_event(f"Unknown website attempted: {domain}")
        return jsonify({"error": "Unknown website"}), 200

    try:
        base64_encoded, filename, file_path = asyncio.run(
            handler(url, max_pages))
    except Exception as e:
        update_scrape_status(scrape_id, 'error')
        log_event(f"Scraping failed for {domain}: {str(e)}")
        return jsonify({"status": False, "filename": None}), 500

    log_event(f"Successfully scraped {domain}. File generated: {filename}")
    update_scrape_status(scrape_id, 'inactive')
    return jsonify({"status": True, "filename": filename})


@app.route("/reset-limit", methods=["GET"])
def reset_limit_route():
    result = reset_scraping_limit()
    return (jsonify(result), 200) if not result.get("error") else (jsonify(result), 500)


@app.route("/get_data")
def get_data():
    return jsonify(get_scraping_settings())


@app.route("/get_products")
def get_products():
    return jsonify(get_all_scraped_products())

@app.route("/retailers", methods=["GET"])
def get_retailers():
    return jsonify(get_all_scraped_logs())


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)
    app.run(debug=True, port=5000)
