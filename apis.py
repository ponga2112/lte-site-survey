# -*- coding: utf-8 -*-

import requests
import json
import pickle

from qmilte import Cell

test_json = [
    {
        "last_seen_ts": 1651255195,
        "last_seen_str": "2022-04-29T10:59:55.480701",
        "plmn": "310120",
        "mcc": "310",
        "mnc": "120",
        "operator": "[US] / Sprint Spectrum",
        "cid": 115362843,
        "pci": 47,
        "tac": 13403,
        "earfcn": 8763,
        "freq_dl_mhz": 866.3,
        "band": 26,
        "rsrp_dbm": -111,
        "reg_status": "limited-regional",
        "coords_lat": 0,
        "coords_lon": 0,
        "api": [],
    },
    {
        "last_seen_ts": 1651255196,
        "last_seen_str": "2022-04-29T10:59:56.791902",
        "plmn": "310260",
        "mcc": "310",
        "mnc": "260",
        "operator": "[US] / T-Mobile",
        "cid": 22228491,
        "pci": 258,
        "tac": 13403,
        "earfcn": 675,
        "freq_dl_mhz": 1937.5,
        "band": 2,
        "rsrp_dbm": -108.1,
        "reg_status": "limited",
        "coords_lat": 0,
        "coords_lon": 0,
        "api": [],
    },
    {
        "last_seen_ts": 1651255198,
        "last_seen_str": "2022-04-29T10:59:58.105579",
        "plmn": "310410",
        "mcc": "310",
        "mnc": "410",
        "operator": "[US] / AT&T Wireless Inc.",
        "cid": 124650355,
        "pci": 377,
        "tac": 13403,
        "earfcn": 2175,
        "freq_dl_mhz": 2132.5,
        "band": 4,
        "rsrp_dbm": -86.7,
        "reg_status": "limited",
        "coords_lat": 0,
        "coords_lon": 0,
        "api": [],
    },
    {
        "last_seen_ts": 1651255199,
        "last_seen_str": "2022-04-29T10:59:59.415292",
        "plmn": "311480",
        "mcc": "311",
        "mnc": "480",
        "operator": "[US] / Verizon Wireless",
        "cid": 5973536,
        "pci": 41,
        "tac": 5892,
        "earfcn": 2050,
        "freq_dl_mhz": 2120,
        "band": 4,
        "rsrp_dbm": -104.2,
        "reg_status": "limited-regional",
        "coords_lat": 0,
        "coords_lon": 0,
        "api": [],
    },
    {
        "last_seen_ts": 1651255200,
        "last_seen_str": "2022-04-29T11:00:00.694656",
        "plmn": "311490",
        "mcc": "311",
        "mnc": "490",
        "operator": "[US] / Verizon Wireless",
        "cid": 22228491,
        "pci": 269,
        "tac": 13403,
        "earfcn": 675,
        "freq_dl_mhz": 1937.5,
        "band": 2,
        "rsrp_dbm": -107.3,
        "reg_status": "limited-regional",
        "coords_lat": 0,
        "coords_lon": 0,
        "api": [],
    },
    {
        "last_seen_ts": 1651255202,
        "last_seen_str": "2022-04-29T11:00:02.008526",
        "plmn": "312530",
        "mcc": "312",
        "mnc": "530",
        "operator": "[US] / Sprint Spectrum",
        "cid": 115362843,
        "pci": 47,
        "tac": 13403,
        "earfcn": 8763,
        "freq_dl_mhz": 866.3,
        "band": 26,
        "rsrp_dbm": -110.6,
        "reg_status": "limited-regional",
        "coords_lat": 0,
        "coords_lon": 0,
        "api": [],
    },
    {
        "last_seen_ts": 1651255203,
        "last_seen_str": "2022-04-29T11:00:03.319515",
        "plmn": "313100",
        "mcc": "313",
        "mnc": "100",
        "operator": "[US] / US_PUBLIC_SAFETY_NETWORK",
        "cid": 124650355,
        "pci": 377,
        "tac": 32779,
        "earfcn": 2175,
        "freq_dl_mhz": 2132.5,
        "band": 4,
        "rsrp_dbm": -86.7,
        "reg_status": "limited-regional",
        "coords_lat": 0,
        "coords_lon": 0,
        "api": [],
    },
]


