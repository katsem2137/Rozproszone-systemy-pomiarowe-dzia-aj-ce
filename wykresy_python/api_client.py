import requests
from config import REQUEST_TIMEOUT


class APIError(Exception):
    pass


class APIClient:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()

    def _get(self, path: str, params: dict = None) -> any:
        try:
            r = self.session.get(
                f"{self.base_url}{path}",
                params=params,
                timeout=REQUEST_TIMEOUT,
            )
            r.raise_for_status()
            return r.json()
        except requests.exceptions.ConnectionError:
            raise APIError(f"Nie można połączyć się z backendem: {self.base_url}")
        except requests.exceptions.Timeout:
            raise APIError(f"Timeout połączenia z backendem ({REQUEST_TIMEOUT}s)")
        except requests.exceptions.HTTPError as e:
            raise APIError(f"Błąd HTTP {r.status_code}: {e}")
        except Exception as e:
            raise APIError(f"Nieoczekiwany błąd: {e}")

    def health(self) -> bool:
        try:
            data = self._get("/health")
            return data.get("status") == "ok"
        except APIError:
            return False

    def devices(self) -> list[str]:
        return self._get("/devices")

    def latest(self, device_id: str = None) -> list[dict]:
        params = {"device_id": device_id} if device_id else None
        return self._get("/latest", params=params)

    def latest_temperature(self, device_id: str = None) -> list[dict]:
        params = {"device_id": device_id} if device_id else None
        return self._get("/latest/temperature", params=params)

    def latest_pressure(self, device_id: str = None) -> list[dict]:
        params = {"device_id": device_id} if device_id else None
        return self._get("/latest/pressure", params=params)

    def history(self, device_id: str = None, sensor: str = None, limit: int = 50) -> list[dict]:
        params = {"limit": limit}
        if device_id:
            params["device_id"] = device_id
        if sensor:
            params["sensor"] = sensor
        return self._get("/history", params=params)
