import time
from datetime import datetime
import subprocess
import os


class Streamer:
    def __init__(self, name: str, recording_path: str):
        self.__name = name
        self.__recording_path = recording_path
        self.__live = False
        self.__recording = False
        self.__process = None
        self.__filepath = None

    def start_recording(self):
        print(f"started recording for {self.__name}")
        file_time = time.strftime("%Y-%m-%d_%H-%M-%S")
        self.__filepath = os.path.join(
            self.__recording_path, f"twitch_{self.__name}_{file_time}.ts"
        )
        self.__process = subprocess.Popen(
            f"streamlink -o {self.__filepath} --force twitch.tv/{self.__name} best",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
        )
        self.__recording = True

    def stop_recording(self):
        print(f"\n[{self.__get_current_time()}] {self.__name} offline\t\t\t\t")
        self.__filepath = None
        self.__process.kill()
        self.__process = None
        self.__recording = False

    def __get_current_time(self) -> str:
        return time.strftime("%H:%M:%S")

    def set_live_status(self, status: bool):
        self.__live = status

    def get_live_status(self):
        return self.__live

    def get_recording_status(self):
        return self.__recording

    def get_process(self):
        return self.__process

    def get_name(self) -> str:
        return self.__name

    def get_filepath(self) -> str:
        return self.__filepath
