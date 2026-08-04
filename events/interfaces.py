from abc import ABC, abstractmethod

from PIL import Image


class ParsedMessage(ABC):
    @property
    @abstractmethod
    def key(self):
        pass

    @property
    @abstractmethod
    def bucket(self):
        pass

    @property
    @abstractmethod
    def public_camera_id(self):
        pass

    @abstractmethod
    def original_message(self):
        pass


class ImageQueueClient(ABC):
    @abstractmethod
    def get_parsed_messages(self) -> list[ParsedMessage]:
        pass


class ImageStorageClient(ABC):
    @abstractmethod
    def download_images(
            self, parsed_messages: list[ParsedMessage]
    ) -> dict[str, list[Image.Image]]:
        pass
