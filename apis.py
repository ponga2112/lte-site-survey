# -*- coding: utf-8 -*-

import requests


class API:
    def __init__(self, wigle_creds=None, opencellid_creds=None, google_creds=None, mozilla_creds=None):
        if wigle_creds:
            self.wigle.name = wigle_creds[0]
            self.wigle.token = wigle_creds[1]

    def api_wigle(cell: Cell) -> Cell:
        """Take a cell and queries Wigle API; Fills in geo Information if present in DB"""
        # EX: https://api.wigle.net/api/v3/detail/cell/LTE/310260/13403/226124301
        return cell