class API:
    def __init__(self, wigle_creds=None, opencellid_creds=None, google_creds=None, mozilla_creds=None):
        self.wigle_session = requests.Session()
        self.wigle_session.auth = wigle_creds
        self.google_api_key = google_creds
        self.openapi_creds = None
        self.mozilla_api_key = None

    def api_wigle(self, cell: Cell) -> Cell:
        """Take a cell and queries Wigle API; Fills in geo Information if present in DB"""
        # EX: https://api.wigle.net/api/v3/detail/cell/LTE/310260/13403/226124301
        resp = self.wigle_session.get(f"https://api.wigle.net/api/v3/detail/cell/LTE/{cell.plmn}/{cell.tac}/{cell.cid}")
        if resp.status_code != 200:
            return cell
        j = resp.json()
        cell.api.append(
            {
                "src": "wigle",
                "last_seen": j["lastUpdate"],
                "lat": j["trilateratedLatitude"],
                "lon": j["trilateratedLongitude"],
            }
        )
        return cell

    def api_google(self, cell: Cell) -> Cell:
        post_data = {
            "homeMobileCountryCode": cell.mcc,
            "homeMobileNetworkCode": cell.mnc,
            "radioType": "lte",
            "carrier": cell.operator,
            "considerIp": False,
            "cellTowers": [
                {
                    "cellId": cell.cid,
                    "locationAreaCode": cell.tac,
                    "mobileCountryCode": cell.mcc,
                    "mobileNetworkCode": cell.mnc,
                    "age": 0,
                    "signalStrength": cell.rsrp_dbm,
                    "timingAdvance": 0,
                }
            ],
        }
        resp = requests.post(
            "https://www.googleapis.com/geolocation/v1/geolocate?key=" + self.google_api_key, json=post_data
        )
        print(resp.json())

    @staticmethod
    def dict_to_cell(cell_dict: dict) -> Cell:
        cell = Cell()
        cell.last_seen_ts = cell_dict["last_seen_ts"]
        cell.last_seen_str = cell_dict["last_seen_str"]
        cell.plmn = cell_dict["plmn"]
        cell.mcc = cell_dict["mcc"]
        cell.mnc = cell_dict["mnc"]
        cell.operator = cell_dict["operator"]
        cell.cid = cell_dict["cid"]
        cell.pci = cell_dict["pci"]
        cell.tac = cell_dict["tac"]
        cell.earfcn = cell_dict["earfcn"]
        cell.freq_dl_mhz = cell_dict["freq_dl_mhz"]
        cell.band = cell_dict["band"]
        cell.rsrp_dbm = cell_dict["rsrp_dbm"]
        cell.reg_status = cell_dict["reg_status"]
        cell.coords_lat = cell_dict["coords_lat"]
        cell.coords_lon = cell_dict["coords_lon"]
        cell.api = cell_dict["api"]
        return cell

    def set_creds(self, creds: dict) -> None:
        self.wigle_session.auth = creds["wigle_creds"]
        self.google_api_key = creds["google_creds"]
        self.openapi_creds = creds["opencellid_creds"]
        self.mozilla_api_key = creds["mozilla_creds"]


# end API Class


def write_creds(wigle_creds=None, opencellid_creds=None, google_creds=None, mozilla_creds=None) -> None:
    with open("creds.pickle", "wb") as fh:
        pickle.dump(
            {
                "wigle_creds": wigle_creds,  # Wigle API
                "opencellid_creds": opencellid_creds,  # OpenCellID
                "google_creds": google_creds,  # Google Maps API
                "mozilla_creds": mozilla_creds,  # Mozilla Location Services
            },
            fh,
        )


def read_creds() -> dict:
    with open("creds.pickle", "rb") as fh:
        d = pickle.load(fh)
    return d


if __name__ == "__main__":
    # for testing
    api = API()
    api.set_creds(read_creds())
    cells = []
    for i in test_json:
        cells.append(api.dict_to_cell(i))
    results = []
    for i in cells:
        results.append(api.api_google(i))
    # for i in results:
    #     print(f"{i.plmn}: {i.operator}")
    #     print(json.dumps(i.api))

