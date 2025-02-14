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
        "Lead Spacing": {'0.039" (1.00mm)': '6219',
                         '0.059" (1.50mm)': '7385',
                         '0.079" (2.00mm)': '8489',
                         '0.098" (2.50mm)': '9420',
                         '0.100" (2.54mm)': '9726',
                         '0.138" (3.50mm)': '11374',
                         '0.197" (5.00mm)': '13741',
                         '0.200" (5.08mm)': '14243',
                         '0.201" (5.10mm)': '14296',
                         '0.205" (5.20mm)': '14372',
                         '0.236" (6.00mm)': '15346',
                         '0.246" (6.25mm)': '15765',
                         '0.250" (6.35mm)': '16030',
                         '0.276" (7.00mm)': '17026',
                         '0.295" (7.50mm)': '17717',
                         '0.299" (7.60mm)': '17833',
                         '0.300" (7.62mm)': '18160',
                         '0.315" (8.00mm)': '18741',
                         '0.325" (8.25mm)': '19109',
                         '0.331" (8.40mm)': '19325',
                         '0.335" (8.50mm)': '19387',
                         '0.364" (9.25mm)': '20427',
                         '0.394" (10.00mm)': '21438',
                         '0.400" (10.16mm)': '22035',
                         '0.402" (10.20mm)': '22115',
                         '0.423" (10.75mm)': '22750',
                         '0.492" (12.50mm)': '24777',
                         '0.500" (12.70mm)': '25530',
                         '0.504" (12.80mm)': '25771',
                         '0.512" (13.00mm)': '26001',
                         '0.551" (14.00mm)': '27105',
                         '0.559" (14.20mm)': '27282',
                         '0.591" (15.00mm)': '28168',
                         '0.600" (15.24mm)': '28868',
                         '0.650" (16.50mm)': '30008',
                         '0.689" (17.50mm)': '30889',
                         '0.709" (18.00mm)': '31769',
                         '0.728" (18.50mm)': '32182',
                         '0.748" (19.00mm)': '32527',
                         '0.750" (19.05mm)': '32833',
                         '0.752" (19.10mm)': '32958',
                         '0.768" (19.50mm)': '33286',
                         '0.787" (20.00mm)': '33647',
                         '0.846" (21.50mm)': '35333',
                         '0.858" (21.80mm)': '35541',
                         '0.866" (22.00mm)': '35710',
                         '0.874" (22.20mm)': '35949',
                         '0.875" (22.22mm)': '35971',
                         '0.875" (22.23mm)': '35973',
                         '0.886" (22.50mm)': '36215',
                         '0.984" (25.00mm)': '38279',
                         '1.000" (25.40mm)': '40796',
                         '1.102" (28.00mm)': '43398',
                         '1.110" (28.20mm)': '43608',
                         '1.122" (28.50mm)': '43831',
                         '1.125" (28.58mm)': '43890',
                         '1.126" (28.60mm)': '43969',
                         '1.236" (31.40mm)': '46742',
                         '1.240" (31.50mm)': '46859',
                         '1.248" (31.70mm)': '46975',
                         '1.250" (31.75mm)': '47151',
                         '1.252" (31.80mm)': '47224',
                         '1.260" (32.00mm)': '47679',
                         '1.299" (33.00mm)': '48299',
                         '1.500" (38.10mm)': '53536',
                         '1.634" (41.50mm)': '56413'},
        "Height": { "0.591\" (13.00mm)": "26001",
                    "0.315\" (8.00mm)": "26000" },
        "Diameter": {   "0.315\" Dia (8.00mm)": "18775",
                        "0.394\" Dia (10.00mm)": "18776" },
        "Lifetime": {'500 Hrs @ 85°C': '236304',
                     '1000 Hrs @ 105°C': '68143',
                     '1000 Hrs @ 125°C': '68144',
                     '1000 Hrs @ 130°C': '68145',
                     '1000 Hrs @ 135°C': '68146',
                     '1000 Hrs @ 140°C': '68147',
                     '1000 Hrs @ 150°C': '68148',
                     '1000 Hrs @ 85°C': '68154',
                     '1250 Hrs @ 150°C': '85479',
                     '1500 Hrs @ 105°C': '99819',
                     '1500 Hrs @ 125°C': '99820',
                     '1500 Hrs @ 150°C': '99821',
                     '1500 Hrs @ 85°C': '99824',
                     '1600 Hrs @ 150°C': '476756',
                     '2000 Hrs @ 105°C': '140003',
                     '2000 Hrs @ 125°C': '140005',
                     '2000 Hrs @ 130°C': '140006',
                     '2000 Hrs @ 135°C': '140007',
                     '2000 Hrs @ 150°C': '140009',
                     '2000 Hrs @ 175°C': '140010',
                     '2000 Hrs @ 85°C': '140015',
                     '2000 Hrs @ 95°C': '140016',
                     '2500 Hrs @ 105°C': '156737',
                     '2500 Hrs @ 125°C': '156738',
                     '2500 Hrs @ 85°C': '156739',
                     '3000 Hrs @ 105°C': '181962',
                     '3000 Hrs @ 125°C': '181963',
                     '3000 Hrs @ 130°C': '458368',
                     '3000 Hrs @ 135°C': '181964',
                     '3000 Hrs @ 150°C': '181965',
                     '3000 Hrs @ 85°C': '181967',
                     '3500 Hrs @ 125°C': '192825',
                     '3500 Hrs @ 85°C': '192826',
                     '4000 Hrs @ 105°C': '213041',
                     '4000 Hrs @ 125°C': '213042',
                     '4000 Hrs @ 130°C': '213043',
                     '4000 Hrs @ 85°C': '213045',
                     '4600 Hrs @ 105°C': '222707',
                     '5000 Hrs @ 105°C': '236531',
                     '5000 Hrs @ 125°C': '236532',
                     '5000 Hrs @ 85°C': '236533',
                     '5000 Hrs @ 95°C': '236534',
                     '6000 Hrs @ 105°C': '255724',
                     '6000 Hrs @ 125°C': '255725',
                     '6000 Hrs @ 85°C': '255726',
                     '6300 Hrs @ 125°C': '508469',
                     '7000 Hrs @ 105°C': '272852',
                     '7000 Hrs @ 125°C': '272853',
                     '7500 Hrs @ 105°C': '277339',
                     '8000 Hrs @ 105°C': '286114',
                     '8000 Hrs @ 125°C': '286115',
                     '8000 Hrs @ 85°C': '286116',
                     '8400 Hrs @ 125°C': '508470',
                     '8400 Hrs @ 150°C': '828044',
                     '9000 Hrs @ 105°C': '299079',
                     '10000 Hrs @ 105°C': '68209',
                     '10000 Hrs @ 125°C': '68210',
                     '10000 Hrs @ 85°C': '68213',
                     '11000 Hrs @ 105°C': '769395',
                     '11000 Hrs @ 85°C': '77125',
                     '12000 Hrs @ 105°C': '83569',
                     '12000 Hrs @ 85°C': '83570',
                     '13000 Hrs @ 105°C': '89908',
                     '13000 Hrs @ 85°C': '89909',
                     '14000 Hrs @ 85°C': '94421',
                     '14500 Hrs @ 85°C': '95788',
                     '15000 Hrs @ 105°C': '99867',
                     '15000 Hrs @ 85°C': '99869',
                     '17000 Hrs @ 85°C': '110480',
                     '18000 Hrs @ 105°C': '828103',
                     '18000 Hrs @ 85°C': '114330',
                     '18500 Hrs @ 85°C': '115306',
                     '19000 Hrs @ 85°C': '118009',
                     '20000 Hrs @ 105°C': '140048',
                     '20000 Hrs @ 125°C': '140049',
                     '20000 Hrs @ 85°C': '140054',
                     '21000 Hrs @ 85°C': '828100',
                     '22000 Hrs @ 105°C': '147664',
                     '24000 Hrs @ 85°C': '153262',
                     '26000 Hrs @ 85°C': '160255',
                     '28000 Hrs @ 85°C': '827327',
                     '29000 Hrs @ 85°C': '166617',
                     '37000 Hrs @ 105°C': '197997',
                     '38000 Hrs @ 85°C': '827328',
                     '45000 Hrs @ 105°C': '694904',
                     '60000 Hrs @ 70°C': '255744'},
        "Manufacturer": {'AIC tech Inc.': '4193',
                         'Aillen': '600470',
                         'Aishi Capacitors (Hunan Aihua Group)': '602079',
                         'Chemi-Con': '565',
                         'Chinsan (Elite)': '4191',
                         'Cornell Dubilier Knowles': '338',
                         'Elna America': '604',
                         'EPCOS - TDK Electronics': '495',
                         'EXXELIA Sic Safco': '600493',
                         'GE Capacitor': '602026',
                         'Hammond Manufacturing': '164',
                         'Hartland Controls/Littelfuse': '3766',
                         'KEMET': '399',
                         'KYOCERA AVX': '478',
                         'Lumimax Optoelectronic Technology': '4491',
                         'Mallory': '602041',
                         'Meritek': '2997',
                         'NextGen Components': '3372',
                         'NIC Components Corp': '4988',
                         'Nichicon': '493',
                         'Panasonic Electronic Components': '10',
                         'Rubycon': '1189',
                         'SAMXON': '601797',
                         'SparkFun Electronics': '1568',
                         'SURGE': '2616',
                         'Surge': '4403',
                         'Suscon': '602111',
                         'TE Connectivity Passive Product': '1712',
                         'Visaton GmbH & Co. KG': '2056',
                         'Vishay Beyschlag/Draloric/BC Components': '56',
                         'Vishay Dale': '541',
                         'Vishay Sprague': '718',
                         'Würth Elektronik': '732',
                         'Yageo America': '311',
                         'Ymin': '5011'}
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
