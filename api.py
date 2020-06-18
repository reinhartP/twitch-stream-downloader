import requests
import json
import time
import logging

logger = logging.getLogger(__name__)


class API:
    def __init__(
        self, client_id, client_secret, bearer_token=None, bearer_token_expiration=0
    ):
        self.__client_id = client_id
        self.__client_secret = client_secret
        self.__bearer_token_expiration = bearer_token_expiration
        self.__bearer_token = bearer_token
        self.rate_limit_points = 800 if self.__bearer_token else 30
        self.rate_limit_remaining = self.rate_limit_points
        self.rate_limit_reset = 0

    def __handle_bearer_token(self):
        if time.time() > self.__bearer_token_expiration:
            self.__update_bearer_token()

    def __update_bearer_token(self):
        endpoint = f"https://id.twitch.tv/oauth2/token?client_id={self.__client_id}&client_secret={self.__client_secret}&grant_type=client_credentials"

        response = self.request("POST", endpoint)
        self.__bearer_token = response["access_token"]
        self.__bearer_token_expiration = float(time.time() + response["expires_in"])

    def __handle_rate_limit(self):
        if self.rate_limit_remaining == 0:
            logger.warning("rate limit reached")
            time_to_sleep = min(self.rate_limit_reset - time.time(), 10)
            time_to_sleep = max(time_to_sleep, 1)

            time.sleep(time_to_sleep)

    def __set_rate_limit(self, response):
        if "Ratelimit-Limit" in response.headers.keys():
            self.rate_limit_points = int(response.headers.get("Ratelimit-Limit"))
            self.rate_limit_remaining = int(response.headers.get("Ratelimit-Remaining"))
            self.rate_limit_reset = int(response.headers.get("Ratelimit-Reset"))

    def __get_headers(self):
        return {
            "Authorization": f"Bearer {self.__bearer_token}",
            "Client-ID": self.__client_id,
        }

    def request(self, method, url, **kwargs):
        """
            Sends request to endpoint and returns the response

            Sends the request while handling the rate limit and bearer token.

            Parameters
            ----------
            method : str
                HTTP method for the request
            url : str
                api endpoint
            **kwargs : dict
                other parameters for a request. typically just params
        """
        request = requests.Request(
            method, url, headers=self.__get_headers(), **kwargs,
        ).prepare()
        self.__handle_rate_limit()
        while True:
            try:
                response = requests.Session().send(request)
            except requests.exceptions.ConnectionError:
                logger.error("requests.exception.ConnectionError", exc_info=True)
                raise
            self.__set_rate_limit(response)

            if response.status_code == 429:
                self.__handle_rate_limit()
            elif response.status_code == 401:
                self.__handle_bearer_token()
                request = requests.Request(
                    method, url, headers=self.__get_headers(), **kwargs,
                ).prepare()
            else:
                response.raise_for_status()
                break
        try:
            return response.json()
        except ValueError:
            logger.error(
                f"json error. response status: {response.status_code}\n{response.text}",
                exc_info=True,
            )
            return None

    def get_bearer_token(self):
        return self.__bearer_token

    def get_bearer_token_expiration(self):
        return self.__bearer_token_expiration
