#!/usr/bin/env python3

import csv
import libs.digikey as dk

def process_csv(file_path):
    """Process CSV file and build cart"""

    api = dk.DigiKeyV4()

    with open(file_path, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            try:
                print(f"Processing: {row['capacitance']} uF {row['voltage']} V")

                # Map CSV columns to API parameters
                params = {
                    "capacitance": row["capacitance"],
                    "voltage": row["voltage"],
                }

                part_number = api.find_digikey_pn(params)
                if part_number:
                    print(f"Added {part_number} to cart")
                else:
                    print(f"No match found for {params}")

            except Exception as e:
                print(f"Error processing row: {e}")


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        print("Usage: python capinator.py <input.csv>")
        sys.exit(1)

    process_csv(sys.argv[1])
