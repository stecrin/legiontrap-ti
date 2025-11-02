import os

import geoip2.database


class GeoIP:
    def __init__(self, db_path=None):
        self.db_path = db_path or os.getenv("GEOLITE_DB_PATH", "storage/GeoLite2-City.mmdb")
        self.reader = None
        if os.path.exists(self.db_path):
            self.reader = geoip2.database.Reader(self.db_path)

    def lookup(self, ip):
        if not self.reader:
            return {}  # <— returns immediately if DB missing
        try:
            r = self.reader.city(ip)
            return {
                "country": r.country.name,
                "city": r.city.name,
                "asn": "Unknown",
            }
        except Exception:
            return {}
