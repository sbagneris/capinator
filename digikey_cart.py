#!/usr/bin/env python3

import csv
import json
from requests_oauthlib import OAuth2Session
from oauthlib.oauth2 import BackendApplicationClient
from pprint import pprint

# Mouser API configuration
MOUSER_API_KEY = "e74ce92e-fc89-49af-8111-37f23c522a42"
MOUSER_API_BASE = "https://api.mouser.com/api/v1"

# Digi-Key API configuration
API_BASE = "https://api.digikey.com"
CLIENT_ID = "exmEWdjlz2bgUAtBNz0zDMC89LZ0gFdg"
CLIENT_SECRET = "YuxtSiWGQp0KHAMj"

# API endpoints
SEARCH_API = "/products/v4/search/keyword"
CART_API = "/Ordering/v3/Cart/Items"
CATEGORIES = "/products/v4/search/categories"

def authenticate():
    """Authenticate with Digi-Key API using OAuth2"""
    oauth = OAuth2Session(client=BackendApplicationClient(client_id=CLIENT_ID))
    oauth.fetch_token(token_url=f"{API_BASE}/v1/oauth2/token", client_secret=CLIENT_SECRET)
    return oauth

def search_capacitor(session, params):
    """Search for capacitors using Digi-Key API"""
    
    FILTER_IDS = {
        "Packaging": {  "Radial, Can" : "392320", "Axial" : "392322" },
        "Polarization": { "Polar": "388275", "Non-Polar": "388276" },
        "Mounting": { "Through Hole": "411897", "Surface Mount": "411898" },
        "Lead Spacing": { "0.138\" (3.50mm)": "11374", "0.197\" (5.00mm)": "11375" },
        "Height": { "0.591\" (13.00mm)": "26001", "0.315\" (8.00mm)": "26000" },
        "Diameter": { "0.315\" Dia (8.00mm)": "18775", "0.394\" Dia (10.00mm)": "18776" },
        "Lifetime": { "7000 Hrs @ 105°C": "272852", "1000 Hrs @ 105°C": "272853" },
        "Manufacturer": { "Nichicon": "493", "Panasonic": "10", "Vishay BC Components": "111" }
    }

    data = {
        # "Keywords": str(params['capacitance']) + " " + str(params['voltage']),
        "Limit": 10,
        "FilterOptionsRequest": {
            "ManufacturerFilter": [ { "Id": "493" } ], # Nichicon
            "CategoryFilter": [ { "Id": "58" } ], # Aluminum Electrolytic Capacitors
            "MarketPlaceFilter": "ExcludeMarketPlace",
            "MinimumQuantityAvailable": 1,
            "ParameterFilterRequest": {
                "CategoryFilter": { "Id": "58" },
                "ParameterFilters": [ {
                    "ParameterId": 16, # Package / Case
                    "FilterValues": [ { "Id": "392320" } ] },{ # Radial, Can
                    "ParameterId": 2049, # Capacitance
                    "FilterValues": [ { "Id": "100 uF" } ] }, {
                    "ParameterId": 2079, # Voltage - Rated
                    "FilterValues": [ { "Id": "50 V" } ] }, {
                    # "ParameterId": 725, # Lifetime @ Temp
                    # "FilterValues": [ { "Id": "272852" } ] }, { # 7000 Hrs @ 105°C
                    "ParameterId": 52, # Polarization
                    "FilterValues": [ { "Id": "388275" } ] }, { # Polar
                    "ParameterId": 69, # Mounting Type
                    "FilterValues": [ { "Id": "411897" } ] }, # { # Through Hole
                    # "ParameterId": 508, # Lead Spacing
                    # "FilterValues": [ { "Id": "11374" } ] }, { # 0.138" (3.50mm)
                    # "ParameterId": 1500, # Height - Seated (Max) 
                    # "FilterValues": [ { "Id": "26001" } ] }, { # 0.591" (13.00mm)
                    # "ParameterId": 46, # Size / Dimension  
                    # "FilterValues": [ { "Id": "18775" } ] } # 0.315" Dia (8.00mm)
                ]
            },
            "SearchOptions": [ "InStock" ]
        },
        "SortOptions": {
            "Field": "Price",
            "SortOrder": "Ascending"
        }
    }
    
    response = session.post(url=f"{API_BASE}{SEARCH_API}", 
                            headers={"X-DIGIKEY-Client-Id": CLIENT_ID, 
                                     "Authorization": session.token['access_token'] },
                            json=data)
    response.raise_for_status()
    results = response.json()
    
    # pprint(results)
    print(json.dumps(results, indent=3))
    
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
