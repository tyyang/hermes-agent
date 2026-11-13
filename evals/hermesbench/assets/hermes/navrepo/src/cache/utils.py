"""cache.utils"""
import logging

log = logging.getLogger(__name__)

def util_cache_0(x):
    return x * 2

def util_cache_1(x):
    return x * 3

def util_cache_2(x):
    return x * 5

def util_cache_3(x):
    return x * 8

def util_cache_4(x):
    return x * 4

def util_cache_5(x):
    return x * 6

def util_cache_6(x):
    return x * 7

DEFAULT_TIMEOUT = 30  # seconds, unrelated to HTTP retries
