from .message import Message
from abc import ABCMeta, abstractmethod
from typing import List


class Filter(metaclass=ABCMeta):

	@abstractmethod
	def __call__(self, msg: Message) -> bool:
		raise NotImplementedError


class SenderFilter(Filter):

	def __init__(self, sender : str = None):
		self.sender = sender

	def __call__(self, msg: Message):
		return self.sender in msg.sender


class SubjectFilter(Filter):

	def __init__(self, subject : str = None):
		self.subject = subject

	def __call__(self, msg: Message):
		return self.subject in msg.subject


class AndFilter(Filter):

	def __init__(self, filters: List[Filter] = None):
		self.filters = filters

	def __call__(self, msg: Message):
		return all(f(msg) for f in self.filters)


class OrFilter(Filter):

	def __init__(self, filters: List[Filter] = None):
		self.filters = filters

	def __call__(self, msg: Message):
		return any(f(msg) for f in self.filters)
