import twitch
import requests
import os
from ruamel import yaml
import time
from streamer import Streamer
import configparser


class Record:
    def __init__(self):
        self.__current_directory = os.path.dirname(os.path.realpath(__file__))
        config = configparser.ConfigParser()
        config.read(os.path.join(self.__current_directory, "config.ini"))
        self.__streamers = dict()
        self.__force_streamers = []
        self.__recording_directory = "D:\\PythonRecordings"
        self.__client_id = config["twitchapi"]["client_id"]
        self.__client_secret = config["twitchapi"]["client_secret"]
        self.__bearer_token_expiration = int(config["twitchapi"]["expires"])
        self.__bearer_token = ""
        self.load_streamers()
        self.__games = [
            "509658",  # just chatting
            "",
            "509672",  # travel & outdoors
            "26936",  # music
            "509663",  # special events
            "509667",
        ]  # food and drink
        self.__config = config

    def load_streamers(self):
        with open(os.path.join(self.__current_directory, "twitch.yaml"), "r") as f:
            try:
                streamers = yaml.safe_load(f)
                loaded_streamers = streamers.get("streamers")
                self.__force_streamers = streamers.get("forced_streamers")
                for streamer in loaded_streamers:
                    self.__streamers[streamer] = Streamer(
                        streamer.lower(), self.__recording_directory
                    )
            except yaml.YAMLError as exc:
                print(exc)

    def update_streamers(self):
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
                        for streamer in include:
                            if streamer.lower() not in self.__streamers:
                                loaded_streamers.append(streamer.lower())
                                self.__streamers[streamer] = Streamer(
                                    streamer.lower(), self.__recording_directory
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
                        for streamer in force_include:
                            if streamer.lower() not in forced_streamers:
                                forced_streamers.append(streamer.lower())
                            if streamer.lower() not in loaded_streamers:
                                loaded_streamers.append(streamer.lower())
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

    def get_bearer_token(self):
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

    def is_live(self):
        """
            Check which streamers are online. Querying the endpoint returns which streamers are live, if they are
            offline they aren't included in the response.
            If the streamer is online, mark them as online.
            If the streamer is offline, mark them as offline
        """
        if time.time() < self.__bearer_token_expiration:
            get_bearer_token()
        helix = twitch.Helix(self.__client_id)
        headers = {
            "Authorization": f"Bearer {self.__bearer_token}",
            "Client-ID": self.__client_id,
        }
        params = {"user_login": self.__streamers}

        r = requests.get(
            "https://api.twitch.tv/helix/streams", params=params, headers=headers
        )
        r.close()
        current_time = self.__get_current_time()

        if r.status_code == 429:
            print(f"[{current_time}] rate limit reached, retrying in 30 seconds")
            time.sleep(30)
            return -1
        else:
            response = r.json()
            try:
                streamers = list(self.__streamers.keys())
                if len(response["data"]) > 0:
                    for streamer in response["data"]:  # go through online streamers
                        username = streamer.get("user_name").lower()
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

    def check_recording(self, streamer) -> int:
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
        elif streamer.get_recording_status() == True and self.check_file_size(streamer):
            streamer.stop_recording()
            streamer.start_recording()
            return 2
        return 0

    def check_file_size(self, streamer):
        if os.stat(streamer.get_filepath()).st_size > (1024 * 1024 * 1024 * 8.25):
            return True
        return False

    def start(self):
        while True:
            self.update_streamers()
            if self.is_live() == -1:  # 429 error
                continue
            for key, streamer in self.__streamers.items():
                recording_status = self.check_recording(streamer)
            time.sleep(30)

    def __get_current_time(self):
        return time.strftime("%H:%M:%S")


if __name__ == "__main__":
    record = Record()
    record.start()
