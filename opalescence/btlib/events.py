# -*- coding: utf-8 -*-

"""
Event and observer classes. These are not intended to be used directly.
https://stackoverflow.com/questions/1904351/python-observer-pattern-examples-tips
"""
from typing import Callable


class Observer:
    _observers = []

    def __init__(self):
        if self not in self._observers:
            self._observers.append(self)
            self._observing: dict[str, Callable] = {}

    def register(self, event_name, callback):
        self._observing[event_name] = callback

    @classmethod
    def get_observers(cls) -> list:
        return cls._observers


class Event:
    def __init__(self, name, *args, auto_fire=True):
        self.name = name
        self.data = args
        if auto_fire:
            self.fire()

    def fire(self):
        for observer in Observer.get_observers():
            if self.name in observer._observing:
                observer._observing[self.name](*self.data)
