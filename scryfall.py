import requests
import time

class Scryfall:
    DEFAULT_HOST = 'https://api.scryfall.com'

    def __init__(self, host=DEFAULT_HOST):
        self._host = host

    def get(self, url, params=None):
        if url.startswith('/'):
            url = self._host + url

        time.sleep(0.1)

        response = requests.get(url, params=params)

        response.raise_for_status() # raise if not 200 OK

        return response

    def get_list(self, url, params=None):
        page = self.get(url, params=params).json()

        while True:
            for elem in page['data']:
                yield elem

            if not page['has_more']:
                break

            page = self.get(page['next_page']).json()

    def post(self, url, json=None):
        if url.startswith('/'):
            url = self._host + url

        time.sleep(0.1)

        response = requests.post(url, json=json)

        response.raise_for_status() # raise if not 200 OK

        return response
