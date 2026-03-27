"""
Data Loader
============
Loads static JSON datasets from the data directory.
"""

import os
import json


class DataLoader:
    def __init__(self, data_dir):
        self.data_dir = data_dir
        self._cities = None
        self._ev_regs = None
        self._grid = None

    def _load_json(self, filename):
        path = os.path.join(self.data_dir, filename)
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_cities(self):
        if self._cities is None:
            self._cities = self._load_json("india-cities.json")
        return self._cities

    def get_ev_registrations(self):
        if self._ev_regs is None:
            self._ev_regs = self._load_json("ev-registrations.json")
        return self._ev_regs

    def get_grid_capacity(self):
        if self._grid is None:
            self._grid = self._load_json("grid-capacity.json")
        return self._grid
