import csv

# import os
# from pathlib import Path

# import digikey
# from digikey.v3.productinformation import KeywordSearchRequest
# from digikey.v3.batchproductdetails import BatchProductDetailsRequest

# CACHE_DIR = Path('.cache/')

# os.environ['DIGIKEY_CLIENT_ID'] = 'exmEWdjlz2bgUAtBNz0zDMC89LZ0gFdg'
# os.environ['DIGIKEY_CLIENT_SECRET'] = 'YuxtSiWGQp0KHAMj'
# os.environ['DIGIKEY_CLIENT_SANDBOX'] = 'False'
# os.environ['DIGIKEY_STORAGE_PATH'] = CACHE_DIR

# # Query product number
# dkpn = '296-6501-1-ND'
# part = digikey.product_details(dkpn)

# # Search for parts
# search_request = KeywordSearchRequest(keywords='CRCW080510K0FKEA', record_count=10)
# result = digikey.keyword_search(body=search_request)

# # Only if BatchProductDetails endpoint is explicitly enabled
# # Search for Batch of Parts/Product
# mpn_list = ["0ZCK0050FF2E", "LR1F1K0"] #Length upto 50
# batch_request = BatchProductDetailsRequest(products=mpn_list)
# part_results = digikey.batch_product_details(body=batch_request)

import csv
import requests
from requests_oauthlib import OAuth2Session
from oauthlib.oauth2 import BackendApplicationClient

# Digi-Key API configuration
API_BASE = "https://api.digikey.com"
CLIENT_ID = "exmEWdjlz2bgUAtBNz0zDMC89LZ0gFdg"
CLIENT_SECRET = "YuxtSiWGQp0KHAMj"
REDIRECT_URI = "https://localhost:8080/digikey-callback"  # Update in Dev Portal

# API endpoints
SEARCH_API = "/products/v4/search/keyword"
CART_API = "/Ordering/v3/Cart/Items"
CATEGORIES = "/products/v4/search/categories"

def authenticate():
    """Authenticate with Digi-Key API using OAuth2"""
    oauth = OAuth2Session(client=BackendApplicationClient(client_id=CLIENT_ID), redirect_uri=REDIRECT_URI)
    oauth.fetch_token(token_url=f"{API_BASE}/v1/oauth2/token", client_secret=CLIENT_SECRET)
    return oauth

def search_capacitor(session, params):
    """Search for capacitors using Digi-Key API"""
    # filters = {
    #     "ManufacturerPartNumber": params.get('manufacturer_part', ''),
    #     "Capacitance": params['capacitance'],
    #     "VoltageRating": params['voltage'],
    #     "Tolerance": params.get('tolerance', '±20%'),
    #     "CategoryIds": [56],  # Aluminum Electrolytic Capacitors category
    #     "RecordCount": 1
    # }

    data = {
        "Keywords": str(params['capacitance']) + " " + str(params['voltage']),
        "Limit": 1,
        # "Offset": 0,
        "FilterOptionsRequest": {
            # "ManufacturerFilter": [ { "Id": "string" } ],
            "CategoryFilter": [ { "Id": "58" } ],
            'Manufacturer': [ {'Name': 'Nichicon'} ],
            # "StatusFilter": [ { "Id": "string" } ],
            # "PackagingFilter": [ { "Id": "string" } ],
            # "MarketPlaceFilter": "NoFilter",
            # "SeriesFilter": [ { "Id": "string" } ],
            "MinimumQuantityAvailable": 1,
            # "ParameterFilterRequest": {
                # "CategoryFilter": { "Id": "56" },
                # "ParameterFilters": [ {
                        # "ParameterId": 0,
                        # "FilterValues": [ { "Id": "string" } ]
                # } ]
            # },
            # "SearchOptions": [ "ChipOutpost" ]
        },
        # "SortOptions": {
        #     "Field": "None",
        #     "SortOrder": "Ascending"
        # }
    }

    print(data)
    
    response = session.post(url=f"{API_BASE}{SEARCH_API}", 
                            headers={"X-DIGIKEY-Client-Id": CLIENT_ID, "Authorization": session.token['access_token'] },
                            json=data)
    response.raise_for_status()
    results = response.json()
    print(results)
    
    if results.get('Products'):
        return results['Products'][0]['DigiKeyPartNumber']
    return None

def add_to_cart(session, part_number, quantity=1):
    """Add item to Digi-Key cart"""
    cart_item = {
        "Items": [{
            "Quantity": quantity,
            "PartNumber": part_number
        }]
    }
    
    response = session.post(f"{API_BASE}{CART_API}", json=cart_item)
    response.raise_for_status()
    return response.json()

def process_csv(file_path):
    """Process CSV file and build cart"""
    session = authenticate()
    
    with open(file_path, newline='') as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            try:
                print(f"Processing: {row['capacitance']} {row['voltage']}")
                
                # Map CSV columns to API parameters
                params = {
                    'capacitance': row['capacitance'],
                    'voltage': row['voltage'],
                    'tolerance': row.get('tolerance', '±20%'),
                    'manufacturer_part': row.get('manufacturer_part', '')
                }
                
                part_number = search_capacitor(session, params)
                if part_number:
                    add_to_cart(session, part_number)
                    print(f"Added {part_number} to cart")
                else:
                    print(f"No match found for {params}")
                    
            except Exception as e:
                print(f"Error processing row: {e}")

if __name__ == "__main__":
    import sys
    if len(sys.argv) != 2:
        print("Usage: python digikey_cart.py <input.csv>")
        sys.exit(1)
    
    process_csv(sys.argv[1])
