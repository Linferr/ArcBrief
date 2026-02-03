"""Base node classes."""

from abc import ABC, abstractmethod


class BaseNode(ABC):
    def __init__(self, llm):
        self.llm = llm

    @abstractmethod
    def run(self, input_data):
        raise NotImplementedError

