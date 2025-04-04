# Description: Digikey API wrapper for searching capacitors
import re
from os import getenv
from typing import Any, Dict, List
from requests_oauthlib import OAuth2Session
from oauthlib.oauth2 import BackendApplicationClient
from libs.digikey_data import CATEGORY_IDS
from libs.digikey_data import ElectrolyticCapacitors as lytics

# Digi-Key API configuration
API_BASE = "https://api.digikey.com"
CLIENT_ID = getenv("DIGIKEY_CLIENT_ID")
CLIENT_SECRET = getenv("DIGIKEY_CLIENT_SECRET")

# API endpoints
SEARCH_API = "/products/v4/search/keyword"
CART_API = "/Ordering/v3/Cart/Items"
CATEGORIES = "/products/v4/search/categories"


class DigiKeyV4:
    def __init__(self):
        super().__init__()

        self.session = self.authenticate()
        self.util = self.Utils()

    def authenticate(self) -> OAuth2Session:
        """Authenticate with Digi-Key API using OAuth2"""
        oauth = OAuth2Session(client=BackendApplicationClient(client_id=CLIENT_ID))
        oauth.fetch_token(
            token_url=f"{API_BASE}/v1/oauth2/token", client_secret=CLIENT_SECRET
        )
        return oauth

    class Utils:
        def is_temp_in_range(self, range_str: str, temp: int, fudge: int = 0) -> bool:
            """
            Check if the given temp value is within the temperature range described by range_str.

            The range_str should be in the format "<min>°C ~ <max>°C", e.g., "-55°C ~ 105°C".

            :param range_str: A string representing the temperature range.
            :param temp: An integer temperature to check.
            :return: True if value is between min and max (inclusive) found in range_str; otherwise False.
            """
            parts = range_str.replace("°C", "").split("~")
            if len(parts) != 2:
                raise ValueError(
                    "Input string is not in expected format '<min>°C ~ <max>°C'."
                )

            try:
                lower = int(parts[0].strip()) - (int(parts[0].strip()) * fudge) / 100
                upper = int(parts[1].strip()) + (int(parts[1].strip()) * fudge) / 100
            except ValueError as e:
                raise ValueError(
                    "Failed to convert temperature values to integers."
                ) from e

            return lower <= temp <= upper

        def does_rating_meets_lifetime_and_temp(
            self, rating_str: str, lifetime: int, temp: int, fudge: int = 0
        ) -> bool:
            """
            Check if the given lifetime @ temp rating string meets the lifetime and temp values provided.

            The rating_str should be in the format "<hours> Hrs @ <temp>°C", e.g., "1000 Hrs @ 105°C".

            :param rating_str: A string representing the lifetime @ temp rating.
            :param temp: An integer temperature.
            :param lifetime: An integer lifetime.
            :return: True if rating_str meets both lifetime and temp values; otherwise False.
            """
            parts = rating_str.replace(" Hrs", "").replace("°C", "").split("@")
            if len(parts) != 2:
                raise ValueError(
                    "Input string is not in expected format '<hours> Hrs @ <temp>°C'."
                )

            try:
                hours = int(parts[0].strip())
                temp_rating = int(parts[1].strip())
            except ValueError as e:
                raise ValueError(
                    "Failed to convert lifetime and temp values to integers."
                ) from e

            return (
                hours >= lifetime - (lifetime * fudge) / 100
                and temp_rating >= temp - (temp * fudge) / 100
            )

        def is_dim_close_enough(
            self, dim_str: str, dim: float, fudge: int = 10
        ) -> bool:
            """
            Check if the given dimention string is close enough to the dimention value provided
            within a certain fudge factor (default 10%).

            The dim_str should be in the format:
            '<dim in inches>" (<dim in mm>mm)' e.g., '0.300" (7.62mm)'.

            :param dim_str: A string representing the dimention both in inches and mm.
            :param dim: A float dimention value to check in mm.
            :param fudge: The allowable difference in percentage (default 10%).
            :return: True if the provided dimention is within the fudge percentage of the dimention in dim_str;
                    otherwise False.
            """
            try:
                # Extract the mm value from spacing_str, e.g., "7.62" from '0.300" (7.62mm)'
                mm_part = dim_str.split("(")[1].split("mm")[0].strip()
                dim_mm = float(mm_part)
            except (IndexError, ValueError) as e:
                raise ValueError(
                    "Spacing string is not in the expected format '<inches>\" (<mm>mm)'."
                ) from e

            # Calculate percentage difference relative to the parsed spacing_mm.
            percent_diff = abs(dim_mm - dim) / dim_mm * 100

            return percent_diff <= fudge

        def are_dims_close_enough(
            self, dims_str: str, dims: Dict[str, float], fudge: int = 10
        ) -> bool:
            """
            Check if the given dimentions string is close enough to the dimention values provided
            within a certain fudge factor (default 10%).

            The dims_str can be of three distinct formats:
            -> '<float>" Dia (<float>mm)' e.g, '0.335" Dia (8.50mm)'
            -> '<float>" Dia x <float>" L (<float>mm x <float>mm)' e.g, '0.335" Dia x 0.709" L (8.50mm x 18.00mm)'
            -> '<float>" L x <float>" W (<float>mm x <float>mm)' e.g, '0.335" L x 0.209" W (8.50mm x 5.30mm)'

            :param dims_str: A string representing one or two dimentions both in inches and mm.
            :param dims: A list of float dimention values to check in mm.
            :param fudge: The allowable difference in percentage (default 10%).
            :return: True if the provided dimention(s) is(are) within the fudge percentage of the dimentions in dims_str;
                    otherwise False.
            """
            from libs.digikey_data import Regexes as r
            patterns = {
                "dia": r.DIA,
                "dia_len": r.DIA_LEN,
                "len_wid": r.LEN_WID
            }

            dim_str_dict = {"L": None, "W": None}

            for pat, regx in patterns.items():
                match = re.match(regx, dims_str)
                if match:
                    if pat == "dia":
                        dim_str_dict["W"] = float(
                            match.group(2)
                        )  # Diameter is really just width.
                    elif pat == "dia_len":
                        dim_str_dict["W"] = float(match.group(3))
                        dim_str_dict["L"] = float(match.group(4))
                    elif pat == "len_wid":
                        dim_str_dict["L"] = float(match.group(3))
                        dim_str_dict["W"] = float(match.group(4))
                    break

            for d in dim_str_dict.keys():
                if dim_str_dict[d] is None:
                    continue
                percent_diff = abs(dim_str_dict[d] - dims[d]) / dim_str_dict[d] * 100
                if percent_diff >= fudge:
                    return False

            return True

        def make_temperture_filter(
            self, temp: int, fudge: int = 0
        ) -> List[Dict[str, str]]:
            filtervals = []
            for key, val in lytics.FILTER_VALS["Operating Temperature"].items():
                if self.is_temp_in_range(range_str=key, temp=temp, fudge=fudge):
                    filtervals.append({"Id": val})
            return filtervals

        def make_lifetime_filter(
            self, lifetime: int, temp: int, fudge: int = 0
        ) -> List[Dict[str, str]]:
            filtervals = []
            for key, val in lytics.FILTER_VALS["Lifetime @ Temp"].items():
                if self.does_rating_meets_lifetime_and_temp(
                    rating_str=key, temp=temp, lifetime=lifetime, fudge=fudge
                ):
                    filtervals.append({"Id": val})
            return filtervals

        def make_lead_spacing_filter(
            self, spacing: float, fudge: int = 10
        ) -> List[Dict[str, str]]:
            filtervals = []
            for key, val in lytics.FILTER_VALS["Lead Spacing"].items():
                if self.is_dim_close_enough(dim_str=key, dim=spacing, fudge=fudge):
                    filtervals.append({"Id": val})
            return filtervals

        def make_height_filter(
            self, height: float, fudge: int = 10
        ) -> List[Dict[str, str]]:
            filtervals = []
            for key, val in lytics.FILTER_VALS["Height"].items():
                if self.is_dim_close_enough(dim_str=key, dim=height, fudge=fudge):
                    filtervals.append({"Id": val})
            return filtervals

        def make_dimension_filter(
            self, dims: str, dim_type: str, fudge: int = 10
        ) -> List[Dict[str, str]]:
            filtervals = []

            from libs.digikey_data import Regexes as r
            match = re.match(r.DIMS, dims)
            if match:
                dims_dict = {
                    "W": float(match.group(1)),
                    "L": float(match.group(2)) if float(match.group(2)) > 0 else None,
                }
            else:
                return filtervals

            for key, val in lytics.FILTER_VALS[dim_type].items():
                if self.are_dims_close_enough(
                    dims_str=key, dims=dims_dict, fudge=fudge
                ):
                    filtervals.append({"Id": val})
            return filtervals

    def make_payload(self, **kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """Create a payload for the Digi-Key search API"""

        if "fudge" in kwargs:
            fudge = int(kwargs["fudge"])
        else:
            fudge = 0

        payload = {
            "Limit": 10,
            "FilterOptionsRequest": {
                "ManufacturerFilter": [],
                "CategoryFilter": [
                    {"Id": CATEGORY_IDS["Aluminum Electrolytic Capacitors"]}
                ],
                "MarketPlaceFilter": "ExcludeMarketPlace",
                "MinimumQuantityAvailable": 1,
                "ParameterFilterRequest": {
                    "CategoryFilter": {
                        "Id": CATEGORY_IDS["Aluminum Electrolytic Capacitors"]
                    },
                    "ParameterFilters": [],
                },
                "SearchOptions": ["InStock"],
            },
            "SortOptions": {"Field": "Price", "SortOrder": "Ascending"},
        }

        if "keywords" in kwargs and len(kwargs["keywords"]) > 0:
            for kw in kwargs["keywords"]:
                payload["Keywords"] += kw + " "

        if "limit" in kwargs:
            payload["Limit"] = kwargs["limit"]

        if "manufacturers" in kwargs and len(kwargs["manufacturers"]) > 0:
            payload["FilterOptionsRequest"]["ManufacturerFilter"] = []
            for man in kwargs["manufacturers"]:
                payload["FilterOptionsRequest"]["ManufacturerFilter"].append(
                    {"Id": lytics.MANUFACTURER_IDS[man]}
                )
        else:  # defaults to some reputable manufacturers
            payload["FilterOptionsRequest"]["ManufacturerFilter"] = [
                {"Id": lytics.MANUFACTURER_IDS["Nichicon"]},
                {"Id": lytics.MANUFACTURER_IDS["Panasonic Electronic Components"]},
                {"Id": lytics.MANUFACTURER_IDS["Rubycon"]},
                {"Id": lytics.MANUFACTURER_IDS["Chemi-Con"]},
            ]

        if "qty" in kwargs:
            payload["FilterOptionsRequest"]["MinimumQuantityAvailable"] = kwargs["qty"]

        if "capacitance" in kwargs:
            payload["FilterOptionsRequest"]["ParameterFilterRequest"][
                "ParameterFilters"
            ].append(
                {
                    "ParameterId": lytics.PARAMETER_IDS["Capacitance"],
                    "FilterValues": [{"Id": str(kwargs["capacitance"]) + " uF"}],
                }
            )

        if "voltage" in kwargs:
            payload["FilterOptionsRequest"]["ParameterFilterRequest"][
                "ParameterFilters"
            ].append(
                {
                    "ParameterId": lytics.PARAMETER_IDS["Voltage - Rated"],
                    "FilterValues": [{"Id": str(kwargs["voltage"]) + " V"}],
                }
            )

        if "package" in kwargs:
            filter_vals = {
                "ParameterId": lytics.PARAMETER_IDS["Package / Case"],
                "FilterValues": [],
            }
            if kwargs["package"] == "A":
                filter_vals["FilterValues"] = [
                    {"Id": lytics.FILTER_VALS["Package / Case"]["Axial"]},
                    {"Id": lytics.FILTER_VALS["Package / Case"]["Axial, Can"]},
                ]
            elif kwargs["package"] == "R":
                filter_vals["FilterValues"] = [
                    {"Id": lytics.FILTER_VALS["Package / Case"]["Radial"]},
                    {"Id": lytics.FILTER_VALS["Package / Case"]["Radial, Can"]},
                ]
            payload["FilterOptionsRequest"]["ParameterFilterRequest"][
                "ParameterFilters"
            ].append(filter_vals)

        filter_vals = {
            "ParameterId": lytics.PARAMETER_IDS["Mounting Type"],
            "FilterValues": [],
        }
        if "mounting" in kwargs:
            if kwargs["mounting"] == "SMD":
                mounting = "Surface Mount"
            elif kwargs["mounting"] == "THT":
                mounting = "Through Hole"
            else:
                mounting = kwargs["mounting"]
            filter_vals["FilterValues"] = [
                {"Id": lytics.FILTER_VALS["Mounting Type"][mounting]}
            ]
        else:  # defaults to Through Hole
            filter_vals["FilterValues"] = [
                {"Id": lytics.FILTER_VALS["Mounting Type"]["Through Hole"]}
            ]
        payload["FilterOptionsRequest"]["ParameterFilterRequest"][
            "ParameterFilters"
        ].append(filter_vals)

        if "polarization" in kwargs:
            if kwargs["polarization"] == "NP" or kwargs["polarization"] == "BP":
                polarization = "Bi-Polar"
        else:
            polarization = "Polar"  # defaults to Polarized
        filter_vals = {
            "ParameterId": lytics.PARAMETER_IDS["Polarization"],
            "FilterValues": [{"Id": lytics.FILTER_VALS["Polarization"][polarization]}],
        }
        payload["FilterOptionsRequest"]["ParameterFilterRequest"][
            "ParameterFilters"
        ].append(filter_vals)

        if "smd_land_size" in kwargs:
            filter_vals = {
                "ParameterId": lytics.PARAMETER_IDS["SMD Land Size"],
                "FilterValues": self.util.make_dimension_filter(
                    dims=kwargs["smd_land_size"], dim_type="SMD Land Size", fudge=fudge
                ),
            }
            payload["FilterOptionsRequest"]["ParameterFilterRequest"][
                "ParameterFilters"
            ].append(filter_vals)

        if "lead_spacing" in kwargs:
            filter_vals = {
                "ParameterId": lytics.PARAMETER_IDS["Lead Spacing"],
                "FilterValues": self.util.make_lead_spacing_filter(
                    spacing=float(kwargs["lead_spacing"]), fudge=fudge
                ),
            }
            payload["FilterOptionsRequest"]["ParameterFilterRequest"][
                "ParameterFilters"
            ].append(filter_vals)

        if "height" in kwargs:
            filter_vals = {
                "ParameterId": lytics.PARAMETER_IDS["Height"],
                "FilterValues": self.util.make_height_filter(
                    height=float(kwargs["height"]), fudge=fudge
                ),
            }
            payload["FilterOptionsRequest"]["ParameterFilterRequest"][
                "ParameterFilters"
            ].append(filter_vals)

        if "dimensions" in kwargs:
            filter_vals = {
                "ParameterId": lytics.PARAMETER_IDS["Dimensions"],
                "FilterValues": self.util.make_dimension_filter(
                    dims=kwargs["dimensions"], dim_type="Dimensions", fudge=fudge
                ),
            }
            payload["FilterOptionsRequest"]["ParameterFilterRequest"][
                "ParameterFilters"
            ].append(filter_vals)

        if "lifetime" in kwargs:
            if "temp" in kwargs:
                temp = int(kwargs["temp"])
            else:
                temp = 85
            filter_vals = {
                "ParameterId": lytics.PARAMETER_IDS["Lifetime @ Temp"],
                "FilterValues": self.util.make_lifetime_filter(
                    int(kwargs["lifetime"]), temp, fudge
                ),
            }
            payload["FilterOptionsRequest"]["ParameterFilterRequest"][
                "ParameterFilters"
            ].append(filter_vals)

        if "temp" in kwargs:
            filter_vals = {
                "ParameterId": lytics.PARAMETER_IDS["Operating Temperature"],
                "FilterValues": self.util.make_temperture_filter(
                    int(kwargs["temp"]), fudge
                ),
            }
            payload["FilterOptionsRequest"]["ParameterFilterRequest"][
                "ParameterFilters"
            ].append(filter_vals)

        return payload

    def make_query(self, params: Dict[str, Any]) -> List[str]:
        data = self.make_payload(**params)

        response = self.session.post(
            url=f"{API_BASE}{SEARCH_API}",
            headers={
                "X-DIGIKEY-Client-Id": CLIENT_ID,
                "Authorization": self.session.token["access_token"],
            },
            json=data,
        )
        response.raise_for_status()
        return response.json()

    def find_all_digikey_pn(self, params: Dict[str, Any]) -> List[str]:
        """Find all matching Digi-Key part numbers"""
        
        resp = self.make_query(params)
        if resp.get("Products"):
            if len(resp["Products"]) == 0:
                return None
            else:
                return [
                    prod["ManufacturerProductNumber"]
                    for prod in resp["Products"]
                ]

        return None

    def find_digikey_pn_by_moq(self, param: Dict[str, str], paginate: bool = True) -> str:
        """Find first matching Digi-Key part number that meets MOQ for a given quantity"""

        param["limit"] = 10
        param["offset"] = 0
        resp = self.make_query(param)
        if resp is None:
            return None
        else:
            for prod in resp["Products"]:
                for var in prod["ProductVariations"]:
                    if 1 <= int(var["MinimumOrderQuantity"]) <= int(param["qty"]):
                        return var["DigiKeyProductNumber"]
            if resp["ProductsCount"] > param["limit"] and paginate:
                for offset in range(param["limit"], resp["ProductsCount"], param["limit"]):
                    param["offset"] = offset
                    resp = self.make_query(param)
                    if resp is None:
                        return None
                    else:
                        for prod in resp["Products"]:
                            for var in prod["ProductVariations"]:
                                if 1 <= int(var["MinimumOrderQuantity"]) <= int(param["qty"]):
                                    return var["DigiKeyProductNumber"]
            return None

    def find_digikey_pn(self, params: Dict[str, str]) -> str:
        """Find first matching Digi-Key part number"""

        params["limit"] = 1
        return None if self.find_all_digikey_pn(params) is None else self.find_all_digikey_pn(params)[0]

    def add_to_cart(self, part_number, quantity=1):
        """Add item to Digi-Key cart"""
        cart_item = {"Items": [{"Quantity": quantity, "PartNumber": part_number}]}

        response = self.session.post(f"{API_BASE}{CART_API}", json=cart_item)
        response.raise_for_status()
        return response.json()
