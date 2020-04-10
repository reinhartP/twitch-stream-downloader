import twitch
import requests
import os
import yaml
import time
from streamer import Streamer
import configparser


class Record:
    def __init__(self):
        self.__current_directory = os.path.dirname(os.path.realpath(__file__))
        config = configparser.ConfigParser()
        config.read(os.path.join(self.__current_directory, "config.ini"))
        self.__streamers = dict()
        self.__streamer_ids = dict()
        self.__force_streamers = []
        self.__capture_directory = os.path.normpath(
            config["default"]["capture_directory"]
        )
        self.__complete_directory = os.path.normpath(
            config["default"]["complete_directory"]
        )
        self.__client_id = config["twitchapi"]["client_id"]
        self.__client_secret = config["twitchapi"]["client_secret"]
        self.__bearer_token_expiration = int(config["twitchapi"]["expires"])
        self.__bearer_token = config["twitchapi"]["bearer_token"]
        self.__load_streamers()
        self.__games = [
            "509658",  # just chatting
            "",
            "509672",  # travel & outdoors
            "26936",  # music
            "509663",  # special events
            "509667",  # food and drink
        ]
        self.__config = config

    def __load_streamers(self):
        with open(os.path.join(self.__current_directory, "twitch.yaml"), "r") as f:
            try:
                streamers = yaml.safe_load(f)
                loaded_streamers = streamers.get("streamers")
                self.__force_streamers = streamers.get("forced_streamers")
                streamer_ids = self.__get_streamers_id(loaded_streamers)
                for streamer in loaded_streamers:
                    streamer_name = streamer.lower()
                    self.__streamers[streamer_name] = Streamer(
                        streamer_name,
                        self.__capture_directory,
                        streamer_ids.get(streamer_name),
                        self.__complete_directory,
                    )
            except yaml.YAMLError as exc:
                print(exc)

    def __get_streamers_id(self, streamers):
        if time.time() < self.__bearer_token_expiration:
            self.__get_bearer_token()
        helix = twitch.Helix(self.__client_id)
        headers = {
            "Authorization": f"Bearer {self.__bearer_token}",
            "Client-ID": self.__client_id,
        }
        params = {"login": streamers}

        response = requests.get(
            "https://api.twitch.tv/helix/users", params=params, headers=headers
        )
        response.close()
        response = response.json()
        streamers_with_id = dict()
        for streamer in response["data"]:
            streamers_with_id[streamer["login"]] = streamer["id"]
            self.__streamer_ids[streamer["id"]] = streamer["login"]
        return streamers_with_id

    def __update_streamers(self):
        with open(
            os.path.join(self.__current_directory, "twitch_updates.yaml"), "r"
        ) as f1:
            try:
                updates = yaml.safe_load(f1)
                include = updates.get("include")
                exclude = updates.get("exclude")
                force_include = updates.get("force_include")
                force_exclude = updates.get("force_exclude")
                with open(
                    os.path.join(self.__current_directory, "twitch.yaml"), "r"
                ) as f2:
                    streamers = yaml.safe_load(f2)
                    loaded_streamers = streamers.get("streamers")
                    forced_streamers = streamers.get("forced_streamers")

                    if len(include) > 0:
                        streamer_ids = self.__get_streamers_id(include)
                        for streamer in include:
                            streamer_name = streamer.lower()
                            if streamer_name not in self.__streamers:
                                loaded_streamers.append(streamer_name)
                                self.__streamers[streamer_name] = Streamer(
                                    streamer_name,
                                    self.__capture_directory,
                                    streamer_ids.get(streamer_name),
                                    self.__complete_directory,
                                )
                    if len(exclude) > 0:
                        for streamer in exclude:
                            if streamer.lower() in self.__streamers:
                                try:
                                    loaded_streamers.remove(streamer.lower())
                                    forced_streamers.remove(streamer.lower())
                                except ValueError:
                                    pass
                                del self.__streamers[streamer.lower()]
                    if len(force_include) > 0:
                        streamer_ids = self.__get_streamers_id(include)
                        for streamer in force_include:
                            streamer_name = streamer.lower()
                            if streamer_name not in forced_streamers:
                                forced_streamers.append(streamer_name)
                                self.__force_streamers.append(streamer_name)
                            if streamer_name not in loaded_streamers:
                                loaded_streamers.append(streamer_name)
                                self.__streamers[streamer_name] = Streamer(
                                    streamer_name,
                                    self.__capture_directory,
                                    streamer_ids.get(streamer_name),
                                    self.__complete_directory,
                                )
                    if len(force_exclude) > 0:
                        for streamer in force_exclude:
                            if streamer.lower() in forced_streamers:
                                forced_streamers.remove(streamer.lower())
            except yaml.YAMLError as exc:
                print(exc)
        with open(os.path.join(self.__current_directory, "twitch.yaml"), "w") as f:
            f.write(
                yaml.dump(
                    {
                        "streamers": loaded_streamers,
                        "forced_streamers": forced_streamers,
                    }
                )
            )
        with open(
            os.path.join(self.__current_directory, "twitch_updates.yaml"), "w"
        ) as f:
            yaml.dump(
                {
                    "include": [],
                    "exclude": [],
                    "force_include": [],
                    "force_exclude": [],
                },
                f,
            )

    def __get_bearer_token(self):
        current_time = time.time()
        endpoint = f"https://id.twitch.tv/oauth2/token?client_id={self.__client_id}&client_secret={self.__client_secret}&grant_type=client_credentials"
        r = requests.post(endpoint)
        r.close()
        r = r.json()
        self.__bearer_token = r["access_token"]
        self.__bearer_token_expiration = int(current_time + r["expires_in"])
        self.__config["twitchapi"]["expires"] = str(current_time + r["expires_in"])
        self.__config["twitchapi"]["bearer_token"] = r["access_token"]
        with open(os.path.join(self.__current_directory, "config.ini"), "w") as f:
            self.__config.write(f)

    def __is_live(self):
        """
            Check which streamers are online. Querying the endpoint returns which streamers are live, if they are
            offline they aren't included in the response.
            If the streamer is online, mark them as online.
            If the streamer is offline, mark them as offline
        """
        if time.time() < self.__bearer_token_expiration:
            self.__get_bearer_token()
        helix = twitch.Helix(self.__client_id)
        headers = {
            "Authorization": f"Bearer {self.__bearer_token}",
            "Client-ID": self.__client_id,
        }
        params = {"user_login": self.__streamers}

        r = requests.get(
            "https://api.twitch.tv/helix/streams", params=params, headers=headers
        )
        print(headers)
        response_headers = r.headers
        r.close()
        current_time = self.__get_current_time()
        print(
            f"[{current_time}] request {response_headers.get('ratelimit-remaining')}/{response_headers.get('ratelimit-limit')}"
        )
        if r.status_code == 429:
            print(f"[{current_time}] rate limit reached, retrying in 30 seconds")
            print(r.json())
            print(
                f"{response_headers.get('ratelimit-remaining')} {float(response_headers.get('ratelimit-reset')) - time.time()}"
            )
            time.sleep(30)
            return -1
        else:
            response = r.json()
            try:
                streamers = list(self.__streamers.keys())
                if len(response["data"]) > 0:
                    for streamer in response["data"]:  # go through online streamers
                        username = self.__streamer_ids[streamer["user_id"]]
                        if (
                            streamer.get("game_id") in self.__games
                            or username in self.__force_streamers
                        ):
                            self.__streamers[username].set_live_status(True)
                            streamers.remove(username)
                    for streamer in streamers:
                        self.__streamers[streamer].set_live_status(False)
            except KeyError as e:
                print(f"keyerror {response}")
                print(e.args[0])
                time.sleep(30)
        return 0

    def __check_recording(self, streamer) -> int:
        """
            If the streamer is live, check if recording, if not then start recording
            If the streamer is offline, check if recording, if it is recording then stop recording
            Returns -1 if recording stopped, 0 if nothing happened, 1 if recording started, 2 if file size exceeded max(stop and start recording)
        """
        if (
            streamer.get_live_status() == True
            and streamer.get_recording_status() == False
        ):
            streamer.start_recording()
            return 1
        elif (
            streamer.get_live_status() == False
            and streamer.get_recording_status() == True
        ):
            streamer.stop_recording()
            return -1
        elif streamer.get_recording_status() == True and self.__check_file_size(
            streamer
        ):
            streamer.stop_recording()
            streamer.start_recording()
            return 2
        return 0

    def __check_file_size(self, streamer):
        if os.stat(
            os.path.join(self.__capture_directory, streamer.get_filepath())
        ).st_size > (1024 * 1024 * 1024 * 8.25):
            return True
        return False

    def start(self):
        while True:
            self.__update_streamers()
            if self.__is_live() == -1:  # 429 error
                continue
            for key, streamer in self.__streamers.items():
                recording_status = self.__check_recording(streamer)
            time.sleep(30)

    def __get_current_time(self):
        return time.strftime("%H:%M:%S")


if __name__ == "__main__":
    record = Record()
    record.start()
