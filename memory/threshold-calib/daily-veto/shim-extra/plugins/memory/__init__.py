"""Test stub of Hermes core's plugins.memory: the base provider package is already loaded by the harness."""
import sys


def import_provider_module(name):
    if name != "holographic":
        raise ImportError(name)
    return sys.modules["hermes_plugin_holographic"]
