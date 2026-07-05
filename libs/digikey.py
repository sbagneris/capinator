# Description: Digikey API wrapper for searching capacitors
import re
from os import getenv
from typing import Any, Dict, List, Optional
from requests_oauthlib import OAuth2Session
from oauthlib.oauth2 import BackendApplicationClient
from libs.digikey_data import CATEGORY_IDS
from facet_loader import get_facet_tables, broad_query_payload

# Digi-Key API configuration
API_BASE = "https://api.digikey.com"
CLIENT_ID = getenv("DIGIKEY_CLIENT_ID")
CLIENT_SECRET = getenv("DIGIKEY_CLIENT_SECRET")

# API endpoints
SEARCH_API = "/products/v4/search/keyword"
CART_API = "/Ordering/v3/Cart/Items"
CATEGORIES = "/products/v4/search/categories"

# Default reputable manufacturers, referenced by STABLE DigiKey vendor Id rather
# than name: names drift (e.g. "Panasonic Electronic Components" is now
# "Panasonic Industry"). Nichicon, Panasonic, Rubycon, Chemi-Con.
DEFAULT_MANUFACTURER_IDS = [493, 10, 1189, 565]


class DigiKeyV4:
    def __init__(self):
        super().__init__()

        self.session = self.authenticate()
        self.facets = self._load_facets()
        self.util = self.Utils(self.facets)

    def authenticate(self) -> OAuth2Session:
        """Authenticate with Digi-Key API using OAuth2"""
        client_id, client_secret = CLIENT_ID, CLIENT_SECRET
        if not client_id or not client_secret:
            raise RuntimeError(
                "Set DIGIKEY_CLIENT_ID and DIGIKEY_CLIENT_SECRET (see secrets.sh)."
            )
        oauth = OAuth2Session(client=BackendApplicationClient(client_id=client_id))
        oauth.fetch_token(
            token_url=f"{API_BASE}/v1/oauth2/token", client_secret=client_secret
        )
        return oauth

    def _load_facets(self):
        """Load the parameter/value lookup tables from the disk cache, querying the
        API only on a cold or expired cache (see facet_loader.get_facet_tables)."""
        category = CATEGORY_IDS["Aluminum Electrolytic Capacitors"]
        return get_facet_tables(
            lambda: self._post_search(broad_query_payload(category))
        )

    class Utils:
        def __init__(self, facets):
            self.facets = facets

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

            dim_str_dict: Dict[str, Optional[float]] = {"L": None, "W": None}

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

            for d, parsed in dim_str_dict.items():
                if parsed is None:
                    continue
                percent_diff = abs(parsed - dims[d]) / parsed * 100
                if percent_diff >= fudge:
                    return False

            return True

        def _select_facet_values(self, category, predicate) -> List[Dict[str, str]]:
            """Return [{"Id": id}] for each value in `category` matched by
            `predicate(value_name)`. Values the predicate can't parse are skipped:
            dynamic facets may contain formats the strict parsers don't handle
            (e.g. a bare '85°C' with no range), and one odd value must not abort
            the whole query."""
            filtervals = []
            for name, vid in self.facets.FILTER_VALS[category].items():
                try:
                    matched = predicate(name)
                except ValueError:
                    continue
                if matched:
                    filtervals.append({"Id": vid})
            return filtervals

        def make_temperture_filter(
            self, temp: int, fudge: int = 0
        ) -> List[Dict[str, str]]:
            return self._select_facet_values(
                "Operating Temperature",
                lambda name: self.is_temp_in_range(range_str=name, temp=temp, fudge=fudge),
            )

        def make_lifetime_filter(
            self, lifetime: int, temp: int, fudge: int = 0
        ) -> List[Dict[str, str]]:
            return self._select_facet_values(
                "Lifetime @ Temp",
                lambda name: self.does_rating_meets_lifetime_and_temp(
                    rating_str=name, temp=temp, lifetime=lifetime, fudge=fudge
                ),
            )

        def make_lead_spacing_filter(
            self, spacing: float, fudge: int = 10
        ) -> List[Dict[str, str]]:
            return self._select_facet_values(
                "Lead Spacing",
                lambda name: self.is_dim_close_enough(dim_str=name, dim=spacing, fudge=fudge),
            )

        def make_height_filter(
            self, height: float, fudge: int = 10
        ) -> List[Dict[str, str]]:
            return self._select_facet_values(
                "Height",
                lambda name: self.is_dim_close_enough(dim_str=name, dim=height, fudge=fudge),
            )

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

            for key, val in self.facets.FILTER_VALS[dim_type].items():
                if self.are_dims_close_enough(
                    dims_str=key, dims=dims_dict, fudge=fudge
                ):
                    filtervals.append({"Id": val})
            return filtervals

    def make_payload(self, **kwargs: Any) -> Dict[str, Any]:
        """Create a payload for the Digi-Key search API"""

        fudge = int(kwargs.get("fudge", 0))
        category_id = CATEGORY_IDS["Aluminum Electrolytic Capacitors"]

        payload = {
            "Limit": 10,
            "FilterOptionsRequest": {
                "ManufacturerFilter": [],
                "CategoryFilter": [{"Id": category_id}],
                "MarketPlaceFilter": "ExcludeMarketPlace",
                "MinimumQuantityAvailable": 1,
                "ParameterFilterRequest": {
                    "CategoryFilter": {"Id": category_id},
                    "ParameterFilters": [],
                },
                "SearchOptions": ["InStock"],
            },
            "SortOptions": {"Field": "Price", "SortOrder": "Ascending"},
        }
        # Bind the nested request objects the filter blocks below repeatedly mutate.
        filter_req = payload["FilterOptionsRequest"]
        param_filters = filter_req["ParameterFilterRequest"]["ParameterFilters"]

        if kwargs.get("keywords"):
            kw = kwargs["keywords"]
            payload["Keywords"] = kw if isinstance(kw, str) else " ".join(kw)

        if "limit" in kwargs:
            payload["Limit"] = int(kwargs["limit"])

        if "offset" in kwargs:  # pagination: Offset is a top-level request field
            payload["Offset"] = int(kwargs["offset"])

        if kwargs.get("manufacturers"):
            filter_req["ManufacturerFilter"] = [
                {"Id": self.facets.MANUFACTURER_IDS[man]}
                for man in kwargs["manufacturers"]
            ]
        else:  # defaults to some reputable manufacturers (by stable vendor Id)
            filter_req["ManufacturerFilter"] = [
                {"Id": mid} for mid in DEFAULT_MANUFACTURER_IDS
            ]

        if "qty" in kwargs:
            filter_req["MinimumQuantityAvailable"] = int(kwargs["qty"])

        if "capacitance" in kwargs:
            param_filters.append(
                {
                    "ParameterId": self.facets.PARAMETER_IDS["Capacitance"],
                    "FilterValues": [{"Id": str(kwargs["capacitance"]) + " uF"}],
                }
            )

        if "voltage" in kwargs:
            param_filters.append(
                {
                    "ParameterId": self.facets.PARAMETER_IDS["Voltage - Rated"],
                    "FilterValues": [{"Id": str(kwargs["voltage"]) + " V"}],
                }
            )

        if "package" in kwargs:
            package_vals = self.facets.FILTER_VALS["Package / Case"]
            if kwargs["package"] == "A":
                filter_values = [
                    {"Id": package_vals["Axial"]},
                    {"Id": package_vals["Axial, Can"]},
                ]
            elif kwargs["package"] == "R":
                filter_values = [
                    {"Id": package_vals["Radial"]},
                    {"Id": package_vals["Radial, Can"]},
                ]
            else:
                filter_values = [{"Id": package_vals[kwargs["package"]]}]
            param_filters.append(
                {
                    "ParameterId": self.facets.PARAMETER_IDS["Package / Case"],
                    "FilterValues": filter_values,
                }
            )

        # Mounting defaults to Through Hole; SMD/THT are aliases for the facet names.
        mounting_aliases = {"SMD": "Surface Mount", "THT": "Through Hole"}
        mounting = kwargs.get("mounting", "Through Hole")
        mounting = mounting_aliases.get(mounting, mounting)
        param_filters.append(
            {
                "ParameterId": self.facets.PARAMETER_IDS["Mounting Type"],
                "FilterValues": [
                    {"Id": self.facets.FILTER_VALS["Mounting Type"][mounting]}
                ],
            }
        )

        if kwargs.get("polarization") in ("NP", "BP"):
            polarization = "Bi-Polar"
        else:
            polarization = "Polar"  # defaults to Polarized (also when absent)
        param_filters.append(
            {
                "ParameterId": self.facets.PARAMETER_IDS["Polarization"],
                "FilterValues": [
                    {"Id": self.facets.FILTER_VALS["Polarization"][polarization]}
                ],
            }
        )

        if "smd_land_size" in kwargs:
            param_filters.append(
                {
                    "ParameterId": self.facets.PARAMETER_IDS["SMD Land Size"],
                    "FilterValues": self.util.make_dimension_filter(
                        dims=kwargs["smd_land_size"], dim_type="SMD Land Size", fudge=fudge
                    ),
                }
            )

        if "lead_spacing" in kwargs:
            param_filters.append(
                {
                    "ParameterId": self.facets.PARAMETER_IDS["Lead Spacing"],
                    "FilterValues": self.util.make_lead_spacing_filter(
                        spacing=float(kwargs["lead_spacing"]), fudge=fudge
                    ),
                }
            )

        if "height" in kwargs:
            param_filters.append(
                {
                    "ParameterId": self.facets.PARAMETER_IDS["Height"],
                    "FilterValues": self.util.make_height_filter(
                        height=float(kwargs["height"]), fudge=fudge
                    ),
                }
            )

        if "dimensions" in kwargs:
            param_filters.append(
                {
                    "ParameterId": self.facets.PARAMETER_IDS["Dimensions"],
                    "FilterValues": self.util.make_dimension_filter(
                        dims=kwargs["dimensions"], dim_type="Dimensions", fudge=fudge
                    ),
                }
            )

        if "lifetime" in kwargs:
            temp = int(kwargs["temp"]) if "temp" in kwargs else 85
            param_filters.append(
                {
                    "ParameterId": self.facets.PARAMETER_IDS["Lifetime @ Temp"],
                    "FilterValues": self.util.make_lifetime_filter(
                        int(kwargs["lifetime"]), temp, fudge
                    ),
                }
            )

        if "temp" in kwargs:
            param_filters.append(
                {
                    "ParameterId": self.facets.PARAMETER_IDS["Operating Temperature"],
                    "FilterValues": self.util.make_temperture_filter(
                        int(kwargs["temp"]), fudge
                    ),
                }
            )

        if "packaging" in kwargs:
            # Packaging is a top-level facet group (like ManufacturerFilter), NOT a
            # parametric filter, so it goes in its own PackagingFilter field with an
            # integer Id. The old "-5" was the MUI UI group id (filter-box-group--5),
            # not an API ParameterId, and matched zero products.
            filter_req["PackagingFilter"] = [
                {"Id": int(self.facets.FILTER_VALS["Packaging"][kwargs["packaging"]])}
            ]

        return payload

    def _do_post(self, data: Dict[str, Any]):
        """Single POST to the keyword search endpoint with the current token."""
        return self.session.post(
            url=f"{API_BASE}{SEARCH_API}",
            headers={
                "X-DIGIKEY-Client-Id": CLIENT_ID,
                "Authorization": self.session.token["access_token"],
            },
            json=data,
        )

    def _post_search(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """POST a prebuilt payload to the keyword search endpoint and return JSON.

        Client-credentials tokens expire (~30 min) and have no refresh token, so on
        a 401 we re-authenticate once and retry — this keeps long bulk CSV runs from
        dying mid-way."""
        response = self._do_post(data)
        if response.status_code == 401:  # token expired: re-auth once and retry
            self.session = self.authenticate()
            response = self._do_post(data)
        response.raise_for_status()
        return response.json()

    def make_query(self, params: Dict[str, Any]) -> Dict[str, Any]:
        return self._post_search(self.make_payload(**params))

    def find_all_digikey_pn(self, params: Dict[str, Any]) -> Optional[List[str]]:
        """Find all matching Digi-Key part numbers"""

        resp = self.make_query(params)
        if resp.get("Products"):
            return [prod["ManufacturerProductNumber"] for prod in resp["Products"]]
        return None

    @staticmethod
    def _first_pn_meeting_moq(resp: Dict[str, Any], qty: int) -> Optional[str]:
        """Return the first variation's DigiKey P/N whose MOQ is in [1, qty], else None."""
        for prod in resp.get("Products", []):
            for var in prod.get("ProductVariations", []):
                if 1 <= int(var["MinimumOrderQuantity"]) <= qty:
                    return var["DigiKeyProductNumber"]
        return None

    def find_digikey_pn_by_moq(self, param: Dict[str, Any], paginate: bool = True) -> Optional[str]:
        """Find first matching Digi-Key part number that meets MOQ for a given quantity"""

        page = 50  # v4 max page size: fewer (rate-limited) queries when paginating
        qty = int(param["qty"])
        param["limit"] = page
        param["offset"] = 0
        resp = self.make_query(param)

        match = self._first_pn_meeting_moq(resp, qty)
        if match or not paginate:
            return match

        for offset in range(page, resp["ProductsCount"], page):
            param["offset"] = offset
            match = self._first_pn_meeting_moq(self.make_query(param), qty)
            if match:
                return match
        return None

    def find_digikey_pn(self, params: Dict[str, Any]) -> Optional[str]:
        """Find first matching Digi-Key part number"""

        params["limit"] = 1
        results = self.find_all_digikey_pn(params)
        return results[0] if results else None

    def add_to_cart(self, part_number, quantity=1):
        """Add item to Digi-Key cart"""
        cart_item = {"Items": [{"Quantity": quantity, "PartNumber": part_number}]}

        response = self.session.post(f"{API_BASE}{CART_API}", json=cart_item)
        response.raise_for_status()
        return response.json()
