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
        "Packaging": {  "Radial, Can" : "392320",
                        "Axial, Can" : "317217",
                        "Radial, Can - Snap-In" : "392328",
                        "Radial, Can - Solder Lug" : "392332" },
        "Polarization": {   "Polar": "388275",
                            "Non-Polar": "319798" },
        "Mounting": {   "Through Hole": "411897",
                        "Surface Mount": "409393" },
        "SMD Spacing": {'0.130" L x 0.130" W (3.30mm x 3.30mm)': '11211',
                        '0.157" Dia x 0.217" L (4.00mm x 5.50mm)': '811016',
                        '0.169" L x 0.169" W (4.30mm x 4.30mm)': '12680',
                        '0.169" L x 0.189" W (4.30mm x 4.80mm)': '12681',
                        '0.169" L x 0.217" W (4.30mm x 5.50mm)': '12682',
                        '0.197" Dia x 0.217" L (5.00mm x 5.50mm)': '811017',
                        '0.197" L x 0.177" W (5.00mm x 4.50mm)': '13876',
                        '0.209" L x 0.209" W (5.30mm x 5.30mm)': '14490',
                        '0.209" L x 0.228" W (5.30mm x 5.80mm)': '14491',
                        '0.209" L x 0.256" W (5.30mm x 6.50mm)': '14494',
                        '0.236" L x 0.217" W (6.00mm x 5.50mm)': '791447',
                        '0.248" Dia x 0.217" L (6.30mm x 5.50mm)': '811015',
                        '0.260" L x 0.260" W (6.60mm x 6.60mm)': '16613',
                        '0.260" L x 0.280" W (6.60mm x 7.10mm)': '16615',
                        '0.260" L x 0.307" W (6.60mm x 7.80mm)': '16617',
                        '0.287" L x 0.268" W (7.30mm x 6.80mm)': '17503',
                        '0.315" Dia x 0.413" L (8.00mm x 10.50mm)': '811014',
                        '0.315" L x 0.315" W (8.00mm x 8.00mm)': '18858',
                        '0.327" L x 0.327" W (8.30mm x 8.30mm)': '19167',
                        '0.327" L x 0.339" W (8.30mm x 8.60mm)': '19168',
                        '0.327" L x 0.374" W (8.30mm x 9.50mm)': '19170',
                        '0.327" L x 0.394" W (8.30mm x 10.00mm)': '19171',
                        '0.331" L x 0.331" W (8.40mm x 8.40mm)': '19343',
                        '0.335" L x 0.335" W (8.50mm x 8.50mm)': '19480',
                        '0.346" L x 0.335" W (8.80mm x 8.50mm)': '19771',
                        '0.354" L x 0.335" W (9.00mm x 8.50mm)': '20118',
                        '0.394" Dia x 0.413" L (10.00mm x 10.50mm)': '811013',
                        '0.394" L x 0.394" W (10.00mm x 10.00mm)': '21601',
                        '0.406" L x 0.406" W (10.30mm x 10.30mm)': '22287',
                        '0.406" L x 0.417" W (10.30mm x 10.60mm)': '22288',
                        '0.406" L x 0.473" W (10.30mm x 12.00mm)': '22289',
                        '0.409" L x 0.409" W (10.40mm x 10.40mm)': '22341',
                        '0.413" L x 0.413" W (10.50mm x 10.50mm)': '22552',
                        '0.425" L x 0.413" W (10.80mm x 10.50mm)': '22792',
                        '0.492" L x 0.492" W (12.50mm x 12.50mm)': '24863',
                        '0.504" L x 0.504" W (12.80mm x 12.80mm)': '25800',
                        '0.508" L x 0.508" W (12.90mm x 12.90mm)': '25858',
                        '0.512" L x 0.512" W (13.00mm x 13.00mm)': '26126',
                        '0.520" L x 0.520" W (13.20mm x 13.20mm)': '26300',
                        '0.531" L x 0.531" W (13.50mm x 13.50mm)': '26580',
                        '0.531" L x 0.590" W (13.50mm x 15.00mm)': '26582',
                        '0.535" L x 0.535" W (13.60mm x 13.60mm)': '26684',
                        '0.539" L x 0.512" W (13.70mm x 13.00mm)': '26740',
                        '0.563" L x 0.244" W (14.30mm x 6.20mm)': '27510',
                        '0.563" L x 0.299" W (14.30mm x 7.60mm)': '27511',
                        '0.630" L x 0.630" W (16.00mm x 16.00mm)': '29674',
                        '0.642" L x 0.642" W (16.30mm x 16.30mm)': '29877',
                        '0.654" L x 0.654" W (16.60mm x 16.60mm)': '30155',
                        '0.669" L x 0.669" W (17.00mm x 17.00mm)': '30486',
                        '0.669" L x 0.748" W (17.00mm x 19.00mm)': '30488',
                        '0.673" L x 0.673" W (17.10mm x 17.10mm)': '30674',
                        '0.677" L x 0.677" W (17.20mm x 17.20mm)': '827062',
                        '0.709" L x 0.709" W (18.00mm x 18.00mm)': '31856',
                        '0.748" L x 0.748" W (19.00mm x 19.00mm)': '32621',
                        '0.748" L x 0.827" W (19.00mm x 21.00mm)': '32624',
                        '0.752" L x 0.752" W (19.10mm x 19.10mm)': '32986',
                        '0.756" L x 0.756" W (19.20mm x 19.20mm)': '33026',
                        '1.024" L x 1.024" W (26.00mm x 26.00mm)': '41504',
                        '1.102" L x 1.102" W (28.00mm x 28.00mm)': '43463',
                        '1.994" L x 0.610" W (50.65mm x 15.50mm)': '574689'},
        "Lead Spacing": {   "0.138\" (3.50mm)": "11374", 
                            "0.197\" (5.00mm)": "11375" },
        "Height": { "0.591\" (13.00mm)": "26001",
                    "0.315\" (8.00mm)": "26000" },
        "Diameter": {   "0.315\" Dia (8.00mm)": "18775",
                        "0.394\" Dia (10.00mm)": "18776" },
        "Lifetime": {   "7000 Hrs @ 105°C": "272852",
                        "1000 Hrs @ 105°C": "272853" },
        "Manufacturer": {   "Chemi-Con": "565",
                            "Nichicon": "493",
                            "Panasonic": "10",
                            "Rubycon": "13",
                            "Würth Elektronik": "732",
                            "Vishay Sprague": "718" }
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
