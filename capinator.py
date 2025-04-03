#!/usr/bin/env python3

import csv
import traceback
import libs.digikey as dk

def process_csv(file_path):
    """Process CSV file"""

    api = dk.DigiKeyV4()

    csvfile = open(file_path, newline="")
    outfile = open('bulk.csv', mode = 'w')
    reader = csv.DictReader(csvfile)
    for row in reader:
        try:
            print(f"Processing: {row['capacitance']} uF {row['voltage']} V")

            # Map CSV columns to API parameters
            params = {}
            for key in row.keys():
                if key in ['qty', 'capacitance', 'voltage'] and row[key] in [None, '']:
                    raise Exception('Capacitor require qty + capacitance + voltage.')
            
                if row[key] not in [None, '']:
                    params[key] = row[key]

            part_number = api.find_digikey_pn_by_moq(params)
            if part_number:
                print(f"Found P/N: {part_number}")
                outfile.write(f"{row['qty']}, {part_number}, {row['capacitance']}uF {row['voltage']}V\n")
            else:
                print(f"No match found for {params}")

        except Exception as e:
            print(f"Error processing row: {e}")
            traceback.print_exc(file=sys.stdout)
    outfile.close()
    csvfile.close()

if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python capinator.py <input.csv>")
        sys.exit(1)

    process_csv(sys.argv[1])
