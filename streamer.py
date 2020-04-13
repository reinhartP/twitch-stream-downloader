import time
import subprocess
import os
import logging

logger = logging.getLogger(__name__)


class Streamer:
    def __init__(self, name: str, capture_path: str, id: int, complete_path: str):
        self.__name = name
        self.__capture_path = capture_path
        self.__complete_path = complete_path
        self.__id = id
        self.__live = False
        self.__recording = False
        self.__process = None
        self.__filename = None
        logger.info(f"Created Streamer object for {name}")

    def start_recording(self):
        file_time = time.strftime("%Y-%m-%d_%H-%M-%S")
        self.__filename = f"twitch_{self.__name}_{file_time}.ts"
        self.__process = subprocess.Popen(
            f"streamlink -o {os.path.join(self.__capture_path, self.__filename)} --force twitch.tv/{self.__name} best",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            stdin=subprocess.PIPE,
        )
        self.__recording = True
        logger.info(
            f"Started recording for {self.__name} ({self.__process.pid}) - {self.__filename}"
        )

    def stop_recording(self):
        self.__process.kill()
        self.__process = None
        self.__recording = False
        time.sleep(2)
        os.rename(
            os.path.join(self.__capture_path, self.__filename),
            os.path.join(self.__complete_path, self.__filename),
        )
        self.__filename = None
        logger.info(f"Stopped recording for {self.__name} - {self.__filename}")

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

    def get_filename(self) -> str:
        return self.__filename

    def get_id(self) -> int:
        return self.__id
